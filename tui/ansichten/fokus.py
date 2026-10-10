# tui/ansichten/fokus.py
#
# Das Listen-/Fokus-Werkzeug der TUI (Zeichner gegen /api/lists und
# /api/projects; die Logik liegt in core/lists.py). Bis 06.10.2026 Closures in
# run_ui (tui/zentrale_tui.py), die Zähl-/Ordnungs-Helfer auf Modulebene dort;
# siehe memory/system/tui_bauplan.md.

import curses
import time

try:                                    # Pixel-Baustein (tui/pixel.py)
    from tui import pixel
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    import pixel

from .basis import BEENDEN, api_call
import listen_baum  # noqa: E402  – core/, eingehängt von basis.kern_pfad


def bar(pct, length=10):
    """Zweifarbiger Balken-String: n gefüllt + Rest leer. (Ohne Farbe hier.)"""
    n = round(max(0.0, min(100.0, pct)) / 100.0 * length)
    return "█" * n + "░" * (length - n)


# Die reinen Baum-Helfer wohnen seit 2026-10-10 in core/listen_baum.py — die
# Listen-Kachel (core/kachel_fokus.py) zeigt eine Liste damit genauso wie
# diese Ansicht. Hier unter den alten Namen.
liste_zaehlen = listen_baum.zaehlen
liste_erledigt = listen_baum.erledigt
liste_hat_fokus = listen_baum.hat_fokus
liste_ordnen = listen_baum.ordnen
bernstein_steine = listen_baum.steine
l_path_to = listen_baum.pfad_zu
l_flatten = listen_baum.flach
l_count = listen_baum.zaehlen
l_done = listen_baum.erledigt
l_find_item = listen_baum.finden


def l_toggle_msg(it):
    """Rückmeldung nach dem Abhaken: abgehakt wandert's in den Bernstein."""
    return "wieder offen" if it.get("done") else "◆ in den bernstein"


class Fokus:
    """Das Listen-/Fokus-Werkzeug (Mitte, Taste 'f'): oben die Projekte,
    darunter die anderen Listen, reindiven wie Ordner, abhaken, umbenennen,
    verschieben, einordnen, fokussieren. proj_render zeichnet auch die
    focus-Box des alten Dashboards. Zustand in self.L (auch z.L)."""

    def __init__(self, z):
        self.z = z
        # ── Listen-Werkzeug (füllt die MITTE-Box, Taste 'l') ────────────────
        # Pendant zum Graph-Werkzeug, aber für abhakbare Todo-/Sammel-Listen.
        # Geteilte Logik (core/lists.py + /api/lists), hier in der TUI verbaut.
        #   active : Werkzeug hat den Fokus
        #   view   : "list" (Listen wählen) | "new" (anlegen) | "view" (Einträge)
        #            | "place" (Knoten Forest-weit einordnen, ">" auf Liste/Eintrag)
        #   sel    : ausgewählte Liste (in "list"); isel: ausgewählter Eintrag (in "view")
        #   adding : in "view" tippen wir gerade einen neuen Eintrag (input)
        #   addparent: id des Eltern-Eintrags beim Tippen (None = oberste Ebene)
        #   imode  : was die Eingabezeile tut — "add"|"sub"|"rename"
        #   edit_iid: beim Umbenennen die id des Eintrags (imode "rename")
        #   lrename: in "new" benennen wir eine bestehende Liste um (id) statt neu
        #   move_iid/nsel: zu verschiebender Eintrag + Zielauswahl ("move"/"move_new")
        #   place_kind/lid/iid: Quell-Knoten beim Einordnen ("place"); nsel = Zielindex
        # Einträge sind Mischtypen: jeder kann eigene Unterpunkte ('items') tragen.
        # In "view" navigiert man wie Ordner: ein Eintrag MIT Kindern ist eine
        # anklickbare Zeile (Enter = reingehen), kein aufgeklappter Baum. path ist
        # der Drill-Pfad (Eintrags-ids) innerhalb der offenen Liste def; isel zählt
        # die DIREKTEN Kinder der gerade offenen Ebene.
        # ── Listen-/Fokus-Werkzeug (füllt die MITTE-Box, Taste 'f'/'l') ─────
        # EIN gemergtes Werkzeug: Look + Reindive-Navigation der früheren
        # Projektansicht (verschachtelte Kästen + Erfüllungsleisten, proj_render)
        # PLUS die volle Editier-Macht des alten Listen-Werkzeugs. Die Wurzel
        # ("forest") ist ZWEIGETEILT: oben die geflaggten Projekte (/api/projects),
        # eine Trennlinie, drunter alle anderen (Nicht-Projekt-)Listen — beide
        # top-level, per enter reindivebar. Ab da ist es die normale Ordner-Sicht
        # einer Liste ("view", def+path). 'f'/space setzt JEDEN Knoten als
        # alleinigen Fokus (rendert dann allein in der rechten FOCUS-Box).
        #   view : "forest" (zwei-Zonen-Wurzel) | "view" (in einer Liste) |
        #          "new" (Liste anlegen/umbenennen) | "place"/"move"/"move_new"
        #   proots : Projekt-Roots als Deskriptoren [{lid,iid}] (iid None = Liste)
        #   fsel   : Cursor-Index in der Forest-Wurzel (proots + Nicht-Projekt-Listen)
        #   isel   : in "view" Index in liste_ordnen(…) der offenen Ebene; -1 =
        #            die Bernsteinleiste oben (enter → abgeschlossene zeigen)
        #   showdone: in "view" nur die abgeschlossenen Einträge der Ebene zeigen
        self.L = z.L = {"active": False, "view": "forest", "lists": [], "sel": 0,
                        "proots": [], "fsel": 0,      # Forest-Wurzel: Projekt-Roots + Cursor
                        "fedit": None,                # Deskriptor beim Inline-Umbenennen (forest)
                        "def": None, "isel": 0, "path": [], "adding": False, "input": "",
                        "showdone": False,
                        "msg": "",
                        "confirm": False,             # Lösch-Nachfrage für ganze Liste
                        "addparent": None,            # Eltern-id beim Anhängen (None = top)
                        "imode": "add",               # Eingabezeile: add|sub|rename
                        "edit_iid": None,             # umzubenennender Eintrag (imode rename)
                        "lrename": None,              # umzubenennende Liste (in "new")
                        "move_iid": None,             # zu verschiebender Eintrag ("move")
                        # Einordnen (">", Forest-weit): Quelle = Liste ODER Eintrag
                        "place_kind": None, "place_lid": None, "place_iid": None,
                        "nsel": 0}                    # Zielwahl-Index (place/move/move_new)

    def l_load(self):
        """Listen-Definitionen (inkl. Einträge) UND die Projekt-Roots
        (/api/projects → obere Forest-Zone) frisch ziehen."""
        L, l_fclamp = self.L, self.l_fclamp
        try:
            L["lists"] = api_call("/api/lists") or []
        except Exception:
            L["lists"] = []
        try:
            pr = api_call("/api/projects") or []
        except Exception:
            pr = []
        roots = []
        for r in pr:
            if not isinstance(r, dict):
                continue
            plid = r.get("lid") or r.get("id")
            roots.append({"lid": plid,
                          "iid": None if r.get("id") == plid else r.get("id")})
        L["proots"] = roots
        if L["sel"] >= len(L["lists"]):
            L["sel"] = max(0, len(L["lists"]) - 1)
        l_fclamp()

    # ── Forest-Wurzel (zwei Zonen) + Fokus: Deskriptor-Helfer ───────────
    # Ein Knoten wird als {lid, iid} adressiert (iid None = ganze Liste). Die
    # Wurzel zeigt oben die Projekt-Roots, unten alle Nicht-Projekt-Listen;
    # per enter geht es in die normale Ordner-Sicht (def+path) einer Liste.
    def l_realnode(self, desc):
        """Echten Listen-/Eintrags-Dict zu {lid,iid} aus L['lists'] — oder None."""
        L = self.L
        if not isinstance(desc, dict):
            return None
        lst = next((l for l in L["lists"]
                    if isinstance(l, dict) and l.get("id") == desc.get("lid")), None)
        if lst is None:
            return None
        if desc.get("iid") is None:
            return lst
        return l_find_item(lst.get("items"), desc.get("iid"))

    def l_desc_view(self, desc):
        """Flacher Anzeige-Knoten {name,done,total,branch,focus,project,whole,
        lid,iid} für proj_render (KEINE children → als eingeklappte Zeile mit
        Leiste gezeichnet, ▸ wenn er Unterpunkte hätte)."""
        l_realnode = self.l_realnode
        node = l_realnode(desc)
        if node is None:
            return None
        kids = node.get("items")
        if isinstance(kids, list) and kids:
            d, t = l_count(kids)
        else:
            d, t = (1 if node.get("done") else 0, 1)
        whole = desc.get("iid") is None
        name = node.get("name") if whole else node.get("text")
        return {"lid": desc["lid"], "iid": desc.get("iid"),
                "name": str(name or ""), "done": d, "total": t,
                "branch": bool(isinstance(kids, list) and kids),
                "focus": bool(node.get("focus")),
                "project": bool(node.get("project")), "whole": whole}

    def l_forest_rows(self):
        """Zwei-Zonen-Wurzel als (rows, ndiv): oben die Projekt-Roots
        (/api/projects), dann alle NICHT-projekt-Listen. ndiv = Zahl der
        Projekt-Zeilen (danach kommt die Trennlinie)."""
        L, l_desc_view = self.L, self.l_desc_view
        rows = []
        for d in L.get("proots") or []:
            v = l_desc_view(d)
            if v:
                rows.append(v)
        ndiv = len(rows)
        for l in L["lists"]:
            if isinstance(l, dict) and not l.get("project"):
                v = l_desc_view({"lid": l.get("id"), "iid": None})
                if v:
                    rows.append(v)
        return rows, ndiv

    def l_fclamp(self):
        L, l_forest_rows = self.L, self.l_forest_rows
        rows, _ = l_forest_rows()
        if L["fsel"] >= len(rows):
            L["fsel"] = max(0, len(rows) - 1)

    def l_open_desc(self, desc):
        """Aus der Forest-Wurzel in einen Knoten reindiven → view='view'.
        Ganze Liste (iid None) → oberste Ebene; Eintrag → Drill-Pfad zu ihm."""
        L = self.L
        lst = next((l for l in L["lists"]
                    if isinstance(l, dict) and l.get("id") == desc.get("lid")), None)
        if lst is None:
            return
        L["def"] = lst
        if desc.get("iid") is None:
            L["path"] = []
        else:
            L["path"] = l_path_to(lst.get("items"), desc["iid"]) or []
        L["isel"] = 0; L["showdone"] = False
        L["adding"] = False; L["input"] = ""; L["msg"] = ""
        L["view"] = "view"

    def l_focus_toggle(self, desc):
        """Den Knoten {lid,iid} als alleinigen Fokus setzen (Toggle,
        /api/projects/focus) — für JEDEN Knoten, auch einen tiefen Unterpunkt."""
        L, l_load = self.L, self.l_load
        body = {"lid": desc["lid"]}
        if desc.get("iid") is not None:
            body["iid"] = desc["iid"]
        try:
            foc = api_call("/api/projects/focus", "POST", body)
            L["msg"] = ("fokus: " + foc["name"]) if foc else "fokus aus"
        except Exception:
            L["msg"] = "fokus fehlgeschlagen"
        l_load()

    def l_container(self):
        """Die gerade offene Ebene auflösen: (direkte Kinder, container-id,
        Breadcrumb-Liste) anhand L["def"] + L["path"]. container-id ist None auf
        oberster Ebene (Listen-Wurzel) bzw. die id des reingegangenen Eintrags.
        Ein gebrochener Pfad (Eintrag inzwischen weg) wird hier gekürzt."""
        L = self.L
        if not L["def"]:
            return [], None, []
        node = L["def"]
        pid = None
        crumbs = [str(L["def"].get("name") or "")]
        valid = []
        for iid in L["path"]:
            nxt = next((it for it in (node.get("items") or [])
                        if isinstance(it, dict) and it.get("id") == iid), None)
            if nxt is None:
                break
            node = nxt
            pid = iid
            valid.append(iid)
            crumbs.append(str(nxt.get("text") or ""))
        if valid != L["path"]:
            L["path"] = valid
        return (node.get("items") or []), pid, crumbs

    def l_vitems(self):
        """Die offene Ebene so, wie sie angezeigt wird (liste_ordnen): offen
        und sortiert — oder nur das Abgeschlossene (showdone)."""
        L, l_container = self.L, self.l_container
        items, _pid, _cr = l_container()
        return liste_ordnen(items, L["showdone"])

    def l_index_in_container(self, iid):
        """Index des Eintrags mit iid in der ANGEZEIGTEN Ebene (l_vitems; 0,
        wenn nicht da — z.B. gerade abgehakt und damit im Bernstein)."""
        l_vitems = self.l_vitems
        for i, it in enumerate(l_vitems()):
            if isinstance(it, dict) and it.get("id") == iid:
                return i
        return 0

    def l_move_targets(self):
        """Listen, in die der gewählte Eintrag wandern darf — alle außer der
        gerade offenen (raus = in eine ANDERE Liste)."""
        L = self.L
        cur = L["def"]["id"] if L["def"] else None
        return [l for l in L["lists"] if isinstance(l, dict) and l.get("id") != cur]

    def l_forest_targets(self, skind, slid, siid):
        """Alle Ziel-Knoten zum Einordnen über ALLE Listen hinweg — flach, mit
        Tiefe & Label, OHNE den eigenen Teilbaum (kein Zyklus). Jeder Eintrag:
        {lid, iid (None = Listen-Top als Ziel), label}. So kann `>` auf jeder
        Ebene jeden Knoten erreichen (oben wie unten gleich)."""
        L = self.L
        excl = set()                                  # eigener Teilbaum (nur item-Quelle)
        if skind == "item":
            src_lst = next((l for l in L["lists"] if isinstance(l, dict) and l.get("id") == slid), None)
            src = l_find_item((src_lst or {}).get("items"), siid)
            if src is not None:
                for it, _d in l_flatten([src]):
                    excl.add(it.get("id"))
        out = []
        for l in L["lists"]:
            if not isinstance(l, dict):
                continue
            lid = l.get("id")
            if skind == "list" and lid == slid:       # ganze Quell-Liste raus
                continue
            out.append({"lid": lid, "iid": None, "label": str(l.get("name") or "")})
            for it, d in l_flatten(l.get("items")):
                if skind == "item" and lid == slid and it.get("id") in excl:
                    continue                          # eigener Teilbaum
                out.append({"lid": lid, "iid": it.get("id"),
                            "label": "  " * (d + 1) + str(it.get("text") or "")})
        return out

    def l_sync_def(self):
        """Nach Änderungen die offene Liste aus der frisch geladenen Registry
        neu greifen (Einträge können dazugekommen / weg sein)."""
        L, l_container, l_vitems = self.L, self.l_container, self.l_vitems
        if not L["def"]:
            return
        cur = next((x for x in L["lists"] if x.get("id") == L["def"]["id"]), None)
        L["def"] = cur
        if cur is None:                       # Liste verschwunden → zurück zur Wurzel
            L["view"] = "forest"; L["path"] = []
            return
        l_container()                         # validiert/kürzt den Drill-Pfad
        n = len(l_vitems())
        if L["isel"] >= n:                    # -1 = Bernsteinleiste, wenn leer
            L["isel"] = n - 1

    def oeffnen(self):
        """Startseite → Fokus-Werkzeug: Wurzel (Projekte oben, Listen unten)."""
        L, l_load = self.L, self.l_load
        L["active"] = True; L["view"] = "forest"; L["fsel"] = 0
        L["adding"] = False; L["confirm"] = False; L["msg"] = ""; l_load()

    def zeige_liste(self, lid, iid=None):
        """Von außen (Adresse zentrale://fokus/<lid>[/<iid>],
        tui/ansichten/sprung.py, 2026-10-10): Werkzeug öffnen und in die Liste
        gehen — mit Eintrag: ein Ordner wird geöffnet, bei einem Punkt steht
        der Cursor auf ihm. Gibt es die Liste nicht mehr, bleibt die Wurzel
        offen und sagt es."""
        L = self.L
        self.oeffnen()
        lst = next((l for l in L["lists"]
                    if isinstance(l, dict) and l.get("id") == lid), None)
        if lst is None:
            L["msg"] = "diese liste gibt es nicht mehr"
            return True
        pfad = l_path_to(lst.get("items"), iid) if iid is not None else None
        if not pfad:
            self.l_open_desc({"lid": lid, "iid": None})
            return True
        item = l_find_item(lst.get("items"), iid)
        if isinstance(item.get("items"), list) and item.get("items"):
            self.l_open_desc({"lid": lid, "iid": iid})            # Ordner: hinein
            return True
        eltern = pfad[-2] if len(pfad) > 1 else None
        self.l_open_desc({"lid": lid, "iid": eltern})
        if l_done(item):
            L["showdone"] = True                                  # steckt im Bernstein
        L["isel"] = self.l_index_in_container(iid)
        return True

    def taste(self, ch):
        """Eine Taste, während das Fokus-Werkzeug den Fokus hat (früher ein Zweig
        der Hauptschleife in run_ui). Gibt BEENDEN zurück, wenn die TUI enden soll."""
        L = self.L
        if L["view"] == "forest":
            return self._taste_wald(ch)
        elif L["view"] == "view":
            return self._taste_ebene(ch)
        elif L["view"] == "place":  # Knoten (Liste/Eintrag) Forest-weit einordnen
            return self._taste_einordnen(ch)
        elif L["view"] == "move":  # Eintrag raus in eine andere Liste
            return self._taste_verschieben(ch)
        elif L["view"] == "move_new":  # Name für die neue Ziel-Liste tippen
            return self._taste_neue_liste(ch)

    def _taste_wald(self, ch):
        """Taste in der Wurzel (forest): oben die Projekte, unten die anderen Listen."""
        L, l_focus_toggle, l_forest_rows = self.L, self.l_focus_toggle, self.l_forest_rows
        l_load, l_move_targets = self.l_load, self.l_move_targets
        l_open_desc, l_realnode = self.l_open_desc, self.l_realnode
        # Zwei-Zonen-Wurzel: oben Projekte, unten andere Listen. cur =
        # gewählter Deskriptor {lid,iid,branch,whole,…}.
        rows, _ndiv = l_forest_rows()
        cur = rows[L["fsel"]] if 0 <= L["fsel"] < len(rows) else None
        enter = ch in (10, 13, curses.KEY_ENTER)
        if L["adding"]:                               # neue Liste / umbenennen tippen
            if ch == 27:
                L["adding"] = False; L["imode"] = "add"
                L["fedit"] = None; L["input"] = ""; L["msg"] = ""
            elif enter:
                txt = L["input"].strip()
                if not txt:
                    L["msg"] = "name fehlt"
                elif L["imode"] == "frename" and L["fedit"] is not None:
                    d = L["fedit"]
                    try:
                        if d.get("iid") is None:
                            api_call("/api/lists/%s/rename" % d["lid"], method="POST",
                                     body={"name": txt})
                        else:
                            api_call("/api/lists/%s/items/%d/rename" % (d["lid"], d["iid"]),
                                     method="POST", body={"text": txt})
                        L["msg"] = "umbenannt"
                    except Exception:
                        L["msg"] = "umbenennen fehlgeschlagen"
                    L["adding"] = False; L["imode"] = "add"
                    L["fedit"] = None; L["input"] = ""; l_load()
                else:                                 # neue Liste anlegen
                    try:
                        api_call("/api/lists", method="POST", body={"name": txt})
                        L["msg"] = "angelegt: " + txt
                    except Exception:
                        L["msg"] = "anlegen fehlgeschlagen"
                    L["adding"] = False; L["input"] = ""; l_load()
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                L["input"] = L["input"][:-1]
            elif 32 <= ch <= 126 and len(L["input"]) < 80:
                L["input"] += chr(ch)
        elif L["confirm"]:                            # Liste löschen? (Nachfrage)
            if ch in (ord("y"), ord("Y"), ord("j"), ord("J"),
                      10, 13, curses.KEY_ENTER):
                if cur and cur.get("iid") is None:
                    try:
                        api_call("/api/lists/" + str(cur["lid"]), method="DELETE")
                        L["msg"] = "gelöscht"
                    except Exception:
                        L["msg"] = "löschen fehlgeschlagen"
                L["confirm"] = False; l_load()
            elif ch != -1:                            # alles andere → abbrechen
                L["confirm"] = False; L["msg"] = ""
        elif ch in (27, ord("l"), ord("L")):           # Esc/l → Werkzeug zu
            L["active"] = False
        elif ch in (ord("q"), ord("Q")):               # q → ganze TUI beenden
            return BEENDEN
        elif ch in (curses.KEY_UP, ord("k")):
            if rows:
                L["fsel"] = (L["fsel"] - 1) % len(rows)
        elif ch in (curses.KEY_DOWN, ord("j")):
            if rows:
                L["fsel"] = (L["fsel"] + 1) % len(rows)
        elif enter or ch == curses.KEY_RIGHT:          # rein / (Blatt) abhaken
            if cur:
                if cur.get("iid") is None or cur.get("branch"):
                    l_open_desc(cur)                   # ganze Liste / Ordner → reindiven
                else:                                  # Blatt-Eintrag → abhaken
                    try:
                        api_call("/api/lists/%s/items/%d/toggle" % (cur["lid"], cur["iid"]),
                                 method="POST")
                        l_load()
                    except Exception:
                        L["msg"] = "umschalten fehlgeschlagen"
        elif ch == ord(" "):                           # space: Blatt-Eintrag abhaken
            if cur and cur.get("iid") is not None and not cur.get("branch"):
                try:
                    api_call("/api/lists/%s/items/%d/toggle" % (cur["lid"], cur["iid"]),
                             method="POST")
                    l_load()
                except Exception:
                    L["msg"] = "umschalten fehlgeschlagen"
        elif ch in (ord("f"), ord("F")):               # f: diesen Knoten fokussieren
            if cur:
                l_focus_toggle(cur)
        elif ch in (ord("n"), ord("N")):               # neue Liste (inline)
            L["adding"] = True; L["imode"] = "newlist"
            L["fedit"] = None; L["input"] = ""; L["msg"] = ""
        elif ch in (ord("r"), ord("R")):               # umbenennen (Liste/Eintrag, inline)
            if cur:
                L["adding"] = True; L["imode"] = "frename"
                L["fedit"] = {"lid": cur["lid"], "iid": cur["iid"]}
                L["input"] = str(cur.get("name") or ""); L["msg"] = ""
        elif ch in (ord("s"), ord("S")):               # reindiven + gleich anhängen
            if cur:
                l_open_desc(cur)
                L["adding"] = True; L["imode"] = "add"
                L["addparent"] = None; L["edit_iid"] = None
                L["input"] = ""; L["msg"] = ""
        elif ch in (ord("d"), ord("D")):               # löschen (Liste → Nachfrage, Eintrag direkt)
            if cur and cur.get("iid") is None:
                L["confirm"] = True; L["msg"] = ""
            elif cur:
                try:
                    api_call("/api/lists/%s/items/%d" % (cur["lid"], cur["iid"]),
                             method="DELETE")
                    l_load()
                except Exception:
                    L["msg"] = "löschen fehlgeschlagen"
        elif ch in (ord("p"), ord("P")):               # Projekt-Flag an/aus (schiebt in obere Zone)
            if cur:
                node = l_realnode(cur)
                on = not (node.get("project") if node else False)
                try:
                    if cur.get("iid") is None:
                        api_call("/api/lists/%s/project" % cur["lid"], method="POST",
                                 body={"project": on})
                    else:
                        api_call("/api/lists/%s/items/%d/project" % (cur["lid"], cur["iid"]),
                                 method="POST", body={"project": on})
                    l_load()
                except Exception:
                    L["msg"] = "projekt fehlgeschlagen"
        elif ch in (ord("m"), ord("M")):               # Eintrag in andere Liste verschieben
            if cur and cur.get("iid") is not None:
                L["def"] = next((l for l in L["lists"]
                                 if isinstance(l, dict) and l.get("id") == cur["lid"]), None)
                if L["def"] and l_move_targets():
                    L["move_iid"] = cur["iid"]; L["nsel"] = 0
                    L["msg"] = ""; L["view"] = "move"
                else:
                    L["msg"] = "keine andere liste"
            elif cur:
                # Die Leiste nennt m — auf einer ganzen Liste sagt es jetzt,
                # was stattdessen geht, statt stumm zu bleiben (2026-10-07).
                L["msg"] = "m verschiebt einträge — eine ganze liste ordnet > ein"
        elif ch == ord(">"):                           # Forest-weit einordnen (Liste/Eintrag)
            if cur:
                L["place_kind"] = "item" if cur.get("iid") is not None else "list"
                L["place_lid"] = cur["lid"]; L["place_iid"] = cur.get("iid")
                L["nsel"] = 0; L["msg"] = ""; L["view"] = "place"

    def _taste_ebene(self, ch):
        """Taste in einer Liste (view): die Einträge der offenen Ebene."""
        L, l_container, l_focus_toggle = self.L, self.l_container, self.l_focus_toggle
        l_index_in_container, l_load = self.l_index_in_container, self.l_load
        l_move_targets, l_sync_def = self.l_move_targets, self.l_sync_def
        l_vitems = self.l_vitems
        lid = L["def"]["id"] if L["def"] else None
        if L["adding"]:                               # Eintrag tippen (neu/sub/umbenennen)
            if ch == 27:
                L["adding"] = False; L["addparent"] = None
                L["edit_iid"] = None; L["imode"] = "add"
                L["input"] = ""; L["msg"] = ""
            elif ch in (10, 13, curses.KEY_ENTER):
                txt = L["input"].strip()
                if txt and lid:
                    try:
                        if L["imode"] == "rename":    # bestehenden Eintrag umbenennen
                            api_call("/api/lists/%s/items/%d/rename"
                                     % (lid, L["edit_iid"]), method="POST",
                                     body={"text": txt})
                            new_id = L["edit_iid"]
                        else:                         # neuen Eintrag/Unterpunkt anhängen
                            body = {"text": txt}
                            # Ziel-Ebene IMMER frisch aus dem Drill-Pfad
                            # ableiten (Single Source of Truth = L["path"]),
                            # NICHT aus einem gemerkten Feld — sonst
                            # „überblutet" ein Folge-Eintrag in die falsche
                            # Ebene. "add" = aktuell offene Ebene; "sub" =
                            # fester Eltern-Eintrag (steht für Serien-Eingabe).
                            if L["imode"] == "sub":
                                parent = L["addparent"]
                            else:                     # "add"
                                _items, parent, _cr = l_container()
                            if parent is not None:
                                body["parent"] = parent
                            new = api_call("/api/lists/%s/items" % lid, method="POST",
                                           body=body)
                            new_id = new.get("id") if new else None
                        # Umbenennen ist einmalig; neu/sub bleibt offen für
                        # Schnell-Eingabe mehrerer Einträge in Folge — der
                        # Eltern-Kontext (Drill-Pfad bzw. sub-addparent)
                        # bleibt dabei erhalten, wird NICHT zurückgesetzt
                        # (sonst landet der nächste Eintrag in der Wurzel).
                        L["input"] = ""; L["edit_iid"] = None
                        close = (L["imode"] == "rename")
                        mode_add = (L["imode"] == "add")
                        if close:
                            L["adding"] = False; L["imode"] = "add"
                            L["addparent"] = None
                        l_load(); l_sync_def()
                        # Cursor nur beim Anhängen auf der OFFENEN Ebene
                        # nachziehen; sub/rename lassen die Auswahl stehen.
                        if mode_add and new_id is not None:
                            L["isel"] = l_index_in_container(new_id)
                    except Exception:
                        L["msg"] = "speichern fehlgeschlagen"
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                L["input"] = L["input"][:-1]
            elif 32 <= ch <= 126 and len(L["input"]) < 80:
                L["input"] += chr(ch)
        else:
            items, pid, _cr = l_container()      # nur die offene Ebene
            vis = l_vitems()                     # so, wie sie angezeigt wird
            cur = vis[L["isel"]] if 0 <= L["isel"] < len(vis) else None
            has_bar = l_count(items)[1] > 0      # Bernsteinleiste da?
            if ch in (27, ord("l"), ord("L")):         # Esc/l → Ebene zurück, sonst Wurzel
                # In der Abgeschlossen-Sicht erst raus aus ihr — außer
                # wir stecken in einem selbst erledigten Ordner (dorthin
                # kam man aus der Abgeschlossen-Sicht): dann eine Ebene
                # hoch und dort abgeschlossen bleiben.
                node = (l_find_item(L["def"].get("items"), L["path"][-1])
                        if L["path"] else None)
                if L["showdone"] and not (node and l_done(node)):
                    L["showdone"] = False; L["isel"] = -1; L["msg"] = ""
                elif L["path"]:
                    back = L["path"][-1]
                    L["path"] = L["path"][:-1]
                    L["isel"] = l_index_in_container(back)
                    L["msg"] = ""
                else:
                    L["view"] = "forest"; L["msg"] = ""; l_load()
            elif ch in (ord("q"), ord("Q")):           # q → ganze TUI beenden
                return BEENDEN
            elif ch in (curses.KEY_UP, ord("k")):      # über den ersten → Bernsteinleiste
                L["isel"] = max(-1 if has_bar else 0, L["isel"] - 1)
            elif ch in (curses.KEY_DOWN, ord("j")):
                L["isel"] = min(len(vis) - 1, L["isel"] + 1)
            elif ch in (10, 13, curses.KEY_ENTER) and L["isel"] == -1:
                # Enter auf dem Bernstein: Abgeschlossenes zeigen / zurück
                L["showdone"] = not L["showdone"]; L["msg"] = ""
                L["isel"] = 0 if l_vitems() else -1
            elif ch in (10, 13, curses.KEY_ENTER):     # Enter: Ordner rein, sonst abhaken
                kids = cur.get("items") if cur else None
                if cur and isinstance(kids, list) and kids:
                    L["path"] = L["path"] + [cur["id"]]; L["isel"] = 0; L["msg"] = ""
                elif cur and lid:
                    try:
                        api_call("/api/lists/%s/items/%d/toggle" % (lid, cur["id"]),
                                 method="POST")
                        l_load(); l_sync_def()
                        L["msg"] = l_toggle_msg(cur)
                    except Exception:
                        L["msg"] = "umschalten fehlgeschlagen"
            elif ch == ord(" "):                       # space: Blatt abhaken
                kids = cur.get("items") if cur else None
                if cur and isinstance(kids, list) and kids:
                    L["msg"] = "ordner hakt sich selbst ab"   # abgeleitet, nicht direkt
                elif cur and lid:
                    try:
                        api_call("/api/lists/%s/items/%d/toggle" % (lid, cur["id"]),
                                 method="POST")
                        l_load(); l_sync_def()
                        L["msg"] = l_toggle_msg(cur)
                    except Exception:
                        L["msg"] = "umschalten fehlgeschlagen"
            elif ch in (ord("a"), ord("A")):           # neuer Eintrag in DIESER Ebene
                L["showdone"] = False                  # Neues ist offen → offene Sicht
                L["adding"] = True; L["imode"] = "add"
                L["addparent"] = pid; L["edit_iid"] = None
                L["input"] = ""; L["msg"] = ""
            elif ch in (ord("s"), ord("S")):           # Unterpunkt zum gewählten Eintrag
                if cur:
                    L["adding"] = True; L["imode"] = "sub"
                    L["addparent"] = cur["id"]; L["edit_iid"] = None
                    L["input"] = ""; L["msg"] = ""
            elif ch in (ord("r"), ord("R")):           # gewählten Eintrag umbenennen
                if cur:
                    L["adding"] = True; L["imode"] = "rename"
                    L["edit_iid"] = cur["id"]; L["addparent"] = None
                    L["input"] = str(cur.get("text") or ""); L["msg"] = ""
            elif ch in (ord("m"), ord("M")):           # Eintrag raus in eine andere Liste
                if cur and l_move_targets():
                    L["move_iid"] = cur["id"]; L["nsel"] = 0
                    L["msg"] = ""; L["view"] = "move"
                elif cur:
                    L["msg"] = "keine andere liste"
            elif ch == ord(">"):                       # diesen Punkt in einen Knoten einordnen (Forest-weit)
                if cur and lid:
                    L["place_kind"] = "item"
                    L["place_lid"] = lid; L["place_iid"] = cur["id"]
                    L["nsel"] = 0; L["msg"] = ""; L["view"] = "place"
            elif ch in (ord("p"), ord("P")):           # diesen Eintrag als Projekt an/aus
                if cur and lid:
                    try:
                        api_call("/api/lists/%s/items/%d/project" % (lid, cur["id"]),
                                 method="POST", body={"project": not cur.get("project")})
                        l_load(); l_sync_def()
                    except Exception:
                        L["msg"] = "projekt fehlgeschlagen"
            elif ch in (ord("d"), ord("D")):
                if cur and lid:
                    try:
                        api_call("/api/lists/%s/items/%d" % (lid, cur["id"]),
                                 method="DELETE")
                        l_load(); l_sync_def()
                    except Exception:
                        L["msg"] = "löschen fehlgeschlagen"
            elif ch in (ord("f"), ord("F")):           # diesen Eintrag fokussieren
                if cur and lid:
                    l_focus_toggle({"lid": lid, "iid": cur["id"]})
                    l_sync_def()
                    L["isel"] = l_index_in_container(cur["id"])  # klebt jetzt oben

    def _taste_einordnen(self, ch):
        """Taste beim Einordnen (place): Knoten (Liste/Eintrag) Forest-weit einordnen"""
        L, l_forest_targets, l_load = self.L, self.l_forest_targets, self.l_load
        l_sync_def = self.l_sync_def
        tg = l_forest_targets(L["place_kind"], L["place_lid"], L["place_iid"])
        back = "view" if L["place_kind"] == "item" else "forest"
        if ch in (27, ord("l"), ord("L")):             # Esc/l → abbrechen
            L["view"] = back; L["place_iid"] = None; L["msg"] = ""
        elif ch in (ord("q"), ord("Q")):               # q → ganze TUI beenden
            return BEENDEN
        elif ch in (curses.KEY_UP, ord("k")):
            L["nsel"] = max(0, L["nsel"] - 1)
        elif ch in (curses.KEY_DOWN, ord("j")):
            L["nsel"] = min(max(0, len(tg) - 1), L["nsel"] + 1)
        elif ch in (10, 13, curses.KEY_ENTER):
            if tg and 0 <= L["nsel"] < len(tg):
                t = tg[L["nsel"]]
                try:
                    if L["place_kind"] == "list":
                        api_call("/api/lists/%s/nest" % L["place_lid"], method="POST",
                                 body={"into": t["lid"], "parent": t["iid"]})
                    else:
                        api_call("/api/lists/%s/items/%d/move" % (L["place_lid"], L["place_iid"]),
                                 method="POST", body={"into": t["lid"], "parent": t["iid"]})
                    L["msg"] = "eingeordnet"
                except Exception:
                    L["msg"] = "einordnen fehlgeschlagen"
                L["view"] = back; L["place_iid"] = None
                l_load()
                if back == "view":
                    l_sync_def()

    def _taste_verschieben(self, ch):
        """Taste beim Verschieben (move): Eintrag raus in eine andere Liste"""
        L, l_load, l_move_targets = self.L, self.l_load, self.l_move_targets
        l_sync_def = self.l_sync_def
        lid = L["def"]["id"] if L["def"] else None
        targets = l_move_targets()
        nopts = 1 + len(targets)       # 0 = neue Liste, dann die Ziele
        if ch in (27, ord("l"), ord("L")):             # Esc/l → zurück zu den Einträgen
            L["view"] = "view"; L["move_iid"] = None; L["msg"] = ""
        elif ch in (ord("q"), ord("Q")):
            return BEENDEN
        elif ch in (curses.KEY_UP, ord("k")):
            L["nsel"] = max(0, L["nsel"] - 1)
        elif ch in (curses.KEY_DOWN, ord("j")):
            L["nsel"] = min(max(0, nopts - 1), L["nsel"] + 1)
        elif ch in (10, 13, curses.KEY_ENTER):
            if L["nsel"] == 0:                         # → in eine NEUE Liste (Name tippen)
                it = l_find_item(L["def"].get("items"), L["move_iid"]) if L["def"] else None
                L["input"] = str(it.get("text") or "") if it else ""
                L["view"] = "move_new"; L["msg"] = ""
            elif 1 <= L["nsel"] < nopts and lid:
                dest = targets[L["nsel"] - 1]
                try:
                    api_call("/api/lists/%s/items/%d/move" % (lid, L["move_iid"]),
                             method="POST", body={"into": dest["id"]})
                    L["msg"] = "verschoben"
                except Exception:
                    L["msg"] = "verschieben fehlgeschlagen"
                L["view"] = "view"; L["move_iid"] = None
                l_load(); l_sync_def()

    def _taste_neue_liste(self, ch):
        """Taste bei move_new: Name für die neue Ziel-Liste tippen"""
        L, l_load, l_sync_def = self.L, self.l_load, self.l_sync_def
        lid = L["def"]["id"] if L["def"] else None
        if ch == 27:
            L["view"] = "move"; L["input"] = ""; L["msg"] = ""
        elif ch in (10, 13, curses.KEY_ENTER):
            name = L["input"].strip()
            if not name:
                L["msg"] = "name fehlt"
            elif lid:
                try:
                    new = api_call("/api/lists", method="POST", body={"name": name})
                    api_call("/api/lists/%s/items/%d/move" % (lid, L["move_iid"]),
                             method="POST", body={"into": new["id"]})
                    L["msg"] = "verschoben → " + name
                    L["view"] = "view"; L["move_iid"] = None; L["input"] = ""
                    l_load(); l_sync_def()
                except Exception:
                    L["msg"] = "verschieben fehlgeschlagen"
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            L["input"] = L["input"][:-1]
        elif 32 <= ch <= 126 and len(L["input"]) < 40:
            L["input"] += chr(ch)

    def draw_list_tool(self, by, bx, bh, bw):
        """Inhalt der MITTE-Box, wenn das Listen-/Fokus-Werkzeug Fokus hat.
        Gezeichnet wird durchweg im FOCUS-Look (proj_render): jede Zeile =
        Titel + Erfüllungsleiste (2 Zeilen), ▸ = reindivebar, ◆ = Fokus."""
        C, L, addclip, draw_box = self.z.C, self.L, self.z.addclip, self.z.draw_box
        l_container, l_forest_rows = self.l_container, self.l_forest_rows
        l_forest_targets, l_move_targets = self.l_forest_targets, self.l_move_targets
        l_vitems, proj_render = self.l_vitems, self.proj_render
        safe_addstr = self.z.safe_addstr
        ix, iw = bx + 2, bw - 4
        bottom = by + bh - 2          # Hinweiszeile unten in der Box
        if iw < 8:
            return

        def rows_render(nodes, sel_idx, y0, y_max, mark_focus=True):
            """Flache proj_render-Knoten (2 Zeilen je Eintrag) mit Cursor-Fenster
            zeichnen. Liefert (nächste_y, wieviele_unten_abgeschnitten)."""
            if not nodes:
                return y0, 0
            per = 2
            avail = max(1, (y_max - y0 + 1) // per)
            start = (max(0, min(sel_idx - avail + 1, len(nodes) - avail))
                     if len(nodes) > avail else 0)
            sel_node = nodes[sel_idx] if 0 <= sel_idx < len(nodes) else None
            y = y0
            for n in nodes[start:start + avail]:
                if y > y_max:
                    break
                y = proj_render(n, ix, y, iw, y_max, sel_node=sel_node,
                                mark_focus=mark_focus)
            rest = len(nodes) - (start + avail)
            return y, max(0, rest)

        if L["view"] == "view" and L["def"]:
            items, _pid, crumbs = l_container()   # NUR die offene Ebene (Ordner-Sicht)
            done, total = l_count(items)
            head = " / ".join(crumbs)             # Breadcrumb: liste / ordner / …
            if L["showdone"]:
                head += " · abgeschlossen"
            addclip(by + 1, ix, head, iw - 8, C["bright"])
            safe_addstr(by + 1, bx + bw - 9, "[a neu]", C["acc"])
            y0 = by + 3
            if total:
                self._bernstein(by + 2, bx, ix, iw, done, total)
                y0 = by + 5
            safe_addstr(y0 - 1, ix, "─" * iw, C["faint"])
            input_row = by + bh - 3
            list_bottom = (input_row - 1) if L["adding"] else bottom
            vis = l_vitems()
            if not vis:
                if L["showdone"]:
                    leer = "noch nichts abgeschlossen — esc zurück"
                elif total:
                    leer = "alles erledigt ◆ — enter auf den bernstein zeigt's"
                else:
                    leer = "noch leer — 'a' hängt was an"
                addclip(y0, ix, leer, iw, C["faint"])
            else:
                # Jeden Eintrag im FOCUS-Look: Titel + Leiste (proj_render).
                # Blatt = eigene done/1-Leiste, Ordner = Blätter-Fortschritt.
                nodes = []
                for it in vis:
                    kids = it.get("items")
                    folder = isinstance(kids, list) and bool(kids)
                    d, t = l_count(kids) if folder else (1 if it.get("done") else 0, 1)
                    nm = str(it.get("text") or "")
                    if it.get("project"):             # als Projekt markiert → ★
                        nm += " ★"
                    nodes.append({"name": nm, "branch": folder,
                                  "focus": bool(it.get("focus")),
                                  "done": d, "total": t})
                _, rest = rows_render(nodes, L["isel"], y0, list_bottom)
                if rest:
                    safe_addstr(list_bottom, ix + iw - 5, "+%d" % rest, C["faint"])
            if L["adding"]:
                lbl = {"sub": "unterpunkt", "rename": "umbenennen"}.get(L["imode"], "neu")
                tip = "enter umbenennen" if L["imode"] == "rename" else "enter anhängen"
                addclip(input_row, ix, lbl + ": " + L["input"] + "_", iw, C["bright"])
                addclip(bottom, ix, (tip + " · esc abbrechen  " + L["msg"]).strip(), iw, C["faint"])
            elif L["msg"]:                     # Shortcuts liegen unter '/'; nur Feedback
                addclip(bottom, ix, L["msg"], iw, C["faint"])
            elif L["isel"] == -1 and total:    # auf dem Bernstein: sagen, was enter tut
                addclip(bottom, ix, "enter: zurück zu den offenen" if L["showdone"]
                        else "enter: abgeschlossene zeigen", iw, C["amber"])

        elif L["view"] == "place":         # Knoten (Liste/Eintrag) Forest-weit einordnen
            if L["place_kind"] == "list":
                src = next((x for x in L["lists"] if isinstance(x, dict) and x.get("id") == L["place_lid"]), None)
                nm = str(src.get("name") if isinstance(src, dict) else "?")
            else:
                src_lst = next((x for x in L["lists"] if isinstance(x, dict) and x.get("id") == L["place_lid"]), None)
                it = l_find_item((src_lst or {}).get("items"), L["place_iid"])
                nm = str(it.get("text") if isinstance(it, dict) else "?")
            addclip(by + 1, ix, "»%s« einordnen in:" % nm[:18], iw, C["bright"])
            safe_addstr(by + 2, ix, "─" * iw, C["faint"])
            tg = l_forest_targets(L["place_kind"], L["place_lid"], L["place_iid"])
            yy = by + 3
            if not tg:
                addclip(yy, ix, "kein ziel da", iw, C["faint"])
            else:
                avail = max(1, bottom - yy)
                start = max(0, min(L["nsel"] - avail + 1, len(tg) - avail)) if len(tg) > avail else 0
                for off, t in enumerate(tg[start:start + avail]):
                    sel = (start + off == L["nsel"])
                    # Listen-Top (iid None) als ≡ markiert, Einträge eingerückt
                    mark = "≡ " if t["iid"] is None else "  "
                    addclip(yy, ix, "%s %s%s" % ("›" if sel else " ", mark, t["label"]),
                            iw, C["bright"] if sel else C["dim"])
                    yy += 1
            if L["msg"]:                       # Shortcuts liegen unter '/'; nur Feedback
                addclip(bottom, ix, L["msg"], iw, C["faint"])

        elif L["view"] == "move" and L["def"]:   # Eintrag raus in eine andere Liste
            it = l_find_item(L["def"].get("items"), L["move_iid"])
            nm = str(it.get("text") if isinstance(it, dict) else "?")
            addclip(by + 1, ix, "»%s« verschieben nach:" % nm[:18], iw, C["bright"])
            safe_addstr(by + 2, ix, "─" * iw, C["faint"])
            # Zielauswahl: erst „neue Liste", dann alle anderen Listen.
            opts = ["[+ neue Liste]"] + [str(l.get("name") or "")
                                         for l in l_move_targets()]
            yy = by + 3
            avail = max(1, bottom - yy)
            start = max(0, min(L["nsel"] - avail + 1, len(opts) - avail)) if len(opts) > avail else 0
            for off, label in enumerate(opts[start:start + avail]):
                sel = (start + off == L["nsel"])
                addclip(yy, ix, "%s %s" % ("›" if sel else " ", label),
                        iw, C["bright"] if sel else C["dim"])
                yy += 1
            if L["msg"]:                       # Shortcuts liegen unter '/'; nur Feedback
                addclip(bottom, ix, L["msg"], iw, C["faint"])

        elif L["view"] == "move_new":            # Name für die neue Ziel-Liste
            addclip(by + 1, ix, "NEUE LISTE (ziel)", iw, C["bright"])
            addclip(by + 3, ix, "name: " + L["input"] + "_", iw, C["bright"])
            addclip(bottom, ix, ("enter anlegen+verschieben · esc zurück  " + L["msg"]).strip(), iw, C["faint"])

        else:  # "forest" — Wurzel: oben Projekte, Trennlinie, unten andere Listen
            rows, ndiv = l_forest_rows()
            if L["confirm"]:                       # Lösch-Nachfrage für ganze Liste
                cur = rows[L["fsel"]] if 0 <= L["fsel"] < len(rows) else None
                nm = str((cur or {}).get("name") or "?")
                addclip(by + 1, ix, "LISTE LÖSCHEN", iw, C["bright"])
                addclip(by + 3, ix, "»%s« wirklich löschen?" % nm[:max(4, iw - 22)],
                        iw, C["bright"])
                addclip(by + 5, ix, "j/enter = ja · sonst abbrechen", iw, C["faint"])
                return
            addclip(by + 1, ix, "LISTEN · FOKUS", iw, C["bright"])
            safe_addstr(by + 1, bx + bw - 9, "[n neu]", C["acc"])
            input_row = by + bh - 3
            grid_bottom = (input_row - 1) if L["adding"] else bottom
            if not rows:
                addclip(by + 3, ix, "noch nichts — 'n' legt eine liste an",
                        iw, C["faint"])
            else:
                # Token-Stream: Zonen-Label (1 Zeile) + Knoten (2 Zeilen). Ein
                # zeilenbasiertes Fenster (auf Token-Grenze eingerastet) hält den
                # Cursor sichtbar, auch wenn beide Zonen zusammen überlaufen.
                y0 = by + 2
                Hh = grid_bottom - y0 + 1
                seq = []
                if ndiv:
                    seq.append(("lbl", "projekte"))
                for i in range(ndiv):
                    seq.append(("node", rows[i], i))
                seq.append(("lbl", "── listen ──" if ndiv else "listen"))
                for j in range(ndiv, len(rows)):
                    seq.append(("node", rows[j], j))
                heights = [2 if t[0] == "node" else 1 for t in seq]
                starts, acc = [], 0
                for h in heights:
                    starts.append(acc); acc += h
                total_lines = acc
                sel_line = next((starts[k] for k, t in enumerate(seq)
                                 if t[0] == "node" and t[2] == L["fsel"]), 0)
                top_line = 0
                if total_lines > Hh:
                    target = max(0, min(sel_line - (Hh - 2), total_lines - Hh))
                    for s in starts:                    # auf Token-Grenze einrasten
                        if s <= target:
                            top_line = s
                        else:
                            break
                sel_node = rows[L["fsel"]] if 0 <= L["fsel"] < len(rows) else None
                for k, t in enumerate(seq):
                    ln = starts[k]
                    if ln + heights[k] - 1 < top_line:  # ganz oberhalb → weg
                        continue
                    yy = y0 + (ln - top_line)
                    if yy > grid_bottom:
                        break
                    if t[0] == "lbl":
                        if t[1]:
                            addclip(yy, ix, t[1], iw, C["faint"])
                    else:
                        proj_render(t[1], ix, yy, iw, grid_bottom,
                                    sel_node=sel_node, mark_focus=True)
                if total_lines > top_line + Hh:
                    safe_addstr(grid_bottom, ix + iw - 5, "+", C["faint"])
            if L["adding"]:                        # neue Liste / umbenennen tippen
                lbl = "umbenennen" if L["imode"] == "frename" else "neue liste"
                tip = ("enter umbenennen" if L["imode"] == "frename"
                       else "enter anlegen")
                addclip(input_row, ix, lbl + ": " + L["input"] + "_",
                        iw, C["bright"])
                addclip(bottom, ix, (tip + " · esc abbrechen  "
                                     + L["msg"]).strip(), iw, C["faint"])
            elif L["msg"]:                     # Shortcuts liegen unter '/'; nur Feedback
                addclip(bottom, ix, L["msg"], iw, C["faint"])

            if L["confirm"] and L["lists"]:        # Mini-Dialog über die Liste legen
                nm = str(L["lists"][L["sel"]].get("name") or "")
                q = "»%s« löschen?" % nm[:18]
                dw = min(iw, max(len(q), 16) + 4)
                dx = bx + (bw - dw) // 2
                dy = by + bh // 2 - 2
                draw_box(dy, dx, 4, dw, "LÖSCHEN", C["warn"])
                addclip(dy + 1, dx + 2, q, dw - 4, C["bright"])
                addclip(dy + 2, dx + 2, "j/enter = ja · sonst abbrechen", dw - 4, C["faint"])

    def _bernstein(self, y, bx, x, w, done, total):
        """Bernsteinleiste (2 Zeilen): ein Stein je Punkt der Ebene, jeder
        abgehakte leuchtet. Rechts der Zähler; ausgewählt (isel -1) zeigt
        ein › links und der Zähler steht invers."""
        C, L, PIX, PIX_MODUS = self.z.C, self.L, self.z.PIX, self.z.PIX_MODUS
        pix_attr, safe_addstr = self.z.pix_attr, self.z.safe_addstr
        sel = (L["isel"] == -1)
        cnt = " %d/%d" % (done, total)
        if C.get("pix_bg") is not None and PIX_MODUS != "off":
            # Pixel-Baustein: Sashas Treppenschliff-Stein, Mix aus Halb-
            # block/Viertel/Sextant; der zuletzt abgehakte glimmt im Takt.
            sw = max(1, w - len(cnt) - 1)
            if PIX["voll"]:
                PIX["pairs"].clear(); PIX["voll"] = False
            glimm = int(time.time() * 4) % 8
            rows = pixel.bernstein_zellen(done, total, sw, C["pix_bg"], glimm,
                                          "half" if PIX_MODUS == "half" else "mix")
            for r, line in enumerate(rows):
                for i, (ch, fg, bgc) in enumerate(line):
                    safe_addstr(y + r, x + i, ch, pix_attr(fg, bgc))
            safe_addstr(y, x + sw + 1, cnt,
                        (C["amber"] | curses.A_REVERSE) if sel else C["amber"])
            if sel:
                safe_addstr(y, bx + 1, "›", C["bright"])
            return
        # Rückfall ohne 256 Farben: schlichte Stein-Spalten
        sw = max(1, w - 2 - len(cnt))             # Platz für die Steine
        cols = bernstein_steine(done, total, sw)
        safe_addstr(y, x, "▐", C["amberdk"])
        safe_addstr(y + 1, x, "▐", C["amberdk"])
        for i, c in enumerate(cols):
            if c == "L":                          # leuchtender Stein, pixelig schattiert:
                anf = i == 0 or cols[i - 1] != "L"            # Glanz oben links,
                end = i == len(cols) - 1 or cols[i + 1] != "L"  # Schatten unten rechts
                breit = not (anf and end)
                safe_addstr(y, x + 1 + i, "█",
                            C["amberhi"] if (anf and breit) else C["amber"])
                safe_addstr(y + 1, x + 1 + i, "█",
                            C["amberdk"] if (end and breit) else C["amber"])
            elif c == "U":                        # leere Fassung
                safe_addstr(y, x + 1 + i, "░", C["amberdk"])
                safe_addstr(y + 1, x + 1 + i, "░", C["amberdk"])
        safe_addstr(y, x + 1 + sw, "▌", C["amberdk"])
        safe_addstr(y + 1, x + 1 + sw, "▌", C["amberdk"])
        safe_addstr(y, x + 2 + sw, cnt,
                    (C["amber"] | curses.A_REVERSE) if sel else C["amber"])
        if sel:
            safe_addstr(y, bx + 1, "›", C["bright"])

    def proj_render(self, node, x, y, w, y_max, sel_node=None, mark_focus=False):
        """EINE Render-Routine für die verschachtelte Projekt-Anzeige — geteilt
        von der FOCUS-Box (rechts) und der Projektansicht (Mitte), damit beide
        BYTE-GLEICH aussehen. Blatt-Projekt = Titel + Erfüllungsleiste (2 Zeilen);
        Knoten mit Unterprojekten = dünner Rahmen (Titel im oberen Rand) um die
        rekursiv gezeichneten Kinder. `sel_node` (Objekt-Identität) wird invers
        hervorgehoben (Cursor der Projektansicht); `mark_focus` hängt an den
        fokussierten Knoten ein ◆. Liefert die nächste freie y-Zeile."""
        C, addclip, proj_render = self.z.C, self.z.addclip, self.proj_render
        safe_addstr = self.z.safe_addstr
        if y > y_max or w < 4:
            return y_max + 1
        name = str(node.get("name") or "")
        if node.get("branch"):                  # eingeklappter Zweig (hat Unterpunkte)
            name = "▸ " + name
        if mark_focus and node.get("focus"):
            name += " ◆"
        sel = (node is sel_node)
        tattr = (C["bright"] | curses.A_REVERSE) if sel else C["bright"]
        kids = node.get("children") or []
        if not kids:                            # Blatt / eingeklappt: Titel + Leiste
            done = int(node.get("done") or 0)
            total = int(node.get("total") or 0)
            cnt = "%d/%d" % (done, total)
            nmw = max(1, w - len(cnt) - 1)
            addclip(y, x, name[:nmw], nmw, tattr)
            safe_addstr(y, x + w - len(cnt), cnt, C["dim"])
            if y + 1 <= y_max:
                frac = (done / total) if total else 0.0
                full = int(round(max(0.0, min(1.0, frac)) * w))
                bar = "█" * full + "░" * (w - full)
                if node.get("focus"):                    # fokussiertes Projekt → Bernstein
                    bcol = C["amber"]
                elif total and done >= total:
                    bcol = C["acc"]
                else:
                    bcol = C["graph"]
                safe_addstr(y + 1, x, bar, bcol)
            return y + 2
        # gerahmter Kasten: Titel im oberen Rand, Kinder rekursiv drin
        inner = w - 2
        label = (" " + name + " ")[:inner]
        safe_addstr(y, x, "┌" + label + "─" * (inner - len(label)) + "┐", C["faint"])
        safe_addstr(y, x + 1, label, tattr)         # Titel hervorheben (ggf. invers)
        cy = y + 1
        for c in kids:
            if cy > y_max:
                break
            cy = proj_render(c, x + 1, cy, w - 2, y_max, sel_node, mark_focus)
        for ry in range(y + 1, min(cy, y_max + 1)):  # senkrechte Ränder
            safe_addstr(ry, x, "│", C["faint"])
            safe_addstr(ry, x + w - 1, "│", C["faint"])
        if cy <= y_max:                              # unterer Rand (wenn Platz)
            safe_addstr(cy, x, "└" + "─" * (w - 2) + "┘", C["faint"])
            return cy + 1
        return y_max + 1                             # abgeschnitten → Schluss
