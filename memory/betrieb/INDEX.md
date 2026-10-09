# Betrieb — Index

Wie ZENTRALE installiert, gestartet, ausgerollt und abgesichert wird. Alles
hier ist „Maschine", nicht „Feature".

| Was du wissen willst | Datei |
|---|---|
| **Einstieg.** Setup & Installation: venv, Modelle, Abhängigkeiten | [setup.md](setup.md) |
| Starten: welche Prozesse, welche Env-Vars, welche Reihenfolge | [starten.md](starten.md) |
| **Wachplan:** PC = Gehirn; feste Schlafenszeiten, Pi aus → PC schläft, Wecken per Router/VPN, Hochfahren vor dem Heimkommen; Schlüssel später | [wachplan.md](wachplan.md) |
| **Systemeinheit:** Autostart als Dienst, Cmd+z-Scratchpad, Desktop-Meldungen | [systemeinheit.md](systemeinheit.md) |
| Deployment auf den Pi: rsync, systemd, Kiosk | [deployment.md](deployment.md) |
| Hardware: Pi, Mikro, PIR, GPIO | [hardware.md](hardware.md) |
| Pi-Bildschirm bleibt schwarz — Debug-Fährte | [display_debug.md](display_debug.md) |
| Remote-LUKS-Unlock via Dropbear im Initramfs | [auto_unlock.md](auto_unlock.md) |
| Browser: Theme-Kopplung, Terminal-Browsing, Tor-Einordnung | [browser.md](browser.md) |
| **Browser der KI** einrichten: Paket + Chromium nachladen, Pi, Fallen | [ki_browser.md](ki_browser.md) |

## Sicherheit

| Was du wissen willst | Datei |
|---|---|
| Bedrohungsmodell, LUKS, Evil-Maid, was verschlüsselt ist | [sicherheit.md](sicherheit.md) |
| **Zugang zum Backend:** von anderen Geräten nur mit Schlüssel; Stellungen aus/melden/an, Schlüssel anlegen, auf Pi und Handy bringen, Browser-Link | [zugang.md](zugang.md) |
| Welche Dateien die KI lesen darf (Whitelist) und was nie in git gehört | [datei_zugriffe.md](datei_zugriffe.md) |
| **Abgleich über die Mitte:** Rechner gleichen verschlüsselt über eine Mitte ab statt direkt; Zusammenführen pro Eintrag, Grabsteine, Schlüssel in KeePass, Umstellung vom rsync-Weg | [abgleich.md](abgleich.md) |
| **Datensicherung** ins private Daten-Repo: Positivliste, Schlüssel-Scanner, ein Branch pro Rechner, täglicher Timer (wird vom Abgleich abgelöst) | [datensicherung.md](datensicherung.md) |

**Zwei Dinge, die hart tabu bleiben:** `push --force` / History umschreiben,
und Secrets committen. `data/*.json`, Keys und Passphrasen bleiben gitignored.
Der Push selbst ist harmlos — gefährlich ist nur, WAS im Commit steckt.

**Neu seit 2026-08:** ZENTRALE ist nicht mehr zwangsläufig offline. Der
Cloud-Kern ist ein Opt-in, das die Offline-Eigenschaft für den Chat bewusst
bricht — was dann rausgeht (auch Tool-Ergebnisse, nicht nur die Frage), steht
in [sicherheit.md](sicherheit.md) und [../ki/ki_system.md](../ki/ki_system.md).
