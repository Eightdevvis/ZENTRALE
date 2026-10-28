#!/usr/bin/env python3
"""Testvektoren fürs Handy (mobile/test/daten/) — erzeugt mit dem ECHTEN Kern.

Das Handy baut Mitte und Kalender in Dart nach (memory/system/zen_mobile.md).
Damit beide Seiten nie auseinanderlaufen, rechnet dieses Skript die
Erwartungen mit dem Python-Code, der auf den Rechnern läuft, und legt sie als
JSON neben die Dart-Tests (Regel: memory/system/bauplan_kern.md — Protokolle
nachbaubar aus der Doku, mit Testvektoren):

  mitte_testvektoren.json     versteckte Namen, Fernet-Tokens (inhalt.enc,
                              Datei, Umschlag, geheim.enc-Eintrag) mit dem
                              konto_schluessel aus konto_testvektoren.json
  kalender_testvektoren.json  ausgedachte, aber echt geformte .ics-Dateien
                              (geschrieben von der Kalender-Fassade selbst plus
                              Google-artige von Hand) und ihre Vorkommen laut
                              kalender.entries_in_range; dazu neue Termine, wie
                              termin_kalender sie schreibt (das Handy muss sie
                              Byte für Byte gleich schreiben)

Nie Sashas Daten: alles läuft in einem Wegwerf-Ordner, die Termine sind
erfunden. Aufruf (Sasha oder ein Agent, aus dem Repo):
    venv/bin/python scripts/handy_testvektoren.py
Danach `flutter test` in mobile/.
"""
import base64
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "core"))

ZIEL = Path(ROOT) / "mobile" / "test" / "daten"
FEST = dt.datetime(2026, 10, 1, 8, 0, tzinfo=dt.timezone.utc)


# ── Mitte ──────────────────────────────────────────────────────────────

def _fernet_fest(schluessel: bytes, klar: bytes, zeit: int, iv: bytes) -> str:
    """Ein reproduzierbares Token (feste Zeit + IV) — nur für Vektoren."""
    from cryptography.fernet import Fernet
    return Fernet(schluessel)._encrypt_from_parts(klar, zeit, iv).decode("ascii")


def mitte_vektoren() -> dict:
    import abgleich_schluessel as schluessel
    konto = json.loads((Path(ROOT) / "tests" / "daten" / "konto_testvektoren.json").read_text())
    k = konto["konto_schluessel"].encode("ascii")
    t = schluessel.Tresor(k)
    pfade = ["data/gespraeche/20261008-101500-a1b2c3/handy.jsonl",
             "data/gespraeche/_knoten/handy.json",
             "data/mobil/kontext.json",
             "data/kalender/termine/0123456789abcdef0123456789abcdef@zentrale.ics",
             "data/adapter/geheim.enc",
             "data/gedaechtnis/dossiers/ümlaut person.md"]
    datei = "Hallo vom Laptop — mit Umlauten: äöü\n".encode("utf-8")
    inhalt = {"format": 1,
              "dateien": {pfade[2]: {"name": t.name(pfade[2]),
                                     "sha": __import__("hashlib").sha256(datei).hexdigest()}},
              "geloescht": {pfade[3]: {"sha": "0" * 64, "von": "laptop", "am": "2026-10-20T10:00:00"}}}
    inhalt_klar = json.dumps(inhalt, ensure_ascii=False).encode("utf-8")
    umschlag = json.dumps({"format": 1, "pfad": pfade[0],
                           "inhalt": base64.b64encode(b'{"text": "vom Handy"}\n').decode()}).encode()
    geheim = {"format": "zentrale-geheim/1", "eintraege": {
        "ki/ANTHROPIC_API_KEY": {"zu": "konto",
                                 "wert": t.zu(b"sk-ant-test-nur-ein-vektor").decode("ascii")},
        "google/token": {"zu": "geraet", "wert": "gAAAAA-nicht-fuer-das-handy"}}}
    iv = bytes(range(0xa0, 0xb0))
    return {
        "beschreibung": "Mitte über die Cloud, erzeugt von scripts/handy_testvektoren.py mit "
                        "core/abgleich_schluessel.Tresor. Schlüssel = konto_schluessel aus "
                        "konto_testvektoren.json.",
        "konto_schluessel": konto["konto_schluessel"],
        "namen": {p: t.name(p) for p in pfade},
        "inhalt_token": t.zu(inhalt_klar).decode("ascii"),
        "inhalt": inhalt,
        "datei_token": t.zu(datei).decode("ascii"),
        "datei_klar_b64": base64.b64encode(datei).decode(),
        "umschlag_token": t.zu(umschlag).decode("ascii"),
        "umschlag": json.loads(umschlag),
        "geheim_enc": json.dumps(geheim),
        "geheim_ki": "sk-ant-test-nur-ein-vektor",
        "fest": {"zeit": 1761091200, "iv_hex": iv.hex(), "klar_b64": base64.b64encode(datei).decode(),
                 "token": _fernet_fest(k, datei, 1761091200, iv)},
    }


# ── Kalender ───────────────────────────────────────────────────────────

GOOGLE = {
    # Einmal-Termin mit fremder UID und Google-Erinnerung (30 min).
    "termine/abc123googlecom.ics": """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Google Inc//Google Calendar 70.9054//EN
BEGIN:VEVENT
DTSTART;TZID=Europe/Berlin:20261029T190000
DTEND;TZID=Europe/Berlin:20261029T200000
DTSTAMP:20261020T100000Z
UID:abc123@google.com
SUMMARY:Abendessen bei Kim
LOCATION:Kims Wohnung\\, Hinterhof
DESCRIPTION:Wein mitbringen
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:This is an event reminder
TRIGGER:-PT30M
END:VALARM
END:VEVENT
END:VCALENDAR
""",
    # UTC-Zeiten vor und nach dem Ende der Sommerzeit (25.10.2026).
    "termine/utc-vorher.ics": """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Google Inc//Google Calendar 70.9054//EN
BEGIN:VEVENT
DTSTART:20261023T090000Z
DTEND:20261023T100000Z
DTSTAMP:20261020T100000Z
UID:utc-vorher@google.com
SUMMARY:Anruf Versicherung
END:VEVENT
END:VCALENDAR
""",
    "termine/utc-nachher.ics": """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Google Inc//Google Calendar 70.9054//EN
BEGIN:VEVENT
DTSTART:20261026T090000Z
DTEND:20261026T100000Z
DTSTAMP:20261020T100000Z
UID:utc-nachher@google.com
SUMMARY:Anruf Bank
END:VEVENT
END:VCALENDAR
""",
    # Wöchentliche Serie aus Google: EXDATE allein, ein verschobenes und ein
    # abgesagtes Vorkommen (RECURRENCE-ID), UNTIL in UTC, lange Zeile gefaltet.
    "termine/serie-google.ics": """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Google Inc//Google Calendar 70.9054//EN
BEGIN:VEVENT
DTSTART;TZID=Europe/Berlin:20261007T180000
DTEND;TZID=Europe/Berlin:20261007T193000
RRULE:FREQ=WEEKLY;BYDAY=WE;UNTIL=20261230T225959Z
EXDATE;TZID=Europe/Berlin:20261021T180000
DTSTAMP:20261020T100000Z
UID:serie42@google.com
SUMMARY:Chorprobe im Gemeindehaus mit dem ganzen Ensemble und Gästen aus der
  Nachbarstadt
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:This is an event reminder
TRIGGER:-PT7H
END:VALARM
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=Europe/Berlin:20261105T190000
DTEND;TZID=Europe/Berlin:20261105T203000
RECURRENCE-ID;TZID=Europe/Berlin:20261104T180000
DTSTAMP:20261020T100000Z
UID:serie42@google.com
SUMMARY:Chorprobe (verschoben)
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=Europe/Berlin:20261118T180000
DTEND;TZID=Europe/Berlin:20261118T193000
RECURRENCE-ID;TZID=Europe/Berlin:20261118T180000
STATUS:CANCELLED
DTSTAMP:20261020T100000Z
UID:serie42@google.com
SUMMARY:Chorprobe
END:VEVENT
END:VCALENDAR
""",
    # Über mehrere Tage mit Uhrzeit (Fr 18:00 – So 14:00).
    "uncommitted/wochenende.ics": """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Google Inc//Google Calendar 70.9054//EN
BEGIN:VEVENT
DTSTART;TZID=Europe/Berlin:20261127T180000
DTEND;TZID=Europe/Berlin:20261129T140000
DTSTAMP:20261020T100000Z
UID:wochenende@google.com
SUMMARY:Wochenende an der See
END:VEVENT
END:VCALENDAR
""",
}

VON, BIS = dt.date(2026, 10, 19), dt.date(2027, 3, 31)

# Was ein Vorkommen für das Handy ausmacht (der Rest der Fassade ist intern).
FELDER = ("label", "time", "ende", "ort", "typ", "vorwarnung", "soll_zeit",
          "ueber_nacht", "motiv", "absage_noetig")


def _kalender_fuellen(kalender):
    """Die Fassade schreibt die Termine selbst — so sehen die Dateien aus wie
    auf Sashas Rechnern (X-ZENTRALE-*, VALARM, EXDATE, Pausen)."""
    kalender.add_layer("termine", "Termine", "#3b82f6")
    kalender.add_layer("uncommitted", "Vielleicht", "#a3a3a3")
    kalender.add_layer("rhythmus", "Rhythmus", "#10b981")
    kalender.add_entry("termine", "2026-10-28", "Zahnarzt", "10:00", ende="11:00", ort="Praxis Dr. Weiß")
    kalender.add_entry("termine", "2026-11-05", "Omas Geburtstag")
    kalender.add_span("termine", "2026-11-12", "2026-11-14", "Messe")
    kalender.add_routine("termine", "Geige", "FREQ=WEEKLY;BYDAY=TU", "17:00", ende="17:45",
                         seit="2026-09-01", absage_noetig=True)
    kalender.set_routine_skip("termine", "Geige", "2026-11-03")
    kalender.add_pause("Geige", "2026-12-21", "2027-01-06", "Weihnachtsferien")
    kalender.add_routine("termine", "Miete überweisen", "FREQ=MONTHLY;BYMONTHDAY=1", seit="2026-01-01")
    kalender.add_routine("termine", "Stammtisch", "FREQ=MONTHLY;BYDAY=2TH;UNTIL=20270301T235959",
                         "19:30", seit="2026-06-01")
    kalender.add_routine("termine", "Parkour", "FREQ=WEEKLY;INTERVAL=2;BYDAY=SA", "10:00",
                         ende="11:30", seit="2026-10-03")
    kalender.add_routine("termine", "Jahrestag", "FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=14", seit="2020-02-14")
    kalender.add_entry("termine", "2026-11-20", "Steuererklärung abgeben", "12:00",
                       typ="deadline", vorwarnung=3 * 24 * 60, soll_abstand=-(2 * 24 * 60 + 18 * 60))
    kalender.add_routine("termine", "Wochenbericht", "FREQ=WEEKLY;BYDAY=FR", "16:00",
                         typ="deadline", vorwarnung=7 * 60, soll_abstand=-120, seit="2026-10-01")
    kalender.add_entry("termine", "2026-12-24", "Geschenke fertig", "18:00", typ="deadline",
                       vorwarnung=0)
    kalender.add_entry("uncommitted", "2026-10-31", "Kino vielleicht", "20:00", ende="22:30")
    kalender.add_routine("uncommitted", "Schwimmen?", "FREQ=WEEKLY;BYDAY=TH;COUNT=10", "07:00",
                         ende="08:00", seit="2026-10-01")
    kalender.add_routine("rhythmus", "Schlaf", "FREQ=DAILY", "23:00", ende="07:00",
                         motiv="schlaf", seit="2026-10-01")
    kalender.add_routine("rhythmus", "Mittagessen", "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", "12:30",
                         ende="13:15", motiv="essen", seit="2026-10-01")


def kalender_vektoren() -> dict:
    import kalender
    import kalender_ics
    import kalender_ics_abbildung as abb
    import kalender_speicher
    import uhr

    zaehler = iter(range(1, 1000))
    abb.neue_uid = lambda: f"{next(zaehler):032x}@zentrale"
    abb._jetzt = lambda _j=None: FEST
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        os.environ["ZENTRALE_KALENDER_SPEICHER"] = "ics"
        kalender_ics.cache_leeren()
        sp = kalender_speicher.ics_speicher(tmp / "ai_calendar.json", tmp / "kalender",
                                            mit_spiegel=False)
        with uhr.gestellt(dt.datetime(2026, 10, 1, 10, 0)), kalender.mit_speicher(sp):
            _kalender_fuellen(kalender)
            for rel, text in GOOGLE.items():
                p = tmp / "kalender" / rel
                p.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
            kalender_ics.cache_leeren()
            tage = kalender.entries_in_range(VON, BIS)
        dateien = {}
        for f in sorted((tmp / "kalender").rglob("*")):
            if f.is_file() and not f.name.startswith("."):
                dateien[str(f.relative_to(tmp)).replace(os.sep, "/")] = f.read_text("utf-8")
    vorkommen = []
    for tag, es in tage.items():
        for e in es:
            v = {"tag": tag, "layer": e["layer"], "kennung": e.get("kennung"),
                 "versteckt": bool(e.get("deaktiviert") or e.get("ausfall"))}
            v.update({k: e[k] for k in FELDER if k in e})
            vorkommen.append(v)
    return {"beschreibung": "Kalender, erzeugt von scripts/handy_testvektoren.py mit "
                            "core/kalender.py (entries_in_range). Alles erfunden.",
            "von": VON.isoformat(), "bis": BIS.isoformat(),
            "dateien": dateien, "vorkommen": vorkommen, "neu": neue_termine(),
            "regeln": regel_vektoren()}


REGELN = [
    ("FREQ=WEEKLY;BYDAY=MO,WE,FR", "2026-10-01"),
    ("FREQ=WEEKLY;INTERVAL=3;BYDAY=MO,FR;WKST=SU", "2026-10-02"),
    ("FREQ=WEEKLY;INTERVAL=2", "2026-10-07"),
    ("FREQ=DAILY;INTERVAL=3;COUNT=5", "2026-10-28"),
    ("FREQ=MONTHLY;BYMONTHDAY=31", "2026-01-31"),
    ("FREQ=MONTHLY;BYMONTHDAY=-1", "2026-01-01"),
    ("FREQ=MONTHLY;BYDAY=-1FR", "2026-01-01"),
    ("FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1", "2026-01-01"),
    ("FREQ=MONTHLY;INTERVAL=2;BYDAY=1MO", "2026-02-01"),
    ("FREQ=MONTHLY", "2026-01-30"),
    ("FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU", "2020-01-01"),
    ("FREQ=YEARLY;BYMONTH=3,10;BYDAY=-1SU", "2020-01-01"),
    ("FREQ=YEARLY", "2024-02-29"),
    ("FREQ=YEARLY;BYDAY=20MO", "2026-01-01"),
    ("FREQ=DAILY;BYMONTH=12;UNTIL=20261224T235959", "2026-11-28"),
    ("FREQ=WEEKLY;BYDAY=SA,SU;COUNT=7", "2026-10-29"),
]


def regel_vektoren() -> list:
    """Reine Regel-Tage (kalender_regel.vorkommen mit `seit`), auch Formen,
    die in den Beispiel-Terminen nicht vorkommen."""
    import kalender_regel
    raus = []
    for regel, seit in REGELN:
        tage = kalender_regel.vorkommen({"rrule": regel, "seit": seit}, dt.date(2026, 1, 1),
                                        dt.date(2028, 12, 31))
        raus.append({"rrule": regel, "seit": seit, "von": "2026-01-01", "bis": "2028-12-31",
                     "tage": [t.date().isoformat() for t in tage]})
    return raus


def neue_termine() -> list:
    """So schreibt der Kern einen neuen Einmal-Termin — das Handy muss es gleich tun."""
    import kalender_ics_abbildung as abb
    faelle = [("2026-11-03", {"label": "Zahnarzt", "time": "10:00", "ende": "11:00"}),
              ("2026-03-29", {"label": "Frühstück mit Kim; danach Park, Café", "time": "09:30",
                              "ende": "10:15"}),
              ("2026-12-24", {"label": "Weihnachten"}),
              ("2026-11-03", {"label": "Kurz", "time": "23:30", "ende": "24:00"}),
              ("2026-11-04", {"label": "Ohne Ende", "time": "08:00"}),
              ("2026-11-05", {"label": "Ein sehr langer Titel, der weit über fünfundsiebzig "
                                       "Zeichen hinausgeht und deshalb gefaltet wird"})]
    raus = []
    for i, (tag, e) in enumerate(faelle):
        uid = f"{0xfeed0000 + i:032x}@zentrale"
        kal = abb.termin_kalender(tag, e, uid, jetzt=FEST)
        raus.append({"tag": tag, "eintrag": e, "uid": uid, "jetzt": FEST.isoformat(),
                     "ics": abb.zusammenfuehren(None, kal, uid).decode("utf-8")})
    return raus


def main():
    ZIEL.mkdir(parents=True, exist_ok=True)
    for name, daten in (("mitte_testvektoren.json", mitte_vektoren()),
                        ("kalender_testvektoren.json", kalender_vektoren())):
        (ZIEL / name).write_text(json.dumps(daten, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print(f"{ZIEL / name}")


if __name__ == "__main__":
    main()
