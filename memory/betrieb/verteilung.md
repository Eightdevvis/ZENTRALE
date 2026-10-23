# Verteilung — apt, pacman, curl-Einzeiler (seit 2026-10-23)

Entscheidung Sasha, 23.10.2026: ZENTRALE wird auf den üblichen Wegen
verteilt — **apt** (Debian/Ubuntu/Pop!_OS), **pacman** (Arch/EndeavourOS: AUR
und/oder eigenes Repo) und ein **curl-Einzeiler**. Die Cloud (Cloudflare
Worker) ist nur Speicher für Konten und Abgleich, nicht die Programmquelle.
Der Code ist lesbar (Python); geschützt wird über Lizenz + wertvolle Teile auf
dem Server. Veröffentlicht wird SPÄTER, hinter einem Schalter, nach einer
Durchsicht. **Heute geht nichts öffentlich, kein Skript lädt etwas hoch.**

## Eine Quelle für alles

```
deploy/paket.txt ─► scripts/paket_bauen.py ─► dist/zentrale-<fassung>.tar.gz + neueste.json
                                               │
         scripts/deb_bauen.py  ◄───────────────┤  dist/zentrale_<fassung>_all.deb
         scripts/arch_bauen.py ◄───────────────┘  dist/arch/PKGBUILD, .SRCINFO, tar.gz-Kopie
deploy/install.sh.in ─► scripts/verteilung.py ─► deploy/install.sh (eingecheckt) + dist/install.sh
```

- Welche Dateien ausgeliefert werden, entscheidet nur `deploy/paket.txt`
  (Verbote in `paket_bauen.py`). .deb und PKGBUILD nehmen genau das tar.gz.
- Fassung: `deploy/RELEASE` (wie bisher).
- Alles auf einmal: `scripts/verteilung.py alles`. Einzeln: `paket_bauen.py`,
  `deb_bauen.py`, `arch_bauen.py`, `verteilung.py install-sh [--pruefen]`.
- Neue Dateien erst committen (oder stagen) — gepackt wird nur, was git kennt.

## Der Schalter: `deploy/verteilung.toml`

| Schlüssel | heute | Wirkung |
|---|---|---|
| `oeffentlich` | `false` | false: install.sh will einen Einladungscode, holt aus der Cloud; `zentrale update` nur mit Konto. true: beide holen ohne Code aus `quelle`. |
| `quelle` | `github` | `github` (Releases des künftigen öffentlichen Repos) oder `cloud` |
| `quellen.github.repo` | `OWNER/zentrale` | Platzhalter — Repo-Name offen |
| `betreuer` | leer | leer = git config (landet in .deb/PKGBUILD!) |
| `lizenz` | leer | leer = „alle Rechte vorbehalten" im Paket |
| `homepage` | leer | Debian `Homepage`, Arch `url` |

- Ins tar.gz schreibt `paket_bauen.py` `VERTEILUNG.json` (Schalter + URL-Vorlagen);
  danach richtet sich `zentrale update` eines install.sh-Hubs.
- `deploy/install.sh` ist **gerendert** (Kopfzeile sagt es), nie von Hand
  ändern: Vorlage `deploy/install.sh.in`, Konstanten aus der toml, Cloud-Adresse
  aus `core/cloud_api.py` (`VORGABE`). `tests/test_verteilung.py` merkt, wenn
  die eingecheckte Datei nicht mehr zur toml passt.
- `quelle = cloud` öffentlich bräuchte im Worker (`cloud/src/paket.ts`) eine
  Freigabe ohne Code — heute 401 ohne Code.

## Kanäle

| Kanal | Erkannt an | Update |
|---|---|---|
| `apt` | Datei `KANAL` = apt (legt nur das .deb an) | apt; `zentrale update` verweigert und nennt den Weg |
| `pacman` | `KANAL` = pacman (PKGBUILD) | pacman/AUR-Helfer; `update` verweigert |
| `script` | liegt unter `~/.local/share/zentrale/hub/` | `zentrale update` (Cloud mit Konto, öffentlich ohne) |
| `dev` | sonst (Checkout) | git |

`zentrale version` und `zentrale status` zeigen den Kanal.

### Paketverwaltung (apt und pacman gleich)

- Programm schreibgeschützt nach `/usr/lib/zentrale/`, Starter
  `packaging/starter.sh` → `/usr/bin/zentrale`.
- **Warum eine Kopie pro Nutzer:** der Kern sucht seine Daten neben dem
  Programm (`<wurzel>/data`, in ~17 Modulen) und löst Pfade mit `realpath`
  auf — aus `/usr/lib` heraus ginge das nicht. Der Starter legt deshalb beim
  ersten Start einer Fassung `~/.local/share/zentrale/paket/<fassung>/` an
  (Kopie, `data -> ../../data`, `venv -> ../venv`), alte Fassungen fliegen.
  Daten liegen in `~/.local/share/zentrale/data` — dieselben wie bei install.sh.
- **Warum venv im Nutzerordner, nicht postinst:** kein pip ins System-Python,
  kein Netz während apt/pacman, kein Root für Python-Pakete.
  `~/.local/share/zentrale/paket/venv` entsteht beim ersten Start, neu nur bei
  geänderter `requirements-basis.txt` oder neuem Python (Stempel).
- Deinstallieren lässt `~/.local/share/zentrale` stehen (Paketverwaltung fasst
  keine Heimordner an).
- .deb: nur `dpkg-deb` (kein debhelper), `Depends: python3 (>= 3.11),
  python3-venv, ca-certificates`, `Recommends: libportaudio2`; copyright +
  changelog.gz liegen bei. lintian war hier nicht installiert — ungeprüft.
- Arch: `dist/arch/PKGBUILD` (+ `.SRCINFO`, von Hand erzeugt wie
  `makepkg --printsrcinfo`; nach Änderungen am PKGBUILD lieber mit makepkg neu
  erzeugen). Lokal bauen: im Ordner `dist/arch` makepkg laufen lassen — das
  tar.gz liegt daneben, der Name vor `::` lässt makepkg es nehmen, sha256 wird
  geprüft. makepkg gibt es nur auf Arch.

## Veröffentlichen — später, Schritt für Schritt

**Vor dem Veröffentlichen (Bedingung, aus der Entscheidung):**
1. Persönliche Daten raus aus Persona und Prompts (`prompts/`, alles, was im
   tar.gz landet) — durchsehen, nicht nur grep.
2. Lizenz festlegen, LICENSE-Datei ins Repo und in `deploy/paket.txt`,
   `lizenz` in der toml.
3. Wertvolle Teile serverseitig — was nicht lesbar ausgeliefert werden soll,
   bleibt aus `deploy/paket.txt` draußen.
4. `betreuer` bewusst setzen (sonst steht die git-Mail im Paket).
5. Öffentliches Repo anlegen, `quellen.github.repo` eintragen.

**Dann:**
1. In der toml `oeffentlich = true`, alles neu bauen, Tests, committen.
2. Ein GitHub-Release `v<fassung>` mit tar.gz und `neueste.json` anlegen
   (`releases/latest/download/neueste.json` muss auf die neueste zeigen).
3. Die gerenderte `install.sh` dorthin legen, wo der Einzeiler sie holt (heute
   R2 `install.sh` hinter `<cloud>/install.sh`; das Hochlade-Skript
   `cloud/scripts/paket_hochladen.mjs` nimmt `deploy/install.sh` + `dist/`).
4. apt: ein eigenes, signiertes apt-Repo (Ort offen: GitHub Pages oder R2) mit
   dem .deb, oder das .deb nur als Release-Download.
5. pacman: PKGBUILD + .SRCINFO ins AUR-Repo `zentrale`; optional eigenes
   pacman-Repo mit dem gebauten Paket.
6. Die Cloud bleibt Konten + Abgleich; Pakete in R2 können danach weg.
