"""Der Kern-Bauplan (memory/system/bauplan_kern.md) gegen den Code.

Sasha, 05.10.2026: „ich will nich dass wir irgendwann an einen punkt kommen
an dem der code unwartbar wird und alles um die ohren fliegt!" ZENTRALE ist
71.000 Zeilen groß und wächst. Gemessen an diesem Tag: zwischen den Schichten
kein einziger Verstoß — aber 11 Import-Kreise im KI-Kern und eine TUI, deren
`run_ui` 7.700 Zeilen lang ist. Beides ist entstanden, weil nichts es
verhindert hat.

Dieser Test liest die Tabellen des Bauplans und wird rot, wenn
  1. eine Kern-Datei keine Schicht hat (oder der Bauplan eine erfindet),
  2. eine Datei aus einer HÖHEREN Schicht importiert,
  3. ein Import-Kreis entsteht, der nicht als Altlast eingetragen ist,
  4. jemand eine Tür umgeht (Tutor, TUI),
  5. eine Funktion oder Datei über die Riesen-Grenze wächst.

Altlasten stehen mit ihrer Zahl im Bauplan und dürfen nur SCHRUMPFEN: ist
eine erledigt, verlangt der Test, sie auszutragen. So kann die Liste nicht
still veralten.

Gezählt werden auch Importe innerhalb von Funktionen — sie sind genauso eine
Abhängigkeit, nur versteckt. Genau dort haben sich die Kreise gehalten.
"""

import ast
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "core")
BAUPLAN = os.path.join(ROOT, "memory", "system", "bauplan_kern.md")

SCHICHT_NAMEN = {1: "Fundament", 2: "Dienste", 3: "KI-Kern",
                 4: "Ablauf und Anschlüsse", 5: "Routen"}

# Wo die Riesen-Grenze gilt. scripts/ und tests/ sind Werkzeuge, keine
# Bausubstanz.
RIESEN_BEREICHE = ("core", "ui", "tui")
RIESE_FUNKTION = 250
RIESE_DATEI = 1500

# skill_vorlagen/: mitgelieferte Skills, darunter fremder Code von Anthropic
# (core/skill_vorlagen/anthropic/, 2026-10-07) — Daten für die Sandbox, kein
# Teil des Kerns und nie importiert.
UEBERSPRINGEN = ("__pycache__", "skill_vorlagen")


# ── Bauplan lesen ──────────────────────────────────────────────────────

def _text():
    with open(BAUPLAN, encoding="utf-8") as f:
        return f.read()


def _abschnitt(ueberschrift):
    text = _text()
    m = re.search(r"^##+ [^\n]*" + re.escape(ueberschrift) + r"[^\n]*\n", text, re.M)
    assert m, f"Abschnitt fehlt im Bauplan: {ueberschrift}"
    rest = text[m.end():]
    n = re.search(r"^##+ ", rest, re.M)
    return rest[:n.start()] if n else rest


def _zeilen(abschnitt):
    """Tabellenzeilen, deren erste Zelle `code` ist → Liste der Zellen."""
    raus = []
    for line in abschnitt.splitlines():
        if line.startswith("| `"):
            raus.append([z.strip() for z in line.strip().strip("|").split("|")])
    return raus


def _code(zelle):
    return re.findall(r"`([^`]+)`", zelle)


def bauplan_schichten():
    raus = {}
    for z in _zeilen(_abschnitt("Module")):
        raus[_code(z[0])[0]] = int(z[1])
    return raus


def bauplan_tueren():
    """Bereich → erlaubte Kern-Module."""
    return {_code(z[0])[0]: set(_code(z[1])) for z in _zeilen(_abschnitt("Türen"))}


def ausgezogene_apps():
    """Modulnamen ausgezogener Apps (Abschnitt „Ausgezogene Apps", erste
    Spalte) — die importiert im Hub niemand (Wächter E1, 2026-10-22)."""
    raus = set()
    for z in _zeilen(_abschnitt("Ausgezogene Apps")):
        raus |= set(_code(z[0]))
    return raus


def altlast_kreise():
    raus = set()
    for z in _zeilen(_abschnitt("Altlast: Kreis-Kanten")):
        a, b = [s.strip() for s in _code(z[0])[0].split("→")]
        raus.add((a, b))
    return raus


def altlast_tueren():
    raus = set()
    for z in _zeilen(_abschnitt("Altlast: Türen")):
        a, b = [s.strip() for s in _code(z[0])[0].split("→")]
        raus.add((a, b))
    return raus


def altlast_riesen():
    return {_code(z[0])[0]: int(z[1].replace(".", "")) for z in
            _zeilen(_abschnitt("Altlast: Riesen"))}


# ── Code lesen ─────────────────────────────────────────────────────────

def kern_module():
    """Modulname → Dateien. Pakete (profil/) zählen als EIN Modul."""
    raus = {}
    for eintrag in sorted(os.listdir(CORE)):
        pfad = os.path.join(CORE, eintrag)
        if eintrag.endswith(".py") and eintrag != "__init__.py":
            raus[eintrag[:-3]] = [pfad]
        elif os.path.isdir(pfad) and os.path.exists(os.path.join(pfad, "__init__.py")):
            raus[eintrag] = [os.path.join(w, f) for w, _, fs in os.walk(pfad)
                             if not any(u in w for u in UEBERSPRINGEN)
                             for f in fs if f.endswith(".py")]
    return raus


def _importierte_namen(pfad):
    """Oberste Namen aller absoluten Importe — auch innerhalb von Funktionen."""
    with open(pfad, encoding="utf-8") as f:
        baum = ast.parse(f.read())
    namen = set()
    for k in ast.walk(baum):
        if isinstance(k, ast.Import):
            namen |= {a.name.split(".")[0] for a in k.names}
        elif isinstance(k, ast.ImportFrom) and k.module and k.level == 0:
            namen.add(k.module.split(".")[0])
    return namen


def kern_kanten():
    """{(von, nach)} zwischen Kern-Modulen."""
    module = kern_module()
    kanten = set()
    for name, dateien in module.items():
        for d in dateien:
            for ziel in _importierte_namen(d):
                if ziel in module and ziel != name:
                    kanten.add((name, ziel))
    return kanten


def kreis_kanten(kanten):
    """Alle Kanten, die in einem Kreis liegen (beide Enden in derselben
    starken Zusammenhangskomponente)."""
    nachbarn = {}
    for a, b in kanten:
        nachbarn.setdefault(a, set()).add(b)
        nachbarn.setdefault(b, set())
    # Tarjan, iterativ genug für 60 Knoten
    index, low, stapel, auf, komp = {}, {}, [], set(), {}
    zaehler = [0]

    def besuche(v):
        index[v] = low[v] = zaehler[0]
        zaehler[0] += 1
        stapel.append(v)
        auf.add(v)
        for w in nachbarn[v]:
            if w not in index:
                besuche(w)
                low[v] = min(low[v], low[w])
            elif w in auf:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            gruppe = set()
            while True:
                w = stapel.pop()
                auf.discard(w)
                gruppe.add(w)
                if w == v:
                    break
            gruppe = frozenset(gruppe)
            for w in gruppe:
                komp[w] = gruppe

    for v in sorted(nachbarn):
        if v not in index:
            besuche(v)
    return {(a, b) for a, b in kanten if komp[a] is komp[b] and len(komp[a]) > 1}


def _py_dateien(bereich):
    for w, _, fs in os.walk(os.path.join(ROOT, bereich)):
        if any(u in w for u in UEBERSPRINGEN):
            continue
        for f in sorted(fs):
            if f.endswith(".py"):
                yield os.path.join(w, f)


def riesen_im_code():
    """'pfad' → Zeilen für Dateien, 'pfad::a.b' → Zeilen für Funktionen."""
    raus = {}
    for bereich in RIESEN_BEREICHE:
        for pfad in _py_dateien(bereich):
            rel = os.path.relpath(pfad, ROOT)
            with open(pfad, encoding="utf-8") as f:
                quelle = f.read()
            n = quelle.count("\n")
            if n > RIESE_DATEI:
                raus[rel] = n

            def gehe(knoten, kette):
                for kind in ast.iter_child_nodes(knoten):
                    if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef,
                                         ast.ClassDef)):
                        name = kette + [kind.name]
                        if not isinstance(kind, ast.ClassDef):
                            laenge = kind.end_lineno - kind.lineno
                            if laenge > RIESE_FUNKTION:
                                raus[rel + "::" + ".".join(name)] = laenge
                        gehe(kind, name)
                    else:
                        gehe(kind, kette)

            gehe(ast.parse(quelle), [])
    return raus


# ── 1. Vollständig ─────────────────────────────────────────────────────

def test_jede_kern_datei_hat_eine_schicht():
    fehlt = sorted(set(kern_module()) - set(bauplan_schichten()))
    assert not fehlt, (
        f"Diese Kern-Module stehen nicht im Bauplan: {fehlt}. Trag sie in "
        f"memory/system/bauplan_kern.md unter 'Module' mit ihrer Schicht ein "
        f"(1 Fundament … 5 Routen). Unsicher? Die niedrigste Schicht, deren "
        f"Regeln das Modul erfüllt.")


def test_der_bauplan_erfindet_keine_module():
    zuviel = sorted(set(bauplan_schichten()) - set(kern_module()))
    assert not zuviel, (
        f"Der Bauplan nennt Module, die es in core/ nicht gibt: {zuviel}. "
        f"Umbenannt oder gelöscht? Dann auch im Bauplan.")


def test_schichten_sind_gueltig():
    falsch = {m: s for m, s in bauplan_schichten().items() if s not in SCHICHT_NAMEN}
    assert not falsch, f"Unbekannte Schicht-Nummern im Bauplan: {falsch}"


# ── 2. Nur nach unten ──────────────────────────────────────────────────

def test_importe_zeigen_nur_nach_unten():
    schicht = bauplan_schichten()
    verstoesse = []
    for a, b in sorted(kern_kanten()):
        if a in schicht and b in schicht and schicht[b] > schicht[a]:
            verstoesse.append(
                f"{a} ({SCHICHT_NAMEN[schicht[a]]}) importiert {b} "
                f"({SCHICHT_NAMEN[schicht[b]]})")
    assert not verstoesse, (
        "Abhängigkeit nach OBEN — eine untere Schicht darf die obere nicht "
        "kennen:\n  " + "\n  ".join(verstoesse) +
        "\nBeheben: das Gebrauchte nach unten verschieben, oder es von oben "
        "hereingeben (als Argument/Callback) statt es zu importieren.")


# ── 3. Kreise ──────────────────────────────────────────────────────────

def test_keine_neuen_import_kreise():
    neu = sorted(kreis_kanten(kern_kanten()) - altlast_kreise())
    assert not neu, (
        "Neuer Import-Kreis (A braucht B, B braucht A — auch über Umwege). "
        "Diese Kanten liegen in einem Kreis und sind keine Altlast:\n  " +
        "\n  ".join(f"{a} → {b}" for a, b in neu) +
        "\nBeheben: das gemeinsam Gebrauchte in ein eigenes, tieferes Modul "
        "ziehen. Nicht als Altlast eintragen — die Liste darf nur schrumpfen.")


def test_erledigte_kreis_altlasten_sind_ausgetragen():
    erledigt = sorted(altlast_kreise() - kreis_kanten(kern_kanten()))
    assert not erledigt, (
        "Gut gemacht — diese Kanten liegen in keinem Kreis mehr:\n  " +
        "\n  ".join(f"{a} → {b}" for a, b in erledigt) +
        "\nStreich sie im Bauplan unter 'Altlast: Kreis-Kanten'.")


# ── 4. Türen ───────────────────────────────────────────────────────────

def _tuer_verstoesse():
    module = set(kern_module())
    erlaubt = bauplan_tueren()
    raus = set()
    # Apps (seit 2026-10-09 der Tutor, eigenes Repo) importiert hier
    # niemand — der Hub redet mit ihnen nur per HTTP (hub_bauplan.md). Welche
    # ausgezogen sind, steht im Bauplan („Ausgezogene Apps", Wächter E1).
    ausgezogen = ausgezogene_apps()
    for bereich in ("core", "ui", "tui", "scripts"):
        for pfad in _py_dateien(bereich):
            rel = os.path.relpath(pfad, ROOT)
            for name in _importierte_namen(pfad) & ausgezogen:
                raus.add((rel, name))
    # Fronten und Addon: nur die freigegebenen Kern-Module.
    for bereich, frei in erlaubt.items():
        for pfad in _py_dateien(bereich.rstrip("/")):
            rel = os.path.relpath(pfad, ROOT)
            for ziel in _importierte_namen(pfad) & module:
                if ziel not in frei:
                    raus.add((rel, ziel))
    return raus


def test_niemand_geht_an_den_tueren_vorbei():
    neu = sorted(_tuer_verstoesse() - altlast_tueren())
    assert not neu, (
        "Tür umgangen:\n  " + "\n  ".join(f"{a} → {b}" for a, b in neu) +
        "\nApps (der Tutor) werden nie importiert, nur per HTTP angesprochen; "
        "die TUI darf aus dem Kern nur, was im Bauplan unter 'Türen' steht. "
        "Die TUI redet sonst per HTTP mit den Routen in ui/routen/.")


def test_erledigte_tuer_altlasten_sind_ausgetragen():
    erledigt = sorted(altlast_tueren() - _tuer_verstoesse())
    assert not erledigt, (
        "Diese Tür-Altlasten gibt es nicht mehr:\n  " +
        "\n  ".join(f"{a} → {b}" for a, b in erledigt) +
        "\nStreich sie im Bauplan unter 'Altlast: Türen'.")


# ── 5. Riesen ──────────────────────────────────────────────────────────

def test_keine_neuen_riesen():
    bekannt = altlast_riesen()
    neu = {k: v for k, v in riesen_im_code().items() if k not in bekannt}
    assert not neu, (
        f"Neu über der Grenze (Funktion > {RIESE_FUNKTION}, Datei > "
        f"{RIESE_DATEI} Zeilen):\n  " +
        "\n  ".join(f"{k}: {v}" for k, v in sorted(neu.items())) +
        "\nAufteilen, bevor es weitergeht — eigene Funktion, eigenes Modul.")


def test_riesen_wachsen_nicht():
    code = riesen_im_code()
    gewachsen = {k: (code[k], grenze) for k, grenze in altlast_riesen().items()
                 if code.get(k, 0) > grenze}
    assert not gewachsen, (
        "Eingefrorene Riesen sind gewachsen:\n  " +
        "\n  ".join(f"{k}: {ist} statt höchstens {g}"
                    for k, (ist, g) in sorted(gewachsen.items())) +
        "\nNeues gehört in eine eigene Datei/Funktion; der Riese wird nur "
        "noch kleiner (Sasha, 05.10.2026: einfrieren, dann zerlegen).")


def test_geschrumpfte_riesen_senken_ihre_grenze():
    code = riesen_im_code()
    kleiner = {k: (code.get(k), grenze) for k, grenze in altlast_riesen().items()
               if code.get(k, 0) < grenze}
    assert not kleiner, (
        "Gut gemacht — kleiner geworden. Im Bauplan unter 'Altlast: Riesen' "
        "die Grenze senken (oder die Zeile streichen, wenn unter der "
        "Riesen-Grenze):\n  " +
        "\n  ".join(f"{k}: {'streichen' if ist is None else f'auf {ist}'} "
                    f"(steht {g})" for k, (ist, g) in sorted(kleiner.items())))


# ── 6. Routen-Schicht ──────────────────────────────────────────────────

def test_app_py_haelt_keine_routen():
    """Bis 2026-10-06 standen alle 89 Routen in ui/app.py. Damit das nicht
    zurückwächst: app.py legt die App an und hängt die Bereiche ein, mehr
    nicht."""
    with open(os.path.join(ROOT, "ui", "app.py"), encoding="utf-8") as f:
        quelle = f.read()
    assert "@app.route(" not in quelle, (
        "In ui/app.py steht wieder eine Route. Sie gehört in ihren Bereich "
        "unter ui/routen/ (oder einen neuen Bereich, eingetragen in "
        "ui/routen/__init__.py).")


def test_jeder_routen_bereich_ist_eingehaengt():
    ordner = os.path.join(ROOT, "ui", "routen")
    module = {f[:-3] for f in os.listdir(ordner)
              if f.endswith(".py") and f not in ("__init__.py", "gemeinsam.py")}
    with open(os.path.join(ordner, "__init__.py"), encoding="utf-8") as f:
        init = f.read()
    m = re.search(r"BEREICHE = \(([^)]*)\)", init)
    assert m, "ui/routen/__init__.py hat kein BEREICHE-Tupel"
    eingehaengt = {n.strip() for n in m.group(1).split(",") if n.strip()}
    fehlt = sorted(module - eingehaengt)
    assert not fehlt, (
        f"Diese Routen-Module werden nie eingehängt: {fehlt}. Trag sie in "
        f"ui/routen/__init__.py unter BEREICHE (und im Import) ein.")


# ── 7. Kern-Auszug: Grenz-Wächter E1 und E2 ───────────────────────────
# memory/hub/kern_auszug_inventur.md Abschnitt E (2026-10-22). E1 steckt in
# _tuer_verstoesse oben (ausgezogene Apps importiert niemand); hier, dass die
# Liste selbst taugt, und E2: die Tür der TUI schrumpft nur.

# Die Tür der TUI am 2026-10-22. Darf nur SCHRUMPFEN: steht im Bauplan ein
# Modul, das hier fehlt, ist es neu — und neu darf keins dazukommen (die TUI
# holt Fach-Bild und -Zahl über HTTP). Fliegt eins raus, hier mit streichen.
TUI_TUER_HOECHSTENS = {"theme", "tone", "pc_status", "listen_baum", "listen_bild",
                       "graph_reihen", "stil", "tastentabelle", "uhr"}


def test_ausgezogene_apps_gibt_es_im_kern_nicht_mehr():
    ausgezogen = ausgezogene_apps()
    assert "tutor" in ausgezogen
    noch_da = sorted(ausgezogen & set(kern_module()))
    assert not noch_da, (
        f"Als ausgezogen eingetragen, aber noch in core/: {noch_da}. Erst "
        f"ausziehen (eigenes Repo, HTTP), dann eintragen.")


def test_tui_tuer_schrumpft_nur():
    tuer = bauplan_tueren()["tui/"]
    neu = sorted(tuer - TUI_TUER_HOECHSTENS)
    assert not neu, (
        f"Neu in der Tür der TUI: {neu}. Die Tür wächst nicht mehr (Leitlinie "
        f"überall deploybar, 2026-10-22): die TUI holt es per HTTP.")
    weg = sorted(TUI_TUER_HOECHSTENS - tuer)
    assert not weg, (
        f"Gut gemacht — {weg} ist aus der Tür. Auch in "
        f"tests/test_kern_bauplan.py TUI_TUER_HOECHSTENS streichen.")


def test_jedes_modul_der_tui_tuer_wird_gebraucht():
    """Jede Zeile der Tür braucht einen Grund: ein Modul, das die TUI nicht
    mehr importiert, fliegt raus (und aus deploy/aussenposten.txt)."""
    benutzt = set()
    for pfad in _py_dateien("tui"):
        benutzt |= _importierte_namen(pfad)
    unbenutzt = sorted(bauplan_tueren()["tui/"] - benutzt)
    assert not unbenutzt, (
        f"In der Tür, aber von tui/ nicht importiert: {unbenutzt}. Streichen "
        f"(Bauplan, TUI_TUER_HOECHSTENS, deploy/aussenposten.txt).")


def test_tuer_traegt_keinen_app_code():
    drin = sorted(bauplan_tueren()["tui/"] & ausgezogene_apps())
    assert not drin, f"Modul einer ausgezogenen App in der Tür der TUI: {drin}"


# ── 8. Apps live outside the core (Sasha, 2026-10-31 — permanent) ─────
# Schematix (building kit 13–15) was built into the core and has to be pulled
# out again. So: the built-in apps in core/eingebaute_apps.py are a legacy
# list that may only SHRINK. The bauplan table „Altlast: Built-in apps" names
# them; this frozen set keeps the table itself from growing.

BUILT_IN_APPS_AT_MOST = {
    "fokus", "notizen", "kalender", "graph", "assistent", "ablage", "desk",
    "schematix",  # to extract (memory/open/schematix_extraction.md)
    "werkstatt", "mail", "klavier", "adapter", "cloud_folder", "cloud",
    "tutor",  # already its own repo; ERSATZ fallback only
}

_RULE = ('CLAUDE.md, section "Apps live outside the core": build every new '
         'app as its own package (own folder/repo with app.toml, like '
         'tutor/map/budget), never as a module in core/, tui/ansichten/ or '
         'ui/routen/ and never as an entry in core/eingebaute_apps.py. '
         'A missing interface becomes a general building block in the core.')


def built_in_apps_in_code():
    """Every app name core/eingebaute_apps.py knows (pure data, layer 1)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_eingebaute_apps_guard", os.path.join(CORE, "eingebaute_apps.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    names = set()
    for table in ("EINGEBAUT", "ERSATZ", "PORTS", "INSTANCE_PORTS"):
        names |= set(getattr(mod, table, {}))
    return names


def built_in_apps_in_bauplan():
    return {_code(z[0])[0] for z in _zeilen(_abschnitt("Altlast: Built-in apps"))}


def test_no_new_built_in_apps():
    new = sorted(built_in_apps_in_code() - built_in_apps_in_bauplan())
    assert not new, f"New built-in app in core/eingebaute_apps.py: {new}. {_RULE}"
    grown = sorted(built_in_apps_in_bauplan() - BUILT_IN_APPS_AT_MOST)
    assert not grown, (
        f"The bauplan table 'Altlast: Built-in apps' grew: {grown}. It may "
        f"only shrink. {_RULE}")


def test_extracted_built_in_apps_are_struck():
    gone = sorted(built_in_apps_in_bauplan() - built_in_apps_in_code())
    assert not gone, (
        f"Well done — {gone} is no longer built in. Strike it in "
        f"memory/system/bauplan_kern.md ('Altlast: Built-in apps').")
    stale = sorted(BUILT_IN_APPS_AT_MOST - built_in_apps_in_bauplan())
    assert not stale, (
        f"{stale} left the bauplan table; strike it in "
        f"tests/test_kern_bauplan.py BUILT_IN_APPS_AT_MOST too.")
