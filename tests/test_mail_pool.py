"""
Mail-Verbindungs-Pool (core/mail.py): warm halten statt jedes Mal neu verbinden.

Das Panel war zäh, weil JEDE Lese-Op (folder_counts/folder_mails/mail_body)
eine frische TLS+XOAUTH2-Verbindung aufbaute und sich danach abmeldete — bei
Outlook ~1-3 s Handshake pro Klick. Der Pool (`_session`) hält pro Konto EINE
Verbindung warm. Geprüft (ohne Netz, Fake-IMAP):

  - zweimal borgen → nur EINMAL verbunden (Wiederverwendung),
  - eine tote Verbindung (NOOP != OK) → transparenter Reconnect,
  - `_pselect` überspringt ein redundantes SELECT auf denselben Ordner/Modus,
  - bricht die Verbindung mitten in der Nutzung weg (_DROP_ERRORS), fliegt sie
    aus dem Pool und der nächste Borrow baut frisch auf.
"""
import imaplib
from contextlib import contextmanager

import pytest

import mail as M  # core/ liegt via conftest auf sys.path


class FakeIMAP:
    """Minimaler IMAP-Stub: zählt NOOP/SELECT, kann „tot" gestellt werden."""
    def __init__(self):
        self.noops = 0
        self.selects = []
        self.logged_out = False
        self.dead = False

    def noop(self):
        self.noops += 1
        if self.dead:
            raise imaplib.IMAP4.abort("dead socket")
        return ("OK", [b"NOOP completed"])

    def select(self, mailbox, readonly=False):
        self.selects.append((mailbox, readonly))
        return ("OK", [b"1"])

    def logout(self):
        self.logged_out = True
        return ("BYE", [b""])


@pytest.fixture()
def pool(monkeypatch):
    """Pool-Zustand leeren und _connect durch eine Fabrik ersetzen, die
    Fake-Verbindungen ausgibt + mitzählt, wie oft verbunden wurde."""
    monkeypatch.setattr(M, "_pool", {})
    monkeypatch.setattr(M, "_pool_selected", {})
    monkeypatch.setattr(M, "_pool_locks", {})
    made = []

    def fake_connect(account):
        imap = FakeIMAP()
        made.append(imap)
        return imap

    monkeypatch.setattr(M, "_connect", fake_connect)
    return made


ACCT = {"name": "outlook-main"}


def test_session_reuses_warm_connection(pool):
    with M._session(ACCT) as a:
        pass
    with M._session(ACCT) as b:
        pass
    assert a is b                 # dieselbe Verbindung wiederverwendet
    assert len(pool) == 1         # nur EINMAL verbunden (kein Handshake-Sturm)
    assert b.noops == 1           # zweiter Borrow: nur ein billiger Lebens-Check


def test_session_reconnects_dead_connection(pool):
    with M._session(ACCT) as a:
        a.dead = True             # Server hat die Idle-Verbindung gekappt
    with M._session(ACCT) as b:
        pass
    assert a is not b             # tote raus, frische rein
    assert a.logged_out           # alte sauber geschlossen
    assert len(pool) == 2


def test_pselect_skips_redundant_select(pool):
    name = ACCT["name"]
    with M._session(ACCT) as imap:
        assert M._pselect(imap, name, "ZENTRALE/Zahlen", readonly=True) == "OK"
        assert M._pselect(imap, name, "ZENTRALE/Zahlen", readonly=True) == "OK"
        # zweiter Aufruf gleicher Ordner+Modus → kein zweites SELECT
        assert imap.selects == [('"ZENTRALE/Zahlen"', True)]
        # anderer Modus (read-write) → muss neu selektieren
        assert M._pselect(imap, name, "ZENTRALE/Zahlen", readonly=False) == "OK"
        assert len(imap.selects) == 2


def test_session_drops_connection_on_break(pool):
    name = ACCT["name"]
    with pytest.raises(imaplib.IMAP4.abort):
        with M._session(ACCT) as imap:
            M._pselect(imap, name, "INBOX", readonly=True)
            raise imaplib.IMAP4.abort("Verbindung weg")
    # nach dem Bruch: Pool leer, Auswahl-Gedächtnis weg → nächster Borrow frisch
    assert name not in M._pool
    assert name not in M._pool_selected
    with M._session(ACCT) as fresh:
        pass
    assert fresh is not pool[0]
    assert len(pool) == 2


# ── XOAUTH2: abgelehntes Token → Refresh + Retry ──────────────────────
# Outlook lehnte gelegentlich ein (gecachtes, scheinbar noch gültiges) Access-
# Token ab → [AUTHENTICATIONFAILED], und der ganze Sweep fiel um. Fix: EINMAL mit
# erzwungenem Token-Refresh frisch verbinden.

def _fresh_pool(monkeypatch):
    monkeypatch.setattr(M, "_pool", {})
    monkeypatch.setattr(M, "_pool_selected", {})
    monkeypatch.setattr(M, "_pool_locks", {})


def test_session_retries_connect_on_rejected_token(monkeypatch):
    _fresh_pool(monkeypatch)
    calls = []
    good = FakeIMAP()

    def fake_connect(account, force_token=False):
        calls.append(force_token)
        if len(calls) == 1:           # erstes Token abgelehnt
            raise imaplib.IMAP4.error(b"[AUTHENTICATIONFAILED] Authentication failed.")
        return good                   # mit frischem Token klappt's

    monkeypatch.setattr(M, "_connect", fake_connect)
    with M._session(ACCT) as imap:
        assert imap is good
    assert calls == [False, True]     # erst normal, dann force_token
    assert M._pool[ACCT["name"]] is good


def test_session_auth_error_propagates_when_retry_also_fails(monkeypatch):
    _fresh_pool(monkeypatch)
    calls = []

    def fake_connect(account, force_token=False):
        calls.append(force_token)
        raise imaplib.IMAP4.error(b"[AUTHENTICATIONFAILED] Authentication failed.")

    monkeypatch.setattr(M, "_connect", fake_connect)
    with pytest.raises(imaplib.IMAP4.error):
        with M._session(ACCT):
            pass
    assert calls == [False, True]     # genau EIN Retry, dann aufgeben (keine Endlosschleife)


def test_access_token_force_refresh_bypasses_cache(monkeypatch):
    import time
    import mail_oauth as O
    monkeypatch.setattr(O, "_token_cache", {"acc": ("STALE", time.time() + 9999)})
    seen = []
    monkeypatch.setattr(O, "refresh", lambda cid, rt, authority=None: (
        seen.append(rt), {"access_token": "FRESH", "expires_in": 3600})[1])
    acct = {"name": "acc", "client_id": "cid", "oauth": {"refresh_token": "RT"}}
    assert O.access_token_for(acct) == "STALE"                    # Cache-Treffer
    assert O.access_token_for(acct, force_refresh=True) == "FRESH"  # erzwingt Refresh
    assert seen == ["RT"]                                          # Refresh lief genau einmal


# ── Body-Cache + Prefetch ─────────────────────────────────────────────

@pytest.fixture()
def bodycache(monkeypatch):
    """Body-Cache leeren und _fetch_body durch einen zählenden Stub ersetzen,
    der so tut, als läge die Mail im move-Ordner 'zahlen'."""
    monkeypatch.setattr(M, "_body_cache", M.OrderedDict())
    fetched = []

    def fake_fetch(cat, uid, account_name=None):
        fetched.append((cat, int(uid), account_name))
        return {"account": account_name or "a", "uid": int(uid),
                "from": "x@y.z", "subject": "s", "date": "",
                "body": "text %d" % int(uid)}

    monkeypatch.setattr(M, "_fetch_body", fake_fetch)
    # category_action so biegen, dass jede Kategorie ein echter move-Ordner ist
    monkeypatch.setattr(M.mail_rules, "category_action",
                        lambda cat: {"action": "move", "folder": "ZENTRALE/X"})
    return fetched


def test_mail_body_caches_immutable_text(bodycache):
    a = M.mail_body("zahlen", 7, account_name="acc")
    b = M.mail_body("zahlen", 7, account_name="acc")
    assert a == b
    assert len(bodycache) == 1          # zweiter Aufruf kam aus dem Cache


def test_mail_body_does_not_cache_errors(bodycache, monkeypatch):
    monkeypatch.setattr(M, "_fetch_body",
                        lambda cat, uid, account_name=None: {"error": "weg"})
    M.mail_body("zahlen", 9, account_name="acc")
    M.mail_body("zahlen", 9, account_name="acc")
    assert ("acc", "zahlen", 9) not in M._body_cache   # Fehler nie gecacht


def test_prefetch_warms_neighbors_then_instant(bodycache):
    M.prefetch_bodies("zahlen", [10, 11], account_name="acc")
    assert sorted(u for _, u, _ in bodycache) == [10, 11]
    bodycache.clear()
    # nach dem Prefetch kommen beide ohne weiteren Fetch aus dem Cache
    M.mail_body("zahlen", 10, account_name="acc")
    M.mail_body("zahlen", 11, account_name="acc")
    assert bodycache == []


def test_prefetch_skips_already_cached(bodycache):
    M.mail_body("zahlen", 12, account_name="acc")
    bodycache.clear()
    M.prefetch_bodies("zahlen", [12], account_name="acc")
    assert bodycache == []              # schon im Cache → kein erneuter Fetch


# ── Batch-MOVE beim Einsortieren (Absender umsortieren war zäh) ────────

class MoveIMAP:
    """IMAP-Stub, der UID-Kommandos protokolliert. `caps` steuert, ob der Server
    MOVE kann (sonst COPY+STORE+EXPUNGE-Fallback)."""
    def __init__(self, caps=(b"MOVE",)):
        self.capabilities = caps
        self.cmds = []
        self.expunges = 0

    def uid(self, cmd, *args):
        self.cmds.append((cmd, args))
        return ("OK", [b""])

    def expunge(self):
        self.expunges += 1
        return ("OK", [b""])


def test_move_uid_set_batches_in_one_move():
    imap = MoveIMAP()
    moved = M._move_uid_set(imap, [b"1", b"2", b"3"], "ZENTRALE/Zahlen")
    assert moved == 3
    # GENAU ein MOVE-Roundtrip für alle drei (nicht drei einzelne).
    moves = [c for c in imap.cmds if c[0] == "MOVE"]
    assert len(moves) == 1
    assert moves[0][1][0] == "1,2,3"


def test_move_uid_set_chunks_long_sets():
    imap = MoveIMAP()
    uids = [str(u).encode() for u in range(1, 451)]      # 450 > chunk 200
    moved = M._move_uid_set(imap, uids, "ZENTRALE/Zahlen", chunk=200)
    assert moved == 450
    assert len([c for c in imap.cmds if c[0] == "MOVE"]) == 3   # 200+200+50


def test_move_uid_set_falls_back_without_move_cap():
    imap = MoveIMAP(caps=())                              # Server kann kein MOVE
    moved = M._move_uid_set(imap, [b"7", b"8"], "ZENTRALE/Zahlen")
    assert moved == 2
    kinds = [c[0] for c in imap.cmds]
    assert "COPY" in kinds and "STORE" in kinds and "MOVE" not in kinds
    assert imap.expunges == 1                             # ein EXPUNGE fürs Set


# ── Einsortieren ist KEYMAP-getrieben: ALLE Ordner, nicht nur der Vor-Ordner ──
# Der alte Weg las die Herkunft aus classify() VOR dem Umschreiben und durch-
# suchte nur diesen einen Ordner. Sobald die Keymap (z.B. per Bulk/CLI) schon
# auf die neue Kategorie zeigte, war Quelle == Ziel → 0 Moves, die Mail blieb
# liegen (der Bug). Jetzt zählt allein die Keymap: JEDER sortierbare Ordner
# (INBOX + move-Ordner, außer dem Ziel) wird nach dem Absender durchsucht.

@pytest.fixture()
def refile(monkeypatch):
    """refile_sender so verdrahten, dass wir ohne Netz sehen, WELCHE Ordner
    durchsucht werden. `searched` sammelt die selektierten Quell-Ordner."""
    searched = []

    class Imap:
        capabilities = (b"MOVE",)
        def uid(self, cmd, *a):
            return ("OK", [b"1 2"] if cmd == "SEARCH" else [b""])

    @contextmanager
    def fake_session(account):
        yield Imap()

    cats = {"zahlen": {"action": "move", "folder": "ZENTRALE/Zahlen"},
            "arbeit": {"action": "move", "folder": "ZENTRALE/Arbeit"},
            M.mail_rules.REVIEW: {"action": "move", "folder": "ZENTRALE/Review"}}
    monkeypatch.setattr(M, "_session", fake_session)
    monkeypatch.setattr(M, "_accounts_for", lambda name=None: [{"name": "acc"}])
    monkeypatch.setattr(M.mail_rules, "assign", lambda s, c, **k: (s, c))
    monkeypatch.setattr(M.mail_rules, "categories", lambda: cats)
    monkeypatch.setattr(M.mail_rules, "category_action", lambda name: cats[name])
    monkeypatch.setattr(M._FolderCache, "target",
                        lambda self, imap, spec: spec["folder"])
    monkeypatch.setattr(M, "_pselect",
                        lambda imap, name, folder, readonly=True:
                        (searched.append(folder), "OK")[1])
    monkeypatch.setattr(M, "_move_uid_set",
                        lambda imap, uids, target, **k: len(list(uids)))
    return searched


def test_refile_searches_all_folders_except_target(refile):
    res = M.refile_sender("x@y.z", "arbeit")             # Ziel = ZENTRALE/Arbeit
    # INBOX + alle move-Ordner AUSSER dem Ziel (Arbeit wird übersprungen)
    assert refile == ["INBOX", "ZENTRALE/Zahlen", "ZENTRALE/Review"]
    assert res["moved"] == 6                             # 3 Ordner × 2 Treffer
    assert set(res["moved_from"]) == {"INBOX", "ZENTRALE/Zahlen", "ZENTRALE/Review"}


def test_refile_skips_target_folder(refile):
    M.refile_sender("x@y.z", "zahlen")                   # Ziel = ZENTRALE/Zahlen
    assert "ZENTRALE/Zahlen" not in refile               # Ziel nie durchsucht
    assert refile == ["INBOX", "ZENTRALE/Arbeit", "ZENTRALE/Review"]


def test_refile_works_for_domain_sender(refile):
    # Domain statt Adresse: SEARCH FROM matcht als Teilstring, Move läuft normal.
    res = M.refile_sender("pearl.de", "arbeit")
    assert res["moved"] == 6


# ── Reconcile: Ordner an die Keymap angleichen (bereits einsortierte Mail) ──
# Der Poll schaut nur in die INBOX — einmal einsortierte Mail wird nie wieder
# gegen die Keymap geprüft. reconcile_account holt das nach: jede Mail wird über
# ihren Absender neu klassifiziert und, falls falsch abgelegt, in den richtigen
# Ordner geschoben. Unbekannte bleiben in Review, der Papierkorb ist keine Quelle,
# und ein zweiter Lauf ist ein No-Op (idempotent).

class FolderIMAP:
    """IMAP-Stub mit echten Ordnern {ordner: {uid: from}} — SELECT/SEARCH/FETCH
    (FROM-Header) und UID MOVE bewegen Mail wirklich zwischen den Ordnern."""
    capabilities = (b"MOVE",)

    def __init__(self, folders):
        self.folders = {f: dict(m) for f, m in folders.items()}
        self.cur = None

    def select(self, mailbox, readonly=False):
        self.cur = mailbox.strip('"')
        self.folders.setdefault(self.cur, {})
        return ("OK", [b"1"])

    def uid(self, cmd, *args):
        if cmd == "SEARCH":
            uids = sorted(self.folders.get(self.cur, {}))
            return ("OK", [" ".join(str(u) for u in uids).encode()])
        if cmd == "FETCH":
            want = [int(x) for x in args[0].split(",")]
            data = []
            for u in want:
                frm = self.folders.get(self.cur, {}).get(u)
                if frm is None:
                    continue
                meta = ("%d (UID %d BODY[HEADER.FIELDS (FROM)] {}" % (u, u)).encode()
                data.append((meta, ("From: %s\r\n\r\n" % frm).encode()))
            return ("OK", data)
        if cmd == "MOVE":
            target = args[1].strip('"')
            self.folders.setdefault(target, {})
            for u in [int(x) for x in args[0].split(",")]:
                if u in self.folders.get(self.cur, {}):
                    self.folders[target][u] = self.folders[self.cur].pop(u)
            return ("OK", [b""])
        return ("OK", [b""])

    def expunge(self):
        return ("OK", [b""])


def _wire_reconcile(monkeypatch, imap, cats, classify):
    from types import SimpleNamespace
    monkeypatch.setattr(M, "_action_delay", lambda: 0.0)  # keine Drossel-Sleeps
    monkeypatch.setattr(M, "_session", contextmanager(lambda account: iter([imap])))
    monkeypatch.setattr(M.mail_rules, "matcher",
                        lambda: SimpleNamespace(classify=classify))
    monkeypatch.setattr(M.mail_rules, "categories", lambda: cats)
    monkeypatch.setattr(M._FolderCache, "target",
                        lambda self, imap, spec: spec.get("folder"))
    monkeypatch.setattr(M, "_pselect",
                        lambda imap, name, folder, readonly=True:
                        (imap.select('"%s"' % folder, readonly=readonly), "OK")[1])


def test_reconcile_moves_misfiled_to_keymap_target(monkeypatch):
    R = M.mail_rules.REVIEW
    imap = FolderIMAP({
        "INBOX": {10: "a@pearl.de"},
        "ZENTRALE/Review": {1: "a@pearl.de", 2: "b@flixbus.com", 3: "c@unknown.io"},
        "ZENTRALE/Werbung": {},
        "ZENTRALE/Reise": {},
    })
    cats = {R: {"action": "move", "folder": "ZENTRALE/Review"},
            "Werbung": {"action": "move", "folder": "ZENTRALE/Werbung"},
            "Reise": {"action": "move", "folder": "ZENTRALE/Reise"}}

    def classify(frm):
        if "pearl.de" in frm:
            return "Werbung", True
        if "flixbus.com" in frm:
            return "Reise", True
        return R, False

    _wire_reconcile(monkeypatch, imap, cats, classify)
    res = M.reconcile_account({"name": "acc"}, dry_run=False)

    # Reconcile lässt die INBOX (Eingang-Tray) in Ruhe → uid 10 bleibt liegen.
    assert imap.folders["ZENTRALE/Werbung"] == {1: "a@pearl.de"}
    assert imap.folders["ZENTRALE/Reise"] == {2: "b@flixbus.com"}
    assert imap.folders["ZENTRALE/Review"] == {3: "c@unknown.io"}   # unbekannt bleibt
    assert imap.folders["INBOX"] == {10: "a@pearl.de"}             # Eingang unangetastet
    assert res["moved"] == 2

    # idempotent: alles liegt richtig → zweiter Lauf bewegt nichts
    res2 = M.reconcile_account({"name": "acc"}, dry_run=False)
    assert res2["moved"] == 0


def test_reconcile_dry_run_moves_nothing(monkeypatch):
    R = M.mail_rules.REVIEW
    imap = FolderIMAP({
        "INBOX": {},
        "ZENTRALE/Review": {1: "a@pearl.de"},
        "ZENTRALE/Werbung": {},
    })
    cats = {R: {"action": "move", "folder": "ZENTRALE/Review"},
            "Werbung": {"action": "move", "folder": "ZENTRALE/Werbung"}}
    _wire_reconcile(monkeypatch, imap, cats, lambda frm: ("Werbung", True))
    res = M.reconcile_account({"name": "acc"}, dry_run=True)
    assert res["moved"] == 1                          # meldet, WAS es täte
    assert res["dry_run"] is True
    assert imap.folders["ZENTRALE/Review"] == {1: "a@pearl.de"}  # aber nichts bewegt
    assert imap.folders["ZENTRALE/Werbung"] == {}


# ── Trie-Matcher: schnelles Longest-Match (Adresse ODER Domain) ───────

def test_trie_domain_rule_matches_subdomains_and_addresses():
    m = M.mail_rules.Matcher(
        {"pearl.de": "Werbung", "flixbus.com": "Reise"},
        {"Werbung", "Reise"})
    assert m.classify("maria.kern@pearl.de") == ("Werbung", True)
    assert m.classify("noreply@trips.mail.flixbus.com") == ("Reise", True)


def test_trie_address_rule_beats_domain_rule():
    m = M.mail_rules.Matcher(
        {"pearl.de": "Werbung", "boss@pearl.de": "arbeit antworten"},
        {"Werbung", "arbeit antworten"})
    assert m.classify("boss@pearl.de") == ("arbeit antworten", True)   # spezifischer
    assert m.classify("x@pearl.de") == ("Werbung", True)               # Domain-Fallback


def test_trie_no_domain_leak_across_boundary():
    m = M.mail_rules.Matcher({"pearl.de": "Werbung"}, {"Werbung"})
    # 'pearl.de' darf NICHT 'pearl.de.evil.com' fangen (Label-Grenze, kein Präfix)
    assert m.classify("x@pearl.de.evil.com") == (M.mail_rules.REVIEW, False)


def test_trie_unknown_and_stale_category_go_to_review():
    m = M.mail_rules.Matcher({"a@b.de": "geloescht-inzwischen"}, {"zahlen"})
    assert m.classify("wer@ganz.anders") == (M.mail_rules.REVIEW, False)  # unbekannt
    # Regel zeigt auf eine Kategorie, die es nicht mehr gibt → Review (safe)
    assert m.classify("a@b.de") == (M.mail_rules.REVIEW, False)


# ── Eingang-Tray: INBOX + \Seen, einsortieren erst beim Lesen ─────────
# Neue Mail bleibt im Eingang (INBOX), bis sie GELESEN ist und der Absender
# bekannt: dann wandert sie in ihre Kategorie. Ungelesenes/Unbekanntes bleibt.

class _HdrIMAP:
    """Liefert für FETCH einen FROM-Header (fester Absender); STORE/uid gezählt."""
    capabilities = (b"MOVE",)
    def __init__(self, frm="a@known.de"):
        self.frm = frm
        self.stored = []
    def uid(self, cmd, *a):
        if cmd == "STORE":
            self.stored.append(a)
            return ("OK", [b""])
        if cmd == "FETCH":
            return ("OK", [(b"1 (UID 1)", ("From: %s\r\n\r\n" % self.frm).encode())])
        return ("OK", [b""])


class _FC:
    def target(self, imap, spec):
        return spec.get("folder")


def _wire_classify(monkeypatch, known_cat="zahlen"):
    monkeypatch.setattr(M, "_record", lambda item: None)   # nicht in echte state.json
    monkeypatch.setattr(M.mail_rules, "category_action",
                        lambda c: {"action": "move", "folder": "ZENTRALE/Zahlen"})


def test_handle_uid_files_only_seen_and_known(monkeypatch):
    _wire_classify(monkeypatch)
    monkeypatch.setattr(M.mail_rules, "classify", lambda f: ("zahlen", True))
    moves = []
    monkeypatch.setattr(M, "_move_uid",
                        lambda imap, uid, target: (moves.append((uid, target)), True)[1])
    imap = _HdrIMAP("a@known.de")
    # gelesen + bekannt → einsortiert
    done, moved = M._handle_uid(imap, "acc", 1, False, _FC(), [], seen=True)
    assert moved is True and moves == [(1, "ZENTRALE/Zahlen")]
    # bekannt, aber UNGELESEN → bleibt im Eingang
    moves.clear()
    done, moved = M._handle_uid(imap, "acc", 1, False, _FC(), [], seen=False)
    assert moved is False and moves == []


def test_handle_uid_unknown_stays_even_if_seen(monkeypatch):
    _wire_classify(monkeypatch)
    monkeypatch.setattr(M.mail_rules, "classify",
                        lambda f: (M.mail_rules.REVIEW, False))
    moves = []
    monkeypatch.setattr(M, "_move_uid",
                        lambda imap, uid, target: (moves.append((uid, target)), True)[1])
    done, moved = M._handle_uid(_HdrIMAP("x@neu.io"), "acc", 1, False, _FC(), [], seen=True)
    assert moved is False and moves == []           # unbekannt bleibt im Eingang


def test_mark_seen_and_file_known(monkeypatch):
    imap = _HdrIMAP("a@known.de")
    monkeypatch.setattr(M, "_session", contextmanager(lambda account: iter([imap])))
    monkeypatch.setattr(M, "_accounts_for", lambda name=None: [{"name": "acc"}])
    monkeypatch.setattr(M, "_pselect",
                        lambda imap, name, folder, readonly=True: "OK")
    monkeypatch.setattr(M.mail_rules, "classify", lambda f: ("zahlen", True))
    monkeypatch.setattr(M.mail_rules, "category_action",
                        lambda c: {"action": "move", "folder": "ZENTRALE/Zahlen"})
    monkeypatch.setattr(M._FolderCache, "target", lambda self, imap, spec: spec["folder"])
    moved = []
    monkeypatch.setattr(M, "_move_uid",
                        lambda imap, uid, target: (moved.append(target), True)[1])
    res = M.mark_seen_and_file(1)
    assert res["seen"] and res["filed"] and res["category"] == "zahlen"
    assert imap.stored and imap.stored[0][1] == "+FLAGS"     # \Seen gesetzt
    assert moved == ["ZENTRALE/Zahlen"]


def test_mark_seen_and_file_unknown_only_marks_seen(monkeypatch):
    imap = _HdrIMAP("x@neu.io")
    monkeypatch.setattr(M, "_session", contextmanager(lambda account: iter([imap])))
    monkeypatch.setattr(M, "_accounts_for", lambda name=None: [{"name": "acc"}])
    monkeypatch.setattr(M, "_pselect",
                        lambda imap, name, folder, readonly=True: "OK")
    monkeypatch.setattr(M.mail_rules, "classify",
                        lambda f: (M.mail_rules.REVIEW, False))
    moved = []
    monkeypatch.setattr(M, "_move_uid",
                        lambda imap, uid, target: (moved.append(target), True)[1])
    res = M.mark_seen_and_file(1)
    assert res["seen"] is True and res["filed"] is False     # nur gelesen, bleibt
    assert imap.stored and moved == []                       # \Seen ja, Move nein


def test_inbox_tray_parses_seen_flag_and_category(monkeypatch):
    from types import SimpleNamespace
    class TrayIMAP:
        def uid(self, cmd, *a):
            if cmd == "SEARCH":
                return ("OK", [b"1 2"])
            if cmd == "FETCH":
                return ("OK", [
                    (b"1 (UID 1 FLAGS (\\Seen) BODY[HEADER])",
                     b"From: a@known.de\r\nSubject: s1\r\n\r\n"),
                    (b"2 (UID 2 FLAGS () BODY[HEADER])",
                     b"From: b@neu.io\r\nSubject: s2\r\n\r\n"),
                ])
            return ("OK", [b""])
    monkeypatch.setattr(M, "_session", contextmanager(lambda account: iter([TrayIMAP()])))
    monkeypatch.setattr(M, "_accounts_for", lambda name=None: [{"name": "acc"}])
    monkeypatch.setattr(M, "_pselect",
                        lambda imap, name, folder, readonly=True: "OK")
    monkeypatch.setattr(M.mail_rules, "matcher", lambda: SimpleNamespace(
        classify=lambda f: ("zahlen", True) if "known.de" in f else (M.mail_rules.REVIEW, False)))
    tray = {t["uid"]: t for t in M.inbox_tray()}
    assert tray[1]["seen"] is True and tray[1]["known"] and tray[1]["category"] == "zahlen"
    assert tray[2]["seen"] is False and not tray[2]["known"] and tray[2]["category"] is None


def test_folder_mails_sorted_by_date_not_uid(monkeypatch):
    """Nach einem Reconcile hat die zuletzt per MOVE einsortierte Mail die
    HÖCHSTE UID, aber evtl. das ÄLTESTE Datum — UID-Ordnung ≠ Chronologie.
    folder_mails muss nach echtem Date-Header ordnen (neueste zuerst)."""
    dates = {                                   # UID-Reihenfolge gegenläufig zum Datum
        1: "Thu, 01 Jan 2026 09:00:00 +0100",   # ältestes Datum, niedrigste UID
        2: "Mon, 01 Jun 2026 09:00:00 +0100",   # NEUESTES Datum, mittlere UID
        3: "Sun, 01 Mar 2026 09:00:00 +0100",   # höchste UID, mittleres Datum
    }

    class DateIMAP:
        def select(self, mailbox, readonly=False):
            return ("OK", [b"3"])

        def uid(self, cmd, *a):
            if cmd == "SEARCH":                 # SORT nicht unterstützt → Fallback greift
                return ("OK", [b"1 2 3"])
            if cmd == "FETCH":
                out = []
                for u in [int(x) for x in a[0].split(",")]:
                    meta = ("%d (UID %d BODY[HEADER])" % (u, u)).encode()
                    hdr = ("From: x@known.de\r\nSubject: s%d\r\nDate: %s\r\n\r\n"
                           % (u, dates[u])).encode()
                    out.append((meta, hdr))
                return ("OK", out)
            return ("OK", [b""])

    monkeypatch.setattr(M.mail_rules, "category_action",
                        lambda c: {"action": "move", "folder": "ZENTRALE/Zahlen"})
    monkeypatch.setattr(M.mail_secrets, "load_accounts",
                        lambda: [{"name": "acc", "enabled": True}])
    monkeypatch.setattr(M, "_session", contextmanager(lambda account: iter([DateIMAP()])))
    monkeypatch.setattr(M, "_pselect",
                        lambda imap, name, folder, readonly=True: "OK")

    mails = M.folder_mails("Zahlen")
    assert [m["uid"] for m in mails] == [2, 3, 1]     # nach DATUM, nicht [3,2,1] nach UID


def test_folder_uids_by_date_prefers_server_sort(monkeypatch):
    """Kann der Server SORT, kommt dessen Datums-Reihenfolge (REVERSE DATE) —
    kein blindes UID-SEARCH mehr."""
    class SortIMAP:
        def __init__(self):
            self.calls = []

        def uid(self, cmd, *a):
            self.calls.append(cmd)
            if cmd == "SORT":
                return ("OK", [b"2 3 1"])       # Server liefert Datums-Ordnung
            if cmd == "SEARCH":
                return ("OK", [b"1 2 3"])
            return ("OK", [b""])

    imap = SortIMAP()
    assert M._folder_uids_by_date(imap, 200) == [2, 3, 1]
    assert "SORT" in imap.calls and "SEARCH" not in imap.calls   # SORT gewann, kein Fallback


# ── Entwurf: Antwort als echter IMAP-Draft (Drafts-Ordner) ────────────

class DraftIMAP:
    """IMAP-Stub für save_draft: LIST liefert einen \\Drafts-Ordner, APPEND wird
    protokolliert (Ordner, Flags, Nachricht)."""
    def __init__(self):
        self.appended = []
        self._list = [b'(\\HasNoChildren \\Drafts) "/" "Entw\xc3\xbcrfe"']

    def list(self):
        return ("OK", self._list)

    def create(self, mailbox):
        return ("OK", [b""])

    def append(self, mailbox, flags, date_time, message):
        self.appended.append((mailbox, flags, message))
        return ("OK", [b"APPEND completed"])


def test_find_drafts_prefers_special_use():
    imap = DraftIMAP()
    assert M._find_drafts(imap) == "Entwürfe"          # Special-Use \Drafts gewinnt


def test_find_drafts_falls_back_to_drafts_name():
    class NoSpecial(DraftIMAP):
        def list(self): return ("OK", [b'(\\HasNoChildren) "/" "INBOX"'])
    assert M._find_drafts(NoSpecial()) == "Drafts"


def test_save_draft_appends_with_draft_flag(monkeypatch):
    from contextlib import contextmanager
    imap = DraftIMAP()

    @contextmanager
    def fake_session(account):
        yield imap
    monkeypatch.setattr(M, "_session", fake_session)

    folder = M.save_draft({"name": "acc", "user": "me@x.z"}, "to@y.z",
                          "Re: hallo", "mein text",
                          in_reply_to="<m1>", references="<m0> <m1>")
    assert folder == "Entwürfe"
    assert len(imap.appended) == 1
    mailbox, flags, message = imap.appended[0]
    assert flags == r"(\Draft)"                       # als Entwurf markiert
    assert b"To: to@y.z" in message
    assert b"Subject: Re: hallo" in message
    assert b"In-Reply-To: <m1>" in message            # Threading erhalten
    assert b"mein text" in message


def test_draft_reply_builds_re_subject_and_threads(monkeypatch):
    captured = {}
    monkeypatch.setattr(M, "mail_body", lambda cat, uid, account_name=None: {
        "account": "acc", "from": "Bob <bob@x.z>", "subject": "Angebot",
        "message_id": "<m1>", "references": "<m0>", "body": "…"})
    monkeypatch.setattr(M, "_accounts_for",
                        lambda name=None: [{"name": "acc", "user": "me@x.z"}])

    def fake_save(account, to_addr, subject, body, in_reply_to=None, references=None):
        captured.update(to=to_addr, subject=subject, irt=in_reply_to, refs=references)
        return "Drafts"
    monkeypatch.setattr(M, "save_draft", fake_save)

    res = M.draft_reply("zahlen", 5, "meine antwort", account_name="acc")
    assert res["ok"] and res["draft"] and res["folder"] == "Drafts"
    assert captured["to"] == "bob@x.z"                # nur die Adresse
    assert captured["subject"] == "Re: Angebot"       # Re: vorangestellt
    assert captured["irt"] == "<m1>"                  # In-Reply-To = Original-ID
    assert "<m1>" in captured["refs"] and "<m0>" in captured["refs"]
