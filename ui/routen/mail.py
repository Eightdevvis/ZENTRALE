# ui/routen/mail.py
#
# Mail-Triage: Panel, Ordner, Lesen/Antworten/Sortieren, Poll und Abgleich.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md): dünne
# Adapter von HTTP auf core/. Die Puffer (Live-Zählung, Ordner-Inhalte) und
# die Hintergrund-Jobs wohnen seit 2026-10-06 in core/mail_puffer.py — hier
# steht nur noch Anfrage lesen → Kern fragen → Antwort formen.

from flask import Blueprint, jsonify, request

import mail         # type: ignore  – Mail-Triage (read-only Panel + Live-Poll)
import mail_puffer  # type: ignore  – Zähl-/Ordner-Puffer und Hintergrund-Jobs
import mail_secrets # type: ignore  – verschlüsselter Zugangsdaten-Speicher

bp = Blueprint('mail', __name__)


@bp.route('/api/mail')
def api_mail():
    """Alles fürs Mail-Panel in einem Rutsch, Drill-down-freundlich:
    `categories` = Ebene 1 (alle Kategorien zum Auswählen). `count` ist der
    lokale Schnappschuss; `live_counts` (separat) trägt die ECHTE Ordnergröße
    aus dem Cache, sobald aufgefrischt. `can_poll` = Passphrase vorhanden,
    `polling`/`counts_refreshing` = Hintergrund-Aktivität läuft."""
    try:
        puffer = mail_puffer.panel_stand()
        return jsonify({
            "categories": mail.category_overview(),
            "recent": mail.recent(limit=200),
            "live_counts": puffer["live_counts"],
            "counts_age_s": puffer["counts_age_s"],
            "counts_refreshing": puffer["counts_refreshing"],
            "can_poll": mail_secrets.available(),
            "polling": puffer["polling"],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/mail/refresh-counts', methods=['POST'])
def api_mail_refresh_counts():
    """Frischt den LIVE-Ordnerzähl-Cache im Hintergrund auf (IMAP STATUS-Sweep).
    Kehrt sofort zurück; das Ergebnis erscheint beim nächsten /api/mail. Key-
    gegatet, Parallel-Refresh verhindert, `?force=1` umgeht die TTL."""
    if not mail_secrets.available():
        return jsonify({"ok": False, "error": "kein key"}), 409
    return jsonify(mail_puffer.zahlen_auffrischen(bool(request.args.get("force"))))


@bp.route('/api/mail/folder')
def api_mail_folder():
    """Die Mails EINER Kategorie. Serviert SOFORT aus dem Ordner-Cache (kein
    Warten aufs IMAP) und frischt bei abgelaufenem Cache im Hintergrund auf; nur
    der allererste Aufruf je Kategorie (kalter Cache) holt synchron. `?force=1`
    umgeht den Cache und holt synchron frisch (nach Umsortieren/Löschen). Ohne
    Key oder ohne eigenen Ordner: lokaler Schnappschuss. `cached`/`refreshing`
    sagen, ob die Liste aus dem Cache kam und ob im Hintergrund nachgezogen wird."""
    cat = request.args.get('cat', '')
    if not cat:
        return jsonify({"error": "cat fehlt"}), 400
    force = bool(request.args.get('force'))
    try:
        if not mail_secrets.available():
            mails = mail.in_category(cat, limit=200)
            return jsonify({"cat": cat, "mails": mails, "live": False,
                            "source": "snapshot"})
        return jsonify(mail_puffer.ordner(cat, force))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/mail/body')
def api_mail_body():
    """Voller Text + Header EINER Mail (Lesemodus). LIVE aus dem Ordner; braucht
    Key. Query: `cat`, `uid`, optional `account`, optional `prefetch` (Komma-
    Liste von Nachbar-uids → werden im Hintergrund in den Body-Cache geholt,
    damit n/N im Panel instant ist)."""
    cat = request.args.get('cat', '')
    uid = request.args.get('uid', type=int)
    account = request.args.get('account') or None
    if not cat or uid is None:
        return jsonify({"error": "cat/uid fehlt"}), 400
    if not mail_secrets.available():
        return jsonify({"error": "kein key — Body nur live lesbar"}), 409
    try:
        body = mail.mail_body(cat, uid, account_name=account)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    pf = request.args.get('prefetch', '')
    neigh = [int(x) for x in pf.split(',') if x.strip().lstrip('-').isdigit()]
    if neigh:
        mail_puffer.vorwaermen(cat, neigh, account)
    return jsonify(body)


@bp.route('/api/mail/assign', methods=['POST'])
def api_mail_assign():
    """Den ABSENDER einer Kategorie zuordnen (Keymap) UND **alle** seine
    vorhandenen Mails (alt + neu) in den Kategorie-Ordner verschieben — Sashas
    Modell: pro Absender EINE Kategorie. Mit Key: live umsortiert (`moved` zählt);
    ohne Key: nur Keymap (künftige Mails). Body: `{sender, category}`."""
    body = request.get_json(silent=True) or {}
    sender = (body.get('sender') or '').strip()
    category = (body.get('category') or '').strip()
    if not sender or not category:
        return jsonify({"error": "sender/category fehlt"}), 400
    try:
        res = mail.refile_sender(sender, category)
        # Der Umzug ist keymap-getrieben und kann aus MEHREREN Ordnern gezogen
        # haben (INBOX + jeder move-Ordner). Statt einzelne Herkünfte zu raten
        # den ganzen Ordner-Cache verwerfen — das nächste Öffnen holt frisch.
        mail_puffer.ordner_verwerfen()
        return jsonify({"ok": True, **res})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/mail/delete', methods=['POST'])
def api_mail_delete():
    """Eine Mail in den Papierkorb verschieben (umkehrbar). LIVE; braucht Key.
    Body: `{cat, uid, account?}`."""
    if not mail_secrets.available():
        return jsonify({"error": "kein key — löschen nur live"}), 409
    body = request.get_json(silent=True) or {}
    cat = (body.get('cat') or '').strip()
    uid = body.get('uid')
    account = body.get('account') or None
    if not cat or uid is None:
        return jsonify({"error": "cat/uid fehlt"}), 400
    try:
        ok = mail.delete_mail(cat, int(uid), account_name=account)
        if ok:                          # gelöschte Mail sofort aus dem Cache nehmen
            mail_puffer.ordner_mail_entfernen(cat, int(uid))
        return jsonify({"ok": bool(ok)}), (200 if ok else 502)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/mail/reply', methods=['POST'])
def api_mail_reply():
    """Antwort auf eine Mail. LIVE; braucht Key. Body: `{cat, uid, text,
    account?, draft?}`. To/Betreff/Threading leitet das Backend aus der
    Original-Mail ab. `draft:true` → speichert die Antwort als ENTWURF im
    Drafts-Ordner (IMAP APPEND) statt sie per SMTP zu senden."""
    if not mail_secrets.available():
        return jsonify({"error": "kein key — senden nicht möglich"}), 409
    body = request.get_json(silent=True) or {}
    cat = (body.get('cat') or '').strip()
    uid = body.get('uid')
    text = body.get('text') or ''
    account = body.get('account') or None
    draft = bool(body.get('draft'))
    if not cat or uid is None or not text.strip():
        return jsonify({"error": "cat/uid/text fehlt"}), 400
    if draft:
        res = mail.draft_reply(cat, int(uid), text, account_name=account)
    else:
        res = mail.reply_to_mail(cat, int(uid), text, account_name=account)
    if res.get("error"):
        return jsonify(res), 502
    return jsonify(res)


@bp.route('/api/mail/poll', methods=['POST'])
def api_mail_poll():
    """Stößt einen LIVE-Poll im Hintergrund an (explizite Nutzer-Aktion =
    Einwilligung; Move/Trash sind umkehrbar). Kehrt sofort zurück — der
    Fortschritt läuft über die normalen Log-Streams. Verhindert Parallel-Polls."""
    if not mail_secrets.available():
        return jsonify({"error": "keine Passphrase (Env oder OS-Keyring) — "
                                 "kein Live-Poll möglich"}), 409
    return jsonify(mail_puffer.poll_starten())


@bp.route('/api/mail/reconcile', methods=['POST'])
def api_mail_reconcile():
    """Gleicht die Server-Ordner an die Keymap an (bereits einsortierte Mail
    nachziehen) — im Hintergrund-Thread, kehrt SOFORT zurück, blockiert die GUI
    also nie. Explizite Nutzer-Aktion = Einwilligung (Move/Trash umkehrbar). Key-
    gegatet, Parallel-Reconcile via Lock verhindert. Fortschritt läuft über die
    Log-Streams; das Panel bleibt bedienbar."""
    if not mail_secrets.available():
        return jsonify({"error": "keine Passphrase (Env oder OS-Keyring) — "
                                 "kein Abgleich möglich"}), 409
    return jsonify(mail_puffer.abgleich_starten())


@bp.route('/api/mail/inbox')
def api_mail_inbox():
    """Der Eingang-Tray: die INBOX mit Gelesen-Flag (`\\Seen`) + vermuteter
    Kategorie je Mail. LIVE; braucht Key (ohne → leer). Neue/ungelesene Mail liegt
    hier, bis Sasha sie liest — dann sortiert sie sich (bekannter Absender) ein."""
    if not mail_secrets.available():
        return jsonify({"mails": [], "live": False, "source": "kein key"})
    try:
        return jsonify({"mails": mail.inbox_tray(limit=200), "live": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/mail/inbox-body')
def api_mail_inbox_body():
    """Voller Text EINER Eingang-Mail (INBOX). LIVE; braucht Key. Query: `uid`,
    optional `account`. Read-only (PEEK) → hakt die Mail NICHT ab."""
    uid = request.args.get('uid', type=int)
    account = request.args.get('account') or None
    if uid is None:
        return jsonify({"error": "uid fehlt"}), 400
    if not mail_secrets.available():
        return jsonify({"error": "kein key — Body nur live lesbar"}), 409
    try:
        return jsonify(mail.inbox_body(uid, account_name=account))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/mail/read', methods=['POST'])
def api_mail_read():
    """Eine Eingang-Mail abhaken: als gelesen markieren (`\\Seen`) und, wenn der
    Absender bekannt ist, sofort einsortieren. LIVE; braucht Key. Body:
    `{uid, account?}`. Sortiert sie ein → alle Ordner-Caches verwerfen."""
    if not mail_secrets.available():
        return jsonify({"error": "kein key — abhaken nur live"}), 409
    body = request.get_json(silent=True) or {}
    uid = body.get('uid')
    account = body.get('account') or None
    if uid is None:
        return jsonify({"error": "uid fehlt"}), 400
    try:
        res = mail.mark_seen_and_file(int(uid), account_name=account)
        if res.get("filed"):        # Mail wanderte in einen Ordner → Caches stale
            mail_puffer.ordner_verwerfen()
        return jsonify({"ok": True, **res})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
