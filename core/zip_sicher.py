# core/zip_sicher.py
#
# Eine Zip sicher lesen und auspacken — das Handwerk, das import_skill
# (core/skill_import.py) und unzip (core/input_dateien.py) teilen.
#
# 2026-10-09 aus skill_import herausgezogen, als unzip dazukam: zwei Kopien
# derselben Prüfung („kein .., kein absoluter Pfad, kein Verweis, nicht zu
# groß") laufen früher oder später auseinander, und dann ist eine davon die
# Lücke.
#
# Die Regeln: ALLE Einträge werden geprüft, bevor eine Datei entsteht; ein
# Pfad nach draußen (absolut, Laufwerk, `..`) oder ein Verweis (Symlink)
# bricht ab; ebenso eine verschlüsselte Zip und zu viel (Zahl oder Größe).
# Die Größe zählt beim Auspacken mit — die Angabe im Verzeichnis der Zip
# kann lügen. Was ausgelassen wird (versteckt, Ballast, Schlüssel), sagt der
# Aufrufer per `auslassen`.
#
# Fehler tragen eine ART (unsicher, zu_gross, kaputt), keinen Code: die
# Vorsilbe gehört dem Werkzeug (S- bei Skills, Z- bei unzip,
# core/fehlercodes.py).
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md): weiß nichts vom Fach.

import os
import re
import zipfile

import context

UNSICHER, ZU_GROSS, KAPUTT = "unsicher", "zu_gross", "kaputt"
BALLAST = {"__MACOSX", "__pycache__"}


class Fehler(Exception):
    def __init__(self, art: str, grund: str):
        super().__init__(grund)
        self.art = art
        self.grund = grund


def auslassen_standard(teile, erlaubt_versteckt=()) -> bool:
    """Versteckt (außer den genannten), Mac-/Python-Ballast, Schlüssel."""
    for t in teile:
        if t in BALLAST or (t.startswith(".") and t not in erlaubt_versteckt):
            return True
    return context._is_secret(teile[-1])


def oeffnen(datei: str) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(datei)
    except (zipfile.BadZipFile, OSError) as e:
        raise Fehler(KAPUTT, f"die Zip lässt sich nicht öffnen ({e})")


def eintraege(zf: zipfile.ZipFile) -> list:
    """→ [(info, teile)] der Dateien (ohne Ordner). Bricht ab bei Pfaden
    nach draußen, Verweisen und Verschlüsselung."""
    raus = []
    for info in zf.infolist():
        name = info.filename.replace("\\", "/")
        teile = [t for t in name.split("/") if t not in ("", ".")]
        if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in teile:
            raise Fehler(UNSICHER, f"Pfad zeigt nach draußen: {info.filename}")
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise Fehler(UNSICHER, f"Verweis (Symlink) in der Zip: {info.filename}")
        if info.flag_bits & 0x1:
            raise Fehler(KAPUTT, "die Zip ist verschlüsselt")
        if teile and not info.is_dir():
            raus.append((info, teile))
    return raus


def grenzen(liste: list, max_dateien: int, max_bytes: int) -> None:
    """Zu viele Dateien oder (laut Verzeichnis) zu groß → Fehler."""
    if len(liste) > max_dateien:
        raise Fehler(ZU_GROSS, f"{len(liste)} Dateien, höchstens {max_dateien}")
    if sum(i.file_size for i, _ in liste) > max_bytes:
        raise Fehler(ZU_GROSS, f"entpackt über {max_bytes // 2**20} MB")


def auspacken(datei: str, ziel: str, *, max_dateien: int, max_bytes: int,
              auslassen=auslassen_standard) -> list:
    """Die Zip nach `ziel` auspacken. → Liste der ausgelassenen Pfade
    („a/.env"). Prüft alles, bevor eine Datei entsteht; wirft Fehler.
    Bei einem Fehler mittendrin kann `ziel` halb gefüllt sein — der
    Aufrufer packt deshalb in einen Wegwerf-Ordner aus."""
    with oeffnen(datei) as zf:
        liste = eintraege(zf)
        grenzen(liste, max_dateien, max_bytes)
        ausgelassen, summe = [], 0
        for info, teile in liste:
            if auslassen(teile):
                ausgelassen.append("/".join(teile))
                continue
            pfad = os.path.join(ziel, *teile)
            os.makedirs(os.path.dirname(pfad), exist_ok=True)
            try:
                with zf.open(info) as q, open(pfad, "wb") as z:
                    while True:
                        stueck = q.read(1 << 16)
                        if not stueck:
                            break
                        summe += len(stueck)
                        if summe > max_bytes:
                            raise Fehler(ZU_GROSS, f"entpackt über {max_bytes // 2**20} MB")
                        z.write(stueck)
            except (zipfile.BadZipFile, OSError, EOFError, RuntimeError) as e:
                raise Fehler(KAPUTT, f"{info.filename} lässt sich nicht entpacken ({e})")
    return ausgelassen
