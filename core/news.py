# core/news.py
#
# Persönliche Tagesschau für die ZENTRALE-KI — Baustein-Modell.
#
# ── Idee ──────────────────────────────────────────────────────────────
# Hol Weltpolitik aus vielen RSS-Feeds (breit gestreut, inkl. Staatsmedien),
# bündle sie zu THEMEN-BAUSTEINEN (ein Stein = ein Thema + die beteiligten
# Stimmen), und lass die lokale KI daraus eine gesprochene Sendung bauen,
# die dieselbe Story über mehrere Quellen GEGENÜBERSTELLT.
#
# ── Warum Bausteine statt einem Brei ──────────────────────────────────
# Sashas Lego-Modell: einzelne Steine sind flexibel. Jeder Stein trägt
# Status-Aufkleber, mit denen sich Sashas Feinheiten sauber abbilden:
#   wichtigkeit       wie "dick" der Stein ist (Annexion >> Kunstausstellung)
#   zuletzt_bewegt    wann zuletzt eine neue Stimme/Entwicklung dazukam
#   gesehen_von_sasha Haken, sobald der Stein in einer Sendung serviert wurde
# Daraus folgt automatisch:
#   - DECAY: Steine verlieren mit der Zeit Gewicht. Leichte fallen unter die
#     Schwelle und werden archiviert (Kunstausstellung interessiert ne Woche
#     später keinen). Schwere verlieren kaum -> bleiben im "schuldest-du-
#     Sasha"-Stapel, auch wenn spät (Trump-Annexion erfährt Sasha trotzdem).
#   - KEINE WIEDERHOLUNG: was Sasha schon gesehen hat, kommt nur wieder, wenn
#     sich der Stein BEWEGT hat ("Update zu X").
#   - SENDUNG = schwerste ungesehene Steine zuerst, gedeckelt -> Aufmerksamkeit
#     bleibt frisch.
#
# ── Cross-Poll-Identität (bge-m3 verdient sich hier sein Geld) ─────────
# Pro Poll clustert das LLM die frischen Meldungen zu Bausteinen. Ob ein
# neuer Baustein zu einem BESTEHENDEN Stein gehört (= dieselbe laufende
# Story, nur neue Stimme), entscheiden wir per Embedding-Ähnlichkeit des
# Themas (cosine). So wächst die Ukraine-Story über Polls hinweg zu EINEM
# Stein, statt jeden Poll neu aufzutauchen.
#
# ── Graph-Kopplung: bewusst KEINE ─────────────────────────────────────
# News leben in EIGENEM Store (data/news_stories.json), NICHT im Konzept-
# Graphen. Der Graph speichert nur Sashas Realität, kein Weltwissen — News
# reinzukippen würde ihn zumüllen + bei Chats mit-aktivieren. Personalisierung
# ("das kennst du schon") läuft später als reine LESE-Brücke beim Sendung-
# Bauen (eigener, späterer Schritt). Was Sasha wirklich aufgreift, landet eh
# über den Konsolidierungs-Extraktor automatisch im Graphen.
#
# ── Transparenz ───────────────────────────────────────────────────────
# Feed-Fetches laufen durch net.get -> orangefarbenes Internet-Panel. Jeder
# Poll-Lauf kündigt sich laut an (push_log + push_internet_log): periodisch,
# aber sichtbar (nicht pro-Call gegatet wie web_suche).

import os
import re
import html as _html
import json as _json
import time
import threading
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

import net          # transparenter HTTP-Wrapper (loggt + spiegelt ins Internet-Panel)
import state        # Log-Streams (stdout + Dashboard-Panel + Internet-Panel)
import embeddings   # bge-m3: Themen-Ähnlichkeit fürs Cross-Poll-Matching
import web          # Web-Suche für den Aufholmodus (RSS hat keine Historie)


# ── Quellen ────────────────────────────────────────────────────────────
# Bewusst breit: westlicher Mainstream NEBEN Staatsmedien gegnerischer
# Blöcke. "herkunft" ist der Einordnungs-Kontext für die KI, keine
# technische Angabe. Tote/geblockte Quellen werden beim Fetch übersprungen.
FEEDS = [
    {"name": "Tagesschau",      "url": "https://www.tagesschau.de/index~rss2.xml",        "herkunft": "DE öffentlich-rechtlich"},
    {"name": "DW",              "url": "https://rss.dw.com/rdf/rss-en-all",               "herkunft": "DE international"},
    {"name": "BBC World",       "url": "http://feeds.bbci.co.uk/news/world/rss.xml",      "herkunft": "UK"},
    {"name": "Guardian World",  "url": "https://www.theguardian.com/world/rss",           "herkunft": "UK liberal"},
    {"name": "France 24",       "url": "https://www.france24.com/en/rss",                 "herkunft": "FR"},
    {"name": "NPR World",       "url": "https://feeds.npr.org/1004/rss.xml",              "herkunft": "US"},
    {"name": "Al Jazeera",      "url": "https://www.aljazeera.com/xml/rss/all.xml",       "herkunft": "QA"},
    {"name": "Times of Israel", "url": "https://www.timesofisrael.com/feed/",             "herkunft": "IL"},
    {"name": "Times of India",  "url": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms", "herkunft": "IN"},
    {"name": "CGTN",            "url": "https://www.cgtn.com/subscribe/rss/section/world.xml",       "herkunft": "CN Staat"},
    {"name": "TASS",            "url": "https://tass.com/rss/v2.xml",                     "herkunft": "RU Staat"},
    {"name": "RT",              "url": "https://www.rt.com/rss/news/",                    "herkunft": "RU Staat"},
]

_UA = ("Mozilla/5.0 (X11; Linux x86_64; rv:121.0) "
       "Gecko/20100101 Firefox/121.0")

# ── Limits / Tuning (alles grob, gehört später gebencht) ───────────────
MAX_PRO_FEED  = 6        # Meldungen pro Quelle pro Poll (klein für num_ctx)
DESC_CAP      = 300      # gespeicherter Anrisstext
CORPUS_DESC   = 160      # was das Cluster-LLM pro Meldung sieht
TIMEOUT_S     = 15

# ── Clustering (bge-m3 Average-Linkage, gemessen 2026-06-08) ──────────
# Das Gruppieren der Meldungen zu Bausteinen macht NICHT mehr das LLM (das
# lumpte ganze Regionen zu Mülleimern oder ließ Geschwister als Singletons
# stehen — gemessen). Stattdessen: bge-m3 bettet jede Meldung ein, Python
# clustert per Greedy-Average-Linkage. "Average" heißt: eine Meldung darf
# nur in einen Cluster, wenn ihre MITTLERE Ähnlichkeit zu ALLEN Mitgliedern
# über der Schwelle liegt — das verhindert Single-Link-Ketten (A~B~C, obwohl
# A≁C), an denen der Nahost-Blob hing. So trennen sich Ort-verschiedene
# Ereignisse (Beirut vs. Gaza vs. Iran-Raketen) von selbst, obwohl ihr
# Framing-Vokabular sich überlappt. T=0.64 empirisch ermittelt (137 echte
# Meldungen: bei 0.64 saubere quellen-/sprachübergreifende Cluster, Blob weg).
NEWS_CLUSTER_SIM         = 0.64
LABEL_BATCH              = 20     # Cluster pro Labeling-LLM-Call (mehr = JSON-Output reißt ab)
# Temperature für die News-LLM-Calls. Tradeoff, bewusst gewählt:
#   - sehr niedrig (0.2) drückt Fabulation, macht aber jede Sendung im selben
#     braven Ton -> monoton (Sasha will Lebendigkeit, 2026-06-08).
#   - Default (~1.0) lebendig, aber das 9B schmuggelt Weltwissen rein.
# 0.7 = lebendige Mitte (gleich wie der prod-Chat). WICHTIG: das löst die
# Fabulation NICHT — gemessen 2026-06-08 erfindet das 9B trotz scharfem Prompt
# + vollem Text noch Zahlen/Orte („7.000 Tote", „Tschernobyl", „Hormus-Sund").
# Das ist ein MODELL-Problem (Reasoning/Halluzination), kein Pipeline-Problem.
# Entscheidung mit Sasha: NICHT gegen das schwache Modell anbauen (extraktiv =
# flach, Python-Wache = komplex, low temp = monoton — jeder Workaround kostet),
# sondern PARKEN bis das stärkere/anti-halluzinations-getunte Modell steht. Bis
# dahin ist die generierte Sendung NICHT faktentreu-vertrauenswürdig.
NEWS_TEMPERATURE         = 0.7

MATCH_THRESHOLD          = 0.66   # Cross-Poll: Centroid-cosine ab hier = "gleiche Story"
HALBWERTSZEIT_H          = 48.0   # Wichtigkeit halbiert sich alle 48 h ohne Bewegung
ARCHIV_FLOOR             = 8.0    # aktuelle Wichtigkeit darunter -> Stein archiviert
SENDUNG_MAX              = 7      # max Bausteine pro Sendung (Aufmerksamkeitsspanne)
SENDUNG_MIN_WICHTIGKEIT  = 15.0   # darunter kommt's gar nicht erst in die Sendung
RUECKBLICK_MAX           = 10     # max Bausteine im Wochenrückblick (länger als Tagessendung)
RUECKBLICK_MIN_WICHTIGKEIT = 25.0 # Trivia (Basis darunter) fliegt aus dem Rückblick
GAP_SCHWELLE_TAGE        = 1.5    # Poll-Lücke im Rückblick-Fenster ab hier -> Aufholmodus (Web statt Store)
AUFHOL_QUERIES = [                # rückblickende Suchanfragen (DE + EN für Breite)
    "wichtigste Weltnachrichten und Weltpolitik der letzten Tage",
    "Weltpolitik Rückblick wichtigste Ereignisse diese Woche",
    "most important world news this week recap politics",
]

# ── Ollama (identisch zu consolidation.py/ai.py, sonst Modell-Reload) ──
OLLAMA_URL        = os.environ.get("OLLAMA_URL",        "http://localhost:11434")
OLLAMA_MODEL      = os.environ.get("OLLAMA_MODEL",      "qwen3.5:9b")
OLLAMA_KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")
OLLAMA_NUM_CTX    = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))
SUPPORTS_THINK    = OLLAMA_MODEL.startswith("qwen3")

INTERVAL_S    = int(os.environ.get("NEWS_INTERVAL_MIN", "180")) * 60
START_DELAY_S = int(os.environ.get("NEWS_START_DELAY_S", "90"))

# ── Pfade ──────────────────────────────────────────────────────────────
_ROOT         = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
_DATA         = os.path.join(_ROOT, "data")
_STORE_PATH   = os.path.join(_DATA, "news_stories.json")   # die Steine + Status
_DIGEST_PATH  = os.path.join(_DATA, "news_digest.json")    # die zuletzt gebaute Sendung


# ════════════════════════════════════════════════════════════════════════
# 1) SAMMELN  (Sashas Teil — Fetch/Parse/Dedup, unverändert)
# ════════════════════════════════════════════════════════════════════════
_TAG_RE = re.compile(r"<[^>]+>")

def _strip_html(s: str, cap: int = DESC_CAP) -> str:
    """HTML-Schnipsel -> reiner Text (Tags raus, Entities auf, gekürzt)."""
    if not s:
        return ""
    s = _TAG_RE.sub(" ", s)
    s = _html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > cap:
        s = s[:cap].rstrip() + " […]"
    return s

def _local(tag: str) -> str:
    """'{ns}entry' -> 'entry'; 'item' -> 'item'. Namespace-agnostisch."""
    return tag.rsplit("}", 1)[-1].lower() if tag else ""

def _child_text(elem, *names: str) -> str:
    """Text des ersten passenden Kind-Elements; href-Fallback (Atom-<link>)."""
    want = {n.lower() for n in names}
    for child in elem:
        if _local(child.tag) in want:
            txt = (child.text or "").strip()
            if txt:
                return txt
            href = child.get("href")
            if href:
                return href.strip()
    return ""

def _parse_feed(xml: bytes) -> list:
    """XML -> Liste roher Meldungs-Dicts. Findet <item> (RSS) + <entry> (Atom)."""
    root = ET.fromstring(xml)
    items = [el for el in root.iter() if _local(el.tag) in ("item", "entry")]
    out = []
    for it in items:
        out.append({
            "titel": _child_text(it, "title"),
            "text":  _child_text(it, "description", "summary", "content"),
            "link":  _child_text(it, "link"),
            "datum": _child_text(it, "pubDate", "published", "updated", "date"),
        })
    return out

def collect(pro_feed: int = MAX_PRO_FEED) -> list:
    """Alle FEEDS holen + parsen + putzen + per Titel deduplizieren.
    Robust: tote Quelle wird übersprungen, nicht der ganze Lauf gekillt."""
    alle = []
    gesehen = set()
    for feed in FEEDS:
        try:
            xml = net.get(feed["url"], timeout=TIMEOUT_S, headers={"User-Agent": _UA})
            items = _parse_feed(xml)
        except Exception as e:
            state.push_log(f"NEWS  ✗ {feed['name']} übersprungen: {e}")
            continue
        genommen = 0
        for it in items:
            titel = (it["titel"] or "").strip()
            if not titel:
                continue
            key = titel.lower()
            if key in gesehen:
                continue
            gesehen.add(key)
            alle.append({
                "quelle":   feed["name"],
                "herkunft": feed["herkunft"],
                "titel":    titel,
                "text":     _strip_html(it["text"]),
                "link":     it["link"],
                "datum":    it["datum"],
            })
            genommen += 1
            if genommen >= pro_feed:
                break
        state.push_log(f"NEWS  {feed['name']} → {genommen} Meldungen")
    return alle


# ════════════════════════════════════════════════════════════════════════
# 2) CLUSTERN  (Poll-Meldungen -> Themen-Bausteine, via LLM)
# ════════════════════════════════════════════════════════════════════════
# Das LLM bündelt EINEN Poll zu Bausteinen und bewertet die Wichtigkeit. Das
# Cross-Poll-Matching (gehört der Baustein zu einem bestehenden Stein?) macht
# danach Python per Embedding — nicht das LLM, das die alten Steine gar nicht
# im Kontext hat.
# Das Gruppieren macht Python (Average-Linkage über bge-m3-Embeddings, s.u.).
# Das LLM benennt nur die FERTIGEN Cluster — eine viel leichtere Aufgabe als
# 60 Schlagzeilen auf einen Schlag zu gruppieren (woran das 9B scheiterte).
_LABEL_PROMPT = (
    "Du bist ein Nachrichten-Redakteur. Du bekommst bereits FERTIG gruppierte "
    "Cluster — jeder Cluster ist EIN Vorfall, belegt durch Schlagzeilen mehrerer "
    "Quellen. Du gruppierst NICHTS um. Vergib pro Cluster (angesprochen über seine "
    "Nummer i):\n"
    "  thema       kurze, sachliche, stabile Überschrift (z.B. 'Parlamentswahl Armenien')\n"
    "  kategorie   eins von: konflikt, wahl, diplomatie, wirtschaft, gesellschaft, katastrophe, kultur, sport, sonstiges\n"
    "  wichtigkeit 0-100, weltpolitische Tragweite. Kriege/Wahlen/Diplomatie/große Krisen HOCH (70-100). "
    "Sport, Promis, Kultur, Lokales NIEDRIG (0-25).\n\n"
    "OUTPUT: nur gültiges JSON, keine Erklärung:\n"
    '{"labels": [{"i": 0, "thema": "...", "kategorie": "...", "wichtigkeit": 0}]}'
)


def _centroid(vecs: list) -> list:
    """
    Mittelvektor einer Liste von Embeddings (leere/None-Einträge ignoriert).
    Dient als inhaltlicher 'Fingerabdruck' eines Clusters: damit matcht
    _integriere denselben Vorfall über mehrere Polls hinweg, statt nur den
    LLM-`thema`-String zu vergleichen (der war zu grob -> Cross-Poll-Blobs).
    """
    gueltig = [v for v in vecs if v]
    if not gueltig:
        return []
    dim = len(gueltig[0])
    summe = [0.0] * dim
    for v in gueltig:
        for k in range(dim):
            summe[k] += v[k]
    return [x / len(gueltig) for x in summe]


def _cluster_items(vecs: list) -> list:
    """
    Greedy-Average-Linkage über die Item-Embeddings. Gibt eine Liste von
    Clustern zurück (jeder Cluster = Liste von Item-Indizes).

    Eine Meldung kommt in den Cluster, zu dessen Mitgliedern ihre MITTLERE
    cosine-Ähnlichkeit am höchsten ist — sofern die >= NEWS_CLUSTER_SIM liegt;
    sonst eröffnet sie einen neuen Cluster. Das 'mittlere zu ALLEN Mitgliedern'
    ist der Trick gegen Single-Link-Ketten: ein Gaza-Artikel kommt NICHT in den
    Beirut-Cluster, nur weil er zu EINEM Mitglied zufällig nah ist — er müsste
    im Schnitt zu allen passen. Items ohne Embedding werden Einzel-Cluster.
    (Reihenfolge-abhängig, aber pro Poll deterministisch — kein temp im Spiel.)
    """
    clusters = []          # list[list[int]]   — Item-Indizes pro Cluster
    cl_vecs  = []          # parallel dazu: die Embeddings der Mitglieder
    for i, vi in enumerate(vecs):
        if not vi:
            clusters.append([i]); cl_vecs.append([]); continue
        best, best_sim = None, NEWS_CLUSTER_SIM
        for c_idx, members in enumerate(cl_vecs):
            if not members:
                continue
            sims = [embeddings.cosine_similarity(vi, mv) for mv in members]
            avg = sum(sims) / len(sims)
            if avg >= best_sim:
                best, best_sim = c_idx, avg
        if best is None:
            clusters.append([i]); cl_vecs.append([vi])
        else:
            clusters[best].append(i); cl_vecs[best].append(vi)
    return clusters


def _label_clusters(clusters: list, items: list) -> list:
    """
    Pro fertigem Cluster thema/kategorie/wichtigkeit holen. Das LLM benennt nur,
    es gruppiert nicht. Fällt ein Call oder das Index-Alignment aus, greift pro
    Cluster ein Heuristik-Fallback (erste Schlagzeile als thema, 'sonstiges',
    Wichtigkeit grob aus der Quellenzahl). Gibt eine Liste paralleler Label-Dicts
    zurück (gleiche Reihenfolge wie `clusters`).

    WICHTIG — gebatcht: alle Cluster in EINEM Call zu labeln sprengt bei vielen
    Themen den JSON-Output (er wird mittendrin abgeschnitten -> Parse-Fehler ->
    ALLE Labels fallen auf die Heuristik zurück; genau das ist im Test passiert).
    Darum in Häppchen von LABEL_BATCH Clustern — jeder Call bleibt klein genug,
    und ein kaputtes Häppchen reißt nur seine ~20 Cluster in den Fallback, nicht alle.
    """
    # Fallback-Labels vorbereiten — gelten, bis das LLM sie überschreibt.
    labels = []
    for c in clusters:
        n_quellen = len({items[i].get("quelle") for i in c})
        labels.append({
            "thema":       (items[c[0]].get("titel") or "Thema").strip()[:80],
            "kategorie":   "sonstiges",
            # Mehr Quellen über dasselbe Ereignis = mehr Tragweite (grobe Heuristik).
            "wichtigkeit": min(60.0, 20.0 + 12.0 * n_quellen),
        })

    for start in range(0, len(clusters), LABEL_BATCH):
        chunk = list(range(start, min(start + LABEL_BATCH, len(clusters))))
        # LLM-Input: Cluster mit LOKALER Nummer (0..len(chunk)-1) + ein paar Schlagzeilen.
        blocks = []
        for local, gi in enumerate(chunk):
            kopf = "\n".join(
                f"   - [{items[i].get('quelle')} · {items[i].get('herkunft')}] {items[i].get('titel')}"
                for i in clusters[gi][:5]
            )
            blocks.append(f"[{local}]\n{kopf}")
        try:
            resp = net.post(
                f"{OLLAMA_URL}/api/chat",
                {
                    "model": OLLAMA_MODEL,
                    **({"think": False} if SUPPORTS_THINK else {}),
                    "messages": [
                        {"role": "system", "content": _LABEL_PROMPT},
                        {"role": "user",   "content": "Cluster:\n" + "\n\n".join(blocks)},
                    ],
                    "stream": False, "format": "json",
                    "keep_alive": OLLAMA_KEEP_ALIVE,
                    "options": {"num_ctx": OLLAMA_NUM_CTX, "temperature": NEWS_TEMPERATURE},
                },
                timeout=180,
            )
            parsed = _json.loads(resp.get("message", {}).get("content", "").strip())
            for lab in (parsed.get("labels", []) if isinstance(parsed, dict) else []):
                if not isinstance(lab, dict):
                    continue
                local = lab.get("i")
                if not isinstance(local, int) or not (0 <= local < len(chunk)):
                    continue
                gi = chunk[local]                     # lokale -> globale Cluster-Nummer
                thema = (lab.get("thema") or "").strip()
                if thema:
                    labels[gi]["thema"] = thema[:80]
                kat = (lab.get("kategorie") or "").strip().lower()
                if kat:
                    labels[gi]["kategorie"] = kat
                try:
                    labels[gi]["wichtigkeit"] = max(0.0, min(100.0, float(lab.get("wichtigkeit"))))
                except (TypeError, ValueError):
                    pass
        except Exception as e:
            state.push_log(f"NEWS  ✗ Cluster-Labeling Häppchen {start}-{start+len(chunk)} "
                           f"fehlgeschlagen (Heuristik-Fallback): {e}")
    return labels


def _cluster_poll(items: list) -> list:
    """
    Frische Meldungen -> Liste von Bausteinen [{thema, kategorie, wichtigkeit,
    stimmen, centroid}]. Pipeline (Python gruppiert, LLM benennt nur):
      1. bge-m3 bettet jede Meldung ein (Titel trägt die Eigennamen, Anriss den Kontext).
      2. Average-Linkage clustert deterministisch + mehrsprachig (_cluster_items).
      3. EIN LLM-Call labelt die fertigen Cluster (_label_clusters).
    Der `centroid` (Mittelvektor) wandert mit in den Store und ankert das
    Cross-Poll-Matching in _integriere. Fehlt das Embed-Modell, wird jede
    Meldung ihr eigener Cluster (kein Crash, nur kein Merge).
    """
    if not items:
        return []
    vecs = [
        embeddings.embed_document(((n.get("titel") or "") + " " + (n.get("text") or "")[:CORPUS_DESC]))
        for n in items
    ]
    clusters = _cluster_items(vecs)
    labels   = _label_clusters(clusters, items)

    bausteine = []
    for c, lab in zip(clusters, labels):
        bausteine.append({
            "thema":       lab["thema"],
            "kategorie":   lab["kategorie"],
            "wichtigkeit": lab["wichtigkeit"],
            "stimmen":     [items[i] for i in c],
            "centroid":    _centroid([vecs[i] for i in c]),
        })
    return bausteine


# ════════════════════════════════════════════════════════════════════════
# 3) STORE + MERGE + DECAY  (die Lego-Wand)
# ════════════════════════════════════════════════════════════════════════
def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")

def _stunden_seit(iso: str) -> float:
    """Stunden zwischen iso-Zeitstempel und jetzt (0 bei Parse-Fehler)."""
    try:
        return max(0.0, (datetime.now() - datetime.fromisoformat(iso)).total_seconds() / 3600.0)
    except Exception:
        return 0.0

def _aktuelle_wichtigkeit(story: dict) -> float:
    """
    Decay: Basis-Wichtigkeit halbiert sich alle HALBWERTSZEIT_H Stunden seit der
    letzten Bewegung. Schwere Steine überleben lange, leichte fallen schnell.
    """
    basis = story.get("wichtigkeit", 0.0)
    h = _stunden_seit(story.get("zuletzt_bewegt", story.get("zuerst_gesehen", _now())))
    return basis * (0.5 ** (h / HALBWERTSZEIT_H))

def _load_store() -> dict:
    if os.path.exists(_STORE_PATH):
        try:
            with open(_STORE_PATH, encoding="utf-8") as f:
                return _json.load(f)
        except Exception:
            pass
    return {"stories": [], "naechste_id": 1, "letzte_sendung": None}

def _save_store(store: dict):
    os.makedirs(_DATA, exist_ok=True)
    with open(_STORE_PATH, "w", encoding="utf-8") as f:
        _json.dump(store, f, ensure_ascii=False, indent=2)

def _merge_voices(story: dict, neue: list) -> bool:
    """Neue Stimmen (nach Titel) in einen Stein einpflegen. True wenn sich
    wirklich was bewegt hat (dann wird der Stein 'aufgefrischt')."""
    bekannt = {s["titel"].lower() for s in story["stimmen"]}
    bewegt = False
    for v in neue:
        if v["titel"].lower() not in bekannt:
            story["stimmen"].append(v)
            bekannt.add(v["titel"].lower())
            bewegt = True
    return bewegt

def _integriere(store: dict, baustein: dict):
    """
    Einen frisch geclusterten Baustein in den Store einfügen: per inhaltlicher
    Ähnlichkeit (Cluster-CENTROID vs. gespeicherter Story-Centroid) an einen
    bestehenden, nicht-archivierten Stein andocken (= laufende Story), sonst
    neuen Stein anlegen. Der Centroid (Mittel der Stimmen-Embeddings) ist ein
    robusterer Anker als der frühere `thema`-String-Vergleich — er bündelt die
    geteilten Fakten der Quellen, statt an einer einzelnen Überschrift zu hängen.
    """
    emb = baustein.get("centroid") or []
    bester, beste_sim = None, 0.0
    if emb:
        for s in store["stories"]:
            if s.get("status") == "archiviert" or not s.get("embedding"):
                continue
            sim = embeddings.cosine_similarity(emb, s["embedding"])
            if sim > beste_sim:
                bester, beste_sim = s, sim

    if bester is not None and beste_sim >= MATCH_THRESHOLD:
        # Laufende Story: Stimmen mergen, Wichtigkeit anheben (max), ggf. auffrischen
        bewegt = _merge_voices(bester, baustein["stimmen"])
        bester["wichtigkeit"] = max(bester["wichtigkeit"], baustein["wichtigkeit"])
        if bewegt:
            bester["zuletzt_bewegt"] = _now()
            # Bereits gesehene Story, die sich bewegt -> als Update wieder eligibel
            bester["status"] = "aktualisiert" if bester.get("gesehen_von_sasha") else "neu"
    else:
        # Neue Story
        store["stories"].append({
            "id":                f"s{store['naechste_id']:04d}",
            "thema":             baustein["thema"],
            "kategorie":         baustein["kategorie"],
            "wichtigkeit":       baustein["wichtigkeit"],
            "stimmen":           baustein["stimmen"],
            "embedding":         emb or [],
            "zuerst_gesehen":    _now(),
            "zuletzt_bewegt":    _now(),
            "gesehen_von_sasha": False,
            "gesehen_am":        None,
            "status":            "neu",
        })
        store["naechste_id"] += 1

def _decay_und_archiviere(store: dict):
    """Steine, deren aktuelle Wichtigkeit unter den Boden fällt, archivieren
    (fliegen aus dem aktiven Pool, bleiben aber als History im File)."""
    for s in store["stories"]:
        if s.get("status") == "archiviert":
            continue
        if _aktuelle_wichtigkeit(s) < ARCHIV_FLOOR:
            s["status"] = "archiviert"


# ════════════════════════════════════════════════════════════════════════
# 4) SENDUNG BAUEN  (Auswahl + Moderation)
# ════════════════════════════════════════════════════════════════════════
_NARRATION_PROMPT = (
    "Du bist die Moderatorin von Sashas persönlicher Tagesschau. Du bekommst "
    "ausgewählte Themen-Bausteine (schon nach Wichtigkeit sortiert, schwerstes "
    "zuerst), jeder mit den Stimmen verschiedener Quellen.\n\n"
    "OBERSTE REGEL — Treue zur Quelle: Du referierst NUR, was in den Stimmen "
    "wörtlich dasteht. Keine Zahl, kein Eigenname, kein Ereignis, das nicht in "
    "den gegebenen Texten steht — KEIN Weltwissen, KEINE Vermutung, KEINE "
    "Ausschmückung. Geben die Stimmen wenig her, sag wenig. Eine kurze belegte "
    "Zeile ist IMMER besser als ein voller erfundener Absatz. Im Zweifel weglassen. "
    "Erfundene Nachrichten sind das Schlimmste, was passieren kann — lieber dünn "
    "und wahr als reich und falsch.\n\n"
    "Bau daraus eine gesprochene Sendung:\n"
    "1. Kurze Hinführung ('Hier deine Weltlage, Sasha …'), dann die Blöcke in "
    "GEGEBENER Reihenfolge (Wichtigstes zuerst — Sashas Aufmerksamkeit soll vorne sitzen).\n"
    "2. Pro Block: was ist laut den Stimmen passiert, und wo erzählen die Quellen "
    "es UNTERSCHIEDLICH ('Tagesschau betont X, TASS stellt es als Y dar'). Quellen "
    "namentlich nennen. Dieser Kontrast ist der Sinn. Steht etwas nur bei EINER "
    "Quelle, sag genau das ('nur die BBC meldet …').\n"
    "3. Gesprochen, locker, flüssige Sätze (wird vorgelesen). Pro Block ein paar "
    "Sätze, nicht ausufern.\n"
    "Bei '[UPDATE]' am Block: kurz einordnen, dass es eine Fortsetzung ist."
)

_REVIEW_PROMPT = (
    "Du bist die Moderatorin von Sashas persönlicher Tagesschau. Sasha war eine "
    "Weile weg und will einen RÜCKBLICK: was in den letzten Tagen das Wichtigste "
    "war. Du bekommst die Themen-Bausteine (nach Wichtigkeit sortiert, schwerstes "
    "zuerst), jeder mit den Stimmen verschiedener Quellen.\n\n"
    "Bau einen gesprochenen Wochenrückblick:\n"
    "1. Kurze Begrüßung ('Willkommen zurück, Sasha — das war die Woche …'), dann "
    "die großen Themen in GEGEBENER Reihenfolge (Wichtigstes zuerst).\n"
    "2. Pro Block: was ist passiert, und wo erzählen die Quellen es UNTERSCHIEDLICH "
    "(Quellen namentlich nennen). Wenn aus den Daten erkennbar, ordne grob zeitlich "
    "ein (früher/später in der Woche).\n"
    "3. NICHTS erfinden — nur was in den Stimmen steht.\n"
    "4. Gesprochen, locker, flüssig (wird vorgelesen). Pro Block ein paar Sätze. "
    "Ein Rückblick darf etwas ausführlicher sein als die Tagessendung, aber kein Roman."
)

def _sendung_korpus(stories: list) -> str:
    """Ausgewählte Steine -> Textblock fürs Moderations-LLM.

    Der Moderator bekommt pro Stimme den VOLLEN gespeicherten Anrisstext
    (`DESC_CAP`=300), nicht nur die 160 Zeichen des Cluster-Schritts. Grund:
    bei zu dünnem Input fabuliert das 9B die Lücken (gemessen 2026-06-08 —
    erfand „Operation Epic Fury" etc.). Mehr echtes Material = weniger
    Erfindungs-Spielraum (Daten-Hebel statt Prompt-Knebel, feedback_data_vs_model).
    """
    bloecke = []
    for s in stories:
        marker = "[UPDATE] " if s.get("status") == "aktualisiert" else ""
        stimmen = "\n".join(
            f"  - [{v['quelle']} · {v['herkunft']}] {v['titel']}: {(v['text'] or '')[:DESC_CAP]}"
            for v in s["stimmen"]
        )
        bloecke.append(f"### {marker}{s['thema']} (Kategorie {s['kategorie']})\n{stimmen}")
    return "\n\n".join(bloecke)

def _waehle_sendung(store: dict) -> list:
    """
    Steine für die nächste Sendung wählen: ungesehene + seit-Sicht-bewegte
    ('aktualisiert'), nach aktueller (decay-bereinigter) Wichtigkeit sortiert,
    über der Schwelle, auf SENDUNG_MAX gedeckelt.
    """
    aktiv = [s for s in store["stories"] if s.get("status") != "archiviert"]
    # Bevorzugt: FRISCHE Themen (ungesehen oder seit-Sicht bewegt) - das ist
    # die "was ist neu"-Sendung.
    frisch = [s for s in aktiv
              if (not s.get("gesehen_von_sasha")) or s.get("status") == "aktualisiert"]
    # FALLBACK (alles schon gesehen): die wichtigsten AKTIVEN Themen als Recap.
    # Eine ausdrückliche Sendung darf nie leer sein - "nochmal die Lage" statt
    # "nichts Neues". Damit kann Sasha eine Sendung auch erneut/wiederholt sehen.
    pool = frisch if frisch else aktiv
    kandidaten = [(_aktuelle_wichtigkeit(s), s) for s in pool
                  if _aktuelle_wichtigkeit(s) >= SENDUNG_MIN_WICHTIGKEIT]
    kandidaten.sort(key=lambda t: t[0], reverse=True)
    return [s for _, s in kandidaten[:SENDUNG_MAX]]

def _llm_text(system_prompt: str, user_content: str) -> str:
    """Generischer nicht-streamender Ollama-Call (System + User -> Text).
    Geteilt von Tagessendung, Wochenrückblick und Aufholmodus. Fehler -> String."""
    try:
        resp = net.post(
            f"{OLLAMA_URL}/api/chat",
            {
                "model": OLLAMA_MODEL,
                **({"think": False} if SUPPORTS_THINK else {}),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_content},
                ],
                "stream": False,
                "keep_alive": OLLAMA_KEEP_ALIVE,
                "options": {"num_ctx": OLLAMA_NUM_CTX, "temperature": NEWS_TEMPERATURE},
            },
            timeout=180,
        )
        return resp.get("message", {}).get("content", "").strip() or "[leer]"
    except Exception as e:
        return f"[LLM-Call fehlgeschlagen: {e}]"

def _narriere(stories: list, system_prompt: str = _NARRATION_PROMPT) -> str:
    """Ausgewählte Steine -> gesprochene Sendung (LLM)."""
    return _llm_text(
        system_prompt,
        "Bausteine (Wichtigstes zuerst):\n\n" + _sendung_korpus(stories) +
        "\n\nBau daraus meine Sendung.")

def baue_sendung(store: dict) -> dict:
    """
    Wählt Steine + lässt die KI moderieren. Markiert die Steine NICHT als
    gesehen (das passiert erst bei AUSLIEFERUNG via lies()). Gibt
    {erstellt, text, story_ids} zurück und schreibt es als data/news_digest.json.
    """
    stories = _waehle_sendung(store)
    if not stories:
        digest = {"erstellt": _now(), "text":
                  "Seit deiner letzten Sendung ist nichts Wichtiges Neues dazugekommen.",
                  "story_ids": []}
    else:
        digest = {"erstellt": _now(), "text": _narriere(stories),
                  "story_ids": [s["id"] for s in stories]}
    os.makedirs(_DATA, exist_ok=True)
    with open(_DIGEST_PATH, "w", encoding="utf-8") as f:
        _json.dump(digest, f, ensure_ascii=False, indent=2)
    return digest


def _innerhalb(iso: str, tage: int) -> bool:
    """True wenn der iso-Zeitstempel innerhalb der letzten `tage` Tage liegt."""
    try:
        return (datetime.now() - datetime.fromisoformat(iso)).total_seconds() <= tage * 86400
    except Exception:
        return False

def _waehle_rueckblick(store: dict, tage: int) -> list:
    """
    Steine für den Wochenrückblick: alle (auch gesehene, auch archivierte) deren
    Story ins Zeitfenster fällt, gerankt nach BASIS-Wichtigkeit (KEIN Decay — bei
    einem Rückblick soll Alter innerhalb des Fensters nicht bestrafen). Trivia
    (Basis < RUECKBLICK_MIN_WICHTIGKEIT) fliegt raus.
    """
    kand = []
    for s in store["stories"]:
        im_fenster = _innerhalb(s.get("zuletzt_bewegt", ""), tage) or _innerhalb(s.get("zuerst_gesehen", ""), tage)
        if not im_fenster:
            continue
        if s.get("wichtigkeit", 0.0) < RUECKBLICK_MIN_WICHTIGKEIT:
            continue
        kand.append((s["wichtigkeit"], s))
    kand.sort(key=lambda t: t[0], reverse=True)
    return [s for _, s in kand[:RUECKBLICK_MAX]]

def _groesste_pollluecke_tage(store: dict, tage: int) -> float:
    """
    Größte Lücke (in Tagen) zwischen aufeinanderfolgenden erfolgreichen Polls
    INNERHALB des Fensters [jetzt - tage, jetzt]. Fenstergrenzen zählen mit.
    Eine große Lücke = die ZENTRALE war in der Zeit offline (kein Netz, z.B.
    Hotspot mit Sasha weg) -> der Store kann das Fenster nicht abdecken.
    """
    jetzt   = datetime.now()
    grenze  = jetzt - timedelta(days=tage)
    zeiten  = [grenze]
    for iso in store.get("poll_historie", []):
        try:
            t = datetime.fromisoformat(iso)
        except Exception:
            continue
        if t >= grenze:
            zeiten.append(t)
    zeiten.append(jetzt)
    zeiten.sort()
    return max((b - a).total_seconds() / 86400.0 for a, b in zip(zeiten, zeiten[1:]))


_AUFHOL_PROMPT = (
    "Du bist die Moderatorin von Sashas persönlicher Tagesschau. Sasha war einige "
    "Tage WEG und die ZENTRALE war in der Zeit OFFLINE — die normalen Quellen "
    "fehlen also. Stattdessen bekommst du WEB-SUCHTREFFER (Titel + kurze Snippets) "
    "zu den wichtigsten Ereignissen der letzten Tage.\n\n"
    "Bau einen ehrlichen Aufhol-Rückblick:\n"
    "1. Begrüßung ('Willkommen zurück, Sasha — du warst weg, hier das Wichtigste aus der Zeit …').\n"
    "2. Die größten Themen zuerst, je ein paar Sätze.\n"
    "3. NUR was in den Treffern steht — nichts erfinden. Die Snippets sind knapp; "
    "bei Zahlen/Details vorsichtig bleiben, und wenn die Quellenlage dünn ist, sag das offen.\n"
    "4. Diese Treffer sind NICHT nach Outlet/Perspektive getaggt wie sonst — also "
    "KEINE erfundenen 'Tagesschau sagt X, TASS sagt Y'-Gegenüberstellungen. Bleib bei dem, was dasteht.\n"
    "5. Gesprochen, locker, flüssig (wird vorgelesen)."
)

def _aufhol_queries(store: dict, max_themen: int = 4) -> list:
    """
    Suchanfragen für den Aufholmodus: ein paar generische PLUS Themen-Seeds aus
    den wichtigsten bekannten Steinen (die vor der Lücke aufliefen). Konkrete
    Themen ('Konflikt Israel-Lebanon aktuelle Entwicklung') liefern bei DuckDuckGo
    echte Artikel-Snippets, während generische Anfragen nur Homepages bringen.
    """
    queries = list(AUFHOL_QUERIES)
    themen = sorted(store.get("stories", []),
                    key=lambda s: s.get("wichtigkeit", 0.0), reverse=True)
    for s in themen[:max_themen]:
        queries.append(f"{s['thema']} aktuelle Entwicklung Nachrichten")
    return queries

def aufholmodus(tage: int = 7) -> str:
    """
    Offline-Aufholmodus: RSS hat keine Historie (rollendes Fenster), also
    rekonstruieren wir die verpasste Zeit über rückblickende WEB-SUCHE
    (web.suche, dieselbe Pipe wie web_suche — läuft durch net.py, leuchtet im
    Internet-Panel). Snippets -> LLM -> Aufhol-Rückblick. Markiert nichts als gesehen.
    """
    state.push_log(f"NEWS  ⟳ Aufholmodus: rückblickende Web-Suche ({tage}-Tage-Lücke) …")
    state.push_internet_log(f"NEWS  ⟳ Aufhol-Rückblick (Web, {tage} Tage)")
    treffer = []
    for q in _aufhol_queries(_load_store()):
        try:
            treffer.append(f"### Suche: {q}\n{web.suche(q)}")
        except Exception as e:
            state.push_log(f"NEWS  ✗ Aufhol-Suche '{q}' fehlgeschlagen: {e}")
    if not treffer:
        return ("Ich konnte den Rückblick nicht holen - die Web-Suche kam nicht "
                "durch (kein Internet?). Sobald du wieder online bist, frag nochmal.")
    return _llm_text(
        _AUFHOL_PROMPT,
        "Web-Suchtreffer:\n\n" + "\n\n".join(treffer) +
        f"\n\nBau daraus meinen Aufhol-Rückblick über die letzten {tage} Tage.")

def wochenrueckblick(tage: int = 7) -> str:
    """
    'Was war die letzten `tage` Tage'. Schaltet automatisch zwischen zwei Quellen:

    - **Store** (du warst zuhause, lückenlos gepollt): die schwersten Steine der
      letzten N Tage aus dem eigenen Speicher.
    - **Aufholmodus/Web** (es gibt eine Poll-Lücke im Fenster -> ZENTRALE war
      offline): rückblickende Web-Suche, weil RSS die Lücke nicht hergibt.

    Markiert NICHTS als gesehen (Rückblick ist orthogonal zur Tagessendung).
    """
    store = _load_store()
    luecke = _groesste_pollluecke_tage(store, tage)
    if luecke >= GAP_SCHWELLE_TAGE:
        state.push_log(f"NEWS  Poll-Lücke {luecke:.1f} Tage im {tage}-Tage-Fenster → Aufholmodus (Web)")
        return aufholmodus(tage)
    stories = _waehle_rueckblick(store, tage)
    if not stories:
        return aufholmodus(tage)          # Store deckt's nicht ab -> auch Web
    return _narriere(stories, _REVIEW_PROMPT)


# ════════════════════════════════════════════════════════════════════════
# 5) ORCHESTRIERUNG
# ════════════════════════════════════════════════════════════════════════
def aktualisiere() -> dict:
    """
    Ein kompletter Poll-Lauf: ankündigen -> sammeln -> clustern -> in den
    Store integrieren (merge/neu) -> decay/archivieren -> die aktuelle Sendung
    vorbauen (cachen, noch NICHT als gesehen markieren). Gibt das Digest zurück.
    """
    state.push_log(f"NEWS  ⟳ Hole Weltlage aus {len(FEEDS)} Quellen …")
    state.push_internet_log(f"NEWS  ⟳ Fetch ({len(FEEDS)} Quellen)")

    store = _load_store()
    items = collect()
    if items:                              # nur ein ERFOLGREICHER (online) Poll zählt
        hist = store.setdefault("poll_historie", [])
        hist.append(_now())
        del hist[:-80]                     # nur die letzten 80 Polls behalten
    for baustein in _cluster_poll(items):
        _integriere(store, baustein)
    _decay_und_archiviere(store)
    _save_store(store)

    aktiv = sum(1 for s in store["stories"] if s.get("status") != "archiviert")
    state.push_log(f"NEWS  ✓ Store: {aktiv} aktive Themen, {len(store['stories'])} gesamt")

    return baue_sendung(store)


# ── KI-Tool: lies_news ─────────────────────────────────────────────────
def lies(tage: int = 0) -> str:
    """
    KI-Tool 'lies_news'. Zwei Modi:

    - tage <= 0 (Default): die aktuelle TAGESSENDUNG. Markiert die enthaltenen
      Steine als gesehen (Auslieferung = gesehen) → fallen beim nächsten Poll
      raus, außer sie bewegen sich. Nicht-blockierend: noch keine Sendung gebaut
      → Hintergrund-Lauf + sofortige Antwort.
    - tage > 0: ein WOCHENRÜCKBLICK über die letzten `tage` Tage aus dem Store
      ('was war diese Woche'). Markiert nichts als gesehen.
    """
    try:
        tage = int(tage or 0)
    except (TypeError, ValueError):
        tage = 0
    if tage > 0:
        return wochenrueckblick(tage)

    if not os.path.exists(_DIGEST_PATH):
        threading.Thread(target=aktualisiere, daemon=True).start()
        return ("Die Nachrichten werden gerade zum ersten Mal zusammengestellt - "
                "frag in ein, zwei Minuten nochmal.")
    try:
        with open(_DIGEST_PATH, encoding="utf-8") as f:
            digest = _json.load(f)
    except Exception as e:
        return f"[Konnte die Sendung nicht lesen: {e}]"

    text = (digest.get("text") or "").strip()
    ids = digest.get("story_ids", [])
    # Leere/alte Sendung (nichts war "frisch" als sie gebaut wurde) -> JETZT
    # frisch bauen. baue_sendung fällt auf einen Recap der wichtigsten Themen
    # zurück, liefert also auch dann eine echte Sendung, wenn schon alles
    # gesehen ist. So gibt's nie ein "nichts Neues"-Loch.
    if not ids or not text:
        digest = baue_sendung(_load_store())
        text = (digest.get("text") or "").strip()
        ids = digest.get("story_ids", [])

    # Steine als gesehen markieren - das steuert NUR die proaktive Frische-Logik
    # (was als "neu" gilt), NICHT was wir hier liefern. Eine ausdrückliche Frage
    # ("hast du News?") liefert IMMER die volle Sendung, auch beim Wiederholen.
    if ids:
        store = _load_store()
        id_set = set(ids)
        now = _now()
        for s in store["stories"]:
            if s["id"] in id_set:
                s["gesehen_von_sasha"] = True
                s["gesehen_am"] = now
                if s.get("status") != "archiviert":
                    s["status"] = "ruht"
        _save_store(store)

    if not text:
        return "Konnte gerade keine Sendung bauen - frag in einem Moment nochmal."
    return f"Sendung (Stand {digest.get('erstellt', '?')}):\n\n{text}"


# ── Periodischer Hintergrund-Fetcher ───────────────────────────────────
def start_fetcher():
    """Daemon-Thread: pollt periodisch + akkumuliert in den Store. Jeder Lauf
    kündigt sich laut an ('periodisch, aber sichtbar'). Aus main.py gerufen."""
    def loop():
        time.sleep(START_DELAY_S)
        while True:
            try:
                aktualisiere()
            except Exception as e:
                state.push_log(f"NEWS  ✗ Fetch-Lauf fehlgeschlagen: {e}")
            time.sleep(INTERVAL_S)
    threading.Thread(target=loop, daemon=True).start()
    state.push_log(f"NEWS  Fetcher gestartet (alle {INTERVAL_S // 60} min)")


# ── Direktaufruf zum Testen: python3 news.py ───────────────────────────
if __name__ == "__main__":
    digest = aktualisiere()
    print(f"\n=== Sendung ({len(digest['story_ids'])} Themen) ===\n")
    print(digest["text"])
