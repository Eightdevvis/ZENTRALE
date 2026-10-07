# core/sandbox.py
#
# Code ausführen, abgeschottet. Die KI schreibt ein kleines Programm (Python
# oder Shell), und es läuft hier in einer Sandbox: eigener Arbeitsordner, kein
# Netz, kein Blick auf Sashas Dateien, Zeit- und Speichergrenze.
#
# 2026-10-07, Phase 7 des Claude-Web-Plans (memory/ki/claude_web_plan.md).
# Sasha: „die idee is, dass assistant später einfach mein coder wird … dafür
# muss sie stuff in sandbox machen können". Jetzt nur das Fundament.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md). Weiß nichts von der KI;
# das Werkzeug run_code (core/ki_werkzeuge.py) ruft ausfuehren().
#
# ── Wie abgeschottet wird ──────────────────────────────────────────────
# bubblewrap (bwrap), unprivilegiert über Benutzer-Namensräume. Das Programm
# sieht ein eigenes, fast leeres Dateisystem:
#   /usr (+ /bin /lib /lib64 /sbin als Verweise)   nur lesen
#   /proc, /dev                                   eigene, minimale
#   /tmp                                          leer, im Speicher
#   /arbeit                                       der Arbeitsordner, der
#                                                 EINZIGE beschreibbare Ort
#   /eingabe/programm.*                           das Programm, nur lesen
# Nicht da: /home (also weder das Repo noch data/ noch ~/.ssh), /etc, /root,
# /var, /run, /mnt, /media. --unshare-all nimmt das Netz (nur ein eigenes
# loopback), die Prozess-Liste und den Rechnernamen. Die Umgebung ist leer bis
# auf PATH/HOME/LANG — keine API-Keys aus os.environ.
#
# NIE ohne Sandbox: fehlt bwrap oder startet es nicht, kommt eine Fehlermeldung
# zurück, und das Programm läuft gar nicht. Einen Rückfall auf „dann eben
# direkt" gibt es absichtlich nicht.
#
# ── Wo der Arbeitsordner liegt (Entscheidung 2026-10-07) ───────────────
# ~/.cache/zentrale/sandbox/<lauf-id>/, NICHT data/sandbox/. Grund: zentrale-
# sync spiegelt alle ungetrackten Dateien unter dem Repo (auch ignorierte, also
# auch data/), additiv und ohne Löschen. Was die KI in der Sandbox erzeugt,
# wanderte sonst auf den anderen Rechner, Aufräumen dort käme nie an, und ein
# Programm, das einen Verweis (Symlink) anlegt, legte ihn mitten ins Repo.
# Außerhalb des Repos ist der Ordner nie Teil von Sync, Git oder Daten.
# Umlenkbar per Einstellung sandbox_dir (Env ZENTRALE_SANDBOX_DIR; Tests).

import json
import os
import resource
import secrets
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time

import ai_config


# Grenzen. Bewusst knapp: rechnen, Daten umformen, kleine Skripte — nicht
# kompilieren oder Modelle trainieren (Entscheidungen 2026-10-07, Bericht).
ZEITLIMIT_STANDARD_S = 30
# Bis hierhin reicht das normale Ja (auch „immer"/„für dieses Gespräch").
# Länger nur nach eigener Rückfrage mit der Dauer im Text, die NUR „einmal"
# anbietet (Sasha 2026-10-07: „wenn die ai mich anfragen kann für mehr zeit
# und ich es per hand dann bestätige"; Regel im Werkzeug-Register).
ZEITLIMIT_OHNE_FRAGE_S = 120
ZEITLIMIT_MAX_S = 30 * 60
SPEICHER_BYTES = 512 * 1024 * 1024      # Adressraum je Prozess
PROZESSE_MAX = 64                        # gegen Fork-Bomben
DATEI_MAX_BYTES = 50 * 1024 * 1024       # größte einzelne Datei
AUSGABE_MAX_ZEICHEN = 20_000             # je Strom, Kopf + Schwanz
DATEIEN_LISTE_MAX = 50                   # so viele neue Dateien melden
TMP_BYTES = 64 * 1024 * 1024             # /tmp liegt im Arbeitsspeicher
AUFBEWAHREN_TAGE = 7

SPRACHEN = {
    # -I: isoliert (kein PYTHON*-Env, kein User-site), -B: keine .pyc in /arbeit
    "python": ("programm.py", ["/usr/bin/python3", "-I", "-B"]),
    "shell":  ("programm.sh", ["/usr/bin/bash", "--noprofile", "--norc"]),
}

_BWRAP = "/usr/bin/bwrap"
SKILL_ZIEL = "/skills"    # darunter <name>/, wie bei Claude /mnt/skills/…


def _bwrap_pfad() -> str | None:
    """Wo bwrap liegt — oder None. Eigene Funktion, damit ein Test „fehlt"
    vorspielen kann."""
    if os.access(_BWRAP, os.X_OK):
        return _BWRAP
    return shutil.which("bwrap")


def basis_ordner() -> str:
    eigen = ai_config.setting("sandbox_dir")
    if eigen:
        return os.path.abspath(os.path.expanduser(str(eigen)))
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(cache, "zentrale", "sandbox")


# ── Sandbox bauen ──────────────────────────────────────────────────────

def _wurzel_argumente() -> list:
    """Das System, nur lesend. /bin & Co. sind auf merged-usr-Systemen
    Verweise nach /usr; auf älteren (Pi?) echte Ordner — dann nur lesend
    einhängen."""
    args = ["--ro-bind", "/usr", "/usr"]
    for name in ("bin", "sbin", "lib", "lib64", "lib32"):
        pfad = "/" + name
        if os.path.islink(pfad):
            args += ["--symlink", os.readlink(pfad), pfad]
        elif os.path.isdir(pfad):
            args += ["--ro-bind", pfad, pfad]
    # Zeitzone: sonst rechnet ein Programm in UTC. Nur die eine Datei.
    zone = os.path.realpath("/etc/localtime")
    if os.path.isfile(zone):
        args += ["--ro-bind", zone, "/etc/localtime"]
    return args


_kann_size: dict = {}


def _tmp_argumente(bwrap: str) -> list:
    """/tmp mit Größengrenze, wenn bwrap das kann (--size gibt es erst ab
    0.9; Raspberry Pi OS bookworm hat 0.8). Ohne: /tmp ohne eigene Grenze —
    einzelne Dateien deckelt trotzdem RLIMIT_FSIZE."""
    if bwrap not in _kann_size:
        try:
            hilfe = subprocess.run([bwrap, "--help"], capture_output=True,
                                   text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            hilfe = ""
        _kann_size[bwrap] = "--size" in hilfe
    if _kann_size[bwrap]:
        return ["--size", str(TMP_BYTES), "--tmpfs", "/tmp"]
    return ["--tmpfs", "/tmp"]


def skill_pfad(skill_ordner: str) -> str:
    """Wo ein Skill-Ordner in der Sandbox liegt: /skills/<name>. Der Name
    bleibt, damit Skripte wie package_skill.py ihn richtig benennen."""
    return SKILL_ZIEL + "/" + os.path.basename(os.path.normpath(skill_ordner))


def _bwrap_befehl(bwrap: str, arbeit: str, programm: str, sprache: str,
                  status_fd: int, skill_ordner: str | None = None) -> list:
    datei, aufruf = SPRACHEN[sprache]
    # Ein Skill-Ordner (scripts/, references/ …) nur lesend unter
    # /skills/<name> —
    # die eine Ausnahme vom „nichts von Sasha" (2026-10-07): ohne sie liefen
    # Skill-Skripte nur, wenn das Modell sie abtippt. Nur DIESER Ordner,
    # nichts daneben; schreiben geht weiter nur nach /arbeit.
    skill = (["--ro-bind", skill_ordner, skill_pfad(skill_ordner)]
             if skill_ordner else [])
    return [
        bwrap,
        "--unshare-all", "--die-with-parent", "--new-session",
        "--unshare-user", "--disable-userns",
        *_wurzel_argumente(),
        "--proc", "/proc", "--dev", "/dev",
        *_tmp_argumente(bwrap),
        "--bind", arbeit, "/arbeit",
        "--ro-bind", programm, "/eingabe/" + datei,
        *skill,
        # Die Wurzel selbst ist ein Speicher-Dateisystem von bwrap; ohne das
        # hier könnte ein Programm dort beliebig viel ablegen (RAM).
        "--remount-ro", "/",
        "--chdir", "/arbeit",
        "--hostname", "sandbox",
        "--clearenv",
        "--setenv", "PATH", "/usr/local/bin:/usr/bin:/bin",
        "--setenv", "HOME", "/arbeit",
        "--setenv", "LANG", "C.UTF-8",
        "--json-status-fd", str(status_fd),
        "/usr/bin/python3", "-I", "-S", "-c", _PROZESS_GRENZE,
        *aufruf, "/eingabe/" + datei,
    ]


# Die Prozess-Grenze wird ERST IN der Sandbox gesetzt (2026-10-07, gemessen):
# RLIMIT_NPROC zählt alle Prozesse des Benutzers. Vor bwrap gesetzt, scheitert
# schon das Anlegen der Namensräume („Resource temporarily unavailable"),
# weil Sasha selbst mehr als 64 Prozesse hat. Hinter dem eigenen Benutzer-
# Namensraum zählen nur noch die Prozesse der Sandbox.
_PROZESS_GRENZE = (
    "import os,resource,sys;"
    f"resource.setrlimit(resource.RLIMIT_NPROC,({PROZESSE_MAX},{PROZESSE_MAX}));"
    "os.execv(sys.argv[1],sys.argv[1:])"
)


def _grenzen_setzen():
    """Läuft im Kindprozess vor bwrap (preexec). Die Grenzen erbt alles darin.
    Die Prozess-Zahl steht NICHT hier, siehe _PROZESS_GRENZE. RLIMIT_CPU ist
    der Rückhalt, falls das Zeitlimit-Töten versagt."""
    def setze(art, wert):
        try:
            resource.setrlimit(art, (wert, wert))
        except (ValueError, OSError):
            pass
    setze(resource.RLIMIT_AS, SPEICHER_BYTES)
    setze(resource.RLIMIT_FSIZE, DATEI_MAX_BYTES)
    setze(resource.RLIMIT_CORE, 0)
    setze(resource.RLIMIT_CPU, ZEITLIMIT_MAX_S + 5)
    try:
        os.nice(10)              # das Dashboard bleibt flüssig
    except OSError:
        pass


# ── Ausgabe mitlesen, gekappt ──────────────────────────────────────────

class _Kappe:
    """Liest einen Strom bis zum Ende, behält Kopf und Schwanz. Ein Programm,
    das in 30 s Gigabytes ausgibt, darf den Speicher des Backends nicht
    füllen — also wird beim Lesen gekappt, nicht danach."""

    def __init__(self, strom, grenze: int):
        self.strom, self.haelfte = strom, grenze // 2
        self.kopf = bytearray()
        self.schwanz = bytearray()
        self.gesamt = 0
        self.faden = threading.Thread(target=self._lesen, daemon=True)
        self.faden.start()

    def _lesen(self):
        # Bytes, nicht Zeichen: grob genug, und UTF-8 wird am Ende geheilt.
        grenze = self.haelfte * 4
        while True:
            stueck = self.strom.read1(65536) if hasattr(self.strom, "read1") \
                else self.strom.read(65536)
            if not stueck:
                break
            self.gesamt += len(stueck)
            platz = grenze - len(self.kopf)
            if platz > 0:
                self.kopf += stueck[:platz]
                stueck = stueck[platz:]
            if stueck:
                self.schwanz += stueck
                if len(self.schwanz) > grenze:
                    del self.schwanz[:len(self.schwanz) - grenze]

    def text(self) -> str:
        self.faden.join(timeout=5)
        kopf = self.kopf.decode("utf-8", "replace")
        if not self.schwanz:
            ganz = kopf
            if len(ganz) <= self.haelfte * 2:
                return ganz
            return (ganz[:self.haelfte] + "\n[… gekürzt …]\n"
                    + ganz[-self.haelfte:])
        schwanz = self.schwanz.decode("utf-8", "replace")
        return (kopf[:self.haelfte]
                + f"\n[… gekürzt, insgesamt {self.gesamt} Bytes …]\n"
                + schwanz[-self.haelfte:])


# ── Arbeitsordner ──────────────────────────────────────────────────────

def _bestand(ordner: str) -> dict:
    """relativer Pfad → (Größe, mtime) aller Dateien. Folgt KEINEN Verweisen:
    ein Programm kann einen Symlink auf /home/… anlegen; außerhalb der
    Sandbox darf ihn niemand auflösen."""
    out = {}
    for wurzel, ordnernamen, dateien in os.walk(ordner, followlinks=False):
        for name in dateien + [d for d in ordnernamen
                               if os.path.islink(os.path.join(wurzel, d))]:
            pfad = os.path.join(wurzel, name)
            try:
                st = os.lstat(pfad)
            except OSError:
                continue
            out[os.path.relpath(pfad, ordner)] = (st.st_size, st.st_mtime_ns)
    return out


def _sicherer_name(name: str) -> str | None:
    """Ein mitgegebener Dateiname, nur innerhalb des Arbeitsordners."""
    name = os.path.normpath(str(name or "").strip())
    if not name or name.startswith(("/", "..")) or name == ".":
        return None
    return name


def lauf_kennung(gespraech: str | None = None) -> str:
    """Eine neue Lauf-Kennung. Mit Gespräch beginnt sie mit dessen id
    (2026-10-07, Phase 5): so gehört ein Arbeitsordner sichtbar zu einem
    Gespräch, und save_from_sandbox kann prüfen, dass eine Datei aus einem
    Lauf DIESES Gesprächs kommt."""
    stempel = time.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3)
    return lauf_vorsatz(gespraech) + stempel if gespraech else stempel


def lauf_vorsatz(gespraech: str) -> str:
    """Womit die Läufe eines Gesprächs beginnen ("<id>--")."""
    vorn = "".join(c if c.isalnum() or c == "-" else "_" for c in str(gespraech))
    return vorn[:60].replace("--", "-") + "--"


def datei_lesen(lauf_id: str, name: str, max_bytes: int) -> bytes:
    """Eine Datei aus dem Arbeitsordner eines Laufs lesen — für die Ablage.

    Nur innerhalb des Lauf-Ordners: kein absoluter Pfad, kein `..`, kein
    Verweis (Symlink) — weder die Datei noch ein Ordner davor. Ein Programm
    in der Sandbox kann einen Verweis auf /home/… anlegen; drinnen zeigt er
    ins Leere, HIER draußen würde er aufgelöst. Wirft ValueError (Klartext)."""
    lauf_id = str(lauf_id or "").strip()
    if not lauf_id or _sicherer_name(lauf_id) != lauf_id or os.sep in lauf_id \
            or lauf_id.startswith((".", "_")):
        raise ValueError(f"Ungültige Lauf-Kennung {lauf_id!r}.")
    rel = _sicherer_name(name)
    if rel is None:
        raise ValueError(f"Ungültiger Dateiname {name!r}.")
    basis = os.path.realpath(basis_ordner())
    arbeit = os.path.join(basis, lauf_id)
    if os.path.islink(arbeit) or not os.path.isdir(arbeit):
        raise ValueError(f"Den Lauf {lauf_id} gibt es nicht (mehr).")
    ziel = os.path.join(arbeit, rel)
    # Jeder Teil des Weges: kein Verweis.
    weg = arbeit
    for teil in rel.split(os.sep):
        weg = os.path.join(weg, teil)
        if os.path.islink(weg):
            raise ValueError(f"{name} ist ein Verweis — wird nicht gelesen.")
    if not os.path.realpath(ziel).startswith(arbeit + os.sep):
        raise ValueError(f"{name} liegt nicht im Arbeitsordner.")
    try:
        fd = os.open(ziel, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        raise ValueError(f"{name} gibt es im Lauf {lauf_id} nicht.")
    except OSError as e:
        raise ValueError(f"{name} lässt sich nicht lesen: {e.strerror}")
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode):
        os.close(fd)
        raise ValueError(f"{name} ist keine normale Datei.")
    with os.fdopen(fd, "rb") as f:
        if st.st_size > max_bytes:
            raise ValueError(f"{name} ist zu groß ({st.st_size} Bytes, "
                             f"höchstens {max_bytes}).")
        return f.read(max_bytes + 1)[:max_bytes]


def aufraeumen(tage: int = AUFBEWAHREN_TAGE) -> int:
    """Arbeitsordner älter als `tage` löschen. Gibt die Anzahl zurück.

    Löschen ist hier richtig (anders als in data/): der Ordner liegt außerhalb
    des Syncs, nichts kommt zurück, und es sind Wegwerf-Ergebnisse."""
    basis = basis_ordner()
    grenze = time.time() - tage * 86400
    weg = 0
    try:
        eintraege = list(os.scandir(basis))
    except OSError:
        return 0
    for e in eintraege:
        try:
            if e.is_dir(follow_symlinks=False) and \
                    e.stat(follow_symlinks=False).st_mtime < grenze:
                shutil.rmtree(e.path, ignore_errors=True)
                weg += 1
        except OSError:
            pass
    return weg


# ── Ausführen ──────────────────────────────────────────────────────────

def _ergebnis(**felder) -> dict:
    erg = {"ausgabe": "", "fehler": "", "rc": None, "dauer_s": 0.0,
           "dateien_neu": [], "abgebrochen": False, "gestoppt": False,
           "ordner": None}
    erg.update(felder)
    return erg


def ausfuehren(code: str, sprache: str = "python",
               zeitlimit_s: float = ZEITLIMIT_STANDARD_S,
               dateien: dict | None = None,
               lauf_id: str | None = None,
               abbruch=None,
               skill_ordner: str | None = None) -> dict:
    """Code in der Sandbox laufen lassen.

    Rückgabe: ausgabe, fehler (stdout/stderr, gekappt), rc (None = gar nicht
    gelaufen), dauer_s, dateien_neu ([{name, bytes}] neu oder geändert),
    abgebrochen (Zeitlimit ODER gestoppt), gestoppt (Sasha hat gestoppt),
    ordner (Arbeitsordner auf dem Rechner).

    `abbruch`: Stopp-Signal (hat is_set(), z. B. threading.Event). Wird es
    gesetzt, stirbt die ganze Prozessgruppe sofort (2026-10-07, Sasha:
    „stoppknopf verlässlich machen").

    `dateien`: {name: text}, wird vor dem Lauf in den Arbeitsordner gelegt.
    `lauf_id`: gleiche id = gleicher Ordner (Dateien bleiben zwischen Läufen);
    ohne = ein frischer.
    `skill_ordner`: ein Skill-Ordner, nur lesend unter /skills/<name> (skills.
    skript_ordner prüft vorher, dass der Skill aktiv ist)."""
    if sprache not in SPRACHEN:
        return _ergebnis(fehler=f"Unbekannte Sprache {sprache!r} "
                                f"(geht: {', '.join(SPRACHEN)}).")
    bwrap = _bwrap_pfad()
    if not bwrap:
        return _ergebnis(fehler="Die Sandbox (bubblewrap) ist auf diesem "
                                "Rechner nicht installiert. Ohne sie führe "
                                "ich keinen Code aus.")
    zeitlimit_s = max(1.0, min(float(zeitlimit_s or ZEITLIMIT_STANDARD_S),
                               ZEITLIMIT_MAX_S))

    if skill_ordner is not None and not os.path.isdir(skill_ordner):
        return _ergebnis(fehler=f"Kein Skill-Ordner {skill_ordner!r}.")
    aufraeumen()
    lauf_id = lauf_id or lauf_kennung()
    if _sicherer_name(lauf_id) != lauf_id or os.sep in lauf_id:
        return _ergebnis(fehler=f"Ungültige Lauf-Kennung {lauf_id!r}.")
    arbeit = os.path.join(basis_ordner(), lauf_id)
    os.makedirs(arbeit, mode=0o700, exist_ok=True)
    os.utime(arbeit)                        # zählt fürs Aufräumen als frisch

    for name, inhalt in (dateien or {}).items():
        rel = _sicherer_name(name)
        if rel is None:
            return _ergebnis(fehler=f"Ungültiger Dateiname {name!r}.",
                             ordner=arbeit)
        ziel = os.path.join(arbeit, rel)
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        with open(ziel, "w", encoding="utf-8") as f:
            f.write(str(inhalt))
    vorher = _bestand(arbeit)

    # Das Programm liegt AUSSERHALB des Arbeitsordners (nur-lesend
    # eingehängt), damit es nicht als „neue Datei" zählt und sich nicht
    # selbst überschreiben kann.
    eingabe = tempfile.mkdtemp(prefix="zentrale_sandbox_eingabe_")
    try:
        programm = os.path.join(eingabe, SPRACHEN[sprache][0])
        with open(programm, "w", encoding="utf-8") as f:
            f.write(code or "")
        return _laufen(bwrap, arbeit, programm, sprache, zeitlimit_s, vorher,
                       abbruch, skill_ordner)
    finally:
        shutil.rmtree(eingabe, ignore_errors=True)


# So oft schaut der Lauf nach dem Stopp-Signal. 0,1 s: Esc fühlt sich
# sofort an, und ein wartender Python-Prozess kostet dabei nichts.
_STOPP_TAKT_S = 0.1


def _warten(proc, zeitlimit_s, abbruch):
    """Warten, bis das Programm endet, die Zeit um ist oder gestoppt wird.
    -> (rc oder None, grund: None | "zeit" | "gestoppt")"""
    frist = time.monotonic() + zeitlimit_s
    while True:
        if abbruch is not None and abbruch.is_set():
            return None, "gestoppt"
        rest = frist - time.monotonic()
        if rest <= 0:
            return None, "zeit"
        try:
            return proc.wait(timeout=min(_STOPP_TAKT_S, rest)), None
        except subprocess.TimeoutExpired:
            continue


def _laufen(bwrap, arbeit, programm, sprache, zeitlimit_s, vorher,
            abbruch=None, skill_ordner=None) -> dict:
    status_r, status_w = os.pipe()
    start = time.monotonic()
    try:
        proc = subprocess.Popen(
            _bwrap_befehl(bwrap, arbeit, programm, sprache, status_w,
                          skill_ordner),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, pass_fds=(status_w,),
            start_new_session=True, preexec_fn=_grenzen_setzen,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
    except OSError as e:
        os.close(status_r)
        os.close(status_w)
        return _ergebnis(fehler=f"Die Sandbox ließ sich nicht starten: {e}",
                         ordner=arbeit)
    os.close(status_w)
    aus = _Kappe(proc.stdout, AUSGABE_MAX_ZEICHEN)
    err = _Kappe(proc.stderr, AUSGABE_MAX_ZEICHEN)
    rc, grund = _warten(proc, zeitlimit_s, abbruch)
    abgebrochen = grund is not None
    if abgebrochen:
        # Ganze Prozessgruppe hart beenden. bwrap ist PID 1 seines
        # Prozess-Namensraums nicht selbst, aber --die-with-parent und der
        # eigene PID-Namensraum nehmen alles darin mit.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        rc = proc.wait()
    dauer = round(time.monotonic() - start, 2)
    with os.fdopen(status_r, "rb") as f:
        status = f.read().decode("utf-8", "replace")
    ausgabe, fehler = aus.text(), err.text()

    if '"child-pid"' not in status:
        # bwrap kam nicht bis zum Programm (Namensräume gesperrt o. ä.).
        # Das Programm ist NICHT gelaufen.
        return _ergebnis(fehler="Die Sandbox ließ sich nicht starten: "
                                + (fehler.strip() or f"Fehlercode {rc}"),
                         dauer_s=dauer, ordner=arbeit)
    rc = _echter_rc(status, rc)
    if grund == "gestoppt":
        fehler = (fehler + "\n[Abgebrochen: vom Nutzer gestoppt.]").lstrip("\n")
    elif abgebrochen:
        fehler = (fehler + f"\n[Abgebrochen: Zeitlimit {zeitlimit_s:g} s "
                           f"überschritten.]").lstrip("\n")
    nachher = _bestand(arbeit)
    neu = [{"name": n, "bytes": g} for n, (g, m) in sorted(nachher.items())
           if vorher.get(n) != (g, m)]
    return _ergebnis(ausgabe=ausgabe, fehler=fehler, rc=rc, dauer_s=dauer,
                     dateien_neu=neu[:DATEIEN_LISTE_MAX],
                     abgebrochen=abgebrochen, gestoppt=grund == "gestoppt",
                     ordner=arbeit)


def _echter_rc(status: str, rc: int) -> int:
    """bwrap meldet den Rückgabewert des Programms auch über das Status-Fd
    ("exit-code"); der ist genauer als der von bwrap selbst (Signale)."""
    for zeile in status.splitlines():
        try:
            d = json.loads(zeile)
        except ValueError:
            continue
        if "exit-code" in d:
            return int(d["exit-code"])
    return rc


_verfuegbar_cache: dict = {}


def verfuegbar() -> bool:
    """Startet die Sandbox auf diesem Rechner wirklich? (Einmal geprüft.)
    bwrap kann installiert sein und trotzdem scheitern, wenn Benutzer-
    Namensräume gesperrt sind (AppArmor, ältere Kernel)."""
    pfad = _bwrap_pfad()
    if pfad not in _verfuegbar_cache:
        if not pfad:
            _verfuegbar_cache[pfad] = False
        else:
            erg = ausfuehren("print('ok')", lauf_id="_probe")
            _verfuegbar_cache[pfad] = erg["rc"] == 0 and \
                erg["ausgabe"].strip() == "ok"
            shutil.rmtree(os.path.join(basis_ordner(), "_probe"),
                          ignore_errors=True)
    return _verfuegbar_cache[pfad]


def als_text(erg: dict) -> str:
    """Das Ergebnis als Werkzeug-Antwort fürs Modell. Kein Pfad von Sashas
    Rechner — im Programm heißt der Arbeitsordner /arbeit."""
    if erg.get("rc") is None:
        return f"[Nicht ausgeführt: {erg.get('fehler') or 'unbekannter Fehler'}]"
    kopf = f"Rückgabewert {erg['rc']}, {erg.get('dauer_s', 0):g} s"
    if erg.get("gestoppt"):
        kopf += " — VOM NUTZER GESTOPPT"
    elif erg.get("abgebrochen"):
        kopf += " — ABGEBROCHEN (Zeitlimit)"
    teile = [kopf]
    if erg.get("ausgabe"):
        teile.append("Ausgabe:\n" + erg["ausgabe"].rstrip("\n"))
    if erg.get("fehler"):
        teile.append("Fehler:\n" + erg["fehler"].rstrip("\n"))
    if not erg.get("ausgabe") and not erg.get("fehler"):
        teile.append("(keine Ausgabe)")
    if erg.get("dateien_neu"):
        teile.append("Neue Dateien in /arbeit: " + ", ".join(
            f"{d['name']} ({d['bytes']} Bytes)" for d in erg["dateien_neu"]))
    return "\n".join(teile)
