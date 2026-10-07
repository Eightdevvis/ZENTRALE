# core/skill_umzug.py
#
# Umzug der Skills vom alten ZENTRALE-Format ins Claude-Format.
#
#   alt:  skills/<name>.md          Kopf im Katalog-Schema (## name,
#                                   - beschreibung/erstellt/herkunft/status)
#   neu:  skills/<name>/SKILL.md    + skills/<name>/_zentrale.json
#
# 2026-10-07 (Sasha: Claudes Skill-Format übernehmen). Läuft bei jedem Zugriff
# auf den Skill-Ordner (skills.ordner()), ist billig, wenn nichts zu tun ist,
# und tut beim zweiten Mal nichts mehr.
#
# Nie löschen: die alte Datei wandert nach skills/_alt/. Der Sync ist additiv
# (rsync, neueste gewinnt) — der andere Rechner bringt die alte Datei zurück,
# bis er selbst umgezogen ist. Dann steht der neue Ordner schon da, und die
# zurückgekommene Datei wird nur wieder beiseitegelegt.
#
# Die neuen Dateien bekommen die Änderungszeit der alten: zieht der zweite
# Rechner später selbst um, darf seine Fassung keine Änderung überschreiben,
# die Sasha auf dem ersten inzwischen gemacht hat (z. B. abgeschaltet).
#
# Sonderfälle (Sasha, 07.10.):
#   kurz       „ist kein Skill, skills sind eher komplexere abläufe" → der
#              Inhalt wird EINE Hausregel (angehängt, .bak), der Skill aus.
#   recherche  zieht um, mit Vermerk: Kandidat zum Ersetzen (Claude im Web
#              recherchiert selbst).
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import os
import shutil

import dateien
import gedaechtnis
import skill_format

ALT_ORDNER = "_alt"
_STATUS = ("aktiv", "vorgeschlagen", "aus")

# In Sashas Ton, als Regel für immer (sein „kurz" war bisher nur ein Skill,
# der erst geladen werden musste).
KURZ_REGEL = ("Bin ich im Stress, unterwegs oder sag „kurz“: Antwort zuerst, "
              "in ein bis drei Sätzen, eine Sache nach der anderen, höchstens "
              "eine Rückfrage.")

SONDERFAELLE = {
    "kurz": {"status": "aus",
             "vermerk": "ist seit 07.10.2026 eine Hausregel — Sasha: "
                        "„skills sind eher komplexere abläufe“"},
    "recherche": {"vermerk": "Kandidat zum Ersetzen — Claude im Web "
                             "recherchiert selbst (Sasha, 07.10.2026)"},
}


def _alt_lesen(text: str) -> tuple:
    """Alte Datei → (kopf, inhalt), wie das alte skills._zerlegen."""
    kopf = gedaechtnis.kopf_lesen(text)
    if not kopf:
        return {}, text.strip()
    teile = text.strip().split("\n\n", 1)
    return kopf, (teile[1].strip() if len(teile) > 1 else "")


def _beiseite(ordner: str, datei: str) -> None:
    """skills/<datei> nach skills/_alt/ — nie überschreiben, was anders ist."""
    quelle = os.path.join(ordner, datei)
    ablage = os.path.join(ordner, ALT_ORDNER)
    os.makedirs(ablage, exist_ok=True)
    ziel = os.path.join(ablage, datei)
    n = 1
    while os.path.exists(ziel):
        if _gleich(quelle, ziel):
            break                        # dieselbe Fassung liegt schon da
        n += 1
        ziel = os.path.join(ablage, f"{datei}.{n}")
    os.replace(quelle, ziel)


def _gleich(a: str, b: str) -> bool:
    try:
        with open(a, "rb") as fa, open(b, "rb") as fb:
            return fa.read() == fb.read()
    except OSError:
        return False


def _neuer_ordner(ordner: str, name: str, text: str, zeit: float) -> dict:
    """Den neuen Skill-Ordner aus der alten Datei bauen (erst unter einem
    Punkt-Namen, dann umbenannt: nie ein halber Skill sichtbar).
    → _zentrale.json-Inhalt + alt_status ({} wenn ein anderer schneller war)"""
    kopf, inhalt = _alt_lesen(text)
    status = (kopf.get("status") or "").strip().lower()
    zentrale = {
        "status": status if status in _STATUS else "aus",
        "herkunft": (kopf.get("herkunft") or "").strip().lower() or "sasha",
        "erstellt": (kopf.get("erstellt") or "").strip() or "-",
        "umgezogen": "aus dem alten Format (skills/_alt/%s.md)" % name,
    }
    zentrale.update(SONDERFAELLE.get(name, {}))
    beschreibung = " ".join((kopf.get("beschreibung") or "").split())
    tmp = os.path.join(ordner, f".{name}.umzug.{os.getpid()}")
    shutil.rmtree(tmp, ignore_errors=True)          # eigener Rest eines Absturzes
    os.makedirs(tmp)
    dateien.atomar_schreiben(os.path.join(tmp, skill_format.SKILL_MD),
                             skill_format.rendern(name, beschreibung, inhalt))
    dateien.json_schreiben(os.path.join(tmp, skill_format.ZENTRALE_JSON), zentrale)
    for pfad in (os.path.join(tmp, skill_format.SKILL_MD),
                 os.path.join(tmp, skill_format.ZENTRALE_JSON), tmp):
        os.utime(pfad, (zeit, zeit))
    try:
        os.rename(tmp, os.path.join(ordner, name))
    except OSError:
        # Ein zweiter Zugriff war schneller — dessen Ordner gilt.
        shutil.rmtree(tmp, ignore_errors=True)
        return {}
    return {"alt_status": status, **zentrale}


def kurz_als_hausregel() -> bool:
    """KURZ_REGEL an Sashas Hausregeln anhängen — nur einmal, mit .bak
    (gedaechtnis.kernakte_schreiben). → True, wenn angehängt."""
    alt = gedaechtnis.kernakte_lesen("hausregeln")
    if KURZ_REGEL in alt:
        return False
    basis = alt.rstrip() + "\n" if alt.strip() else gedaechtnis.HAUSREGELN_KOPF
    try:
        gedaechtnis.kernakte_schreiben("hausregeln",
                                       basis + gedaechtnis.regel_zeile(KURZ_REGEL))
    except ValueError:
        return False                     # Akte voll: lieber nichts als halb
    return True


def umziehen(ordner: str) -> list:
    """Alle alten Skill-Dateien in `ordner` umziehen. → Namen der umgezogenen.
    Was schon umgezogen ist, wird nur noch beiseitegelegt."""
    try:
        eintraege = sorted(os.listdir(ordner))
    except FileNotFoundError:
        return []
    umgezogen = []
    for datei in eintraege:
        if datei.endswith(".md.bak") and skill_format.gueltiger_name(datei[:-7]):
            _beiseite(ordner, datei)
            continue
        name = datei[:-3]
        if not datei.endswith(".md") or not skill_format.gueltiger_name(name):
            continue
        pfad = os.path.join(ordner, datei)
        if not os.path.isfile(pfad):
            continue
        if not os.path.isdir(os.path.join(ordner, name)):
            with open(pfad, encoding="utf-8") as f:
                text = f.read()
            neu = _neuer_ordner(ordner, name, text, os.path.getmtime(pfad))
            if not neu:
                continue
            umgezogen.append(name)
            # Nur wenn Sasha „kurz" an hatte: was er abgeschaltet hatte, wird
            # nicht über den Umweg Hausregel wieder wirksam.
            if name == "kurz" and neu["alt_status"] == "aktiv":
                kurz_als_hausregel()
        _beiseite(ordner, datei)
    return umgezogen
