# core/cloud_api.py
#
# Der Draht zur ZENTRALE-Cloud (Cloudflare Workers, memory/hub/knoten_beitritt.md
# „Bauplan v1 — Schnittstelle"). Nur stdlib (urllib), keine neue Abhängigkeit,
# kein Terminal: Fehler kommen als CloudFehler mit einem englischen Satz, den
# jede Oberfläche so zeigen kann.
#
# Adresse: Env ZENTRALE_CLOUD > Einstellung `cloud` > VORGABE (eine Stelle).

import json
import urllib.error
import urllib.parse
import urllib.request

import ai_config

# Die eine Stelle für die Adresse der Cloud (Sasha trägt die echte ein).
VORGABE = "https://zentrale-cloud.sevendevs.workers.dev"
ZEIT = 30


class CloudFehler(Exception):
    """Ein Fehler der Cloud oder des Netzes. `code` = der Fehler-Code des
    Servers ("jemand_schneller", "falsches_passwort" …) oder "netz"; `status`
    = HTTP-Status (0 = gar keine Antwort)."""

    def __init__(self, text, code="", status=0):
        super().__init__(text)
        self.code, self.status = code, status


def adresse() -> str:
    return str(ai_config.setting("cloud") or VORGABE).rstrip("/")


_TEXTE = {
    401: "You are not logged in (or the session has expired). Run 'zentrale login'.",
    403: "The server refused this request.",
    404: "Not found on the server.",
    409: "Someone else changed the data first.",
    429: "Too many attempts. Please wait a few minutes and try again.",
}


class Client:
    """Ein Aufruf = eine Methode. `token` = Sitzung (Bearer) oder None."""

    def __init__(self, basis: str = None, token: str = None, zeit: float = ZEIT):
        self.basis = (basis or adresse()).rstrip("/")
        self.token, self.zeit = token, zeit

    def roh(self, methode, pfad, daten=None, abfrage=None, roh_body=None,
            erwartet_bytes=False):
        url = self.basis + pfad
        if abfrage:
            url += "?" + urllib.parse.urlencode(abfrage)
        kopf = {"Accept": "application/json", "User-Agent": "zentrale-hub"}
        body = None
        if daten is not None:
            body = json.dumps(daten).encode("utf-8")
            kopf["Content-Type"] = "application/json"
        elif roh_body is not None:
            body = roh_body
            kopf["Content-Type"] = "application/octet-stream"
        if self.token:
            kopf["Authorization"] = "Bearer " + self.token
        anfrage = urllib.request.Request(url, data=body, method=methode, headers=kopf)
        try:
            with urllib.request.urlopen(anfrage, timeout=self.zeit) as r:
                inhalt = r.read()
                status = r.status
        except urllib.error.HTTPError as e:
            raise self._fehler(e.code, e.read()) from None
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            grund = getattr(e, "reason", e)
            raise CloudFehler(f"Cannot reach the ZENTRALE cloud at {self.basis} ({grund}).",
                              "netz", 0) from None
        if erwartet_bytes:
            return status, inhalt
        if not inhalt:
            return status, {}
        try:
            return status, json.loads(inhalt)
        except ValueError:
            raise CloudFehler("The cloud sent an unreadable answer.", "antwort", status) from None

    def _fehler(self, status, inhalt):
        code, text = "", ""
        try:
            d = json.loads(inhalt or b"{}")
            code, text = str(d.get("fehler") or ""), str(d.get("text") or "")
        except (ValueError, AttributeError):
            pass
        return CloudFehler(text or _TEXTE.get(status) or f"The cloud answered with error {status}.",
                           code, status)

    def get(self, pfad, **kw):
        return self.roh("GET", pfad, **kw)[1]

    def post(self, pfad, daten, **kw):
        return self.roh("POST", pfad, daten=daten, **kw)[1]

    def put(self, pfad, daten, **kw):
        return self.roh("PUT", pfad, daten=daten, **kw)[1]

    def delete(self, pfad, **kw):
        return self.roh("DELETE", pfad, **kw)[1]

    def bytes_senden(self, pfad, daten: bytes):
        """PUT mit rohen Bytes (application/octet-stream)."""
        return self.roh("PUT", pfad, roh_body=daten)[1]

    def bytes_holen(self, pfad, abfrage=None):
        return self.roh("GET", pfad, abfrage=abfrage, erwartet_bytes=True)[1]
