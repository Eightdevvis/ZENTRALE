"""Eine gespielte ZENTRALE-Cloud für Tests und `zentrale dev`: http.server in einem Thread, die
Routen aus memory/hub/knoten_beitritt.md („Bauplan v1 — Schnittstelle"),
alles im Speicher. Nie das Netz, nie die echte Cloud.

Sie prüft, was der echte Server prüfen muss, so weit es den Client betrifft:
Code wird verbraucht (Groß/klein und Leerzeichen egal), anmelde_schluessel nur
als Hash, KDF mindestens 19456 KiB, Bearer-Sitzung, Notfall-Token nur für das
Passwort, altes_anmelde_schluessel beim Passwortwechsel, Knoten nur unter dem
eigenen Namen, Blobs nach sha256 (400 pruefsumme / blob_fehlt),
Compare-and-Swap auf den Kopf der Mitte (409 jemand_schneller),
GET /v1/nutzung nur für `betreiber` (sonst 403 nur_betreiber).
Build steps 7 and 8 (2026-10-30): `insecure` {version: {since, link, reason}}
→ `Deprecation`/`Link` on every answer to a client whose `Zentrale-Release` is
marked (never `Sunset`) and `insecure` on its device in GET /v1/knoten;
DELETE /v1/knoten/<name> turns that device's sessions into removed ones
(401 device_removed) and leaves a tombstone; PUT /v1/konto/schluessel swaps
wraps + Mitte head at once (409 when the head moved) and ends the others.
GET/PUT /v1/besitz (build step 10): one opaque ownership string per account.
Konten heißen nach Benutzernamen (anonym, keine Mail): '@' → 400, vergeben →
409 name_vergeben (der Code bleibt dann frei).
Stand: Absprache mit dem Server-Teil 2026-10-22, anonym seit 2026-10-23
(server/openapi.yaml).

Since 2026-10-30 it lives in devkit/ (was tests/_falsche_cloud.py) so the
developer installer mode (memory/hub/building_kit_plan.md 5.4) plays against
the very same fake as the tests. With `datei=` its state is a JSON file:
every request reloads and saves it under a file lock, so several dev commands
(and a running dev shell) share one cloud and a profile's account survives.
`paket` may be a callable returning (version, bytes) or None."""

import base64
import contextlib
import datetime
import fcntl
import hashlib
import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse


class Zustand:
    def __init__(self):
        self.codes = {"ZB-AAAA-BBBB-CCCC-DDDD", "ZB-EEEE-FFFF-GGGG-HHHH"}
        self.konten = {}            # name → dict
        self.sitzungen = {}         # token → (name, knoten | None); None = Notfall-Token
        self.blobs = {}             # sha256 → bytes
        self.kopf = {}              # name → kennung | None
        self.staende = {}           # kennung → {name: bytes}
        self.eltern = {}            # kennung → basis
        self.knoten = {}            # konto-name → {knoten-name: beschreibung}
        self.paket = None           # (version, bytes)
        self.betreiber = set()      # Namen, die GET /v1/nutzung sehen dürfen
        self.insecure = {}          # release version → {"since": ms, "link": url, "reason": text}
        self.removed = {}           # token of a removed device → (konto, knoten)
        self.besitz = {}            # konto-name → (opaque string, iso time) — GET/PUT /v1/besitz
        self.nutzung = {"zeit": "2026-10-23T09:00:00.000Z", "grenzen_geprueft": "2026-10-23",
                        "grenzen": [], "warnungen": []}
        self.aufrufe = []           # (methode, pfad) — zum Nachsehen in Tests
        self.datei = None           # JSON file of the state (zentrale dev), else memory only
        self.zaehler = 0
        self.sperre = threading.Lock()


# ── Persistence (only with FalscheCloud(datei=...)) ────────────────────
_PERSISTED = ("codes", "konten", "sitzungen", "blobs", "kopf", "staende", "eltern",
              "knoten", "betreiber", "nutzung", "zaehler", "insecure", "removed", "besitz")


def _encode(v):
    if isinstance(v, bytes):
        return {"__b64__": base64.b64encode(v).decode()}
    if isinstance(v, set):
        return {"__set__": sorted(v)}
    if isinstance(v, dict):
        return {k: _encode(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_encode(x) for x in v]
    return v


def _decode(v):
    if isinstance(v, dict):
        if set(v) == {"__b64__"}:
            return base64.b64decode(v["__b64__"])
        if set(v) == {"__set__"}:
            return set(v["__set__"])
        return {k: _decode(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_decode(x) for x in v]
    return v


def _load(z, datei):
    try:
        with open(datei, encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        return
    for name in _PERSISTED:
        if name in d:
            setattr(z, name, _decode(d[name]))
    z.sitzungen = {k: tuple(v) if isinstance(v, list) else v for k, v in z.sitzungen.items()}
    z.removed = {k: tuple(v) if isinstance(v, list) else v for k, v in z.removed.items()}


def _save(z, datei):
    tmp = datei + ".neu"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({name: _encode(getattr(z, name)) for name in _PERSISTED}, f)
    os.replace(tmp, datei)


@contextlib.contextmanager
def state_file(datei):
    """Edit a persisted fake cloud from outside (zentrale dev): lock, load,
    yield the Zustand, save. A running FalscheCloud on the same file sees it
    with its next request."""
    os.makedirs(os.path.dirname(datei) or ".", exist_ok=True)
    with open(datei + ".lock", "a") as sperre:
        fcntl.flock(sperre, fcntl.LOCK_EX)
        z = Zustand()
        _load(z, datei)
        yield z
        _save(z, datei)


def _code(c):
    return "".join(str(c or "").split()).upper()


def _name(d):
    return str(d.get("name") or "").strip().lower()


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
        i = self.z.insecure.get((self.headers.get("Zentrale-Release") or "").strip())
        if i:
            self.send_header("Deprecation", f"@{int(i['since']) // 1000}")
            self.send_header("Link", f'<{i["link"]}>; rel="deprecation"; type="text/html"')
        self.end_headers()
        self.wfile.write(body)

    def _fehler(self, status, code, text):
        self._antwort(status, {"fehler": code, "text": text})

    def _json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _sitzung(self):
        kopf = self.headers.get("Authorization", "")
        if kopf.startswith("Bearer "):
            return self.z.sitzungen.get(kopf[7:])
        return None

    def _konto(self):
        s = self._sitzung()
        return s[0] if s and s[1] is not None else None

    def _code_ok(self, abfrage):
        return _code((abfrage.get("code") or [""])[0]) in self.z.codes or self._konto()

    def _roh(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n)

    # ── Mitte stand + key change (shared by /v1/mitte/stand and /v1/konto/schluessel)
    def _stand_pruefen(self, konto, d):
        """→ None or (status, code, text)."""
        if d.get("basis") != self.z.kopf.get(konto):
            return 409, "jemand_schneller", "Someone else was faster."
        if any(s not in self.z.blobs for s in d.get("verweise", {}).values()):
            return 400, "blob_fehlt", "A referenced blob is missing."
        return None

    def _stand_setzen(self, konto, d):
        z = self.z
        neu = dict(z.staende.get(d.get("basis"), {}))
        for name, sha in d.get("verweise", {}).items():
            neu[name] = z.blobs[sha]
        for name, b64 in d.get("schreiben", {}).items():
            neu[name] = base64.b64decode(b64)
        for name in d.get("loeschen", []):
            neu.pop(name, None)
        z.zaehler += 1
        kennung = f"s{z.zaehler:04d}"
        z.staende[kennung], z.eltern[kennung] = neu, d.get("basis")
        z.kopf[konto] = kennung
        return kennung

    def _schluessel_wechseln(self, konto):
        """PUT /v1/konto/schluessel: current password, then stand + wraps at once."""
        z, d = self.z, self._json()
        k = z.konten[konto]
        if _hash(d.get("altes_anmelde_schluessel") or "") != k["hash"]:
            return self._fehler(401, "falsche_anmeldung", "The password is wrong.")
        if int(d["kdf"].get("m", 0)) < 19456:
            return self._fehler(400, "ungueltig", "Key derivation too weak.")
        fehler = self._stand_pruefen(konto, d.get("stand") or {})
        if fehler:
            return self._fehler(*fehler)
        kennung = self._stand_setzen(konto, d["stand"])
        k.update(salz=d["salz"], kdf=d["kdf"], hash=_hash(d["anmelde_schluessel"]),
                 verpackt_passwort=d["verpackt_passwort"], verpackt_notfall=d["verpackt_notfall"],
                 notfall_beweis=_hash(d["notfall_beweis"]))
        eigen = self.headers.get("Authorization", "")[7:]
        for t in [t for t, s in z.sitzungen.items() if s[0] == konto and t != eigen]:
            del z.sitzungen[t]
        return self._antwort(200, {"kennung": kennung})

    # ── Verteiler ──────────────────────────────────────────────────────
    def _gehen(self, methode):
        u = urlparse(self.path)
        pfad, abfrage = u.path, parse_qs(u.query)
        self.z.aufrufe.append((methode, pfad))
        with self.z.sperre, self._datei_sperre():
            try:
                self._route(methode, pfad, abfrage)
            except Exception as e:   # noqa: BLE001 — ein Testserver soll laut sagen, was los ist
                self._fehler(500, "kaputt", repr(e))

    @contextlib.contextmanager
    def _datei_sperre(self):
        datei = self.z.datei
        if not datei:
            yield
            return
        with open(datei + ".lock", "a") as sperre:
            fcntl.flock(sperre, fcntl.LOCK_EX)
            _load(self.z, datei)
            try:
                yield
            finally:
                _save(self.z, datei)

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
            name = _name(self._json())
            k = z.konten.get(name)
            if k:
                return self._antwort(200, {"salz": k["salz"], "kdf": k["kdf"]})
            erfunden = hashlib.sha256(b"fake" + name.encode()).digest()[:16]
            return self._antwort(200, {"salz": base64.urlsafe_b64encode(erfunden).rstrip(b"=").decode(),
                                       "kdf": {"name": "argon2id", "t": 1, "m": 19456, "p": 1}})
        if (m, pfad) == ("POST", "/v1/konto"):
            d = self._json()
            if _code(d.get("code")) not in z.codes:
                return self._fehler(403, "code_ungueltig", "This invite code is not valid.")
            if int(d["kdf"].get("m", 0)) < 19456:
                return self._fehler(400, "ungueltig", "Key derivation too weak.")
            name = _name(d)
            if "@" in name or "mail" in d:
                return self._fehler(400, "ungueltig", "No email needed.")
            if name in z.konten:
                return self._fehler(409, "name_vergeben", "This name is already taken.")
            z.codes.discard(_code(d["code"]))
            z.konten[name] = {"salz": d["salz"], "kdf": d["kdf"], "hash": _hash(d["anmelde_schluessel"]),
                              "verpackt_passwort": d["verpackt_passwort"],
                              "verpackt_notfall": d["verpackt_notfall"],
                              "notfall_beweis": _hash(d["notfall_beweis"])}
            z.kopf[name] = None
            return self._antwort(201, {"name": name})
        if (m, pfad) == ("POST", "/v1/sitzung"):
            d = self._json()
            k = z.konten.get(_name(d))
            if not k or k["hash"] != _hash(d["anmelde_schluessel"]):
                return self._fehler(401, "falsch", "Wrong name or password.")
            token = secrets.token_hex(16)
            z.sitzungen[token] = (_name(d), d.get("knoten") or "")
            return self._antwort(200, {"token": token, "laeuft_ab": "2099-01-01T00:00:00Z",
                                       "verpackt_passwort": k["verpackt_passwort"]})
        if self.headers.get("Authorization", "")[7:] in z.removed:
            return self._fehler(401, "device_removed",
                                "This device was removed from the account. Log in again to add it back.")
        if (m, pfad) == ("DELETE", "/v1/sitzung"):
            kopf = self.headers.get("Authorization", "")[7:]
            z.sitzungen.pop(kopf, None)
            return self._antwort(200, {})
        if (m, pfad) == ("POST", "/v1/notfall"):
            d = self._json()
            k = z.konten.get(_name(d))
            if not k or k["notfall_beweis"] != _hash(d["notfall_beweis"]):
                return self._fehler(403, "falsch", "Wrong emergency key.")
            token = secrets.token_hex(16)
            z.sitzungen[token] = (_name(d), None)                # nur fürs Passwort
            return self._antwort(200, {"verpackt_notfall": k["verpackt_notfall"], "token": token,
                                       "laeuft_ab": "2099-01-01T00:00:00Z"})
        paket = z.paket() if callable(z.paket) else z.paket
        if (m, pfad) == ("GET", "/v1/paket"):
            if not self._code_ok(abfrage) or not paket:
                return self._fehler(403, "code_ungueltig", "Invite code or login needed.")
            v, daten = paket
            return self._antwort(200, {"version": v, "sha256": hashlib.sha256(daten).hexdigest(),
                                       "groesse": len(daten)})
        if m == "GET" and pfad.startswith("/v1/paket/"):
            if not self._code_ok(abfrage) or not paket:
                return self._fehler(403, "code_ungueltig", "Invite code or login needed.")
            return self._antwort(200, roh=paket[1])

        sitzung = self._sitzung()
        if sitzung is None:
            return self._fehler(401, "nicht_angemeldet", "Not logged in.")
        if (m, pfad) == ("PUT", "/v1/konto/passwort"):
            d = self._json()
            k = z.konten[sitzung[0]]
            if sitzung[1] is not None and _hash(d.get("altes_anmelde_schluessel") or "") != k["hash"]:
                return self._fehler(403, "falsche_anmeldung", "The current password is wrong.")
            if int(d["kdf"].get("m", 0)) < 19456:
                return self._fehler(400, "ungueltig", "Key derivation too weak.")
            k.update(salz=d["salz"], kdf=d["kdf"], hash=_hash(d["anmelde_schluessel"]),
                     verpackt_passwort=d["verpackt_passwort"])
            eigen = self.headers.get("Authorization", "")[7:]
            for t in [t for t, s in z.sitzungen.items() if s[0] == sitzung[0] and t != eigen
                      or (t == eigen and s[1] is None)]:
                del z.sitzungen[t]          # alle anderen Sitzungen enden, Notfall-Token auch
            return self._antwort(200, {})
        konto = self._konto()
        if konto is None:
            return self._fehler(403, "nur_passwort", "This session may only set a new password.")
        if (m, pfad) == ("PUT", "/v1/konto/schluessel"):
            return self._schluessel_wechseln(konto)
        if (m, pfad) == ("GET", "/v1/nutzung"):
            if konto not in z.betreiber:
                return self._fehler(403, "nur_betreiber", "Usage figures are only for the operator of this cloud.")
            return self._antwort(200, z.nutzung)
        if (m, pfad) == ("GET", "/v1/mitte"):
            kopf = z.kopf.get(konto)
            return self._antwort(200, {"kennung": kopf,
                                       "namen": sorted(z.staende.get(kopf, {})) if kopf else []})
        if m == "GET" and pfad.startswith("/v1/mitte/datei/"):
            name = unquote(pfad[len("/v1/mitte/datei/"):])
            stand = z.staende.get(z.kopf.get(konto), {})
            if name not in stand:
                return self._fehler(404, "fehlt", "No such file.")
            return self._antwort(200, roh=stand[name])
        if (m, pfad) == ("POST", "/v1/mitte/fehlende"):
            return self._antwort(200, {"fehlen": [s for s in self._json().get("sha256", [])
                                                  if s not in z.blobs]})
        if m == "PUT" and pfad.startswith("/v1/mitte/blob/"):
            sha, daten = pfad.rsplit("/", 1)[1], self._roh()
            if hashlib.sha256(daten).hexdigest() != sha:
                return self._fehler(400, "pruefsumme", "Checksum mismatch.")
            z.blobs[sha] = daten
            return self._antwort(200, {})
        if (m, pfad) == ("POST", "/v1/mitte/stand"):
            d = self._json()
            fehler = self._stand_pruefen(konto, d)
            if fehler:
                return self._fehler(*fehler)
            return self._antwort(200, {"kennung": self._stand_setzen(konto, d)})
        if m == "GET" and pfad.startswith("/v1/mitte/enthaelt/"):
            gesucht, k = unquote(pfad.rsplit("/", 1)[1]), z.kopf.get(konto)
            while k is not None and k != gesucht:
                k = z.eltern.get(k)
            return self._antwort(200, {"enthaelt": k is not None})
        if m == "PUT" and pfad.startswith("/v1/knoten/"):
            name = unquote(pfad.rsplit("/", 1)[1])
            if name != sitzung[1]:
                return self._fehler(403, "fremder_knoten", "You can only describe your own device.")
            z.knoten.setdefault(konto, {})[name] = self._json()
            return self._antwort(200, {})
        if (m, pfad) == ("GET", "/v1/knoten"):
            liste = []
            for b in z.knoten.get(konto, {}).values():
                b = {k: v for k, v in b.items() if k != "insecure"}
                i = z.insecure.get(str(b.get("programm")))
                if i:
                    since = datetime.datetime.fromtimestamp(int(i["since"]) / 1000, datetime.timezone.utc)
                    b["insecure"] = {"since": since.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                                     "link": i["link"], "reason": i.get("reason", "")}
                liste.append(b)
            return self._antwort(200, {"knoten": liste})
        if m == "DELETE" and pfad.startswith("/v1/knoten/"):
            name = unquote(pfad.rsplit("/", 1)[1])
            tokens = [t for t, s in z.sitzungen.items() if s[0] == konto and s[1] == name]
            alt = z.knoten.get(konto, {}).get(name)
            if alt is None and not tokens:
                return self._fehler(404, "unknown_device", "There is no device with this name on your account.")
            for t in tokens:
                z.removed[t] = z.sitzungen.pop(t)
            removed = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
            z.knoten.setdefault(konto, {})[name] = dict(alt or {}, name=name, removed=removed,
                                                         removed_by=sitzung[1])
            return self._antwort(200, {"name": name, "removed": removed, "sessions_ended": len(tokens)})
        if (m, pfad) == ("GET", "/v1/besitz"):
            b = z.besitz.get(konto)
            return self._antwort(200, {"besitz": b[0] if b else None, "aktualisiert": b[1] if b else None})
        if (m, pfad) == ("PUT", "/v1/besitz"):
            d = self._json()
            if not isinstance(d.get("besitz"), str) or not d["besitz"]:
                return self._fehler(400, "ungueltig", "'besitz' must be a non-empty string.")
            jetzt = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")
            z.besitz[konto] = (d["besitz"], jetzt)
            return self._antwort(200, {"aktualisiert": jetzt})
        return self._fehler(404, "unbekannt", f"No route {m} {pfad}")


class FalscheCloud:
    def __init__(self, datei=None, port=0):
        self.zustand = Zustand()
        self.zustand.datei = datei
        if datei:
            with state_file(datei) as z:
                for name in _PERSISTED:
                    setattr(self.zustand, name, getattr(z, name))
        handler = type("H", (_Handler,), {"z": self.zustand})
        self.server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        self.adresse = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.faden = threading.Thread(target=self.server.serve_forever, args=(0.05,), daemon=True)
        self.faden.start()

    def stopp(self):
        self.server.shutdown()
        self.server.server_close()
