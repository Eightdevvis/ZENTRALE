# Archiv — Index

Code, der aus dem Live-System entfernt wurde, aber wiederverwendbar sein
könnte. Jede Datei: was er tat, warum er raus ist, wann er wieder nützlich
wäre, woran er hing — und der Code wörtlich (Pfad, Zeilen, Commit).
Was hier steht, läuft NICHT. Reiner Müll kommt nicht hierher, der ist gelöscht.

| Datei | Was | Warum archiviert |
|---|---|---|
| [ki_chat_nicht_streaming.md](ki_chat_nicht_streaming.md) | `ai.chat()` — blockierender Ollama-Chat ohne Stream | kein Aufrufer mehr, alles läuft über `chat_stream` |
| [tui_ki_ring.md](tui_ki_ring.md) | TUI-Ring (`ring_punkte`/`ring_zeilen`) + Lage-Poll-Thread | seit dem Rad (02.10.2026) nicht mehr gezeichnet, Poll lief ins Leere |
| [tui_zeit_plot.md](tui_zeit_plot.md) | `draw_time_plot` — 24h-Gitter für einen time/period-Graphen | nirgends aufgerufen, `draw_overlay` zeichnet die Graphen |
