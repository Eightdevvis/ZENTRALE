# Sicherheit – Bedrohungsmodell, LUKS, Auto-Unlock

**Stand 2026-09-18:** Relevante Achsen sind Diebstahlschutz (LUKS, Daten
at rest) und Remote-Hardening; ein Hochsicherheits-Setup wäre Overkill.
LUKS-Header-Backup und Notfall-Keyslot existieren (2026-05-19), der
Remote-Unlock über Dropbear im Initramfs ist eingerichtet und funktioniert
(`auto_unlock.md`) — seit dem Wachplan nur noch für den echten Aus-Fall.
Bewusst akzeptierte Lücken: Evil Maid (`/boot` unverschlüsselt),
Disk-PW = User-PW. Seit 2026-06 gibt es einen gewollten Ausgangskanal
(KI-Tools `web_search`/`fetch_url`, hart gegated), seit 2026-08 optional den
Cloud-Kern (`memory/ki/ki_system.md`). Offen: Firewall, SSH-Hardening,
Notfall-Passphrase auf Papier, Live-USB.

Sammelpunkt für Security-Themen rund um den ZENTRALE-Stack. Konkrete
Setups gehören in eigene Themen-Files (z.B. `memory/betrieb/auto_unlock.md`, später
`firewall.md`), hier landen das **Bedrohungsmodell** und bekannte
**offene Lücken**.

## Was wir schützen wollen

| Asset                              | Wert | Warum                                  |
|------------------------------------|------|----------------------------------------|
| `data/*.json` (LTM, STM, Graph)    | mittel | Privates Memory der Hausbewohner    |
| SSH-Keys, Browser-Credentials      | hoch | Lateral movement in andere Systeme   |
| Brain-Konfig (Prompts, Modelle)    | niedrig | Reproduzierbar aus Repo            |
| Sensoren / Aktoren-Kontrolle       | mittel | Wer Brain kontrolliert, kontrolliert Aktionen im Haus |

## Realistische Angreifer

| Angreifer                  | Wahrscheinlichkeit | Was sie wollen      |
|----------------------------|--------------------|---------------------|
| Einbrecher (klaut Hardware)| mittel             | Geld, nicht Daten   |
| Polizei/Behörde (beschlag.)| sehr niedrig       | Inhalt der Disk     |
| Remote-Skript-Kiddie       | mittel             | Botnet, Crypto-Miner|
| Gezielter Hacker           | sehr niedrig       | konkrete Daten      |
| Mitbewohner / Gast         | mittel             | Neugier, kein Schaden|

Schlussfolgerung: **Diebstahlschutz und Remote-Hardening** sind die
relevanten Achsen. Hochsicherheits-Setup wäre Overkill.

## Ausgehender Kanal: Internet-Pipe der KI

Bis 2026-06-07 hatte ZENTRALE **keinen** gewollten Ausgangskanal (offline by
default). Die KI-Tools `web_search`/`fetch_url` (`core/web.py`; in der
`klein`-Schiene `web_suche`/`hole_url`, das Gate prüft über
`ai.braucht_erlaubnis()` immer den kanonischen Namen) öffnen einen –
und damit theoretisch einen **Exfiltrations-Pfad**: ein lokales 9b-Modell
könnte (durch böswillige User-Eingabe oder **Prompt-Injection** aus dem Text
einer geholten Seite) dazu gebracht werden, privates Graph-Wissen in eine
Suchanfrage/URL zu verpacken und rauszuschicken.

Mitigationen (bewusst, kein Modell-Vertrauen):
- **Hartes Gate im Backend** (`PERMISSION_REQUIRED_TOOLS`): jeder Such-/Lade-
  Call zeigt Sasha vorher die exakte Query/URL als JA/NEIN-Dialog. Nichts geht
  ohne Klick raus. Nicht modellgetrieben → injection-resistent
  ([[feedback_permission_gate_backend]]).
- **Internet-Monitor** (rechtes Panel): jeder rausgehende Call leuchtet auf.
  Nicht-gegateter Internet-Traffic dort = Alarm.
- **Restrisiko:** wer „ja" reflexhaft klickt, hebelt das Gate aus – die
  Query/URL ist sichtbar, aber lange Querystrings könnten Daten verstecken.
  Akzeptiert; Gegenmaßnahme wäre Längen-/Inhalts-Check der Query vor Anzeige.

## LUKS – Wovor es schützt, wovor nicht

LUKS schützt **nur Daten-at-rest** (PC aus, Disk verschlüsselt).
Sobald gebootet ist, ist die Disk im Klartext gemounted und LUKS macht
gar nichts mehr.

Konkret:

| Szenario                              | LUKS hilft? |
|---------------------------------------|-------------|
| Einbrecher klaut PC im Aus-Zustand    | ✅          |
| Platte ausbauen + extern mounten      | ✅          |
| Brute-Force LUKS-Passwort             | ✅ (Argon2) |
| Lebender PC, gesperrter Bildschirm    | ❌          |
| Remote-Exploit übers Netz             | ❌          |
| **Evil Maid Attack**                  | ⚠️ siehe unten |
| DMA-Angriff via Thunderbolt/PCIe      | ❌          |
| Cold-Boot kurz nach Aus               | ⚠️ theoretisch |

## ⚠️ Bekannte offene Lücke: Evil Maid

`/boot` ist nicht verschlüsselt – das ist ein systembedingter Punkt,
weil der Bootloader irgendwo unverschlüsselt liegen muss, um das
LUKS-Passwort abfragen zu können.

**Konkreter Angriff:**

1. Jemand bekommt physisch Zugriff auf den ausgeschalteten PC
   (Einbruch ohne Klau, Hotel-Putzfrau-Szenario, Werkstatt).
2. Bootet von USB-Stick, mounted `/boot`.
3. Patcht das Initramfs oder den Kernel mit einem Keylogger.
4. Verschwindet wieder.
5. Beim nächsten Boot tippt der User sein LUKS-Passwort in den
   manipulierten Bootloader → Passwort wandert irgendwohin
   (USB-Stick, Netz, versteckte Partition).

**Risiko-Einschätzung für ZENTRALE:** niedrig. Wir sind im Privathaus,
kein gezielter Angreifer mit physischem Zugriff zu erwarten. Notiert
als bekannte Lücke, aktuell **nicht mitigated**.

**Mögliche Mitigations (falls Bedrohungslage steigt):**

- **Secure Boot** + signiertes Initramfs/Kernel: das System bootet nur
  ein signiertes Boot-Image, das nicht ohne Signatur-Key modifizierbar
  ist.
- **TPM2-Measurement** (auch bei manueller Passwort-Eingabe): TPM misst
  Boot-Komponenten, weigert sich beim Unlock wenn die Messung nicht
  zur erwarteten passt → erkennt Manipulationen.
- **`/boot` auf separatem USB-Stick**, den der User immer mitnimmt.
  Funktioniert, ist aber unpraktisch.

→ Für ZENTRALE aktuell: **bewusste Restakzeptanz**. Wenn sich die
Lage ändert (z.B. das System wird produktiv mit echten Nutzerdaten
Dritter), Secure Boot + TPM-Measurement umsetzen.

## Auto-Unlock-Strategie (Dropbear im Initramfs)

> Seit dem Wachplan (`wachplan.md`) schläft der PC nur noch (Suspend),
> Schritt 1 (WoL) ist der normale Weck-Weg; Schritte 2–5 braucht es nur nach
> echtem Aus.

Damit der Pi den PC remote wecken UND entsperren kann, ohne dass jemand
am PC sitzen muss, läuft im Initramfs ein minimaler SSH-Server
(Dropbear). Workflow:

1. Pi schickt WoL-Magic-Packet → PC bootet.
2. PC lädt Initramfs, kommt zum LUKS-Prompt.
3. Dropbear im Initramfs läuft auf festen Port, Key-Only-Auth.
4. Entweder:
   - Direkt am PC: Passwort tippen.
   - Vom Pi: `ssh -p <port> root@192.168.50.1 cryptroot-unlock`.
5. LUKS unlockt, System bootet durch.
6. `zentrale-pc.service` (siehe `memory/betrieb/deployment.md`) startet automatisch –
   ohne User-Login.

**Bewusste Design-Entscheidungen:**

- **Kein TPM-Auto-Unlock.** Würde den Klauschutz neutralisieren
  (Mainboard + Disk wandern als Paket).
- **Kein Tang/Clevis.** Würde "Pi reichts wenn er im Netz ist"
  bedeuten – wer beides klaut, hat alles.
- **Manuelle Eingabe bleibt notwendig**, der einzige Komfortgewinn ist
  der Eingabe-*Ort* (Pi statt PC).

**Was das nicht löst:**
- Evil Maid (Initramfs ist immer noch im unverschlüsselten `/boot`).
- User-Login auf X-Session bleibt manuell (gewollt: Brain läuft als
  systemd, kein Autologin).

**Netzwerk-im-Initramfs:** kein funktionales `ip=<adresse>`-Kernel-Param
(das hat bei der LAN-Migration die kaputte Default-Route produziert, siehe
`memory/system/topologie.md`), sondern `ip=off` plus eigenes
init-premount-Skript ohne Default-Route. Begründung, Befehle, Debug-Pfad und
Rollback: **`memory/betrieb/auto_unlock.md`** (eingerichtet, funktioniert).

## Recovery-Stand (LUKS)

### Erledigt (2026-05-19)

- **LUKS-Header-Backup** existiert in zwei Kopien:
  - PC lokal: `/home/sasha/luks-header-nvme0n1p3-20260519.img`
    (16 MiB, chmod 600, owner sasha:sasha)
  - Pi: `zentrale:~/luks-header-nvme0n1p3-20260519.img`
    (gleicher Inhalt, chmod 600)
- **Zweiter Keyslot** (Slot 1) mit Notfall-Passphrase angelegt.
  Slot 0 = primäres Disk-PW (= aktuell auch User-Login-PW),
  Slot 1 = unabhängige Notfall-Phrase, **nicht** identisch mit Slot 0.

### Recovery-Spickzettel

Header restoren falls korrupt:
```bash
sudo cryptsetup luksHeaderRestore /dev/nvme0n1p3 \
  --header-backup-file <pfad-zum-img>
```

Header neu dumpen (z.B. nach `luksAddKey`/`luksKillSlot`):
```bash
sudo cryptsetup luksHeaderBackup /dev/nvme0n1p3 \
  --header-backup-file /home/sasha/luks-header-nvme0n1p3-$(date +%Y%m%d).img
scp /home/sasha/luks-header-nvme0n1p3-*.img zentrale:~/
```
**Wichtig:** Header-Backup nach JEDER Slot-Änderung neu machen,
sonst restored der alte Header eine veraltete Slot-Belegung.

Slot killen wenn Passphrase kompromittiert:
```bash
sudo cryptsetup luksKillSlot /dev/nvme0n1p3 <slot-nr>
```

## TODO / offen

- [ ] **Notfall-Passphrase fest aufbewahren** (Papier in Safe /
  KeePass / Tresor). Nicht nur im Kopf, das ist genau der Failure-Mode
  den der Slot abdecken soll.
- [ ] **Live-USB beschaffen** (Pop!_OS ISO auf USB-Stick). Pop hat zwar
  Recovery auf `nvme0n1p2` (4 GB FAT), Live-USB ist robuster für
  Initramfs-Reparatur falls's mal nicht bootet. Verschoben auf später.
- [x] **Dropbear im Initramfs**: eingerichtet und belegt funktionierend
  (Details + Historie in `memory/betrieb/auto_unlock.md`).
- [ ] **Firewall** (`nftables`/`ufw`) durchgehen – welche Ports sind
  offen, welche müssen offen sein, was loggt was.
- [ ] **SSH-Hardening**: Key-only-Auth bestätigen
  (`PasswordAuthentication no`), Fail2Ban / nft rate-limit,
  Port-Knocking optional.
- [ ] **Disk-PW != User-PW**: derzeit dasselbe Passwort für LUKS-Slot 0
  und User-Account. Pragmatisch ok, aber wenn das User-PW mal leaked
  (Shoulder-Surfing, Shell-History, Keylogger), ist auch die Disk auf.
  Eigene LUKS-Passphrase setzen wäre die saubere Lösung.
- [ ] **Evil-Maid-Mitigation**: Secure Boot + TPM-Measurement, wenn
  das Bedrohungsmodell sich verschärft (aktuell bewusst akzeptiert).

## Historie

- **2026-05-19** — LUKS-Header-Backup (PC + Pi) und Notfall-Keyslot 1.
- **2026-06-01** — Auto-Unlock-Strategie entschieden (kein TPM, kein
  Tang/Clevis, Eingabe-Ort wandert nur), Netz-Bringup im Initramfs
  angewendet.
- **2026-06-07** — erster gewollter Ausgangskanal: KI-Web-Tools mit hartem
  Gate.
- **2026-08** — Cloud-Kern als Opt-in (`memory/ki/ki_system.md`): bricht die
  Offline-Eigenschaft für den Chat bewusst; was rausgeht, auch
  Tool-Ergebnisse.
- **2026-09-14** — Wachplan: Suspend statt Aus, Dropbear nur noch für den
  Aus-Fall.
