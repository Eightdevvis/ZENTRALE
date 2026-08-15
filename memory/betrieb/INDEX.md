# Betrieb — Index

Wie ZENTRALE installiert, gestartet, ausgerollt und abgesichert wird. Alles
hier ist „Maschine", nicht „Feature".

| Was du wissen willst | Datei |
|---|---|
| **Einstieg.** Setup & Installation: venv, Modelle, Abhängigkeiten | [setup.md](setup.md) |
| Starten: welche Prozesse, welche Env-Vars, welche Reihenfolge | [starten.md](starten.md) |
| Deployment auf den Pi: rsync, systemd, Kiosk | [deployment.md](deployment.md) |
| Hardware: Pi, Mikro, PIR, GPIO | [hardware.md](hardware.md) |
| Pi-Bildschirm bleibt schwarz — Debug-Fährte | [display_debug.md](display_debug.md) |
| Remote-LUKS-Unlock via Dropbear im Initramfs | [auto_unlock.md](auto_unlock.md) |
| Browser: Theme-Kopplung, Terminal-Browsing, Tor-Einordnung | [browser.md](browser.md) |

## Sicherheit

| Was du wissen willst | Datei |
|---|---|
| Bedrohungsmodell, LUKS, Evil-Maid, was verschlüsselt ist | [sicherheit.md](sicherheit.md) |
| Welche Dateien die KI lesen darf (Whitelist) und was nie in git gehört | [datei_zugriffe.md](datei_zugriffe.md) |

**Zwei Dinge, die hart tabu bleiben:** `push --force` / History umschreiben,
und Secrets committen. `data/*.json`, Keys und Passphrasen bleiben gitignored.
Der Push selbst ist harmlos — gefährlich ist nur, WAS im Commit steckt.

**Neu seit 2026-08:** ZENTRALE ist nicht mehr zwangsläufig offline. Der
Cloud-Kern ist ein Opt-in, das die Offline-Eigenschaft für den Chat bewusst
bricht — was dann rausgeht (auch Tool-Ergebnisse, nicht nur die Frage), steht
in [sicherheit.md](sicherheit.md) und [../ki/ki_system.md](../ki/ki_system.md).
