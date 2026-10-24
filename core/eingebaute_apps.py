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
                 # wenn der Adapter einen Kalender-Anschluss hat (abgleich_apps
                 # schneidet sie sonst heraus): dann fährt EIN Gerät die Brücke
                 # zu Google, alle anderen bekommen sie aus der Cloud.
                 "daten": {"muster": ["data/kalender_neben.json", "data/kalender/**"],
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
