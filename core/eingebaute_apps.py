# core/eingebaute_apps.py
#
# Die eingebauten Apps (memory/hub/cloud_app.md, „Übergang"): solange
# Listen, Kalender, Gedächtnis … im Kern stecken, melden sie sich hier beim
# Hub an — mit Name, Titel und `[daten]` wie ein echtes app.toml. Zieht eine
# App aus (wie Tutor, Karte), kommt ihr `[daten]` aus ihrem eigenen Manifest;
# hier fällt dann nur ihre Zeile weg.
#
# Die Muster stehen im Namensraum der Positivliste (core/abgleich_auswahl.py,
# relativ zum ZENTRALE-Ordner). Jedes Muster dort gehört zu GENAU einer App —
# tests/test_abgleich_apps.py wird rot, wenn ein neues keine hat.
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md): nur Daten, keine Imports.

# name → {titel, daten: {muster, abgleichen}}. Titel wie im app.toml (deutsch);
# Namen für Menschen im Befehl `zentrale` stehen in zentrale_cli/texte.py.
EINGEBAUT = {
    "fokus": {"titel": "Listen",
              "daten": {"muster": ["data/lists.json", "data/features.json"], "abgleichen": True}},
    "notizen": {"titel": "Notizen",
                "daten": {"muster": ["data/notes.json"], "abgleichen": True}},
    "kalender": {"titel": "Kalender",
                 # Seit 2026-10-24 auch die Termine (data/kalender/**) — aber nur,
                 # wenn adapter.kalender_ueber_cloud() (abgleich_apps schneidet
                 # sie sonst heraus): Quelle der Kalender-App zencloud
                 # (core/kalender_einstellung.py), ohne Einstellung der alte Weg
                 # mit Google-Anschluss und EINER Brücke.
                 "daten": {"muster": ["data/kalender_neben.json", "data/calendar_colours.json",
                                      "data/kalender/**"],
                           "abgleichen": True}},
    "graph": {"titel": "Graphen",
              "daten": {"muster": ["data/graphs.json", "data/g_*.json", "data/sleep_quality.json"],
                        "abgleichen": True}},
    "assistent": {"titel": "Assistent",
                  "daten": {"muster": ["data/gedaechtnis/**", "data/gespraeche/**",
                                       "data/ai_transcripts/*.jsonl", "data/rueckmeldungen/*.jsonl",
                                       "data/mobil/kontext.json", "data/ai_usage.json"],
                            "abgleichen": True}},
    "ablage": {"titel": "Ablage",
               "daten": {"muster": ["data/ablage/**"], "abgleichen": True}},
    "desk": {"titel": "Desk",
             "daten": {"muster": ["data/desk/**"], "abgleichen": True}},
    "werkstatt": {"titel": "Werkstatt",
                  "daten": {"muster": ["data/apps/**", "data/shop/**"], "abgleichen": True}},
    "mail": {"titel": "Mail",
             "daten": {"muster": ["data/mail_rules.json"], "abgleichen": True}},
    "klavier": {"titel": "Klavier",
                "daten": {"muster": ["data/melodies.json"], "abgleichen": True}},
    # Der Adapter (core/adapter.py, memory/hub/adapter.md): die eine Tür zu
    # fremden Diensten. Immer installiert, immer abgeglichen („pflicht": wird
    # nie gefragt und nie abgewählt) — sonst hätte ein neues Gerät weder KI
    # noch Kalender. Die Zugangsdaten gleichen nur angemeldet ab (abgleich_apps).
    "adapter": {"titel": "Adapter", "pflicht": True,
                "daten": {"muster": ["data/adapter/anschluesse/*.json", "data/adapter/bruecke/**",
                                     "data/adapter/geheim.enc"],
                          "abgleichen": True}},
    # The cloud folder (core/cloud_folder.py, memory/hub/cloud_folder.md,
    # 2026-10-29): ~/Zentrale/Cloud, anything dropped there syncs. Its own app
    # next to the service `cloud` below, which has no data of its own.
    "cloud_folder": {"titel": "Cloud",
                     "daten": {"muster": ["data/cloud/**"], "abgleichen": True}},
    # Die Cloud selbst (Konto, Abgleich, Geräte, Nutzungs-Wächter): ein Dienst
    # ohne eigene Daten. Ob sie an ist, sagt abgleich.cloud_an().
    "cloud": {"titel": "Cloud", "dienst": True},
}

# Ersatz für eine ausgezogene App, deren app.toml noch kein `[daten]` hat.
# Gilt nur, bis ihr Manifest es selbst sagt (dann gewinnt das Manifest) —
# und auch, wenn die App auf diesem Gerät gar nicht installiert ist: ihre
# Lernstände liegen noch am alten Ort ZENTRALE/tutor/data (hub_bauplan.md,
# Schritt 1 „Noch nicht"). Offen: language-tutor/app.toml bekommt `[daten]`.
ERSATZ = {
    "tutor": {"titel": "Sprach-Tutor",
              "daten": {"muster": ["tutor/data/tutor_config.json", "tutor/data/aktiver_stand",
                                   "tutor/data/staende/**", "tutor/data/es/**"],
                        "abgleichen": True}},
}

# ── Ports (building kit step 9, memory/hub/port_types.md) ───────────────
#
# What each built-in app needs and offers, in the manifest's English keys
# `needs` / `offers` (contracts/ports/1/ports.schema.json, $defs/manifestPorts).
# An app whose data may sync has the socket `data` that takes a `sync` wire
# (0..1: off = stays on this device); the adapter must sync (`pflicht`), so
# its socket takes exactly one. tests/test_port_types.py checks every entry
# against the schema and that each app with `daten` has the socket.
_DATA_SYNC = {"id": "data", "type": "sync", "range": "^1", "occurrences": [0, 1]}

PORTS = {
    "fokus": {"needs": [_DATA_SYNC]},
    "notizen": {"needs": [_DATA_SYNC]},
    "kalender": {"needs": [_DATA_SYNC]},
    "graph": {"needs": [_DATA_SYNC]},
    "assistent": {"needs": [_DATA_SYNC,
                            # optional until the plug dialog (step 11) wires it
                            {"id": "model", "type": "model", "range": "^1", "occurrences": [0, 1]}]},
    "ablage": {"needs": [_DATA_SYNC], "offers": [{"id": "files", "type": "files"}]},
    "desk": {"needs": [_DATA_SYNC]},
    "werkstatt": {"needs": [_DATA_SYNC]},
    "mail": {"needs": [_DATA_SYNC]},
    "klavier": {"needs": [_DATA_SYNC]},
    "adapter": {"needs": [dict(_DATA_SYNC, occurrences=[1, 1])],
                "offers": [{"id": "model", "type": "model"},
                           {"id": "google", "type": "calendar-source"}]},
    "cloud_folder": {"needs": [_DATA_SYNC], "offers": [{"id": "files", "type": "files"}]},
    "cloud": {"offers": [{"id": "sync", "type": "sync"},
                         {"id": "calendar", "type": "calendar-source"}]},
    "tutor": {"needs": [_DATA_SYNC]},
}

# One calendar instance (core/kalender_einstellung.py) is its own piece: it
# takes exactly one `calendar-source` wire (google / zencloud / local).
INSTANCE_PORTS = {"kalender": {"needs": [{"id": "source", "type": "calendar-source", "range": "^1"}]}}

# What every node offers by itself (its platform): the local calendar
# source. Hardware ports come from the node description (core/knoten.py).
NODE_PORTS = {"offers": [{"id": "calendar-local", "type": "calendar-source"}]}
