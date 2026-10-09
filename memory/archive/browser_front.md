# Browser-Front (Monolith) — archiviert am 2026-10-06

**Was sie war:** das Web-Dashboard von ZENTRALE. Ein einziges großes HTML
(`monolith.html`, ~220 KB mit mehreren Script-Blöcken) plus Helfer
(`engine.js` = Daten-Adapter mit Polling, `viz.js` = Sparklines/Plots,
`ascii.js` = ASCII-Bibliothek und Bild→ASCII-Filter, `fonts/`). Ausgeliefert
von Flask unter `/` (Alias `/monolith`), Assets unter `/static/`. Dazu die
Design-Entwürfe aus `zentrale-new-design/dashboards/` (Bernstein, Kern, Orakel,
Monolith-Varianten).

**Warum archiviert:** Seit 2026-08-15 wird nur noch an der TUI gearbeitet,
seit 2026-10-04 war der Browser offiziell geparkt. Sasha, 2026-10-06: *„die
browserfront ist so geparkt die gehört mittlerweile eigentlich einfach ins
archiv in der memory."* Geparkter Code im Live-Baum kostet trotzdem: jede
Suche findet ihn, Doku muss ihn erwähnen, Tests müssen ihn tragen.

**Wann wieder nützlich:** wenn ZENTRALE wieder eine Browser-Ansicht bekommen
soll (z. B. ein Wand-Display ohne Terminal). Die Gestaltung (Bernstein,
Klavier-Panel, ASCII-Exhibit) und `ascii.js` (Bild→ASCII im Canvas) sind die
wertvollsten Stücke.

**Lebt weiter (2026-10-10):** der Bild→ASCII-Filter (`canvasToAscii` aus
`ascii.js` und der Foto-Filter aus `monolith.html`: Auto-Levels 1 %/99 %,
Rampe ` .,:;-~=+ox*#%8B@`, mono/farbe) ist nach Python übertragen in
`core/bild_vorschau.py` — die Vorschau der Bilder auf dem Desk
([desk_view.md](../system/desk_view.md) „Bilder").

**Woran sie hing:**
- Flask-Routen `/`, `/monolith` (`render_template`, `ki_aus`-Flag aus
  `ai_backends.lokale_ki_aus()`), `/api/photos`, `/api/photos/<name>` (Ordner
  `data/photos/`, Env `ZENTRALE_PHOTO_DIR`) — alle unten wörtlich.
- Polling von `/api/state` jede Sekunde, `/api/chat` (SSE), `/api/chat/clear`,
  `/api/categories`, `/api/mail`, `/api/lists`, `/api/melodies` u. a. — diese
  Routen bleiben, die TUI oder der Kern nutzen sie.
- Die Fotos selbst liegen seit 2026-10-06 in `data/_beiseite/photos/`.

**Wo jetzt:**
- `browser_front/monolith.html` (war `ui/templates/monolith.html`)
- `browser_front/static/` (war `ui/static/`)
- `browser_front/entwuerfe/` (war `zentrale-new-design/dashboards/`)
- die alte Hook-Doku dazu: [ui_hooks.md](ui_hooks.md) (lag früher im Bereich `system/`, war dort schon als veraltet markiert)

Herkunft: alles aus Commit `29d95b6`.

## Die entfernten Routen (ui/app.py)

```python
# ── Dashboard ─────────────────────────────────────────────────────────

@app.route('/')
@app.route('/monolith')   # Alias: alte Kiosk-/Bookmark-/Deeplink-URL bleibt gueltig
def index():
    """
    Liefert das Browser-Dashboard (monolith.html). GEPARKT seit 2026-10-04:
    die TUI ist die einzige Front, der Browser bleibt nur im Code, falls man
    ihn wieder einbinden will. ki_aus blendet die KI-Blöcke aus, wenn dieser
    Knoten keine lokale KI hat. /monolith bleibt als Alias für alte Bookmarks.

    Statische Assets (engine.js = Daten-Adapter, viz.js, ascii.js, fonts/) liegen
    in ui/static/ und werden von Flask automatisch unter /static/<file> bedient.
    """
    resp = render_template('monolith.html',
                           ki_aus=ai_backends.lokale_ki_aus())
    from flask import make_response
    r = make_response(resp)
    # Cache deaktivieren: der Browser soll immer die aktuelle Version laden,
    # nicht eine gecachte – wichtig bei Entwicklung und Pi-Restart.
    r.headers['Cache-Control'] = 'no-store'
    return r


# ── Fotos (Quelle für den ASCII-Bild-Filter) ──────────────────────────
#
# Bilder werden LOKAL vom Backend serviert (gleicher Origin wie das
# Dashboard), nicht direkt vom Netz geladen. Grund: nur same-origin-Bilder
# darf der Browser-Canvas per getImageData() auslesen - sonst ist der
# Canvas "tainted" und der ASCII-Filter (canvasToAscii) bekommt keine
# Pixel. Ordner per Env überschreibbar; Default data/photos/.
# (Das ist zugleich der erste echte Baustein von "Fotos zeigen".)

_PHOTO_DIR = os.environ.get(
    "ZENTRALE_PHOTO_DIR",
    os.path.join(_DATA_DIR, "photos"),
)
_PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")


@app.route('/api/photos')
def api_photos():
    """Liste der verfügbaren Bild-Dateinamen (sortiert). Leere Liste wenn kein Ordner."""
    if not os.path.isdir(_PHOTO_DIR):
        return jsonify([])
    names = [f for f in sorted(os.listdir(_PHOTO_DIR))
             if f.lower().endswith(_PHOTO_EXTS)]
    return jsonify(names)


@app.route('/api/photos/<path:name>')
def api_photo_file(name):
    """
    Liefert eine einzelne Bild-Datei aus _PHOTO_DIR aus.
    send_from_directory schützt gegen Path-Traversal (../) - der Name darf
    den Ordner nicht verlassen.
    """
    return send_from_directory(_PHOTO_DIR, name)
```

## Die entfernten Tests (tests/test_backend_api.py)

```python
# ── Eine Front, KI per Flag ─────────────────────────────────────────────────
# Es gibt nur EIN Browser-Template (monolith.html, geparkt); ohne lokale KI
# rendert es mit ki_aus=True (KI-Blöcke weg). Die folgenden Tests
# sichern genau diese Gate-Grenze ab — sie war vorher gar nicht getestet
# (die Route '/' lief in keinem Test).

def test_index_ki_frei_ohne_lokale_ki(client):
    # conftest fährt ZENTRALE_LOKALE_KI=aus → ki_aus=True.
    r = client.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "window.KI_AUS = true" in html        # Flag korrekt durchgereicht
    assert 'id="chat-input"' not in html          # Chat-Konsole gegated
    assert 'id="ai-state"' not in html            # AI-State gegated
    assert "OLLAMA" not in html                   # KI-Header-Status gegated
    # Visualizer + Werkzeuge bleiben für ALLE Fronten:
    assert 'id="core"' in html                    # ASCII-Exhibit
    assert 'id="ai-meta"' in html                 # Direktor-Meta (kein KI)
    assert 'class="box shortcuts"' in html        # Shortcut-Footer statt Chat
    for tab in ('data-ex="listen"', 'data-ex="mail"', 'data-ex="klavier"',
                'id="lists-panel"', 'id="mail-panel"', 'id="piano-panel"'):
        assert tab in html, f"Werkzeug fehlt in der KI-freien Front: {tab}"


def test_index_ki_front_mit_lokaler_ki(client, monkeypatch):
    # Lokale KI an → ki_aus=False; lokale_ki_aus() liest die Env zur
    # Laufzeit (kein Cache), also reicht setenv vor dem Request.
    monkeypatch.setenv("ZENTRALE_LOKALE_KI", "an")
    r = client.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "window.KI_AUS = false" in html
    assert 'id="chat-input"' in html              # Chat-Konsole da
    assert 'id="ai-state"' in html
    assert "OLLAMA" in html
    assert 'class="box shortcuts"' not in html    # kein Shortcut-Footer
    # Werkzeug-Tabs sind frontübergreifend auch hier vorhanden
    assert 'data-ex="listen"' in html and 'data-ex="mail"' in html
```
