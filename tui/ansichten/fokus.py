# tui/ansichten/fokus.py
#
# Das Listen-/Fokus-Werkzeug der TUI (Zeichner gegen /api/lists und
# /api/projects; die Logik liegt in core/lists.py). Bis 06.10.2026 Closures in
# run_ui (tui/zentrale_tui.py), die Zähl-/Ordnungs-Helfer auf Modulebene dort;
# siehe memory/system/tui_bauplan.md.
#
# Seit 2026-10-11 zeichnet diese Ansicht die Liste NICHT selbst: was wo
# steht (Kopf, Bernstein, Kästen mit Titel und Markern, Auswahl), kommt aus
# core/listen_bild.py — derselben Quelle, aus der die Listen-Kachel
# (core/kachel_fokus.py) ihr Bild nimmt. Hier werden nur Rollen auf
# curses-Farben abgebildet (FARBROLLEN) und die Stücke gemalt; der
# Pixel-Bernstein ist eine reine TUI-Veredelung an der Stelle, die die Quelle
# angibt. Regel: memory/hub/listen_app.md.
#
# Since lists step 3 (2026-10-31, memory/hub/list_extraction_plan.md) this
# view computes no list logic in its own process: counts, effective done and
# display order come with GET /api/lists?view=1 (`view` on every node), the
# "einordnen" targets from GET /api/lists/targets, the picture of an open
# level from GET /api/lists/<lid>/bild. The forest root's boxes come with
# GET /api/lists?view=1&box=W (`view.box`, Sasha 2026-10-31: the list app
# delivers the single boxes; zones, labels and scrolling are this surface's).
# No list module is imported here.

import curses
import time
import urllib.parse

try:                                    # Pixel-Baustein (tui/pixel.py)
    from tui import pixel
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    import pixel

from .basis import BEENDEN, api_call
from .desk_kacheln import farbe as rolle_farbe
from .tasten import Tasten


# Rows of one root box (core/listen_bild.KASTEN_HOEHE); the root's scroll
# window counts with it.
BOX_HEIGHT = 3


def bar(pct, length=10):
    """Zweifarbiger Balken-String: n gefüllt + Rest leer. (Ohne Farbe hier.)"""
    n = round(max(0.0, min(100.0, pct)) / 100.0 * length)
    return "█" * n + "░" * (length - n)


# Finding a node by id in the tree the core sent — plain walking, no list
# rules (counts, done, order come in `view`, GET /api/lists?view=1).
def _nodes(items, above=()):
    """Every item with the ids above it: [(item, (ids…)), …], stored order."""
    out = []
    for it in items or []:
        if isinstance(it, dict):
            out.append((it, tuple(above)))
            out += _nodes(it.get("items"), tuple(above) + (it.get("id"),))
    return out


def l_find_item(items, iid):
    """The item with this id anywhere below (or None)."""
    return next((it for it, _a in _nodes(items) if it.get("id") == iid), None)


def l_path_to(items, iid):
    """Ids from the top of the list down to iid (inclusive) — or None."""
    return next((list(a) + [iid] for it, a in _nodes(items) if it.get("id") == iid), None)


def l_view(node):
    """What the core says about a node (GET /api/lists?view=1)."""
    v = node.get("view") if isinstance(node, dict) else None
    return v if isinstance(v, dict) else {}


def l_done(node):
    """Effectively done (a folder is when all its points are) — from the core."""
    return bool(l_view(node).get("complete"))


def l_toggle_msg(it):
    """Rückmeldung nach dem Abhaken: abgehakt wandert's in den Bernstein."""
    return "wieder offen" if it.get("done") else "◆ in den bernstein"


class Fokus:
    """Das Listen-/Fokus-Werkzeug (Mitte, Taste 'f'): oben die Projekte,
    darunter die anderen Listen, reindiven wie Ordner, abhaken, umbenennen,
    verschieben, einordnen, fokussieren. Knoten = Kästen (kasten_render);
    proj_render zeichnet die Fokus-Box, die es nur noch im alten
    3-Spalten-Dashboard gibt (Backup, /dashboard an). Zustand in self.L (auch z.L)."""

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
        # EIN gemergtes Werkzeug: Reindive-Navigation der früheren
        # Projektansicht, jeder Knoten ein Kasten nur mit Titel (kasten_render;
        # Status allein im Bernstein der Ebene) PLUS die volle Editier-Macht des alten Listen-Werkzeugs. Die Wurzel
        # ("forest") ist ZWEIGETEILT: oben die geflaggten Projekte (/api/projects),
        # eine Trennlinie, drunter alle anderen (Nicht-Projekt-)Listen — beide
        # top-level, per enter reindivebar. Ab da ist es die normale Ordner-Sicht
        # einer Liste ("view", def+path). 'f'/space setzt JEDEN Knoten als
        # alleinigen Fokus (als Box angezeigt nur im Backup-Dashboard, /dashboard an).
        #   view : "forest" (zwei-Zonen-Wurzel) | "view" (in einer Liste) |
        #          "new" (Liste anlegen/umbenennen) | "place"/"move"/"move_new"
        #   proots : Projekt-Roots als Deskriptoren [{lid,iid}] (iid None = Liste)
        #   fsel   : Cursor-Index in der Forest-Wurzel (proots + Nicht-Projekt-Listen)
        #   isel   : in "view" Index in l_vitems() der offenen Ebene; -1 =
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
        q = "/api/lists?view=1"
        if L.get("box_w"):                 # the root's boxes, as wide as drawn
            q += "&box=%d" % L["box_w"]
        try:
            L["lists"] = api_call(q) or []
        except Exception:
            L["lists"] = []
        L["lists_box_w"] = L.get("box_w")
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
        lid,iid,box} der Wurzel; `box` is its box from the core
        (view.box {plain, selected}, GET /api/lists?view=1&box=W)."""
        l_realnode = self.l_realnode
        node = l_realnode(desc)
        if node is None:
            return None
        kids = node.get("items")
        d, t = l_view(node).get("done", 0), l_view(node).get("total", 0)
        whole = desc.get("iid") is None
        name = node.get("name") if whole else node.get("text")
        return {"lid": desc["lid"], "iid": desc.get("iid"),
                "name": str(name or ""), "done": d, "total": t,
                "branch": bool(isinstance(kids, list) and kids),
                "focus": bool(node.get("focus")),
                "project": bool(node.get("project")), "whole": whole,
                "box": l_view(node).get("box")}

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
        items, pid, crumbs, _node = self._offen()
        return items, pid, crumbs

    def _offen(self):
        """l_container plus the open node itself (list or item) — its `view`
        holds the display order of the level."""
        L = self.L
        if not L["def"]:
            return [], None, [], None
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
        return (node.get("items") or []), pid, crumbs, node

    def l_vitems(self):
        """Die offene Ebene so, wie sie angezeigt wird: offen und sortiert —
        oder nur das Abgeschlossene (showdone). The order is the core's
        (`view.order` / `view.finished` of the open node)."""
        L = self.L
        items, _pid, _cr, node = self._offen()
        ids = l_view(node).get("finished" if L["showdone"] else "order") or []
        by_id = {it.get("id"): it for it in items if isinstance(it, dict)}
        return [by_id[i] for i in ids if i in by_id]

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
        {lid, iid (None = Listen-Top als Ziel), label}. Which ones: the core
        (GET /api/lists/targets); asked once per loaded state."""
        L = self.L
        key = (skind, slid, siid, id(L.get("lists")))
        memo = self.__dict__.setdefault("_memo", {}).get("ziele")
        if memo and memo[0] == key:
            return memo[1]
        q = "/api/lists/targets?kind=%s&lid=%s" % (skind, urllib.parse.quote(str(slid or "")))
        if siid is not None:
            q += "&iid=%d" % siid
        try:
            got = api_call(q) or []
        except Exception:
            got = []
        out = [{"lid": t.get("lid"), "iid": t.get("iid"),
                "label": "  " * int(t.get("tiefe") or 0) + str(t.get("text") or "")}
               for t in got if isinstance(t, dict)]
        self._memo["ziele"] = (key, out)
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

    # ── Tasten: EINE Tabelle, aus der Verteilung und Leiste lesen ──────
    # (tui/ansichten/tasten.py, 2026-10-11). Ohne Text = verarbeitet, aber
    # nicht gezeigt (vim-Pfeile, Großbuchstaben, q). Die Wurzel ist je nach
    # gewähltem Knoten eine andere Ansicht (ganze Liste, Ordner-Eintrag,
    # Blatt-Eintrag), weil Leertaste, enter und m dort Verschiedenes tun.
    _WALD = [
        ("↑↓", "w_waehlen", "select"), ("k/j", "w_waehlen"),
        ("s", "w_oeffnen_anhaengen", "open + add"), ("S", "w_oeffnen_anhaengen"),
        ("n", "w_neue_liste", "new list"), ("N", "w_neue_liste"),
        ("f", "w_fokus", "focus"), ("F", "w_fokus"),
        ("r", "w_umbenennen", "rename"), ("R", "w_umbenennen"),
        ("p", "w_projekt", "project"), ("P", "w_projekt"),
    ]
    _WALD_ENDE = [
        (">", "w_einordnen", "place"), ("d", "w_loeschen", "delete"), ("D", "w_loeschen"),
        ("esc/l", "w_schliessen", "close"), ("L", "w_schliessen"), ("q/Q", "beenden"),
    ]
    TASTEN = Tasten({
        # Wurzel, gewählt ist eine ganze Liste
        "wald": [("enter/→", "w_oeffnen", "open")] + _WALD + [
            ("m/M", "w_verschieben")] + _WALD_ENDE,       # m: sagt, dass > es tut
        # … ein Projekt-Eintrag mit Unterpunkten
        "wald:ordner": [("enter/→", "w_oeffnen", "open")] + _WALD + [
            ("m", "w_verschieben", "move item"), ("M", "w_verschieben")] + _WALD_ENDE,
        # … ein Projekt-Eintrag ohne Unterpunkte (Blatt)
        "wald:punkt": [("enter/→", "w_oeffnen", "check"), ("space", "w_abhaken")] + _WALD + [
            ("m", "w_verschieben", "move item"), ("M", "w_verschieben")] + _WALD_ENDE,
        "wald:leer": [
            ("n", "w_neue_liste", "new list"), ("N", "w_neue_liste"),
            ("esc/l", "w_schliessen", "close"), ("L", "w_schliessen"), ("q/Q", "beenden"),
        ],
        "wald:frage": [
            ("j/y/enter", "w_ja", "delete"), ("J/Y", "w_ja"), ("any key", "w_nein", "cancel"),
        ],
        "wald:neu": [
            ("type", "w_tippen", "type name"), ("enter", "w_name_setzen", "create"),
            ("⌫", "w_zeichen_weg", "delete"), ("esc", "w_name_abbrechen", "cancel"),
        ],
        "wald:umbenennen": [
            ("type", "w_tippen", "type name"), ("enter", "w_name_setzen", "rename"),
            ("⌫", "w_zeichen_weg", "delete"), ("esc", "w_name_abbrechen", "cancel"),
        ],
        # In einer Liste, ein Eintrag gewählt
        "liste": [
            ("↑↓", "e_waehlen", "select"), ("k/j", "e_waehlen"),
            ("enter", "e_oeffnen", "open / check"), ("space", "e_abhaken", "check"),
            ("a/s", "e_neu", "add"), ("A/S", "e_neu"),
            ("r", "e_umbenennen", "rename"), ("R", "e_umbenennen"),
            ("p", "e_projekt", "project"), ("P", "e_projekt"),
            ("f", "e_fokus", "focus"), ("F", "e_fokus"),
            (">", "e_einordnen", "place"),
            ("m", "e_verschieben", "move out"), ("M", "e_verschieben"),
            ("d", "e_loeschen", "delete"), ("D", "e_loeschen"),
            ("esc/l", "e_zurueck", "back"), ("L", "e_zurueck"), ("q/Q", "beenden"),
        ],
        # … der Bernstein oben gewählt (enter zeigt das Abgeschlossene / zurück)
        "liste:bernstein": [
            ("↓", "e_waehlen", "select"), ("j", "e_waehlen"),
            ("enter", "e_bernstein", "done / open"),
            ("a", "e_neu", "add"), ("A", "e_neu"),
            ("esc/l", "e_zurueck", "back"), ("L", "e_zurueck"), ("q/Q", "beenden"),
        ],
        # … der Bernstein, darunter nichts (alles erledigt / nichts abgeschlossen)
        "liste:bernstein:leer": [
            ("enter", "e_bernstein", "done / open"),
            ("a", "e_neu", "add"), ("A", "e_neu"),
            ("esc/l", "e_zurueck", "back"), ("L", "e_zurueck"), ("q/Q", "beenden"),
        ],
        # … die Ebene ist ganz leer
        "liste:leer": [
            ("a", "e_neu", "add"), ("A", "e_neu"),
            ("esc/l", "e_zurueck", "back"), ("L", "e_zurueck"), ("q/Q", "beenden"),
        ],
        "liste:neu": [
            ("type", "e_tippen", "type"), ("enter", "e_eintrag_setzen", "add"),
            ("⌫", "e_zeichen_weg", "delete"), ("esc", "e_eingabe_abbrechen", "done"),
        ],
        "liste:umbenennen": [
            ("type", "e_tippen", "type"), ("enter", "e_eintrag_setzen", "rename"),
            ("⌫", "e_zeichen_weg", "delete"), ("esc", "e_eingabe_abbrechen", "cancel"),
        ],
        # Knoten Forest-weit einordnen (>)
        "einordnen": [
            ("↑↓", "p_waehlen", "select"), ("k/j", "p_waehlen"),
            ("enter", "p_nehmen", "take"),
            ("esc/l", "p_abbrechen", "cancel"), ("L", "p_abbrechen"), ("q/Q", "beenden"),
        ],
        "einordnen:leer": [
            ("esc/l", "p_abbrechen", "cancel"), ("L", "p_abbrechen"), ("q/Q", "beenden"),
        ],
        # Eintrag raus in eine andere Liste (m); Ziel 0 = neue Liste
        "verschieben": [
            ("↑↓", "v_waehlen", "select"), ("k/j", "v_waehlen"),
            ("enter", "v_nehmen", "take"),
            ("esc/l", "v_abbrechen", "cancel"), ("L", "v_abbrechen"), ("q/Q", "beenden"),
        ],
        "verschieben:name": [
            ("type", "v_tippen", "type name"), ("enter", "v_name_setzen", "create + move"),
            ("⌫", "v_zeichen_weg", "delete"), ("esc", "v_name_abbrechen", "back"),
        ],
    })

    def ansicht(self):
        """Welche Ansicht der Tabelle gerade offen ist."""
        L = self.L
        v = L["view"]
        if v == "place":
            return "einordnen" if self._p_ziele() else "einordnen:leer"
        if v == "move":
            return "verschieben"
        if v == "move_new":
            return "verschieben:name"
        if v == "view":
            if L["adding"]:
                return "liste:umbenennen" if L["imode"] == "rename" else "liste:neu"
            _pid, vis, cur, has_bar = self._ebene_lage()
            if has_bar and (L["isel"] == -1 or not vis):
                return "liste:bernstein" if vis else "liste:bernstein:leer"
            return "liste" if cur else "liste:leer"
        # forest
        if L["adding"]:
            return "wald:umbenennen" if L["imode"] == "frename" else "wald:neu"
        if L["confirm"]:
            return "wald:frage"
        cur = self._wald_cur()
        if cur is None:
            return "wald:leer"
        if cur.get("iid") is None:
            return "wald"
        return "wald:ordner" if cur.get("branch") else "wald:punkt"

    def taste(self, ch):
        """Eine Taste, während das Fokus-Werkzeug den Fokus hat (früher ein Zweig
        der Hauptschleife in run_ui). Gibt BEENDEN zurück, wenn die TUI enden soll."""
        self._bernstein_klemmen()
        return self.TASTEN.verteilen(self, self.ansicht(), ch)

    def aktion_beenden(self, _taste):
        return BEENDEN

    # ── Wurzel (forest): oben die Projekte, unten die anderen Listen ──
    def _wald_cur(self):
        """Der gewählte Deskriptor der Wurzel {lid,iid,branch,whole,…} oder None."""
        rows, _ndiv = self.l_forest_rows()
        f = self.L["fsel"]
        return rows[f] if 0 <= f < len(rows) else None

    def _toggle(self, lid, iid):
        """Einen Eintrag der Wurzel abhaken/wieder öffnen."""
        try:
            api_call("/api/lists/%s/items/%d/toggle" % (lid, iid), method="POST")
            self.l_load()
        except Exception:
            self.L["msg"] = "umschalten fehlgeschlagen"

    def aktion_w_waehlen(self, taste):
        L = self.L
        rows, _ndiv = self.l_forest_rows()
        if rows:
            d = -1 if taste in ("up", "k") else 1
            L["fsel"] = (L["fsel"] + d) % len(rows)

    def aktion_w_oeffnen(self, _taste):
        """enter/→: ganze Liste / Ordner → reindiven, Blatt → abhaken."""
        cur = self._wald_cur()
        if cur:
            if cur.get("iid") is None or cur.get("branch"):
                self.l_open_desc(cur)
            else:
                self._toggle(cur["lid"], cur["iid"])

    def aktion_w_abhaken(self, _taste):
        cur = self._wald_cur()
        if cur and cur.get("iid") is not None and not cur.get("branch"):
            self._toggle(cur["lid"], cur["iid"])

    def aktion_w_fokus(self, _taste):
        cur = self._wald_cur()
        if cur:
            self.l_focus_toggle(cur)

    def aktion_w_neue_liste(self, _taste):
        L = self.L
        L["adding"] = True; L["imode"] = "newlist"
        L["fedit"] = None; L["input"] = ""; L["msg"] = ""

    def aktion_w_umbenennen(self, _taste):
        L, cur = self.L, self._wald_cur()
        if cur:
            L["adding"] = True; L["imode"] = "frename"
            L["fedit"] = {"lid": cur["lid"], "iid": cur["iid"]}
            L["input"] = str(cur.get("name") or ""); L["msg"] = ""

    def aktion_w_oeffnen_anhaengen(self, _taste):
        """s: reindiven und gleich einen Eintrag anhängen."""
        L, cur = self.L, self._wald_cur()
        if cur:
            self.l_open_desc(cur)
            L["adding"] = True; L["imode"] = "add"
            L["addparent"] = None; L["edit_iid"] = None
            L["input"] = ""; L["msg"] = ""

    def aktion_w_loeschen(self, _taste):
        """d: ganze Liste → Nachfrage, Eintrag direkt."""
        L, cur = self.L, self._wald_cur()
        if cur and cur.get("iid") is None:
            L["confirm"] = True; L["msg"] = ""
        elif cur:
            try:
                api_call("/api/lists/%s/items/%d" % (cur["lid"], cur["iid"]),
                         method="DELETE")
                self.l_load()
            except Exception:
                L["msg"] = "löschen fehlgeschlagen"

    def aktion_w_projekt(self, _taste):
        """p: Projekt-Flag an/aus (schiebt in die obere Zone)."""
        L, cur = self.L, self._wald_cur()
        if not cur:
            return
        node = self.l_realnode(cur)
        on = not (node.get("project") if node else False)
        try:
            if cur.get("iid") is None:
                api_call("/api/lists/%s/project" % cur["lid"], method="POST",
                         body={"project": on})
            else:
                api_call("/api/lists/%s/items/%d/project" % (cur["lid"], cur["iid"]),
                         method="POST", body={"project": on})
            self.l_load()
        except Exception:
            L["msg"] = "projekt fehlgeschlagen"

    def aktion_w_verschieben(self, _taste):
        """m: Eintrag in eine andere Liste; auf einer ganzen Liste sagt es,
        was stattdessen geht (2026-10-07)."""
        L, cur = self.L, self._wald_cur()
        if cur and cur.get("iid") is not None:
            L["def"] = next((l for l in L["lists"]
                             if isinstance(l, dict) and l.get("id") == cur["lid"]), None)
            if L["def"] and self.l_move_targets():
                L["move_iid"] = cur["iid"]; L["nsel"] = 0
                L["msg"] = ""; L["view"] = "move"
            else:
                L["msg"] = "keine andere liste"
        elif cur:
            L["msg"] = "m verschiebt einträge — eine ganze liste ordnet > ein"

    def aktion_w_einordnen(self, _taste):
        """>: Forest-weit einordnen (Liste oder Eintrag)."""
        L, cur = self.L, self._wald_cur()
        if cur:
            L["place_kind"] = "item" if cur.get("iid") is not None else "list"
            L["place_lid"] = cur["lid"]; L["place_iid"] = cur.get("iid")
            L["nsel"] = 0; L["msg"] = ""; L["view"] = "place"

    def aktion_w_schliessen(self, _taste):
        self.L["active"] = False

    def aktion_w_ja(self, _taste):
        """Liste wirklich löschen."""
        L, cur = self.L, self._wald_cur()
        if cur and cur.get("iid") is None:
            try:
                api_call("/api/lists/" + str(cur["lid"]), method="DELETE")
                L["msg"] = "gelöscht"
            except Exception:
                L["msg"] = "löschen fehlgeschlagen"
        L["confirm"] = False; self.l_load()

    def aktion_w_nein(self, _taste):
        self.L["confirm"] = False; self.L["msg"] = ""

    # neue Liste / umbenennen tippen (Wurzel)
    def aktion_w_tippen(self, zeichen):
        if len(self.L["input"]) < 80:
            self.L["input"] += zeichen

    def aktion_w_zeichen_weg(self, _taste):
        self.L["input"] = self.L["input"][:-1]

    def aktion_w_name_abbrechen(self, _taste):
        L = self.L
        L["adding"] = False; L["imode"] = "add"
        L["fedit"] = None; L["input"] = ""; L["msg"] = ""

    def aktion_w_name_setzen(self, _taste):
        L = self.L
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
            L["fedit"] = None; L["input"] = ""; self.l_load()
        else:                                 # neue Liste anlegen
            try:
                api_call("/api/lists", method="POST", body={"name": txt})
                L["msg"] = "angelegt: " + txt
            except Exception:
                L["msg"] = "anlegen fehlgeschlagen"
            L["adding"] = False; L["input"] = ""; self.l_load()

    # ── In einer Liste (view): die Einträge der offenen Ebene ──
    def _ebene_lage(self):
        """(container-id, angezeigte Einträge, gewählter Eintrag oder None,
        Bernsteinleiste da?) der offenen Ebene."""
        L = self.L
        items, pid, _cr, node = self._offen()     # nur die offene Ebene
        vis = self.l_vitems()                     # so, wie sie angezeigt wird
        cur = vis[L["isel"]] if 0 <= L["isel"] < len(vis) else None
        return pid, vis, cur, bool(items) and l_view(node).get("total", 0) > 0

    def _bernstein_klemmen(self):
        """Steht unter dem Bernstein nichts, ist er gewählt — so zeigt die
        Auswahl, wofür die Leiste enter anbietet."""
        L = self.L
        if L.get("view") == "view" and L.get("def") and not L.get("adding"):
            _pid, vis, _cur, has_bar = self._ebene_lage()
            if has_bar and not vis:
                L["isel"] = -1

    def _lid(self):
        return self.L["def"]["id"] if self.L["def"] else None

    def aktion_e_zurueck(self, _taste):
        """esc/l: Ebene zurück, sonst Wurzel. In der Abgeschlossen-Sicht erst
        raus aus ihr — außer wir stecken in einem selbst erledigten Ordner
        (dorthin kam man aus der Abgeschlossen-Sicht): dann eine Ebene hoch
        und dort abgeschlossen bleiben."""
        L = self.L
        node = (l_find_item(L["def"].get("items"), L["path"][-1])
                if L["path"] and L["def"] else None)
        if L["showdone"] and not (node and l_done(node)):
            L["showdone"] = False; L["isel"] = -1; L["msg"] = ""
        elif L["path"]:
            back = L["path"][-1]
            L["path"] = L["path"][:-1]
            L["isel"] = self.l_index_in_container(back)
            L["msg"] = ""
        else:
            L["view"] = "forest"; L["msg"] = ""; self.l_load()

    def aktion_e_waehlen(self, taste):
        """↑ über den ersten → Bernsteinleiste."""
        L = self.L
        _pid, vis, _cur, has_bar = self._ebene_lage()
        if taste in ("up", "k"):
            L["isel"] = max(-1 if has_bar else 0, L["isel"] - 1)
        else:
            L["isel"] = min(len(vis) - 1, L["isel"] + 1)

    def aktion_e_bernstein(self, _taste):
        """enter auf dem Bernstein: Abgeschlossenes zeigen / zurück."""
        L = self.L
        L["showdone"] = not L["showdone"]; L["msg"] = ""
        L["isel"] = 0 if self.l_vitems() else -1

    def _e_toggle(self, cur):
        L, lid = self.L, self._lid()
        if not lid:
            return
        try:
            api_call("/api/lists/%s/items/%d/toggle" % (lid, cur["id"]), method="POST")
            self.l_load(); self.l_sync_def()
            L["msg"] = l_toggle_msg(cur)
        except Exception:
            L["msg"] = "umschalten fehlgeschlagen"

    def aktion_e_oeffnen(self, _taste):
        """enter: Ordner rein, sonst abhaken."""
        L = self.L
        _pid, _vis, cur, _bar = self._ebene_lage()
        kids = cur.get("items") if cur else None
        if cur and isinstance(kids, list) and kids:
            L["path"] = L["path"] + [cur["id"]]; L["isel"] = 0; L["msg"] = ""
        elif cur:
            self._e_toggle(cur)

    def aktion_e_abhaken(self, _taste):
        """space: Blatt abhaken; ein Ordner hakt sich selbst ab."""
        _pid, _vis, cur, _bar = self._ebene_lage()
        kids = cur.get("items") if cur else None
        if cur and isinstance(kids, list) and kids:
            self.L["msg"] = "ordner hakt sich selbst ab"   # abgeleitet, nicht direkt
        elif cur:
            self._e_toggle(cur)

    def aktion_e_neu(self, taste):
        """a: neuer Eintrag in DIESER Ebene; s: Unterpunkt zum gewählten."""
        L = self.L
        pid, _vis, cur, _bar = self._ebene_lage()
        if taste in ("s", "S"):
            if cur:
                L["adding"] = True; L["imode"] = "sub"
                L["addparent"] = cur["id"]; L["edit_iid"] = None
                L["input"] = ""; L["msg"] = ""
            return
        L["showdone"] = False                  # Neues ist offen → offene Sicht
        L["adding"] = True; L["imode"] = "add"
        L["addparent"] = pid; L["edit_iid"] = None
        L["input"] = ""; L["msg"] = ""

    def aktion_e_umbenennen(self, _taste):
        L = self.L
        _pid, _vis, cur, _bar = self._ebene_lage()
        if cur:
            L["adding"] = True; L["imode"] = "rename"
            L["edit_iid"] = cur["id"]; L["addparent"] = None
            L["input"] = str(cur.get("text") or ""); L["msg"] = ""

    def aktion_e_verschieben(self, _taste):
        """m: Eintrag raus in eine andere Liste."""
        L = self.L
        _pid, _vis, cur, _bar = self._ebene_lage()
        if cur and self.l_move_targets():
            L["move_iid"] = cur["id"]; L["nsel"] = 0
            L["msg"] = ""; L["view"] = "move"
        elif cur:
            L["msg"] = "keine andere liste"

    def aktion_e_einordnen(self, _taste):
        """>: diesen Punkt in einen Knoten einordnen (Forest-weit)."""
        L, lid = self.L, self._lid()
        _pid, _vis, cur, _bar = self._ebene_lage()
        if cur and lid:
            L["place_kind"] = "item"
            L["place_lid"] = lid; L["place_iid"] = cur["id"]
            L["nsel"] = 0; L["msg"] = ""; L["view"] = "place"

    def aktion_e_projekt(self, _taste):
        L, lid = self.L, self._lid()
        _pid, _vis, cur, _bar = self._ebene_lage()
        if cur and lid:
            try:
                api_call("/api/lists/%s/items/%d/project" % (lid, cur["id"]),
                         method="POST", body={"project": not cur.get("project")})
                self.l_load(); self.l_sync_def()
            except Exception:
                L["msg"] = "projekt fehlgeschlagen"

    def aktion_e_loeschen(self, _taste):
        L, lid = self.L, self._lid()
        _pid, _vis, cur, _bar = self._ebene_lage()
        if cur and lid:
            try:
                api_call("/api/lists/%s/items/%d" % (lid, cur["id"]), method="DELETE")
                self.l_load(); self.l_sync_def()
            except Exception:
                L["msg"] = "löschen fehlgeschlagen"

    def aktion_e_fokus(self, _taste):
        L, lid = self.L, self._lid()
        _pid, _vis, cur, _bar = self._ebene_lage()
        if cur and lid:
            self.l_focus_toggle({"lid": lid, "iid": cur["id"]})
            self.l_sync_def()
            L["isel"] = self.l_index_in_container(cur["id"])  # klebt jetzt oben

    # Eintrag tippen (neu/sub/umbenennen)
    def aktion_e_tippen(self, zeichen):
        if len(self.L["input"]) < 80:
            self.L["input"] += zeichen

    def aktion_e_zeichen_weg(self, _taste):
        self.L["input"] = self.L["input"][:-1]

    def aktion_e_eingabe_abbrechen(self, _taste):
        L = self.L
        L["adding"] = False; L["addparent"] = None
        L["edit_iid"] = None; L["imode"] = "add"
        L["input"] = ""; L["msg"] = ""

    def aktion_e_eintrag_setzen(self, _taste):
        L, lid = self.L, self._lid()
        txt = L["input"].strip()
        if not (txt and lid):
            return
        try:
            if L["imode"] == "rename":    # bestehenden Eintrag umbenennen
                api_call("/api/lists/%s/items/%d/rename" % (lid, L["edit_iid"]),
                         method="POST", body={"text": txt})
                new_id = L["edit_iid"]
            else:                         # neuen Eintrag/Unterpunkt anhängen
                body = {"text": txt}
                # Ziel-Ebene IMMER frisch aus dem Drill-Pfad ableiten (Single
                # Source of Truth = L["path"]), NICHT aus einem gemerkten Feld
                # — sonst „überblutet" ein Folge-Eintrag in die falsche Ebene.
                # "add" = aktuell offene Ebene; "sub" = fester Eltern-Eintrag
                # (steht für Serien-Eingabe).
                if L["imode"] == "sub":
                    parent = L["addparent"]
                else:                     # "add"
                    _items, parent, _cr = self.l_container()
                if parent is not None:
                    body["parent"] = parent
                new = api_call("/api/lists/%s/items" % lid, method="POST", body=body)
                new_id = new.get("id") if new else None
            # Umbenennen ist einmalig; neu/sub bleibt offen für Schnell-Eingabe
            # mehrerer Einträge in Folge — der Eltern-Kontext (Drill-Pfad bzw.
            # sub-addparent) bleibt dabei erhalten, wird NICHT zurückgesetzt
            # (sonst landet der nächste Eintrag in der Wurzel).
            L["input"] = ""; L["edit_iid"] = None
            close = (L["imode"] == "rename")
            mode_add = (L["imode"] == "add")
            if close:
                L["adding"] = False; L["imode"] = "add"
                L["addparent"] = None
            self.l_load(); self.l_sync_def()
            # Cursor nur beim Anhängen auf der OFFENEN Ebene nachziehen;
            # sub/rename lassen die Auswahl stehen.
            if mode_add and new_id is not None:
                L["isel"] = self.l_index_in_container(new_id)
        except Exception:
            L["msg"] = "speichern fehlgeschlagen"

    # ── Einordnen (place): Knoten (Liste/Eintrag) Forest-weit einordnen ──
    def _p_ziele(self):
        L = self.L
        return self.l_forest_targets(L["place_kind"], L["place_lid"], L["place_iid"])

    def aktion_p_waehlen(self, taste):
        L = self.L
        if taste in ("up", "k"):
            L["nsel"] = max(0, L["nsel"] - 1)
        else:
            L["nsel"] = min(max(0, len(self._p_ziele()) - 1), L["nsel"] + 1)

    def aktion_p_abbrechen(self, _taste):
        L = self.L
        L["view"] = "view" if L["place_kind"] == "item" else "forest"
        L["place_iid"] = None; L["msg"] = ""

    def aktion_p_nehmen(self, _taste):
        L = self.L
        tg = self._p_ziele()
        back = "view" if L["place_kind"] == "item" else "forest"
        if not (tg and 0 <= L["nsel"] < len(tg)):
            return
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
        self.l_load()
        if back == "view":
            self.l_sync_def()

    # ── Verschieben (move): Eintrag raus in eine andere Liste ──
    def aktion_v_waehlen(self, taste):
        L = self.L
        if taste in ("up", "k"):
            L["nsel"] = max(0, L["nsel"] - 1)
        else:
            nopts = 1 + len(self.l_move_targets())    # 0 = neue Liste, dann die Ziele
            L["nsel"] = min(max(0, nopts - 1), L["nsel"] + 1)

    def aktion_v_abbrechen(self, _taste):
        L = self.L
        L["view"] = "view"; L["move_iid"] = None; L["msg"] = ""

    def aktion_v_nehmen(self, _taste):
        L, lid = self.L, self._lid()
        targets = self.l_move_targets()
        if L["nsel"] == 0:                         # → in eine NEUE Liste (Name tippen)
            it = l_find_item(L["def"].get("items"), L["move_iid"]) if L["def"] else None
            L["input"] = str(it.get("text") or "") if it else ""
            L["view"] = "move_new"; L["msg"] = ""
        elif 1 <= L["nsel"] <= len(targets) and lid:
            dest = targets[L["nsel"] - 1]
            try:
                api_call("/api/lists/%s/items/%d/move" % (lid, L["move_iid"]),
                         method="POST", body={"into": dest["id"]})
                L["msg"] = "verschoben"
            except Exception:
                L["msg"] = "verschieben fehlgeschlagen"
            L["view"] = "view"; L["move_iid"] = None
            self.l_load(); self.l_sync_def()

    # Name für die neue Ziel-Liste tippen (move_new)
    def aktion_v_tippen(self, zeichen):
        if len(self.L["input"]) < 40:
            self.L["input"] += zeichen

    def aktion_v_zeichen_weg(self, _taste):
        self.L["input"] = self.L["input"][:-1]

    def aktion_v_name_abbrechen(self, _taste):
        L = self.L
        L["view"] = "move"; L["input"] = ""; L["msg"] = ""

    def aktion_v_name_setzen(self, _taste):
        L, lid = self.L, self._lid()
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
                self.l_load(); self.l_sync_def()
            except Exception:
                L["msg"] = "verschieben fehlgeschlagen"

    def draw_list_tool(self, by, bx, bh, bw):
        """Inhalt der MITTE-Box, wenn das Listen-/Fokus-Werkzeug Fokus hat.
        Jeder Knoten ist ein Kasten mit nur dem Titel (▸ reindivebar, ★ Projekt,
        ◆ Fokus), Status allein im Bernstein oben — Aussehen und Aufbau der
        Ebenen-Sicht kommen aus core/listen_bild.py (dasselbe Bild wie die
        Kachel), die Wurzel setzt deren Kästen in ihre zwei Zonen."""
        C, L, addclip = self.z.C, self.L, self.z.addclip
        l_container, l_forest_rows = self.l_container, self.l_forest_rows
        l_forest_targets, l_move_targets = self.l_forest_targets, self.l_move_targets
        kasten_render = self.kasten_render
        safe_addstr = self.z.safe_addstr
        ix, iw = bx + 2, bw - 4
        # Unterste Zeile: nur Rückmeldungen (L["msg"]). Die Tasten stehen seit
        # 2026-10-11 allein in der Leiste ganz unten (Tastentabelle TASTEN).
        bottom = by + bh - 2
        if iw < 8:
            return

        if L["view"] == "view" and L["def"]:
            # Das Bild der Ebene kommt ganz aus listen_bild (wie die Kachel, über HTTP);
            # hier nur malen, dazu der Pixel-Bernstein.
            self._bernstein_klemmen()
            l_container()                         # cuts a broken drill path
            input_row = by + bh - 3
            list_bottom = (input_row - 1) if L["adding"] else bottom
            bild = self._ebene_bild(iw, list_bottom - by)
            self._malen(by + 1, ix, bild["zeilen"])
            if bild["bernstein"]:
                self._bernstein(by + 1 + bild["bernstein"]["zeile"], bx, ix, bild["bernstein"])
            if L["adding"]:
                lbl = {"sub": "unterpunkt", "rename": "umbenennen"}.get(L["imode"], "neu")
                addclip(input_row, ix, lbl + ": " + L["input"] + "_", iw, C["bright"])
            if L["msg"]:
                addclip(bottom, ix, L["msg"], iw, C["faint"])

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
            if L["msg"]:                       # nur Rückmeldung (Tasten: Leiste)
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
            if L["msg"]:                       # nur Rückmeldung (Tasten: Leiste)
                addclip(bottom, ix, L["msg"], iw, C["faint"])

        elif L["view"] == "move_new":            # Name für die neue Ziel-Liste
            addclip(by + 1, ix, "NEUE LISTE (ziel)", iw, C["bright"])
            addclip(by + 3, ix, "name: " + L["input"] + "_", iw, C["bright"])
            if L["msg"]:
                addclip(bottom, ix, L["msg"], iw, C["faint"])

        else:  # "forest" — Wurzel: oben Projekte, Trennlinie, unten andere Listen
            rows, ndiv = l_forest_rows()
            if L["confirm"]:                       # Lösch-Nachfrage für ganze Liste
                cur = rows[L["fsel"]] if 0 <= L["fsel"] < len(rows) else None
                nm = str((cur or {}).get("name") or "?")
                addclip(by + 1, ix, "LISTE LÖSCHEN", iw, C["bright"])
                addclip(by + 3, ix, "»%s« wirklich löschen?" % nm[:max(4, iw - 22)],
                        iw, C["bright"])
                return
            addclip(by + 1, ix, "LISTEN · FOKUS", iw, C["bright"])
            input_row = by + bh - 3
            grid_bottom = (input_row - 1) if L["adding"] else bottom
            if not rows:
                addclip(by + 3, ix, "noch nichts", iw, C["faint"])
            else:
                # Token-Stream: Zonen-Label (1 Zeile) + Kasten (3 Zeilen). Ein
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
                heights = [BOX_HEIGHT if t[0] == "node" else 1 for t in seq]
                starts, acc = [], 0
                for h in heights:
                    starts.append(acc); acc += h
                total_lines = acc
                sel_line = next((starts[k] for k, t in enumerate(seq)
                                 if t[0] == "node" and t[2] == L["fsel"]), 0)
                top_line = 0
                if total_lines > Hh:
                    target = max(0, min(sel_line - (Hh - 3), total_lines - Hh))
                    # auf Token-Grenze einrasten — AUFrunden, sonst rutscht
                    # der gewählte Kasten unten halb aus dem Fenster
                    top_line = next((s for s in starts if s >= target), target)
                sel_node = rows[L["fsel"]] if 0 <= L["fsel"] < len(rows) else None
                for k, t in enumerate(seq):
                    ln = starts[k]
                    if ln + heights[k] - 1 < top_line:  # ganz oberhalb → weg
                        continue
                    yy = y0 + (ln - top_line)
                    if yy + heights[k] - 1 > grid_bottom:   # nur ganze Kästen
                        break
                    if t[0] == "lbl":
                        if t[1]:
                            addclip(yy, ix, t[1], iw, C["faint"])
                    else:
                        kasten_render(self._root_box(t[1], iw), ix, yy, iw,
                                      grid_bottom, sel=(t[1] is sel_node))
                if total_lines > top_line + Hh:
                    safe_addstr(grid_bottom, ix + iw - 5, "+", C["faint"])
            if L["adding"]:                        # neue Liste / umbenennen tippen
                lbl = "umbenennen" if L["imode"] == "frename" else "neue liste"
                addclip(input_row, ix, lbl + ": " + L["input"] + "_",
                        iw, C["bright"])
            if L["msg"]:
                addclip(bottom, ix, L["msg"], iw, C["faint"])

    def _root_box(self, row, w):
        """The box of one root node, w cells wide, from the core
        (view.box, GET /api/lists?view=1&box=W). The loaded lists carry
        boxes of the width last drawn; at another width (first draw, a
        resize) the boxes are asked once for that width — without touching
        the loaded state — and the next load brings them along."""
        L = self.L
        if L.get("lists_box_w") == w:
            return row.get("box")
        L["box_w"] = w
        key = (w, id(L.get("lists")))
        memo = self.__dict__.setdefault("_memo", {}).get("boxes")
        if not (memo and memo[0] == key):
            found = {}
            try:
                fresh = api_call("/api/lists?view=1&box=%d" % w) or []
            except Exception:
                fresh = []

            def walk(lid, items):
                for it in items or []:
                    if isinstance(it, dict):
                        if l_view(it).get("box"):
                            found[(lid, it.get("id"))] = l_view(it)["box"]
                        walk(lid, it.get("items"))

            for lst in fresh if isinstance(fresh, list) else []:
                if isinstance(lst, dict):
                    if l_view(lst).get("box"):
                        found[(lst.get("id"), None)] = l_view(lst)["box"]
                    walk(lst.get("id"), lst.get("items"))
            memo = (key, found)
            self._memo["boxes"] = memo
        return memo[1].get((row.get("lid"), row.get("iid")))

    def _ebene_bild(self, w, h):
        """The picture of the open level from the core (GET
        /api/lists/<lid>/bild, the same as the tile) — asked again only when
        something it shows changed (the loaded lists, path, selection, size)."""
        L = self.L
        lid = L["def"].get("id")
        key = (lid, tuple(L["path"]), L["isel"], L["showdone"], w, h, id(L.get("lists")))
        memo = self.__dict__.setdefault("_memo", {}).get("bild")
        if memo and memo[0] == key:
            return memo[1]
        q = "/api/lists/%s/bild?w=%d&h=%d&auswahl=%d" % (
            urllib.parse.quote(str(lid)), max(1, w), max(1, h), L["isel"])
        if L["path"]:
            q += "&pfad=" + ",".join(str(i) for i in L["path"])
        if L["showdone"]:
            q += "&erledigte=1"
        try:
            bild = api_call(q) or {}
        except Exception:
            bild = {}
        if not isinstance(bild.get("zeilen"), list):
            bild = {"zeilen": [[["liste nicht erreichbar", "leise"]]], "bernstein": None}
        self._memo["bild"] = (key, bild)
        return bild

    def _malen(self, y, x, zeilen, y_max=None):
        """Neutrale Zeilen (Stücke [text, rolle], core/listen_bild.py) ab
        (y, x) malen: Rolle → TUI-Farbe (FARBROLLEN), sonst nichts."""
        C, safe_addstr = self.z.C, self.z.safe_addstr
        for r, zeile in enumerate(zeilen):
            if y_max is not None and y + r > y_max:
                break
            xx = x
            for text, rolle in zeile:
                safe_addstr(y + r, xx, text, C.get(rolle_farbe(rolle), 0))
                xx += len(text)

    def _bernstein(self, y, bx, x, info):
        """TUI-Veredelung der Bernsteinleiste, die listen_bild an Zeile y
        gesetzt hat (info: breite, done, total): dieselbe Stelle, dieselbe
        Breite, nur schöner — Pixel-Steine (Sashas Treppenschliff, der zuletzt
        abgehakte glimmt) oder schattierte Bernstein-Spalten; der Zähler in
        Bernstein. Gewählt (isel -1): › links, Zähler invers."""
        C, L, PIX_MODUS = self.z.C, self.L, self.z.PIX_MODUS
        pix_attr, safe_addstr = self.z.pix_attr, self.z.safe_addstr
        done, total, breite = info["done"], info["total"], info["breite"]
        sel = (L["isel"] == -1)
        cnt = " %d/%d" % (done, total)
        sw = breite - 2                           # Steine zwischen ▐ und ▌
        zattr = (C["amber"] | curses.A_REVERSE) if sel else C["amber"]
        if C.get("pix_bg") is not None and PIX_MODUS != "off":
            glimm = int(time.time() * 4) % 8
            rows = pixel.bernstein_zellen(done, total, breite, C["pix_bg"], glimm,
                                          "half" if PIX_MODUS == "half" else "mix")
            for r, line in enumerate(rows):
                for i, (ch, fg, bgc) in enumerate(line):
                    safe_addstr(y + r, x + i, ch, pix_attr(fg, bgc))
        else:                                     # ohne 256 Farben: Spalten schattieren
            cols = list(info.get("steine") or "")    # columns from the core's picture
            for r in (0, 1):
                safe_addstr(y + r, x, "▐", C["amberdk"])
                safe_addstr(y + r, x + 1 + sw, "▌", C["amberdk"])
            for i, c in enumerate(cols):
                if c == "L":                      # Glanz oben links, Schatten unten rechts
                    anf = i == 0 or cols[i - 1] != "L"
                    end = i == len(cols) - 1 or cols[i + 1] != "L"
                    breit = not (anf and end)
                    safe_addstr(y, x + 1 + i, "█",
                                C["amberhi"] if (anf and breit) else C["amber"])
                    safe_addstr(y + 1, x + 1 + i, "█",
                                C["amberdk"] if (end and breit) else C["amber"])
                elif c == "U":
                    safe_addstr(y, x + 1 + i, "░", C["amberdk"])
                    safe_addstr(y + 1, x + 1 + i, "░", C["amberdk"])
        safe_addstr(y, x + breite, cnt, zattr)
        if sel:
            safe_addstr(y, bx + 1, "›", C["bright"])

    def kasten_render(self, box, x, y, w, y_max, sel=False):
        """ONE node as a box at (y, x): the rows come from the core (view.box
        {plain, selected}, w cells wide), only painted here. What would fall
        below y_max is left out. Returns the next free row."""
        if y > y_max:
            return y_max + 1
        rows = (box or {}).get("selected" if sel else "plain")
        if not isinstance(rows, list):        # no box (core not reached)
            rows = [[], [["?", "leise"]], []]
        self._malen(y, x, rows, y_max)
        return y + BOX_HEIGHT

    def proj_render(self, node, x, y, w, y_max, sel_node=None, mark_focus=False):
        """Render-Routine für die verschachtelte Projekt-Anzeige der Fokus-Box —
        die gibt es nur noch im alten 3-Spalten-Dashboard (Backup, /dashboard an,
        tui/ansichten/dashboard.py); das Listen-Werkzeug zeichnet seit 2026-10-11
        Kästen (kasten_render). Blatt-Projekt = Titel + Erfüllungsleiste (2 Zeilen);
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
