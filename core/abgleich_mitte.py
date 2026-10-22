# core/abgleich_mitte.py
#
# Die Mitte, gegen die jeder Rechner abgleicht (memory/betrieb/abgleich.md).
# Der Abgleich kennt sie nur über vier Handgriffe — holen, vorbereiten,
# senden, enthaelt —, damit sie austauschbar ist: heute ein git-Repo
# (GitHub, privat), später der PC als Server (HTTP). Sasha, 2026-10-08:
# „später wenn der pc mit netzwerk ready ist, die cloud mit ihm auszutauschen".
#
# Die Mitte sieht nur, was ihr gegeben wird: verschlüsselte Bytes unter
# versteckten Namen. Verschlüsseln ist Sache von core/abgleich.py.
#
# Seit 2026-10-22 zwei Arten: `git` (GitHub, Sashas Weg bis heute) und
# `http` (die ZENTRALE-Cloud, memory/hub/knoten_beitritt.md „Bauplan v1").

import hashlib
import os
import subprocess
import urllib.parse

import cloud_api

ZWEIG = "abgleich"


class MitteFehler(Exception):
    """Mitte nicht erreichbar oder kaputt — für Sasha lesbar."""


class MitteBewegt(MitteFehler):
    """Die Mitte hat sich mitten im Lesen geändert (nur HttpMitte: die Dateien
    werden einzeln geholt). Der Abgleich holt dann einfach neu."""


class GitMitte:
    """Die Mitte als git-Repo. Ein eigener Klon unter `klon` dient nur als
    Zwischenlager; die Wahrheit ist der Zweig `abgleich` im entfernten Repo.

    „Nur senden, wenn die Mitte noch auf meinem Stand ist" erledigt git
    selbst: ein normaler Push wird abgelehnt, wenn jemand dazwischen
    gesendet hat. Nie --force — das würde den Stand des anderen löschen."""

    def __init__(self, adresse: str, klon: str, zweig: str = ZWEIG):
        self.adresse, self.klon, self.zweig = adresse, klon, zweig

    def _git(self, *args, check=True, zeit=120):
        umgebung = dict(os.environ, GIT_TERMINAL_PROMPT="0",
                        GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=15")
        try:
            r = subprocess.run(
                ["git", "-c", "user.name=ZENTRALE", "-c", "user.email=zentrale@localhost",
                 "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
                cwd=self.klon, capture_output=True, text=True, timeout=zeit, env=umgebung)
        except subprocess.TimeoutExpired:
            raise MitteFehler("Die Mitte antwortet nicht (Zeit abgelaufen).") from None
        if check and r.returncode != 0:
            raise MitteFehler(f"git {args[0]}: {(r.stderr or r.stdout).strip()[:300]}")
        return r

    def _bereit(self):
        if not os.path.isdir(os.path.join(self.klon, ".git")):
            os.makedirs(self.klon, exist_ok=True)
            self._git("init", "-q")
            self._git("remote", "add", "origin", self.adresse)
        else:
            self._git("remote", "set-url", "origin", self.adresse)

    def _entfernt(self):
        """Kennung des Zweigs in der Mitte, oder None (Mitte noch leer)."""
        r = self._git("ls-remote", "--heads", "origin", self.zweig, check=False, zeit=60)
        if r.returncode != 0:
            raise MitteFehler("Die Mitte ist nicht erreichbar: "
                              + (r.stderr.strip().splitlines() or ["?"])[-1][:200])
        zeile = r.stdout.strip().split()
        return zeile[0] if zeile else None

    def holen(self):
        """→ (kennung oder None, lesen(name) -> bytes|None, namen)."""
        self._bereit()
        stand = self._entfernt()
        if stand is None:
            # Leere Mitte: auf einen Zweig ohne Vorgeschichte stellen (auch
            # wenn ein früherer, nie gesendeter Versuch dort etwas hinterließ).
            self._git("symbolic-ref", "HEAD", "refs/heads/_leer")
            self._git("update-ref", "-d", "refs/heads/_leer", check=False)
            self._git("rm", "-rqf", "--cached", "--ignore-unmatch", ".", check=False)
            self._leeren()
            return None, (lambda name: None), []
        self._git("fetch", "-q", "origin", self.zweig)
        self._git("checkout", "-q", "-f", "-B", self.zweig, "FETCH_HEAD")
        self._git("clean", "-qfdx")

        def lesen(name):
            try:
                with open(os.path.join(self.klon, name), "rb") as f:
                    return f.read()
            except FileNotFoundError:
                return None
        namen = self._git("ls-files").stdout.split()
        return stand, lesen, namen

    def _leeren(self):
        for eintrag in os.listdir(self.klon):
            if eintrag == ".git":
                continue
            p = os.path.join(self.klon, eintrag)
            if os.path.isdir(p):
                import shutil
                shutil.rmtree(p)
            else:
                os.remove(p)

    def vorbereiten(self, schreiben: dict, loeschen, nachricht: str) -> str:
        """Den neuen Stand im Klon bauen (auf dem zuletzt geholten). → Kennung.
        Noch nicht gesendet."""
        for name, inhalt in schreiben.items():
            p = os.path.join(self.klon, name)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(inhalt)
        for name in loeschen:
            try:
                os.remove(os.path.join(self.klon, name))
            except FileNotFoundError:
                pass
        self._git("add", "-A")
        self._git("commit", "-q", "--allow-empty", "-m", nachricht)
        return self._git("rev-parse", "HEAD").stdout.strip()

    def senden(self, kennung: str) -> bool:
        """In die Mitte stellen. False = jemand war schneller (neu holen)."""
        r = self._git("push", "-q", "origin", f"{kennung}:refs/heads/{self.zweig}",
                      check=False)
        if r.returncode == 0:
            return True
        text = (r.stderr or "").lower()
        if "rejected" in text or "non-fast-forward" in text or "fetch first" in text:
            return False
        raise MitteFehler("Senden an die Mitte ging nicht: " + r.stderr.strip()[:200])

    def enthaelt(self, kennung: str) -> bool:
        """Ist dieser Stand in der Mitte angekommen?"""
        self._bereit()
        if self._entfernt() is None:
            return False
        self._git("fetch", "-q", "origin", self.zweig)
        r = self._git("merge-base", "--is-ancestor", kennung, "FETCH_HEAD", check=False)
        return r.returncode == 0


VORLAEUFIG = "vorlaeufig-"


class HttpMitte:
    """Die Mitte als HTTP-Dienst (die ZENTRALE-Cloud). Dieselben vier
    Handgriffe, als Routen:

        holen       GET  /v1/mitte  (+ GET /v1/mitte/datei/<name> je Datei, erst bei Bedarf)
        vorbereiten nur im Speicher; → vorläufige Kennung
        senden      POST /v1/mitte/fehlende → PUT /v1/mitte/blob/<sha256> (nur was fehlt)
                    → POST /v1/mitte/stand {basis, verweise, loeschen} → True, 409 → False
        enthaelt    GET  /v1/mitte/enthaelt/<kennung>

    „Nur senden, wenn die Mitte noch auf meinem Stand ist" macht der Server
    (Compare-and-Swap auf den Kopf). Die echte Kennung kennt erst der Server;
    `vorbereiten` gibt eine vorläufige zurück: „vorlaeufig-" + Prüfwert des
    vorbereiteten inhalt.enc. Fernet würfelt jedes Mal neu, also steht genau
    dieses inhalt.enc nur dann in der Mitte, wenn WIR es gesendet haben — so
    beantwortet `enthaelt` auch nach einem Absturz die vorläufige Kennung.
    Nach dem Senden liefert `echte_kennung` die des Servers."""

    INHALT = "inhalt.enc"

    def __init__(self, client):
        self.client = client
        self._basis = None
        self._vorrat = {}          # vorläufige Kennung → (schreiben, loeschen)
        self._echt = {}            # vorläufige Kennung → Kennung des Servers

    def _rufen(self, fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except cloud_api.CloudFehler as e:
            raise MitteFehler(str(e)) from None

    def _datei(self, name):
        try:
            return self.client.bytes_holen("/v1/mitte/datei/" + urllib.parse.quote(name, safe="/"))
        except cloud_api.CloudFehler as e:
            if e.status == 404:
                return None
            raise MitteFehler(str(e)) from None

    def holen(self):
        """→ (kennung oder None, lesen(name) -> bytes|None, namen)."""
        d = self._rufen(self.client.get, "/v1/mitte")
        self._basis = d.get("kennung")
        namen = list(d.get("namen") or [])
        if self._basis is None:
            return None, (lambda name: None), []
        vorhanden, zwischen, stand = set(namen), {}, self._basis

        def lesen(name):
            # Die Dateien kommen einzeln und immer aus dem AKTUELLEN Stand.
            # Fehlt eine, die das (womöglich neuere) Inhaltsverzeichnis nennt,
            # ist die Mitte weitergelaufen → MitteBewegt, der Abgleich holt neu.
            # Liest er sonst gemischt, scheitert sein Senden ohnehin am
            # Compare-and-Swap (409) und er holt ebenso neu.
            if name not in zwischen:
                zwischen[name] = self._datei(name) if name in vorhanden else None
                if zwischen[name] is None and self._rufen(
                        self.client.get, "/v1/mitte").get("kennung") != stand:
                    raise MitteBewegt("The data in the cloud changed while reading — retrying.")
            return zwischen[name]
        return self._basis, lesen, namen

    def vorbereiten(self, schreiben: dict, loeschen, nachricht: str = "") -> str:
        """Den neuen Stand nur merken (gesendet wird alles in EINEM Aufruf).
        `nachricht` braucht der Server nicht."""
        inhalt = schreiben.get(self.INHALT, b"")
        kennung = VORLAEUFIG + hashlib.sha256(inhalt).hexdigest()[:32]
        self._vorrat[kennung] = (dict(schreiben), list(loeschen))
        return kennung

    MAX_BLOB = 24 * 1024 * 1024

    def _hochladen(self, inhalte: dict):
        """Was der Server noch nicht hat, als Blob hochladen
        (POST /v1/mitte/fehlende → PUT /v1/mitte/blob/<sha256>)."""
        d = self._rufen(self.client.post, "/v1/mitte/fehlende", {"sha256": sorted(inhalte)})
        for sha in d.get("fehlen") or []:
            if sha not in inhalte:
                continue
            self._rufen(self.client.bytes_senden, "/v1/mitte/blob/" + sha, inhalte[sha])

    def senden(self, kennung: str) -> bool:
        """In die Mitte stellen. False = jemand war schneller (neu holen).

        Die Dateien gehen einzeln als Blob nach Prüfsumme hoch (nur, was dem
        Server fehlt); der neue Stand ist dann nur eine Liste von Verweisen
        Name → sha256 — so bleibt jede Anfrage klein, auch bei der ersten
        Befüllung."""
        schreiben, loeschen = self._vorrat[kennung]
        inhalte, verweise = {}, {}
        for name, b in schreiben.items():
            if len(b) > self.MAX_BLOB:
                raise MitteFehler(f"A file is too large for the cloud ({len(b) // 2**20} MiB, "
                                  f"at most {self.MAX_BLOB // 2**20} MiB).")
            sha = hashlib.sha256(b).hexdigest()
            inhalte[sha], verweise[name] = b, sha
        daten = {"basis": self._basis, "verweise": verweise, "loeschen": list(loeschen)}
        for versuch in range(2):
            self._hochladen(inhalte)
            try:
                d = self.client.post("/v1/mitte/stand", daten)
                break
            except cloud_api.CloudFehler as e:
                if e.status == 409:
                    return False
                if e.code == "blob_fehlt" and versuch == 0:
                    continue          # zwischen Hochladen und Stand verschwunden: nochmal
                raise MitteFehler("Sending to the cloud failed: " + str(e)) from None
        echt = d.get("kennung")
        if not echt:
            raise MitteFehler("The cloud accepted the data but sent no version id.")
        self._echt[kennung] = echt
        self._basis = echt
        del self._vorrat[kennung]
        return True

    def echte_kennung(self, kennung: str) -> str:
        return self._echt.get(kennung, kennung)

    def enthaelt(self, kennung: str) -> bool:
        """Ist dieser Stand in der Mitte angekommen?"""
        kennung = self.echte_kennung(kennung)
        if kennung.startswith(VORLAEUFIG):
            d = self._rufen(self.client.get, "/v1/mitte")
            if d.get("kennung") is None or self.INHALT not in (d.get("namen") or []):
                return False
            inhalt = self._datei(self.INHALT) or b""
            if VORLAEUFIG + hashlib.sha256(inhalt).hexdigest()[:32] != kennung:
                return False
            self._echt[kennung] = d["kennung"]
            return True
        d = self._rufen(self.client.get, "/v1/mitte/enthaelt/" + urllib.parse.quote(kennung, safe=""))
        return bool(d.get("enthaelt"))


def oeffnen(art: str, adresse: str, klon: str, token: str = None):
    """Die Mitte nach Einstellung: 'git' (adresse = Repo, klon = Zwischenlager)
    oder 'http' (adresse = die Cloud, token = Sitzung des Kontos)."""
    if art == "git":
        return GitMitte(adresse, klon)
    if art == "http":
        return HttpMitte(cloud_api.Client(adresse, token=token))
    raise MitteFehler(f"Eine Mitte der Art „{art}“ gibt es nicht (nur git oder http).")
