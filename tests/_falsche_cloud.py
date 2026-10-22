"""Eine gespielte ZENTRALE-Cloud für Tests: http.server in einem Thread, die
Routen aus memory/hub/knoten_beitritt.md („Bauplan v1 — Schnittstelle"),
alles im Speicher. Nie das Netz, nie die echte Cloud.

Sie prüft, was der echte Server prüfen muss, so weit es den Client betrifft:
Code wird verbraucht, anmelde_schluessel nur als Hash, Bearer-Sitzung,
Compare-and-Swap auf den Kopf der Mitte (409 jemand_schneller)."""

import base64
import hashlib
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse


class Zustand:
    def __init__(self):
        self.codes = {"EINLADUNG-1", "EINLADUNG-2"}
        self.konten = {}            # mail → dict
        self.sitzungen = {}         # token → mail
        self.kopf = {}              # mail → kennung | None
        self.staende = {}           # kennung → {name: bytes}
        self.eltern = {}            # kennung → basis
        self.knoten = {}            # mail → {name: beschreibung}
        self.paket = None           # (version, bytes)
        self.aufrufe = []           # (methode, pfad) — zum Nachsehen in Tests
        self.zaehler = 0
        self.sperre = threading.Lock()


def _hash(anmelde):
    return hashlib.pbkdf2_hmac("sha256", anmelde.encode(), b"server-salz", 1000).hex()


class _Handler(BaseHTTPRequestHandler):
    z: Zustand = None

    def log_message(self, *a):
        pass

    # ── Hilfen ─────────────────────────────────────────────────────────
    def _antwort(self, status, daten=None, roh=None):
        body = roh if roh is not None else json.dumps(daten if daten is not None else {}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream" if roh is not None
                         else "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _fehler(self, status, code, text):
        self._antwort(status, {"fehler": code, "text": text})

    def _json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _mail(self):
        kopf = self.headers.get("Authorization", "")
        if kopf.startswith("Bearer "):
            return self.z.sitzungen.get(kopf[7:])
        return None

    def _code_ok(self, abfrage):
        return (abfrage.get("code") or [""])[0] in self.z.codes or self._mail()

    # ── Verteiler ──────────────────────────────────────────────────────
    def _gehen(self, methode):
        u = urlparse(self.path)
        pfad, abfrage = u.path, parse_qs(u.query)
        self.z.aufrufe.append((methode, pfad))
        with self.z.sperre:
            try:
                self._route(methode, pfad, abfrage)
            except Exception as e:   # noqa: BLE001 — ein Testserver soll laut sagen, was los ist
                self._fehler(500, "kaputt", repr(e))

    def do_GET(self):
        self._gehen("GET")

    def do_POST(self):
        self._gehen("POST")

    def do_PUT(self):
        self._gehen("PUT")

    def do_DELETE(self):
        self._gehen("DELETE")

    def _route(self, m, pfad, abfrage):
        z = self.z
        if (m, pfad) == ("POST", "/v1/vorab"):
            mail = self._json()["mail"].lower()
            k = z.konten.get(mail)
            if k:
                return self._antwort(200, {"salz": k["salz"], "kdf": k["kdf"]})
            erfunden = hashlib.sha256(b"fake" + mail.encode()).digest()[:16]
            return self._antwort(200, {"salz": base64.urlsafe_b64encode(erfunden).rstrip(b"=").decode(),
                                       "kdf": {"name": "argon2id", "t": 1, "m": 64, "p": 1}})
        if (m, pfad) == ("POST", "/v1/konto"):
            d = self._json()
            if d.get("code") not in z.codes:
                return self._fehler(403, "code_ungueltig", "This invite code is not valid.")
            mail = d["mail"].lower()
            if mail in z.konten:
                return self._fehler(409, "mail_vergeben", "An account with this email exists.")
            z.codes.discard(d["code"])
            z.konten[mail] = {"salz": d["salz"], "kdf": d["kdf"], "hash": _hash(d["anmelde_schluessel"]),
                              "verpackt_passwort": d["verpackt_passwort"],
                              "verpackt_notfall": d["verpackt_notfall"],
                              "notfall_beweis": _hash(d["notfall_beweis"])}
            z.kopf[mail] = None
            return self._antwort(201, {})
        if (m, pfad) == ("POST", "/v1/sitzung"):
            d = self._json()
            k = z.konten.get(d["mail"].lower())
            if not k or k["hash"] != _hash(d["anmelde_schluessel"]):
                return self._fehler(401, "falsch", "Wrong email or password.")
            token = secrets.token_hex(16)
            z.sitzungen[token] = d["mail"].lower()
            return self._antwort(200, {"token": token, "laeuft_ab": "2099-01-01T00:00:00Z",
                                       "verpackt_passwort": k["verpackt_passwort"]})
        if (m, pfad) == ("DELETE", "/v1/sitzung"):
            kopf = self.headers.get("Authorization", "")[7:]
            z.sitzungen.pop(kopf, None)
            return self._antwort(200, {})
        if (m, pfad) == ("POST", "/v1/notfall"):
            d = self._json()
            k = z.konten.get(d["mail"].lower())
            if not k or k["notfall_beweis"] != _hash(d["notfall_beweis"]):
                return self._fehler(403, "falsch", "Wrong emergency key.")
            token = secrets.token_hex(16)
            z.sitzungen[token] = d["mail"].lower()
            return self._antwort(200, {"verpackt_notfall": k["verpackt_notfall"], "token": token})
        if (m, pfad) == ("GET", "/v1/paket"):
            if not self._code_ok(abfrage) or not z.paket:
                return self._fehler(403, "code_ungueltig", "Invite code or login needed.")
            v, daten = z.paket
            return self._antwort(200, {"version": v, "sha256": hashlib.sha256(daten).hexdigest(),
                                       "groesse": len(daten)})
        if m == "GET" and pfad.startswith("/v1/paket/"):
            if not self._code_ok(abfrage) or not z.paket:
                return self._fehler(403, "code_ungueltig", "Invite code or login needed.")
            return self._antwort(200, roh=z.paket[1])

        mail = self._mail()
        if mail is None:
            return self._fehler(401, "nicht_angemeldet", "Not logged in.")
        if (m, pfad) == ("PUT", "/v1/konto/passwort"):
            d = self._json()
            k = z.konten[mail]
            k.update(salz=d["salz"], kdf=d["kdf"], hash=_hash(d["anmelde_schluessel"]),
                     verpackt_passwort=d["verpackt_passwort"])
            return self._antwort(200, {})
        if (m, pfad) == ("GET", "/v1/mitte"):
            kopf = z.kopf.get(mail)
            return self._antwort(200, {"kennung": kopf,
                                       "namen": sorted(z.staende.get(kopf, {})) if kopf else []})
        if m == "GET" and pfad.startswith("/v1/mitte/datei/"):
            name = unquote(pfad[len("/v1/mitte/datei/"):])
            stand = z.staende.get(z.kopf.get(mail), {})
            if name not in stand:
                return self._fehler(404, "fehlt", "No such file.")
            return self._antwort(200, roh=stand[name])
        if (m, pfad) == ("POST", "/v1/mitte/stand"):
            d = self._json()
            if d.get("basis") != z.kopf.get(mail):
                return self._fehler(409, "jemand_schneller", "Someone else was faster.")
            neu = dict(z.staende.get(d.get("basis"), {}))
            for name, b64 in d.get("schreiben", {}).items():
                neu[name] = base64.b64decode(b64)
            for name in d.get("loeschen", []):
                neu.pop(name, None)
            z.zaehler += 1
            kennung = f"s{z.zaehler:04d}"
            z.staende[kennung], z.eltern[kennung] = neu, d.get("basis")
            z.kopf[mail] = kennung
            return self._antwort(200, {"kennung": kennung})
        if m == "GET" and pfad.startswith("/v1/mitte/enthaelt/"):
            gesucht, k = unquote(pfad.rsplit("/", 1)[1]), z.kopf.get(mail)
            while k is not None and k != gesucht:
                k = z.eltern.get(k)
            return self._antwort(200, {"enthaelt": k is not None})
        if m == "PUT" and pfad.startswith("/v1/knoten/"):
            z.knoten.setdefault(mail, {})[unquote(pfad.rsplit("/", 1)[1])] = self._json()
            return self._antwort(200, {})
        if (m, pfad) == ("GET", "/v1/knoten"):
            return self._antwort(200, {"knoten": list(z.knoten.get(mail, {}).values())})
        return self._fehler(404, "unbekannt", f"No route {m} {pfad}")


class FalscheCloud:
    def __init__(self):
        self.zustand = Zustand()
        handler = type("H", (_Handler,), {"z": self.zustand})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.adresse = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.faden = threading.Thread(target=self.server.serve_forever, args=(0.05,), daemon=True)
        self.faden.start()

    def stopp(self):
        self.server.shutdown()
        self.server.server_close()
