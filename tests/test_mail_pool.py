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


# ── Einsortieren durchsucht GENAU EINEN Ordner ────────────────────────
# Ein Absender ist immer genau einer Kategorie zugeordnet und der Poll hat seine
# Mails längst aus der INBOX in diesen Ordner geräumt → seine Mails liegen an
# genau einer Stelle: dem bisherigen Kategorie-Ordner (Review, solange unbekannt).

@pytest.fixture()
def refile(monkeypatch):
    """refile_sender so verdrahten, dass wir ohne Netz sehen, WELCHE Ordner
    durchsucht werden. `searched` sammelt die selektierten Quell-Ordner."""
    from contextlib import contextmanager
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
    monkeypatch.setattr(M.mail_rules, "category_action", lambda name: cats[name])
    monkeypatch.setattr(M._FolderCache, "target",
                        lambda self, imap, spec: spec["folder"])
    monkeypatch.setattr(M, "_pselect",
                        lambda imap, name, folder, readonly=True:
                        (searched.append(folder), "OK")[1])
    monkeypatch.setattr(M, "_move_uid_set",
                        lambda imap, uids, target, **k: len(list(uids)))
    return searched


def test_refile_searches_only_prev_folder(refile, monkeypatch):
    monkeypatch.setattr(M.mail_rules, "classify", lambda s: ("zahlen", True))
    res = M.refile_sender("x@y.z", "arbeit")             # zahlen → arbeit
    assert refile == ["ZENTRALE/Zahlen"]                 # GENAU ein Ordner, kein INBOX
    assert res["moved"] == 2                             # 1 Ordner × 2 Treffer


def test_refile_unknown_sender_searches_review(refile, monkeypatch):
    # Unbekannter Absender: classify() liefert REVIEW → nur dessen Ordner.
    monkeypatch.setattr(M.mail_rules, "classify",
                        lambda s: (M.mail_rules.REVIEW, False))
    M.refile_sender("neu@y.z", "arbeit")
    assert refile == ["ZENTRALE/Review"]


def test_refile_same_category_searches_nothing(refile, monkeypatch):
    # In dieselbe Kategorie umsortieren: der bisherige Ordner IST das Ziel →
    # wird übersprungen, es gibt nichts zu durchsuchen/verschieben.
    monkeypatch.setattr(M.mail_rules, "classify", lambda s: ("arbeit", True))
    res = M.refile_sender("x@y.z", "arbeit")
    assert refile == []
    assert res["moved"] == 0


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
