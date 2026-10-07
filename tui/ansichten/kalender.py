# tui/ansichten/kalender.py
#
# Der Kalender der TUI (Zeichner gegen /api/calendar; die Logik liegt in
# core/kalender.py). Bis 06.10.2026 Closures in run_ui (tui/zentrale_tui.py),
# siehe memory/system/tui_bauplan.md. Wird in tui/ansichten/ relativ
# importiert — mit core/kalender.py kann es deshalb nie verwechselt werden.

import curses
import time
from datetime import date, timedelta

from .basis import BEENDEN, api_call, parse_clock
from .kalender_ansichten import (ANSICHT_NAMEN, DATENANSICHT, INV,
                                 naechste_ansicht, tasten_hinweis, text_breite)
from .kalender_ansichten import zeichne as stil_zeichnen


KAL_WD = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


# Deutsche Wochentags-Kürzel → iCal-BYDAY-Codes (für Routine-Anlage)
KAL_BYDAY = {"mo": "MO", "di": "TU", "mi": "WE", "do": "TH",
             "fr": "FR", "sa": "SA", "so": "SU"}


def k_parse_byday(s):
    """Wochentag-Eingabe → Liste iCal-Codes. 'Di' → ['TU'], 'Mo,Mi,Fr' →
    ['MO','WE','FR']. None bei Unsinn. Akzeptiert dt. Kürzel (erste 2 Buchst.)
    ODER direkt die Codes (MO..SU)."""
    out = []
    for p in (s or "").replace(" ", ",").split(","):
        p = p.strip()
        if not p:
            continue
        code = KAL_BYDAY.get(p[:2].lower())
        if not code and p.upper() in KAL_BYDAY.values():
            code = p.upper()
        if code and code not in out:
            out.append(code)
    return out or None


def _k_entry_line(e, day_iso=None):
    """Eine Termin-Zeile kompakt: Zeit(spanne) + Label (+ Ort). Ausfall
    (Ferien) als ℹ-Hinweis statt Termin. Mehrtägige Termine (spanning)
    laufen NICHT hier durch — die zeichnet der Wochen-Render als durchgehende
    Klammer in der linken Spann-Gosse (day_iso bleibt nur der Kompatibilität
    halber im Signatur)."""
    if e.get("ausfall"):
        return "ℹ %s fällt aus" % e.get("label", "?")
    if e.get("time") and e.get("ende"):
        t = "%s-%s " % (e["time"], e["ende"])
    elif e.get("time"):
        t = "%s " % e["time"]
    else:
        t = ""
    ort = " @%s" % e["ort"] if e.get("ort") else ""
    return "%s%s%s" % (t, e.get("label", "?"), ort)


class Kalender:
    """Der Kalender (Mitte, Taste 'c'): Woche mit Sidebar-Liste, Monat,
    Formular für Termin/Routine/Mehrtägig, Routine-Screen. Ein reiner
    Zeichner — Datums- und Layer-Logik liefert /api/calendar fertig.
    Zustand in self.K (auch z.K: run_ui liest daraus die Eingabezeile unten)."""

    def __init__(self, z):
        self.z = z
        # ── Kalender (füllt die MITTE-Box, Taste 'c') ──────────────────────
        # Wie die Karte ein reiner Zeichner: alle Datums-/Layer-Logik liegt im
        # Backend (core/kalender.py → /api/calendar). Die TUI hält nur die Ansicht
        # (Woche|Monat) + das Referenzdatum zum Blättern und die letzte Antwort.
        #   active : Kalender hat den Fokus (Blätter-/Umschalt-Tasten gehen hierher)
        #   view   : "week" (Mo-So-Liste) | "month" (Monatsgitter)
        #   ref    : ISO-Datum irgendwo im gezeigten Zeitraum (Blätter-Anker)
        #   data   : letzte /api/calendar-Antwort (None ⇒ beim Zeichnen neu holen)
        #   mode   : "view" (blättern/auswählen) | "add" (Termin-Eingabe, gestaffelt)
        #            | "routine" (De-/Aktivieren-Screen eines Routine-Vorkommens)
        #   sel    : Auswahl-Index über ALLE Einträge der Woche (Einmal + Routine)
        #   astage : Add-Stufe 0=Datum/Wochentag 1=Zeit 2=Titel; aday/atime/alabel=Eingaben
        #   atype  : "entry" (Einmal-Termin) | "routine" (wöchentlich) — Tab im Add-Formular
        #   editing: None | (iso,label,layer) — Add-Formular im Ändern-Modus
        #   ract   : der im "routine"-Screen gewählte Eintrag (für De-/Aktivieren)
        #   showhidden: erledigte/abgeschaltete Einträge mit-anzeigen? Ein GEMEINSAMER
        #            Schalter (Taste 'x') über dreierlei „passiert nicht": einzeln
        #            deaktivierte Routine-Vorkommen (deaktiviert), per Zeitraum-Pause
        #            ausgefallene (ausfall, z.B. Ferien) UND abgehakte Wochenplan-
        #            Items (done). Default aus → der Kalender startet aufgeräumt;
        #            'x' blendet alles gemeinsam ein bzw. wieder aus.
        #   listfocus: Fokus in der rechten Sidebar-Liste (flache »week«-Liste)?
        #            Taste 'l' schiebt rein (nur Wochenansicht), Esc/'l' wieder raus.
        #            lsel = Auswahl-Index in der Sidebar; im Fokus bearbeitbar
        #            (a neu / r umbenennen / d löschen / Space abhaken) — KEIN Move
        #            in andere Listen (isolierte Einheit).
        #   linput/lmode/ledit_iid: Text-Eingabe der Sidebar. linput=None ⇒ inaktiv,
        #            sonst getippter Text; lmode "add"|"rename"; ledit_iid = iid beim
        #            Umbenennen.
        #   lsort: Sortier-Modus in der Sidebar (Taste 's')? Dann verschieben ↑↓ das
        #            fokussierte Item statt die Auswahl (POST …/reorder).
        self.K = z.K = {"active": False, "view": "week", "ref": date.today().isoformat(),
                        "data": None, "msg": "", "mode": "view", "sel": 0, "confirmdel": False,
                        "astage": 0, "aday": "", "atime": "", "alabel": "", "amsg": "",
                        "atype": "entry", "editing": None, "ract": None, "rconfirm": False,
                        "showhidden": False, "listfocus": False, "lsel": 0,
                        "linput": None, "lmode": "add", "ledit_iid": None, "lsort": False,
                        "spantgt": None,
                        # Ansicht A/B/C (kalender_ansichten.py) oder None = der
                        # jetzige Kalender. Nur pro Sitzung, bewusst nicht gemerkt.
                        "stil": None, "sdata": None}

    def k_fetch(self):
        """Kalender fürs aktuelle view+ref synchron holen (localhost, wenige ms).
        Fehler-Marker statt None, damit draw_calendar nicht bei totem Backend
        jeden Frame neu anfragt — erst Blättern/Umschalten löst einen neuen
        Versuch aus (setzt data=None)."""
        K = self.K
        try:
            # Woche bleibt die normale Mo-So-Kalenderwoche; nur die Wochenplan-
            # Items (week_plan) rollen — auf ihr nächstes Vorkommen in den 7
            # Tagen ab heute verankert, erscheinen am passenden Datum.
            resp = api_call("/api/calendar?view=%s&ref=%s"
                            % (K["view"], K["ref"]), timeout=2.0)
            # Nur ein dict ist zeichenbar; null/Liste/String (auch von einem
            # kaputten Backend) → Fehler-Marker, sonst crasht draw_calendar an
            # .get(). Wie der Karten-Pfad: truthy Marker statt None verhindert
            # Dauer-Refetch jeden Frame.
            K["data"] = resp if isinstance(resp, dict) else {"failed": True}
            K["msg"] = "" if isinstance(resp, dict) else "kalender: backend?"
        except Exception:
            K["data"] = {"failed": True}
            K["msg"] = "kalender: backend?"

    def k_step(self, delta):
        """Eine Periode vor/zurück: Woche = ±7 Tage, Monat = ±1 Monat (auf den
        1. normalisiert, sonst springt z.B. der 31. krumm)."""
        K = self.K
        r = date.fromisoformat(K["ref"])
        if K["view"] == "month":
            m = r.month - 1 + delta
            r = date(r.year + m // 12, m % 12 + 1, 1)
        else:
            r = r + timedelta(days=7 * delta)
        K["ref"] = r.isoformat()
        K["data"] = None

    def k_toggle(self):
        K = self.K
        K["view"] = "month" if K["view"] == "week" else "week"
        K["data"] = None

    # ── Ansichten A/B/C: v dreht jetziger → A → B → C → jetziger ──────────
    # Sasha, 07.10.2026: A/B/C sind reine Anzeige (←→ blättern, 0 heute, esc
    # zu); bearbeitet wird nur im jetzigen Kalender. Die Daten kommen über
    # denselben /api/calendar wie immer — kein neuer Datenweg.
    def k_stil_weiter(self):
        K = self.K
        K["stil"] = naechste_ansicht(K["stil"])
        K["sdata"] = None; K["sel"] = 0; K["confirmdel"] = False
        K["msg"] = ("ansicht: " + ANSICHT_NAMEN[K["stil"]]) if K["stil"] else ""

    def k_stil_fetch(self):
        K = self.K
        dv = DATENANSICHT.get(K["stil"], "month")
        try:
            resp = api_call("/api/calendar?view=%s&ref=%s" % (dv, K["ref"]), timeout=2.0)
            K["sdata"] = resp if isinstance(resp, dict) else {"failed": True}
        except Exception:
            K["sdata"] = {"failed": True}
        K["sdata"]["_for"] = (K["stil"], K["ref"])

    def k_stil_step(self, delta):
        """Blättern in A/B/C: A tageweise, B monatsweise, C wochenweise."""
        K = self.K
        r = date.fromisoformat(K["ref"])
        if K["stil"] == "A":                    # A zeigt ein paar Tage → tageweise
            r = r + timedelta(days=delta)
        elif DATENANSICHT.get(K["stil"]) == "week":
            r = r + timedelta(days=7 * delta)
        else:
            m = r.month - 1 + delta
            r = date(r.year + m // 12, m % 12 + 1, 1)
        K["ref"] = r.isoformat(); K["sdata"] = None

    def _taste_stil(self, ch):
        """Tasten, solange A/B/C zu sehen ist — nur Anzeige."""
        K = self.K
        if ch in (27, ord("c"), ord("C")):
            K["active"] = False
        elif ch in (ord("q"), ord("Q")):
            return BEENDEN
        elif ch in (ord("v"), ord("V")):
            self.k_stil_weiter()
        elif ch in (curses.KEY_LEFT, ord("h")):
            self.k_stil_step(-1)
        elif ch in (curses.KEY_RIGHT, ord("l")):
            self.k_stil_step(1)
        elif ch == ord("0"):
            K["ref"] = date.today().isoformat(); K["sdata"] = None
        elif ch in (ord("x"), ord("X")):
            K["showhidden"] = not K["showhidden"]
            K["msg"] = "erledigte: " + ("an" if K["showhidden"] else "aus")
        elif ch in (ord("t"), ord("T")):
            self.z.cycle_theme()
        elif ch in (ord("a"), ord("A"), ord("e"), ord("E"), ord("d"), ord("D")):
            K["msg"] = "bearbeiten im normalen kalender (v)"
        return None

    def _kal_stil(self, by, bx, bh, bw):
        """A/B/C in die Mitte zeichnen: Zeilen aus kalender_ansichten.py,
        Rollen auf die Palette; „_inv" heißt Fläche (Farbe umgekehrt)."""
        C, K, z = self.z.C, self.K, self.z
        ix, iw = bx + 2, bw - 4
        bottom = by + bh - 2
        if (not K["sdata"]) or K["sdata"].get("_for") != (K["stil"], K["ref"]):
            self.k_stil_fetch()
        d = K["sdata"]
        if d.get("failed"):
            z.addclip(by + 1, ix, "kalender: backend?", iw, C["faint"])
            return
        hoehe = bottom - (by + 1)
        try:
            zeilen = stil_zeichnen(K["stil"], d, iw, hoehe, erledigte=K["showhidden"])
        except Exception as e:          # eine kaputte Ansicht darf die TUI nicht reißen
            z.addclip(by + 1, ix, "ansicht %s: %s" % (K["stil"], e), iw, C["warn"])
            return
        for i, zeile in enumerate(zeilen[:hoehe]):
            x = ix
            for text, rolle in zeile:
                if rolle.endswith(INV):
                    attr = C.get(rolle[:-len(INV)], C["dim"]) | curses.A_REVERSE
                else:
                    attr = C.get(rolle, C["dim"])
                if text.strip() or rolle.endswith(INV):
                    z.addclip(by + 1 + i, x, text, ix + iw - x, attr)
                x += text_breite(text)
        hint = tasten_hinweis(K["stil"])
        z.addclip(bottom, ix, hint, iw, C["faint"])
        if K["msg"]:
            z.addclip(bottom, ix + iw - len(K["msg"]), K["msg"], len(K["msg"]), C["faint"])

    def k_today(self):
        K = self.K
        K["ref"] = date.today().isoformat()
        K["data"] = None

    def k_selectable(self):
        """Flache Liste ALLER auswählbaren Einträge der Antwort in Render-
        Reihenfolge (Einmal-Termine UND Routine-Vorkommen; nur reine Ausfälle/
        Ferien sind nicht handelbar). Jeder Eintrag als Dict mit Typ-Infos —
        Quelle für Auswahl (K['sel']) + alle Aktionen. Reihenfolge MUSS zum
        Wochen-Render passen (sortierte Tage, Eintragsreihenfolge), sonst zeigt
        der ›-Cursor auf den falschen Termin. Defensiv gegen kaputte JSON-Daten."""
        K = self.K
        d = K["data"]
        if not isinstance(d, dict):
            return []
        days = d.get("days")
        if not isinstance(days, dict):
            return []
        out = []
        for iso in sorted(days.keys()):
            ents = days.get(iso)
            if not isinstance(ents, list):
                continue
            for e in ents:
                if not isinstance(e, dict) or e.get("ausfall"):
                    continue   # Ausfall (Ferien) ist nur Info, nicht handelbar
                if e.get("deaktiviert") and not K["showhidden"]:
                    continue   # ausgeblendet (nur mit 'x'); MUSS exakt zur Skip-
                    # Bedingung im Wochen-Render passen, sonst zeigt der ›-Cursor
                    # auf den falschen Termin (di-Index läuft synchron mit).
                out.append({"iso": iso, "label": e.get("label", ""),
                            "layer": e.get("layer", "termine"),
                            "recurring": bool(e.get("recurring")),
                            "deaktiviert": bool(e.get("deaktiviert")),
                            "spanning": bool(e.get("spanning")),
                            "von": e.get("von"), "bis": e.get("bis"),
                            "span_first": bool(e.get("span_first")),
                            "span_last": bool(e.get("span_last")),
                            "time": e.get("time"), "ende": e.get("ende"),
                            "ort": e.get("ort")})
        return out

    def k_sidebar_items(self):
        """Die SICHTBAREN Items der flachen »week«-Sidebar (abgehakte fallen mit
        dem 'x'-Schalter raus). Gleiche Filterung wie im Render → Handler und
        Zeichnung sehen exakt dieselbe Reihenfolge/Länge (lsel bleibt gültig)."""
        K = self.K
        d = K["data"]
        wp = d.get("weekplan") if isinstance(d, dict) else None
        items = wp.get("items") if isinstance(wp, dict) else None
        if not isinstance(items, list):
            return []
        return [it for it in items if isinstance(it, dict)
                and (K["showhidden"] or not it.get("done"))]

    def k_sidebar_lid(self):
        """id der »week«-Liste aus der letzten Antwort (oder None)."""
        K = self.K
        d = K["data"]
        wp = d.get("weekplan") if isinstance(d, dict) else None
        return wp.get("lid") if isinstance(wp, dict) else None

    def k_parse_day(self, s):
        """Tippeingabe → ISO-Datum. Akzeptiert 'TT.MM', 'TT.MM.JJJJ',
        'JJJJ-MM-TT'; leer = heute; Jahr aus dem Blätter-Anker, wenn nur TT.MM.
        None bei Unsinn (Aufrufer meldet 'datum?')."""
        K = self.K
        s = (s or "").strip()
        if not s:
            return date.today().isoformat()
        parts = [p for p in s.replace("-", ".").replace("/", ".").split(".") if p]
        try:
            if len(parts) == 3 and len(parts[0]) == 4:        # JJJJ.MM.TT
                y, m, dd = int(parts[0]), int(parts[1]), int(parts[2])
            elif len(parts) == 3:                              # TT.MM.JJJJ
                dd, m, y = int(parts[0]), int(parts[1]), int(parts[2])
                if y < 100:
                    y += 2000
            elif len(parts) == 2:                              # TT.MM (Jahr aus ref)
                dd, m = int(parts[0]), int(parts[1])
                y = date.fromisoformat(K["ref"]).year
            else:
                return None
            return date(y, m, dd).isoformat()
        except (ValueError, IndexError):
            return None

    def k_add_save(self):
        """Add-/Edit-Formular absenden. Routine (atype) → wöchentliche Routine
        anlegen; sonst Einmal-Termin neu (POST) oder ändern (PUT). Konflikt-
        Hinweis mitnehmen, zurück in die View."""
        K, k_parse_day = self.K, self.k_parse_day
        label = K["alabel"].strip()
        if not label:
            K["amsg"] = "titel fehlt"; return

        if K["atype"] == "span":               # MEHRTÄGIGER (ganztägiger) Termin
            von = k_parse_day(K["aday"])
            bis = k_parse_day(K["atime"])      # Stufe 1 hält das Bis-Datum
            if von is None or bis is None:
                K["amsg"] = "datum? TT.MM"; return
            if bis < von:
                K["amsg"] = "bis < von"; return
            try:
                api_call("/api/calendar/entry", method="POST",
                         body={"day": von, "bis": bis, "label": label})
                K["msg"] = "mehrtägig angelegt: " + label
                K["ref"] = von; K["data"] = None
                K["mode"] = "view"; K["astage"] = 0; K["atype"] = "entry"
                K["aday"] = K["atime"] = K["alabel"] = K["amsg"] = ""
            except Exception:
                K["amsg"] = "speichern fehlgeschlagen"
            return

        time = K["atime"].strip() or None
        if time and parse_clock(time) is None:
            K["amsg"] = "zeit? HH:MM (leer=ganztags)"; return

        if K["atype"] == "routine":            # NEUE wöchentliche Routine
            days = k_parse_byday(K["aday"])
            if not days:
                K["amsg"] = "wochentag? Mo/Di/.."; return
            try:
                api_call("/api/calendar/routine", method="POST",
                         body={"label": label, "byday": days, "time": time})
                K["msg"] = "Routine angelegt: " + label
                K["data"] = None; K["mode"] = "view"; K["astage"] = 0
                K["atype"] = "entry"
                K["aday"] = K["atime"] = K["alabel"] = K["amsg"] = ""
            except Exception:
                K["amsg"] = "speichern fehlgeschlagen"
            return

        day = k_parse_day(K["aday"])
        if day is None:
            K["amsg"] = "datum? TT.MM"; return
        new = {"day": day, "label": label}
        if time:
            new["time"] = time
        try:
            if K["editing"]:
                old_iso, old_label, old_layer = K["editing"]
                res = api_call("/api/calendar/entry", method="PUT",
                               body={"day": old_iso, "label": old_label,
                                     "layer": old_layer, "new": new})
                verb = "geändert: "
            else:
                res = api_call("/api/calendar/entry", method="POST", body=new)
                verb = "angelegt: "
            conf = (res or {}).get("conflicts") or []
            K["msg"] = verb + label + (" ⚠" if conf else "")
            K["ref"] = day; K["data"] = None       # zur Woche des Termins springen
            K["mode"] = "view"; K["astage"] = 0; K["editing"] = None
            K["aday"] = K["atime"] = K["alabel"] = K["amsg"] = ""
        except Exception:
            K["amsg"] = "speichern fehlgeschlagen"

    def k_begin_edit(self):
        """Den ausgewählten Eintrag bearbeiten: Einmal-Termin → Ändern-Formular
        (vorbefüllt); Routine-Vorkommen → De-/Aktivieren-Screen."""
        K, k_selectable = self.K, self.k_selectable
        sels = k_selectable()
        if not sels or not (0 <= K["sel"] < len(sels)):
            return
        it = sels[K["sel"]]
        if it["recurring"]:
            K["mode"] = "routine"; K["ract"] = it; K["msg"] = ""
        elif it.get("spanning"):
            # Mehrtägig: „bearbeiten" heißt Uhrzeit NUR für diesen Tag setzen
            # (leer = wieder ganztags). Eingabe unten in der ›-Leiste.
            K["linput"] = it.get("time") or ""; K["lmode"] = "spantime"
            K["spantgt"] = (it["layer"], it.get("von"), it["label"], it["iso"])
            K["msg"] = ""
        else:
            K["mode"] = "add"; K["astage"] = 0; K["amsg"] = ""; K["msg"] = ""
            K["atype"] = "entry"           # Ändern gibt es nur für Einmal-Termine
            K["editing"] = (it["iso"], it["label"], it["layer"])
            K["aday"] = date.fromisoformat(it["iso"]).strftime("%d.%m")
            K["atime"] = it.get("time") or ""
            K["alabel"] = it["label"]

    def k_delete_sel(self, item):
        K = self.K
        day, label, layer = item
        try:
            res = api_call("/api/calendar/entry", method="DELETE",
                           body={"day": day, "label": label, "layer": layer})
            n = (res or {}).get("deleted", 0)
            K["msg"] = ("gelöscht: " + label) if n else "nichts gelöscht"
        except Exception:
            K["msg"] = "löschen fehlgeschlagen"
        K["data"] = None

    def k_routine_toggle(self, off):
        """Das im Routine-Screen gewählte EINZELNE Vorkommen de-/aktivieren
        (POST /api/calendar/routine/skip). off=True deaktiviert, False aktiviert."""
        K = self.K
        it = K["ract"]
        if not it:
            K["mode"] = "view"; return
        try:
            res = api_call("/api/calendar/routine/skip", method="POST",
                           body={"layer": it["layer"], "label": it["label"],
                                 "day": it["iso"], "off": off, "time": it.get("time")})
            # `changed` ehrlich auswerten: traf der Skip keine an dem Tag
            # vorkommende Routine (z.B. Namens-Verwechslung), passiert nichts —
            # das soll der User sehen, nicht ein falsches „deaktiviert".
            if (res or {}).get("changed"):
                K["msg"] = ("deaktiviert: " if off else "aktiviert: ") + it["label"]
            else:
                K["msg"] = "keine passende Routine an dem Tag"
        except Exception:
            K["msg"] = "fehlgeschlagen (backend neu starten?)"
        K["mode"] = "view"; K["ract"] = None; K["data"] = None

    def k_routine_delete(self):
        """Die GANZE Routine löschen (DELETE /api/calendar/routine) — alle
        Vorkommen weg, nicht nur dieser eine Tag."""
        K = self.K
        it = K["ract"]
        if not it:
            K["mode"] = "view"; K["rconfirm"] = False; return
        try:
            res = api_call("/api/calendar/routine", method="DELETE",
                           body={"layer": it["layer"], "label": it["label"],
                                 "day": it["iso"], "time": it.get("time")})
            n = (res or {}).get("deleted", 0)
            K["msg"] = ("Routine gelöscht: " + it["label"]) if n else "nichts gelöscht"
        except Exception:
            K["msg"] = "löschen fehlgeschlagen"
        K["mode"] = "view"; K["ract"] = None; K["rconfirm"] = False; K["data"] = None

    def oeffnen(self):
        """Startseite → Kalender: frisch laden, Ansicht-Modus, nichts offen."""
        K = self.K
        K["active"] = True; K["data"] = None
        K["mode"] = "view"; K["sel"] = 0; K["confirmdel"] = False; K["msg"] = ""
        K["editing"] = None; K["ract"] = None; K["rconfirm"] = False; K["atype"] = "entry"

    def taste(self, ch):
        """Eine Taste, während der Kalender den Fokus hat (früher ein Zweig der
        Hauptschleife in run_ui). Gibt BEENDEN zurück, wenn die TUI enden soll."""
        K, cycle_theme, k_add_save = self.K, self.z.cycle_theme, self.k_add_save
        k_begin_edit, k_delete_sel = self.k_begin_edit, self.k_delete_sel
        k_fetch, k_parse_day = self.k_fetch, self.k_parse_day
        k_routine_delete, k_routine_toggle = self.k_routine_delete, self.k_routine_toggle
        k_selectable, k_sidebar_items = self.k_selectable, self.k_sidebar_items
        k_sidebar_lid, k_step, k_today = self.k_sidebar_lid, self.k_step, self.k_today
        k_toggle = self.k_toggle
        if K["stil"] and K["mode"] == "view" and not K["listfocus"]:
            return self._taste_stil(ch)
        if K["mode"] == "add":             # gestaffeltes Eingabe-Formular
            cur_key = ("aday", "atime", "alabel")[K["astage"]]
            is_rt = (K["atype"] == "routine")
            is_span = (K["atype"] == "span")   # mehrtägig: Stufe 1 = Bis-Datum
            if ch == 9 and not K["editing"]:   # Tab → Termin→Routine→Mehrtägig
                K["atype"] = {"entry": "routine", "routine": "span",
                              "span": "entry"}[K["atype"]]
                K["aday"] = ""; K["atime"] = ""; K["astage"] = 0; K["amsg"] = ""
            elif ch == 27:                 # Esc: Stufe zurück bzw. Formular verlassen
                if K["astage"] > 0:
                    K["astage"] -= 1; K["amsg"] = ""
                else:
                    K["mode"] = "view"; K["amsg"] = ""; K["editing"] = None
            elif ch in (10, 13, curses.KEY_ENTER):
                if K["astage"] == 0:
                    bad = (k_parse_byday(K["aday"]) is None) if is_rt else (k_parse_day(K["aday"]) is None)
                    if bad:
                        K["amsg"] = "wochentag? Mo/Di/.." if is_rt else "datum? TT.MM"
                    else:
                        K["astage"] = 1; K["amsg"] = ""
                elif K["astage"] == 1:
                    if is_span:                # Stufe 1 = Bis-Datum (Pflicht)
                        if k_parse_day(K["atime"]) is None:
                            K["amsg"] = "bis-datum? TT.MM"
                        else:
                            K["astage"] = 2; K["amsg"] = ""
                    elif K["atime"].strip() and parse_clock(K["atime"]) is None:
                        K["amsg"] = "zeit? HH:MM (leer=ganztags)"
                    else:
                        K["astage"] = 2; K["amsg"] = ""
                else:
                    k_add_save()
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                K[cur_key] = K[cur_key][:-1]
            elif 32 <= ch <= 126:
                cc = chr(ch)
                if K["astage"] == 0:
                    if is_rt and (cc.isalpha() or cc in ", ") and len(K["aday"]) < 24:
                        K["aday"] += cc            # Wochentag(e): Mo,Mi,Fr
                    elif (not is_rt) and (cc.isdigit() or cc in "./-") and len(K["aday"]) < 10:
                        K["aday"] += cc            # (Von-)Datum: TT.MM
                elif K["astage"] == 1:
                    if is_span and (cc.isdigit() or cc in "./-") and len(K["atime"]) < 10:
                        K["atime"] += cc           # Bis-Datum: TT.MM
                    elif (not is_span) and (cc.isdigit() or cc == ":") and len(K["atime"]) < 5:
                        K["atime"] += cc           # Zeit: HH:MM
                elif K["astage"] == 2 and len(K["alabel"]) < 60:
                    K["alabel"] += cc
        elif K["mode"] == "routine":       # Routine-Vorkommen de-/aktivieren / Routine löschen
            it = K["ract"] or {}
            if K["rconfirm"]:              # „ganze Routine löschen?" offen
                if ch in (ord("j"), ord("J"), ord("y"), ord("Y"), 10, 13, curses.KEY_ENTER):
                    k_routine_delete()
                elif ch != -1:
                    K["rconfirm"] = False
            elif ch == 27:                 # Esc → zurück ohne Änderung
                K["mode"] = "view"; K["ract"] = None
            elif ch in (ord("x"), ord("X")):   # x → ganze Routine löschen (mit Nachfrage)
                K["rconfirm"] = True
            elif it.get("deaktiviert") and ch in (ord("a"), ord("A"),
                                                  10, 13, curses.KEY_ENTER):
                k_routine_toggle(False)    # wieder aktivieren
            elif (not it.get("deaktiviert")) and ch in (ord("d"), ord("D"),
                                                        10, 13, curses.KEY_ENTER):
                k_routine_toggle(True)     # diesen Termin deaktivieren
        elif K["linput"] is not None:      # ›-Leisten-Eingabe: Sidebar (a/r) ODER Spannen-Zeit
            if ch == 27:                   # Esc → Eingabe abbrechen
                K["linput"] = None; K["ledit_iid"] = None; K["spantgt"] = None
            elif ch in (10, 13, curses.KEY_ENTER):
                txt = K["linput"].strip()
                if K["lmode"] == "spantime":    # per-Tag-Uhrzeit einer Spanne
                    if txt and parse_clock(txt) is None:
                        K["msg"] = "zeit? HH:MM (leer=ganztags)"
                    else:
                        tgt = K["spantgt"]
                        if tgt:
                            layer, von, label, day = tgt
                            api_call("/api/calendar/entry/spantime", method="POST",
                                     body={"layer": layer, "von": von, "label": label,
                                           "day": day, "time": txt})
                            K["msg"] = ("zeit gesetzt: " + txt) if txt else "wieder ganztags"
                            k_fetch()
                        K["linput"] = None; K["spantgt"] = None
                else:                           # Sidebar-Liste: neu / umbenennen
                    lid = k_sidebar_lid()
                    if txt and lid:
                        if K["lmode"] == "add":
                            api_call("/api/lists/%s/items" % lid, method="POST",
                                     body={"text": txt})
                        elif K["ledit_iid"] is not None:
                            api_call("/api/lists/%s/items/%s/rename" % (lid, K["ledit_iid"]),
                                     method="POST", body={"text": txt})
                        k_fetch()
                    K["linput"] = None; K["ledit_iid"] = None
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                K["linput"] = K["linput"][:-1]
            elif 32 <= ch <= 126 and len(K["linput"]) < 60:
                K["linput"] += chr(ch)
        elif K["confirmdel"]:              # Lösch-Nachfrage (Einmal-Termin) offen
            if ch in (ord("j"), ord("J"), ord("y"), ord("Y"), 10, 13, curses.KEY_ENTER):
                sels = k_selectable()
                if sels and 0 <= K["sel"] < len(sels) and not sels[K["sel"]]["recurring"]:
                    it = sels[K["sel"]]
                    # Mehrtägig: über den Start-Tag (von) löschen → ganze Spanne weg.
                    day = it.get("von") or it["iso"]
                    k_delete_sel((day, it["label"], it["layer"]))
                K["confirmdel"] = False
            elif ch != -1:                 # alles andere bricht ab
                K["confirmdel"] = False; K["msg"] = ""
        elif K["listfocus"]:               # Fokus in der Sidebar-Liste
            # Isolierte Einheit: bearbeiten ja (a/r/d/Space) + sortieren (s),
            # aber KEIN Move in andere Listen. lid/Items aus der letzten Antwort.
            lid = k_sidebar_lid()
            sit = k_sidebar_items()
            if ch in (ord("c"), ord("C")):                 # c → Kalender ganz zu
                K["active"] = False; K["listfocus"] = False; K["lsort"] = False
            elif ch in (ord("q"), ord("Q")):
                return BEENDEN
            elif ch in (ord("t"), ord("T")):
                cycle_theme()
            elif K["lsort"]:                               # ── Sortier-Modus ──
                if ch in (27, ord("s"), ord("S"), ord("l"), ord("L"),
                          10, 13, curses.KEY_ENTER):
                    K["lsort"] = False; K["msg"] = ""      # sortieren fertig
                elif ch in (curses.KEY_UP, ord("k"), curses.KEY_DOWN, ord("j")):
                    delta = -1 if ch in (curses.KEY_UP, ord("k")) else 1
                    if lid and 0 <= K["lsel"] < len(sit):
                        iid = sit[K["lsel"]]["id"]
                        api_call("/api/lists/%s/items/%s/reorder" % (lid, iid),
                                 method="POST", body={"delta": delta})
                        k_fetch()
                        for idx2, itx in enumerate(k_sidebar_items()):
                            if itx.get("id") == iid:       # Cursor dem Item nachziehen
                                K["lsel"] = idx2; break
            else:                                          # ── normaler Fokus ──
                if ch in (27, curses.KEY_LEFT, ord("h"), ord("l")):  # zurück zum Kalender
                    K["listfocus"] = False; K["msg"] = ""
                elif ch in (curses.KEY_UP, ord("k")):
                    K["lsel"] = max(0, K["lsel"] - 1)
                elif ch in (curses.KEY_DOWN, ord("j")):
                    K["lsel"] = min(max(0, len(sit) - 1), K["lsel"] + 1)
                elif ch in (ord(" "), 10, 13, curses.KEY_ENTER):   # abhaken (mit Link-Sync)
                    if lid and 0 <= K["lsel"] < len(sit):
                        api_call("/api/lists/%s/items/%s/toggle" % (lid, sit[K["lsel"]]["id"]),
                                 method="POST")
                        k_fetch()
                elif ch in (ord("s"), ord("S")):           # s → Sortier-Modus
                    if sit:
                        K["lsort"] = True; K["msg"] = ""
                elif ch in (ord("a"), ord("A")):           # a → neues Item
                    K["linput"] = ""; K["lmode"] = "add"; K["ledit_iid"] = None; K["msg"] = ""
                elif ch in (ord("r"), ord("R")):           # r → umbenennen
                    if 0 <= K["lsel"] < len(sit):
                        K["linput"] = str(sit[K["lsel"]].get("text", ""))
                        K["lmode"] = "rename"; K["ledit_iid"] = sit[K["lsel"]]["id"]; K["msg"] = ""
                elif ch in (ord("d"), ord("D")):           # d → löschen (nur Kopie, nicht Quelle)
                    if lid and 0 <= K["lsel"] < len(sit):
                        api_call("/api/lists/%s/items/%s" % (lid, sit[K["lsel"]]["id"]),
                                 method="DELETE")
                        k_fetch()
                elif ch in (ord("x"), ord("X")):           # erledigte ein/aus gilt auch hier
                    K["showhidden"] = not K["showhidden"]; K["lsel"] = 0
                    K["msg"] = "erledigte: " + ("an" if K["showhidden"] else "aus")
                elif ch == 9:                              # Tab: Monat hat keine Sidebar → Fokus raus
                    K["listfocus"] = False; k_toggle(); K["sel"] = 0; K["msg"] = ""
                elif ch in (ord("v"), ord("V")):           # v → Ansicht A/B/C
                    K["listfocus"] = False; self.k_stil_weiter()
        else:                              # View-Modus: blättern/auswählen
            if ch in (27, ord("c"), ord("C")):             # Esc/c → Kalender zu
                K["active"] = False
            elif ch in (ord("q"), ord("Q")):               # q → ganze TUI beenden
                return BEENDEN
            elif ch in (curses.KEY_LEFT, ord("h")):
                k_step(-1); K["sel"] = 0; K["msg"] = ""
            elif ch == curses.KEY_RIGHT:                   # → nächste Periode (l ist jetzt Sidebar)
                k_step(1); K["sel"] = 0; K["msg"] = ""
            elif ch in (ord("l"), ord("L")):               # l → Fokus in die Sidebar-Liste
                if K["view"] == "week":
                    K["listfocus"] = True; K["lsel"] = 0; K["msg"] = ""
                else:
                    K["msg"] = "liste nur in der wochenansicht"
            elif ch in (curses.KEY_UP, ord("k")):
                K["sel"] = max(0, K["sel"] - 1)
            elif ch in (curses.KEY_DOWN, ord("j")):
                K["sel"] = K["sel"] + 1    # Klemmung passiert beim Zeichnen
            elif ch == 9:                                  # Tab → Woche↔Monat
                k_toggle(); K["sel"] = 0; K["msg"] = ""
            elif ch in (ord("v"), ord("V")):               # v → Ansicht A/B/C (Sasha, 07.10.)
                self.k_stil_weiter()
            elif ch == ord("0"):                           # 0 → zurück zu heute
                k_today(); K["sel"] = 0; K["msg"] = ""
            elif ch in (ord("x"), ord("X")):               # x → erledigtes ein-/ausblenden
                # Ein Schalter für alles „passiert nicht": deaktivierte +
                # ausgefallene (Ferien/Pause) Termine + abgehakte Plan-Punkte.
                # Nur Anzeige-Filter → kein Neu-Laden nötig.
                K["showhidden"] = not K["showhidden"]; K["sel"] = 0
                K["msg"] = "erledigte: " + ("an" if K["showhidden"] else "aus")
            elif ch in (ord("a"), ord("A")):               # a → neuer Termin (Tab: Routine)
                K["mode"] = "add"; K["astage"] = 0; K["amsg"] = ""; K["msg"] = ""
                K["editing"] = None; K["atype"] = "entry"
                K["aday"] = date.fromisoformat(K["ref"]).strftime("%d.%m")
                K["atime"] = ""; K["alabel"] = ""
            elif ch in (ord("e"), ord("E"), 10, 13, curses.KEY_ENTER):   # bearbeiten
                if K["view"] == "week":
                    k_begin_edit()
            elif ch in (ord("d"), ord("D")):               # d → löschen / Routine-Screen
                if K["view"] == "week":
                    sels = k_selectable()
                    if sels and 0 <= K["sel"] < len(sels):
                        if sels[K["sel"]]["recurring"]:
                            K["mode"] = "routine"; K["ract"] = sels[K["sel"]]; K["msg"] = ""
                        else:
                            K["confirmdel"] = True; K["msg"] = ""
            elif ch in (ord("t"), ord("T")):               # Theme darf auch hier zyklieren
                cycle_theme()

    def draw_calendar(self, by, bx, bh, bw):
        """Inhalt der MITTE-Box, wenn der Kalender Fokus hat. Holt bei Bedarf
        frische Daten (Blättern/Umschalten) und zeichnet Woche (Liste) oder
        Monat (Gitter) — die Datums-Logik kam fertig vom Backend.

        Die Teile (Formular, Routine-Screen, Monat, Woche mit Tagen und
        Sidebar) stehen seit 06.10.2026 in eigenen _kal_*-Methoden; am Stück
        waren es 432 Zeilen, ein Riese nach dem Kern-Bauplan."""
        C, K, addclip, k_fetch = self.z.C, self.K, self.z.addclip, self.k_fetch
        ix, iw = bx + 2, bw - 4
        bottom = by + bh - 2          # Status-/Hilfezeile unten in der Box
        if iw < 8:
            return
        if K["stil"] and K["mode"] == "view" and not K["listfocus"]:
            self._kal_stil(by, bx, bh, bw)
            return
        if (not K["data"]) or K["data"].get("_for") != (K["view"], K["ref"]):
            k_fetch()
            if isinstance(K["data"], dict):
                K["data"]["_for"] = (K["view"], K["ref"])
        d = K["data"]
        if not d or d.get("failed"):
            addclip(by + 1, ix, K["msg"] or "lade kalender…", iw, C["faint"])
            return

        # Defensiv wie der ganze Render-Pfad: alles kommt über HTTP/JSON, ein
        # kaputtes Backend kann statt dict/list auch String/Zahl/None liefern.
        days = d.get("days")
        if not isinstance(days, dict):
            days = {}
        today = d.get("today")
        label = d.get("label", "")
        if not isinstance(label, str):
            label = ""
        alarms = d.get("alarms")
        nalarm = len(alarms) if isinstance(alarms, list) else 0
        # Zyklus-Marker der sichtbaren Tage ({iso: 'pms'|'next'}), abgeleitet vom
        # Backend aus dem »periode«-Graphen (core/cycle.py) — kein Kalender-Layer,
        # nichts Gespeichertes, reine Tönung. Defensiv: fehlt/kaputt → leer.
        cmarks = d.get("cycle")
        if not isinstance(cmarks, dict):
            cmarks = {}
        head = ("Woche " if K["view"] == "week" else "Monat ") + label
        if nalarm:
            head += "  ⚠%d" % nalarm
        addclip(by + 1, ix, head, iw, C["bright"])

        # Add-/Edit-Formular hat Vorrang: füllt den Body, wenn mode == "add".
        if K["mode"] == "add":
            self._kal_formular(by, ix, iw, bottom)
            return

        # Routine-Screen: ein einzelnes Vorkommen de-/aktivieren ODER die ganze
        # Routine löschen.
        if K["mode"] == "routine":
            self._kal_routine(by, ix, iw, bottom)
            return

        if K["view"] == "month":
            if not self._kal_monat(by, ix, iw, bottom, d, days, today, cmarks):
                return
            span_hint = ""
        else:
            span_hint = self._kal_woche(by, ix, iw, bottom, d, days, today, cmarks)
            if span_hint is None:
                return

        info = "%s · %s" % ("woche" if K["view"] == "week" else "monat", label)
        if span_hint:
            info += "   " + span_hint
        addclip(bottom, ix, info, iw, C["bright"])
        if K["confirmdel"]:                    # Shortcuts liegen unter '/'
            hint = "löschen? j/n"
        else:
            hint = K["msg"]
        if hint:
            addclip(bottom, ix + iw - len(hint), hint, len(hint), C["faint"])

    def _kal_formular(self, by, ix, iw, bottom):
        """Das Add-/Edit-Formular (Termin, Routine, Mehrtägig) füllt den Body."""
        C, K, addclip, safe_addstr = self.z.C, self.K, self.z.addclip, self.z.safe_addstr
        fy = by + 3
        cz = "_"                        # Cursor-Marker an der aktiven Stufe
        is_rt = (K["atype"] == "routine")
        is_span = (K["atype"] == "span")
        if K["editing"]:
            title = "TERMIN ÄNDERN"
        elif is_rt:
            title = "NEUE ROUTINE"
        elif is_span:
            title = "MEHRTÄGIG"
        else:
            title = "NEUER TERMIN"
        addclip(fy, ix, title, iw, C["bright"])
        # Typ-Umschalter (nur bei Neuanlage, nicht beim Ändern).
        if not K["editing"]:
            tabs = [("Termin", not is_rt and not is_span),
                    ("Routine", is_rt), ("Mehrtägig", is_span)]
            xx = ix + len(title) + 3
            for name, on in tabs:
                seg = ("[%s]" % name) if on else (" %s " % name)
                safe_addstr(fy, xx, seg, C["acc"] if on else C["faint"])
                xx += len(seg) + 1
            safe_addstr(fy, xx + 1, "(Tab)", C["faint"])
        if is_rt:
            addclip(fy + 2, ix, "Tag:   " + K["aday"] + (cz if K["astage"] == 0 else "")
                    + "   (Mo/Di/.., mehrere mit Komma)", iw,
                    C["bright"] if K["astage"] == 0 else C["dim"])
        else:
            lbl0 = "Von:   " if is_span else "Datum: "
            addclip(fy + 2, ix, lbl0 + K["aday"] + (cz if K["astage"] == 0 else "")
                    + "   (TT.MM, leer=heute)", iw, C["bright"] if K["astage"] == 0 else C["dim"])
        if is_span:
            addclip(fy + 3, ix, "Bis:   " + K["atime"] + (cz if K["astage"] == 1 else "")
                    + "   (TT.MM, letzter tag)", iw, C["bright"] if K["astage"] == 1 else C["dim"])
        else:
            addclip(fy + 3, ix, "Zeit:  " + K["atime"] + (cz if K["astage"] == 1 else "")
                    + "   (HH:MM, leer=ganztags)", iw, C["bright"] if K["astage"] == 1 else C["dim"])
        addclip(fy + 4, ix, "Titel: " + K["alabel"] + (cz if K["astage"] == 2 else ""),
                iw, C["bright"] if K["astage"] == 2 else C["dim"])
        addclip(bottom, ix, ("enter weiter/speichern · esc zurück  " + K["amsg"]).strip(),
                iw, C["faint"])

    def _kal_routine(self, by, ix, iw, bottom):
        """Routine-Screen: ein Vorkommen de-/aktivieren oder die ganze Routine löschen."""
        C, K, addclip = self.z.C, self.K, self.z.addclip
        it = K["ract"] or {}
        fy = by + 3
        try:
            wd = KAL_WD[date.fromisoformat(it.get("iso", "")).weekday()]
            dd = date.fromisoformat(it["iso"]).strftime("%d.%m.%Y")
        except (KeyError, ValueError):
            wd, dd = "", it.get("iso", "")
        t = (it.get("time") or "")
        addclip(fy, ix, "ROUTINE-TERMIN", iw, C["bright"])
        addclip(fy + 2, ix, "%s  ·  %s %s %s" % (it.get("label", "?"), wd, dd, t), iw, C["dim"])
        if K["rconfirm"]:
            addclip(fy + 4, ix, "GANZE Routine '%s' löschen?" % it.get("label", "?"), iw, C["warn"])
            addclip(fy + 5, ix, "(alle Vorkommen, unwiderruflich)", iw, C["faint"])
            addclip(bottom, ix, "j = ja, löschen · sonst abbrechen", iw, C["faint"])
        elif it.get("deaktiviert"):
            addclip(fy + 4, ix, "Dieser Termin ist DEAKTIVIERT.", iw, C["faint"])
            addclip(bottom, ix, "a = wieder aktivieren · x = Routine ganz löschen · esc", iw, C["faint"])
        else:
            addclip(fy + 4, ix, "Nur DIESEN Termin deaktivieren (d)?", iw, C["dim"])
            addclip(fy + 5, ix, "oder die GANZE Routine löschen (x)?", iw, C["faint"])
            addclip(bottom, ix, "d = nur dieser aus · x = ganze Routine löschen · esc", iw, C["faint"])

    def _kal_monat(self, by, ix, iw, bottom, d, days, today, cmarks):
        """Monatsgitter. -> False, wenn die Antwort kaputt ist (dann ohne Fußzeile)."""
        C, K, addclip = self.z.C, self.K, self.z.addclip
        # Monatsgitter: 7 Spalten Mo-So, bis zu 6 Wochenzeilen.
        colw = max(3, iw // 7)
        for c, wd in enumerate(KAL_WD):
            addclip(by + 2, ix + c * colw, wd, colw, C["faint"])
        try:
            start = date.fromisoformat(d["start"]); end = date.fromisoformat(d["end"])
            first = date.fromisoformat(d["first"]); last = date.fromisoformat(d["last"])
        except (KeyError, ValueError):
            return False
        row, cur = by + 3, start
        while cur <= end and row < bottom:
            c = cur.weekday()
            iso = cur.isoformat()
            in_month = first <= cur <= last
            ents = days.get(iso)
            if isinstance(ents, list) and not K["showhidden"]:
                ents = [e for e in ents
                        if not (isinstance(e, dict)
                                and (e.get("deaktiviert") or e.get("ausfall")))]
            has = bool(ents) and isinstance(ents, list)
            # Zyklus: ◆ = vorhergesagter Perioden-Start, · = PMS-Fenster.
            # Der Marker steht IMMER (auch wenn Termine da sind); die Farbe
            # nimmt sich der Tag nur, wenn er sonst nichts zu sagen hat —
            # ein Termin bleibt wichtiger als eine Schätzung.
            cyc = cmarks.get(iso)
            cell = "%2d" % cur.day + ("•" if has else "") + \
                ("◆" if cyc == "next" else ("·" if cyc == "pms" else ""))
            if iso == today:
                attr = C["bright"] | curses.A_REVERSE
            elif not in_month:
                attr = C["faint"]
            elif has:
                attr = C["acc"]
            elif cyc:
                attr = C["cyc"]
            else:
                attr = C["dim"]
            addclip(row, ix + c * colw, cell, colw, attr)
            if c == 6:                 # Sonntag → nächste Zeile
                row += 1
            cur += timedelta(days=1)
        return True

    def _kal_woche(self, by, ix, iw, bottom, d, days, today, cmarks):
        """Wochenansicht mit Spann-Gosse und Sidebar. -> ▶-Hinweis für die
        Fußzeile, oder None, wenn die Antwort kaputt ist (dann ohne Fußzeile)."""
        C, K, addclip, k_selectable = self.z.C, self.K, self.z.addclip, self.k_selectable
        k_sidebar_items, safe_addstr = self.k_sidebar_items, self.z.safe_addstr
        span_hint = ""                 # ▶-Hinweis, wenn ein Spann-Tag gewählt ist
        # Wochenansicht: normale Mo-So-Kalenderwoche. Pro Tag ein
        # zeilen-ausgerichtetes BAND — links die Termine (auswählbar,
        # ›-Cursor/K["sel"]), rechts die zugeordneten Items der »week«-Liste
        # (week_plan rollt: dieser Wochentag = sein nächstes Vorkommen ab
        # heute, erscheint also am passenden Datum dieser Woche). Die Bänder
        # stapeln sich, jeder Tag hat seine eigene Höhe → Montag-Items können
        # NICHT in die Dienstag-Zeile bluten. Passt alles in die Box →
        # natürliche Höhe (gestreckt); reicht der Platz nicht → pro Tag
        # einklappen ("…+N"). Reihenfolge der Termine = k_selectable().
        try:
            start = date.fromisoformat(d["start"]); end = date.fromisoformat(d["end"])
        except (KeyError, ValueError):
            return None
        # Sidebar = flache »week«-Liste (wochenunabhängig), EINE Spalte über
        # die volle Höhe — NICHT mehr pro Tag. sitems = sichtbare Items
        # (abgehakte via 'x' aus). lsel defensiv klemmen.
        sitems = k_sidebar_items()
        if K["lsel"] >= len(sitems):
            K["lsel"] = max(0, len(sitems) - 1)
        nsel = len(k_selectable())
        if K["sel"] >= nsel:
            K["sel"] = max(0, nsel - 1)

        # Spalten: links Termine, rechts Wochenplan (nur wenn breit genug).
        rcw = max(0, (iw - 3) * 2 // 5)        # ~40 % für die Plan-Spalte
        if rcw < 8:
            rcw = 0                             # zu schmal → keine Plan-Spalte
        lcw = iw - rcw - (1 if rcw else 0)     # Rest links (− Trenner)
        divx = ix + lcw                         # Spalte des "│"-Trenners

        # Pro Tag die Zeilen einsammeln (_kal_woche_tage).
        days_rows, span_map = self._kal_woche_tage(start, end, days)

        # Spann-Gosse links: je Mehrtages-Termin EINE durchgehende Klammer über
        # alle betroffenen Tages-Zeilen; überlappende Spannen bekommen eigene
        # Spalten (Lanes, Greedy). gw = Gossenbreite → die Tages-Spalte rückt
        # um gw(+1) nach rechts, damit die Klammer außerhalb der Daten steht.
        spans = []
        for _key, sm in span_map.items():
            idxs = [c[0] for c in sm["cells"]]
            spans.append({"label": sm["label"], "cells": sm["cells"],
                          "d0": min(idxs), "d1": max(idxs)})
        spans.sort(key=lambda s: (s["d0"], s["d1"]))
        lane_end = []                           # letzter belegter day_idx je Lane
        for s in spans:
            s["lane"] = None
            for li in range(len(lane_end)):
                if s["d0"] > lane_end[li]:
                    lane_end[li] = s["d1"]; s["lane"] = li; break
            if s["lane"] is None:
                s["lane"] = len(lane_end); lane_end.append(s["d1"])
        gw = min(len(lane_end), max(0, (iw - rcw) // 4))
        cx = ix + (gw + 1 if gw else 0)         # Start-Spalte der Tages-Inhalte
        lw = (divx - cx) if rcw else (ix + iw - cx)
        if lw < 6:                              # Notbremse: zu schmal → keine Gosse
            gw = 0; cx = ix; lw = lcw if rcw else iw

        # Höhen verteilen: Bedarf je Tag = max(links, rechts, 1) Inhaltszeilen
        # (+1 Kopfzeile). Passt die Summe → jeder bekommt seinen Bedarf;
        # sonst fair aufteilen und den Rest reihum an die Hungrigen geben.
        y0 = by + 2
        avail = bottom - y0
        nd = len(days_rows)
        needs = [max(len(l), len(r), 1) for (_c, _i, l, r) in days_rows]
        caps = [0] * nd
        budget = avail - nd                     # je Tag eine Kopfzeile abziehen
        if budget > 0 and nd:
            base = budget // nd
            for i in range(nd):
                caps[i] = min(needs[i], base)
            leftover = budget - sum(caps)
            i = 0
            while leftover > 0 and any(caps[j] < needs[j] for j in range(nd)):
                if caps[i] < needs[i]:
                    caps[i] += 1; leftover -= 1
                i = (i + 1) % nd

        # Bleibt nach dem Füllen Höhe übrig (großes Display), als etwas Luft
        # ZWISCHEN die Tage geben, statt sie unten zu sammeln — dezent
        # (max 2 Leerzeilen je Lücke), Trenner läuft durch.
        gap = min(2, max(0, (avail - (nd + sum(caps))) // max(1, nd - 1)))

        day_top = [None] * nd                   # y der Kopfzeile je Tag
        day_bot = [None] * nd                   # y der letzten Zeile je Tag
        yy = y0
        for idx, (cd, iso, left, right) in enumerate(days_rows):
            if yy >= bottom:
                break
            day_top[idx] = yy
            is_today = (iso == today)
            hdr = "%s %s" % (KAL_WD[cd.weekday()], cd.strftime("%d.%m."))
            # Zyklus-Anhang an der Tages-Kopfzeile (aus dem »periode«-Graphen
            # geschätzt): der vorhergesagte Start als ◆, die Woche davor als
            # leises »· pms«. Heute behält seine eigene Hervorhebung.
            cyc = cmarks.get(iso)
            if cyc == "next":
                hdr += "  ◆ periode (erwartet)"
            elif cyc == "pms":
                hdr += "  · pms"
            addclip(yy, cx, hdr + ("  ‹heute›" if is_today else ""),
                    lw, C["bright"] if is_today else (C["cyc"] if cyc else C["acc"]))
            if rcw:
                safe_addstr(yy, divx, "│", C["faint"])
            day_bot[idx] = yy
            yy += 1
            cap = caps[idx]
            for r in range(cap):
                if yy >= bottom:
                    break
                if rcw:
                    safe_addstr(yy, divx, "│", C["faint"])
                # Linke Spalte: Termine (letzte sichtbare Zeile klappt den Rest ein).
                if r < len(left):
                    if r == cap - 1 and len(left) > cap:
                        addclip(yy, cx, "  …+%d" % (len(left) - cap + 1), lw, C["faint"])
                    else:
                        txt, attr, dd = left[r]
                        if dd is None:
                            addclip(yy, cx, txt, lw, attr)
                        else:
                            mark = "› " if dd == K["sel"] else "  "
                            addclip(yy, cx, mark + txt, lw, attr)
                elif not left and r == 0:
                    addclip(yy, cx + 2, "—", lw - 2, C["faint"])
                # (rechte Spalte: siehe Sidebar-Block nach der Tages-Schleife)
                day_bot[idx] = yy
                yy += 1
            # Luft zwischen den Tagen (nicht nach dem letzten); Trenner durch.
            if gap and idx < nd - 1:
                for _g in range(gap):
                    if yy >= bottom:
                        break
                    if rcw:
                        safe_addstr(yy, divx, "│", C["faint"])
                    yy += 1

        # ── Spann-Gosse zeichnen: durchgehende Klammer + senkrechter Titel ──
        # ┌ am ersten sichtbaren Tag, └ am letzten; dazwischen laufen die
        # Titel-Buchstaben AM STÜCK nach unten (ein Zeichen pro Zeile), Rest
        # als │. Der ausgewählte Tag (Cursor) hebt seinen Klammer-Abschnitt
        # invers hervor — so bleibt die Spanne per ↑↓ ansteuerbar (e/d).
        for s in spans:
            lane = s["lane"]
            if lane >= gw or s["d0"] >= nd or s["d1"] >= nd:
                continue
            ytop, ybot = day_top[s["d0"]], day_bot[s["d1"]]
            if ytop is None or ybot is None:
                continue
            gx = ix + lane
            title = s["label"] or "?"
            sel_day = next((dd for (dd, ddi) in s["cells"] if ddi == K["sel"]), None)
            for y in range(ytop, ybot + 1):
                if y == ytop:
                    chc = "┌"
                elif y == ybot:
                    chc = "└"
                else:
                    pos = y - (ytop + 1)
                    chc = title[pos] if pos < len(title) else "│"
                hot = (sel_day is not None and day_top[sel_day] is not None
                       and day_top[sel_day] <= y <= day_bot[sel_day])
                safe_addstr(y, gx, chc,
                            (C["bright"] | curses.A_REVERSE) if hot else C["span"])
            if sel_day is not None:
                span_hint = "▶ %s · %s" % (title, days_rows[sel_day][1])

        # ── Sidebar: flache »week«-Liste (rechte Spalte, volle Höhe) ──
        # Unabhängig von den Tages-Bändern. 'l' schiebt den Fokus hierher
        # (‹fokus›), dann bearbeitbar (a/r/d/Space). Abgehakte via 'x' aus.
        if rcw:
            self._kal_sidebar(y0, bottom, ix, iw, divx, sitems)
        return span_hint

    def _kal_woche_tage(self, start, end, days):
        """Woche: pro Tag die Zeilen einsammeln. -> (days_rows, span_map).
        days_rows = [(datum, iso, [(text, attr, di|None)], [])]; span_map
        sammelt die Mehrtages-Termine für die Spann-Gosse."""
        C, K = self.z.C, self.K
        # Pro Tag die Zeilen einsammeln. di läuft über ALLE Termine in
        # k_selectable-Reihenfolge (sortierte Tage, Eintragsreihenfolge);
        # Ausfälle (Ferien) sind reine Info (di=None, nicht auswählbar).
        days_rows = []
        di = 0
        span_map = {}          # (von,label,layer) → {"label", "cells":[(day_idx,di)]}
        day_idx = 0
        cur = start
        while cur <= end:
            iso = cur.isoformat()
            ents = days.get(iso)
            if not isinstance(ents, list):
                ents = []
            left = []                           # [(txt, attr, di|None)]
            for e in ents:
                if not isinstance(e, dict):
                    continue
                if e.get("ausfall"):
                    # Ferien/Pausen-Ausfall (add_pause über Zeitraum) ist
                    # dieselbe Sorte „passiert nicht" wie einzeln deaktiviert
                    # → GLEICHER Toggle. Reine Info (di=None), berührt den
                    # Auswahl-Index nie → kein Sync-Problem mit k_selectable.
                    if not K["showhidden"]:
                        continue
                    left.append(("  " + _k_entry_line(e, iso), C["faint"], None))
                    continue
                if e.get("deaktiviert") and not K["showhidden"]:
                    continue   # ausgeblendet: NICHT zeichnen und di NICHT
                    # erhöhen → Index bleibt synchron mit k_selectable().
                cur_di = di; di += 1
                if e.get("spanning"):
                    # Mehrtägig: NICHT inline (sonst reißt die Klammer, sobald
                    # der Tag andere Termine hat) → sammeln für die linke
                    # Spann-Gosse. di trotzdem zählen → Sync mit k_selectable;
                    # auswählbar bleibt es (Cursor hebt die Gosse des Tages).
                    key = (e.get("von"), e.get("label"), e.get("layer"))
                    sm = span_map.setdefault(
                        key, {"label": e.get("label") or "?", "cells": []})
                    sm["cells"].append((day_idx, cur_di))
                    continue
                if e.get("deaktiviert"):
                    left.append(("✗ " + _k_entry_line(e, iso) + "  (aus)", C["faint"], cur_di))
                elif cur_di == K["sel"]:
                    left.append((_k_entry_line(e, iso), C["bright"] | curses.A_REVERSE, cur_di))
                else:
                    left.append((_k_entry_line(e, iso), C["dim"], cur_di))
            # Rechte Spalte pro Tag gibt es nicht mehr — die Sidebar ist EINE
            # flache Liste (unten separat). right bleibt leer, damit die
            # Höhenverteilung nur die Termine (links) berücksichtigt.
            days_rows.append((cur, iso, left, []))
            day_idx += 1
            cur += timedelta(days=1)
        return days_rows, span_map

    def _kal_sidebar(self, y0, bottom, ix, iw, divx, sitems):
        """Sidebar: die flache »week«-Liste rechts, über die volle Höhe."""
        C, K, addclip, safe_addstr = self.z.C, self.K, self.z.addclip, self.z.safe_addstr
        for yv in range(y0, bottom):        # Trenner über die volle Höhe
            safe_addstr(yv, divx, "│", C["faint"])
        foc = K["listfocus"]
        sx = divx + 1                        # Cursor-Gosse ab hier
        sw = ix + iw - sx                    # Restbreite rechts
        if K["linput"] is not None and K["lmode"] in ("add", "rename"):
            head = "liste  ‹" + ("neu" if K["lmode"] == "add"
                                 else "umbenennen") + " unten›"
        elif K["lsort"]:
            head = "liste  ‹sortieren ↑↓›"
        elif foc:
            head = "liste  ‹fokus›"
        else:
            head = "liste"
        addclip(y0, sx + 1, head, sw - 1, C["bright"] if foc else C["acc"])
        sy = y0 + 1
        avail = max(0, bottom - sy)          # verfügbare Zeilen
        step = 2                             # 1 Leerzeile Abstand je Item
        cap = max(1, (avail + 1) // step)    # so viele Items passen
        n = len(sitems)
        off = (min(max(0, K["lsel"] - cap // 2), max(0, n - cap))
               if (foc and n > cap) else 0)
        if n == 0:
            addclip(sy, sx + 1, "— leer (a: neu)", sw - 1, C["faint"])
        else:
            # Ombre: nach unten (visible-Position) progressiv transparenter.
            ombre = C.get("ombre") or [C["dim"]]
            shown = 0
            i = off
            while i < n and shown < cap:
                yy2 = sy + shown * step
                if shown == cap - 1 and (n - off) > cap:
                    addclip(yy2, sx + 1, "…+%d" % (n - off - cap + 1),
                            sw - 1, C["faint"])
                    break
                it = sitems[i]
                done = bool(it.get("done"))
                cur_s = foc and i == K["lsel"]
                head_mark = ("⇅ " if (cur_s and K["lsort"])
                             else ("› " if cur_s else "  "))
                txt = (head_mark + ("✓ " if done else "• ")
                       + str(it.get("text", ""))
                       + (" ↔" if it.get("linked") else ""))
                attr = ((C["bright"] | curses.A_REVERSE) if cur_s
                        else ombre[min(shown, len(ombre) - 1)])
                addclip(yy2, sx, txt, sw, attr)
                i += 1
                shown += 1
