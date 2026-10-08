# scripts/pruefstand_teile/ — die Teile des Prüfstands (scripts/pruefstand.py).
#
# Wozu, wie Fälle aussehen, was ein Durchgang kostet: memory/ki/pruefstand.md.
# Die Fälle selbst liegen in tests/pruefstand/faelle/ (YAML, für Sasha lesbar).
#
#   faelle      Fälle laden und prüfen; Entwurf aus einem echten Gespräch
#   uhr         die Uhr auf den Zeitpunkt des Falls stellen
#   umgebung    Wegwerf-Daten, Schlüssel, Netz-Attrappe, Antworten auf Fragen
#   lauf        einen Fall über den echten Weg fahren (POST /api/chat)
#   endzustand  stimmt der Kalender danach?
#   metriken    Werkzeug-Aufrufe, Fehler, Lösch+Neu, Rückfragen
#   richter     Belegpflicht: jede Behauptung gegen die Werkzeug-Ergebnisse
#   bericht     Markdown + JSON, Transkripte, Vergleich zweier Stände
