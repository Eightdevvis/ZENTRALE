# core/mail_oauth.py
#
# OAuth2 für Outlook.com-IMAP (XOAUTH2). Microsoft hat Basic-Auth für IMAP bei
# Privat-Konten abgeschaltet — IMAP geht nur noch mit einem OAuth2-Access-Token.
#
# ── Zwei Login-Wege (beide enden im selben refresh_token) ─────────────
# Microsoft hat App-Erstellung ohne eigenes Verzeichnis abgeschafft; ein
# Gratis-Entra-Tenant will eine Kreditkarte sehen. Darum zwei Wege:
#
#   A) THUNDERBIRD-CLIENT-ID (Default, KEIN Azure, kein Geld, kein Ablauf):
#      Wir leihen die öffentliche Client-ID von Mozilla Thunderbird — von
#      Microsoft für Privatkonten freigegeben, genau wie OfflineIMAP/mutt es
#      tun. Diese App ist auf den AUTH-CODE-Flow registriert (nicht Device-
#      Code): Browser-Login → Code aus der Adressleiste zurückkopieren.
#      Redirect ist der „nativeclient"-Endpunkt, also kein localhost-Server.
#      PKCE (S256) sichert den Code-Tausch ohne Client-Secret ab.
#
#   B) EIGENE AZURE-APP (Device-Code, headless): nur sinnvoll mit eigenem
#      Verzeichnis (z.B. 30-Tage-Trial-Tenant). Einmalig:
#        1. POST /devicecode -> user_code + verification_uri.
#        2. Sasha öffnet die URL, tippt den Code, meldet sich an.
#        3. Wir pollen /token bis Erfolg -> access_token + REFRESH_TOKEN.
#
# Der langlebige refresh_token wird verschlüsselt gespeichert (mail_secrets);
# bei jedem Poll tauscht access_token_for() ihn gegen ein frisches, kurz-
# lebiges access_token. Der Refresh-Pfad ist für A und B identisch.
#
# ── Privat-Konto-Spezifika (verifiziert 2026-06, Microsoft Learn) ─────
#   Authority: https://login.microsoftonline.com/consumers  (Privatkonten)
#              bzw. /common (Thunderbird-Weg, akzeptiert Privat + Org).
#   Scope:     offline_access IMAP.AccessAsUser.All + SMTP.Send (beide unter
#              outlook.office.com → EIN Token deckt IMAP-Lesen UND SMTP-Senden).
#   IMAP-Host: outlook.office365.com:993 (SSL), SASL XOAUTH2.
#   SMTP-Host: smtp.office365.com:587 (STARTTLS), SASL XOAUTH2.
#
# ── Transparenz ───────────────────────────────────────────────────────
# Diese Calls gehen an login.microsoftonline.com (echtes Internet). Da sie
# nicht durch core/net.py laufen, loggen wir sie selbst ins orangene
# Internet-Panel — aber NIE Tokens, nur Endpunkt + Status.

import os
import sys
import time
import json
import base64
import hashlib
import urllib.parse
import urllib.request
import urllib.error

# core/ auf den Pfad, damit `import state` auch bei `python -m core.mail_oauth`
# greift (sonst liegt nur das Projekt-Root auf sys.path, nicht core/).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import state
import mail_secrets

DEFAULT_AUTHORITY = "https://login.microsoftonline.com/consumers"
# IMAP-Lesen UND SMTP-Senden in EINEM Scope — beide Ressourcen liegen unter
# outlook.office.com, ein Access-Token deckt damit beides ab. Wer den alten
# (nur-IMAP) refresh_token hat, muss EINMAL neu einloggen (Re-Consent für
# SMTP.Send): venv/bin/python -m core.mail_oauth login
SCOPE = ("offline_access "
         "https://outlook.office.com/IMAP.AccessAsUser.All "
         "https://outlook.office.com/SMTP.Send")

# Mozilla Thunderbirds öffentliche Client-ID — von Microsoft für Privatkonten
# freigegeben. Damit braucht ZENTRALE KEINE eigene Azure-App (Weg A oben).
THUNDERBIRD_CLIENT_ID = "9e5f94bc-e8a4-4e73-b8be-63364c29d753"
THUNDERBIRD_AUTHORITY = "https://login.microsoftonline.com/common"

# „nativeclient"-Redirect: registrierter Out-of-Band-Endpunkt der Public
# Clients. Nach dem Login landet der Browser hier mit ?code=… in der URL —
# kein localhost-Webserver nötig, Sasha kopiert den Code zurück.
NATIVE_REDIRECT = "https://login.microsoftonline.com/common/oauth2/nativeclient"

# In-Memory-Cache der kurzlebigen Access-Tokens: name -> (token, expires_at).
# Bewusst NICHT persistiert — nach Neustart holen wir per Refresh-Token neu
# (ein billiger HTTP-Call). Nur der refresh_token liegt verschlüsselt auf Platte.
_token_cache = {}


class OAuthError(RuntimeError):
    def __init__(self, status, data):
        self.status = status
        self.data = data or {}
        super().__init__(self.data.get("error_description") or self.data.get("error") or f"HTTP {status}")


def _authority(account):
    return (account.get("authority") or DEFAULT_AUTHORITY).rstrip("/")


def _form_post(url, fields):
    """POST application/x-www-form-urlencoded -> dict. Loggt transparent,
    ohne Tokens. Bei 4xx wird der JSON-Fehlerkörper als OAuthError geliefert
    (der Device-Poll braucht den 'authorization_pending'-Code)."""
    host = urllib.parse.urlparse(url).netloc
    state.push_log(f"OAUTH → {host} ({fields.get('grant_type', 'devicecode')})")
    state.push_internet_log(f"OAUTH → {host}")
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = {}
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            pass
        raise OAuthError(e.code, body)


# ── Einmaliger Device-Login ───────────────────────────────────────────

def begin_device_login(client_id, authority=DEFAULT_AUTHORITY):
    url = f"{authority.rstrip('/')}/oauth2/v2.0/devicecode"
    return _form_post(url, {"client_id": client_id, "scope": SCOPE})


def poll_for_token(client_id, device, authority=DEFAULT_AUTHORITY):
    """Pollt /token bis der User sich angemeldet hat. `device` = Antwort von
    begin_device_login. Liefert das Token-Dict (mit refresh_token)."""
    url = f"{authority.rstrip('/')}/oauth2/v2.0/token"
    interval = int(device.get("interval", 5))
    deadline = time.time() + int(device.get("expires_in", 900))
    fields = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": client_id,
        "device_code": device["device_code"],
    }
    while time.time() < deadline:
        time.sleep(interval)
        try:
            return _form_post(url, fields)
        except OAuthError as e:
            err = e.data.get("error")
            if err == "authorization_pending":
                continue
            if err == "slow_down":
                interval += 5
                continue
            # authorization_declined / expired_token / bad_verification_code …
            raise
    raise OAuthError(408, {"error": "expired_token",
                           "error_description": "Device-Code abgelaufen"})


def refresh(client_id, refresh_token, authority=DEFAULT_AUTHORITY):
    url = f"{authority.rstrip('/')}/oauth2/v2.0/token"
    return _form_post(url, {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
        "scope": SCOPE,
    })


# ── Einmaliger Auth-Code-Login (Thunderbird-Weg, kein Azure) ──────────
# PKCE (RFC 7636, S256): wir würfeln einen Verifier, schicken nur dessen
# SHA-256-Hash mit dem Auth-Request und beweisen beim Code-Tausch den
# Verifier — so ist der Flow auch ohne Client-Secret sicher.

def _pkce_pair():
    verifier = base64.urlsafe_b64encode(os.urandom(40)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_auth_url(client_id, code_challenge, authority=THUNDERBIRD_AUTHORITY,
                   redirect_uri=NATIVE_REDIRECT):
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": SCOPE,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return f"{authority.rstrip('/')}/oauth2/v2.0/authorize?" + urllib.parse.urlencode(params)


def exchange_code(client_id, code, code_verifier, authority=THUNDERBIRD_AUTHORITY,
                  redirect_uri=NATIVE_REDIRECT):
    """Tauscht den Auth-Code gegen Tokens (mit refresh_token)."""
    url = f"{authority.rstrip('/')}/oauth2/v2.0/token"
    return _form_post(url, {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
        "scope": SCOPE,
    })


def extract_code(pasted):
    """Akzeptiert entweder den nackten Code oder die ganze Redirect-URL aus
    der Adressleiste (…/nativeclient?code=…&session_state=…)."""
    s = pasted.strip()
    if "code=" in s:
        query = urllib.parse.urlparse(s).query or s.split("?", 1)[-1]
        params = urllib.parse.parse_qs(query)
        if params.get("code"):
            return params["code"][0]
    return s


# ── Im Betrieb: gültiges Access-Token für ein Konto ───────────────────

def access_token_for(account):
    """Liefert ein frisches Access-Token. Nutzt den In-Memory-Cache, sonst
    Refresh über den gespeicherten refresh_token. Rotiert Microsoft den
    refresh_token, wird der neue verschlüsselt zurückgespeichert."""
    name = account["name"]
    cached = _token_cache.get(name)
    if cached and cached[1] - 60 > time.time():
        return cached[0]

    oauth = account.get("oauth") or {}
    rt = oauth.get("refresh_token")
    if not rt:
        raise OAuthError(401, {"error": "no_refresh_token",
                               "error_description": f"Konto '{name}' ist nicht "
                               "eingeloggt — erst: python -m core.mail_oauth login"})
    client_id = account["client_id"]
    tok = refresh(client_id, rt, _authority(account))

    access = tok["access_token"]
    expires_at = time.time() + int(tok.get("expires_in", 3600))
    _token_cache[name] = (access, expires_at)

    # Refresh-Token-Rotation: neuen RT persistieren, sonst läuft der alte aus.
    new_rt = tok.get("refresh_token")
    if new_rt and new_rt != rt:
        account.setdefault("oauth", {})["refresh_token"] = new_rt
        try:
            mail_secrets.upsert(account)
        except Exception as e:
            state.push_log(f"MAIL: refresh_token-Rotation nicht gespeichert "
                           f"({type(e).__name__}) — Login könnte später nötig werden")
    return access


# ── CLI: einmaliger Login eines Outlook-Kontos ────────────────────────
#   ZENTRALE_MAIL_KEY=… venv/bin/python -m core.mail_oauth login

def _save_account(name, user, client_id, authority, refresh_token):
    acct = {
        "name": name, "provider": "outlook", "user": user,
        "auth": "oauth2", "client_id": client_id, "authority": authority,
        "oauth": {"refresh_token": refresh_token},
        "enabled": True,
    }
    mail_secrets.upsert(acct)
    print(f"\n✓ '{name}' eingeloggt + verschlüsselt gespeichert. "
          "Test:  venv/bin/python core/mail.py --poll")


def _login_thunderbird(name, user):
    """Weg A: Auth-Code-Flow mit Thunderbirds Client-ID, kein Azure."""
    client_id = THUNDERBIRD_CLIENT_ID
    authority = THUNDERBIRD_AUTHORITY
    verifier, challenge = _pkce_pair()
    url = build_auth_url(client_id, challenge, authority)
    print("\n" + "=" * 64)
    print("1. Öffne diese URL im Browser und melde dich bei Outlook an:\n")
    print("   " + url)
    print("\n2. Danach landet der Browser auf einer (fast leeren) Seite.")
    print("   Kopiere die GANZE Adresse aus der Adressleiste (enthält ?code=…)")
    print("=" * 64)
    pasted = input("\nCode oder Redirect-URL einfügen: ").strip()
    code = extract_code(pasted)
    if not code:
        print("FEHLER: kein Code erkannt.", file=__import__("sys").stderr)
        return 2
    tok = exchange_code(client_id, code, verifier, authority)
    _save_account(name, user, client_id, authority, tok["refresh_token"])
    return 0


def _login_device(name, user):
    """Weg B: Device-Code mit eigener Azure-App (z.B. Trial-Tenant)."""
    client_id = input("Azure App (client) ID: ").strip()
    authority = input(f"Authority [{DEFAULT_AUTHORITY}]: ").strip() or DEFAULT_AUTHORITY
    device = begin_device_login(client_id, authority)
    print("\n" + "=" * 60)
    print(device.get("message")
          or f"Öffne {device['verification_uri']} und gib den Code ein: {device['user_code']}")
    print("=" * 60)
    print("\nWarte auf Anmeldung im Browser …")
    tok = poll_for_token(client_id, device, authority)
    _save_account(name, user, client_id, authority, tok["refresh_token"])
    return 0


def _cli():
    import sys
    args = sys.argv[1:]
    if not args or args[0] != "login":
        print("Nutzung: python -m core.mail_oauth login", file=sys.stderr)
        return 2
    if not os.environ.get("ZENTRALE_MAIL_KEY"):
        print("FEHLER: ZENTRALE_MAIL_KEY nicht gesetzt.", file=sys.stderr)
        return 2

    print("Outlook-OAuth-Login\n")
    print("  [1] Thunderbird-Client-ID  (Default, kein Azure, kein Geld)")
    print("  [2] eigene Azure-App       (Device-Code, eigenes Verzeichnis nötig)")
    route = input("Weg [1]: ").strip() or "1"

    name = input("Kurzname [outlook]: ").strip() or "outlook"
    user = input("Outlook-Mailadresse: ").strip()

    if route == "2":
        return _login_device(name, user)
    return _login_thunderbird(name, user)


if __name__ == "__main__":
    raise SystemExit(_cli())
