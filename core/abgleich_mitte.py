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

import os
import subprocess

ZWEIG = "abgleich"


class MitteFehler(Exception):
    """Mitte nicht erreichbar oder kaputt — für Sasha lesbar."""


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


def oeffnen(art: str, adresse: str, klon: str):
    """Die Mitte nach Einstellung. Später: art 'http' = der PC als Server
    mit denselben vier Handgriffen als Routen."""
    if art == "git":
        return GitMitte(adresse, klon)
    raise MitteFehler(f"Eine Mitte der Art „{art}“ gibt es noch nicht (nur git).")
