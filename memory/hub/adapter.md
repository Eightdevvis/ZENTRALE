# Der Adapter — die eine Tür zu fremden Diensten

**Stand 2026-10-24: Plan, Bau läuft.** Sasha, als der Mini-PC beitrat und der
Kalender fehlte:

> *„bleib beim gedanken dass der kalender eigentlich über zentrale komplett
> laufen soll und google nur da ist weil es noch keine app gibt. man soll auch
> die möglichkeit offen haben google und andere dienste zu verbinden aber das
> soll man auch nur über eine einzelne schnittstelle machen müssen. ich stelle
> mir im hub dafür eine app oder einen teil beim schmied vor namens „adapter"
> wo man so outsider sachen ankabeln kann. der adapter wird dann aber genauso
> überall durchgesynct in seiner konfiguration. … wenn man eine clean slate
> zentrale hat würde der adapter immer mit installiert. er ist quasi neben dem
> internen shop die zweite stelle wie man an apps und schnittstellen kommt."*

Messlatte ([../leitbild.md](../leitbild.md)): Unterbau — jetzt nötig, weil
ein neues Gerät (Mini-PC) sonst ohne Kalender und ohne KI dasteht. „Ein
Login, alles da" ist die Voraussetzung dafür, dass Räume Knoten werden.

## Das Modell

1. **ZENTRALE ist die Wahrheit.** Kalender, Listen, … leben in ZENTRALE und
   gleichen über die Cloud ab wie alles andere. Ein fremder Dienst ist nur
   ein **Anschluss**, nie die Quelle.
2. **Der Adapter ist eine App**, immer installiert (auch bei clean slate).
   Neben dem Shop die zweite Stelle, an der Apps und Schnittstellen
   hereinkommen. Er gehört zur Werkstatt-Familie: die Anbindungs-Pipe
   ([hub_bauplan.md](hub_bauplan.md) „Anbindungs-Pipe der Werkstatt",
   Format `core/werkzeug_erzeuger/anbindung.schema.json`) ist seine
   Maschine für Dienste mit API.
3. **Ein Anschluss** = eine Beschreibung (was, wohin, welche App er speist)
   plus seine **Zugangsdaten**. Die Beschreibung gleicht überall ab
   (`data/adapter/`), die Zugangsdaten auch — **nur verschlüsselt** über die
   Cloud (Zero-Knowledge), nie im Klartext irgendwohin.
4. **Ein Gerät fährt die Brücke.** Ein Anschluss, der mit einem fremden
   Dienst abgleicht (Google-Kalender), läuft auf genau **einem** Gerät — dem
   **Brücken-Gerät**, das in der Beschreibung steht. Alle anderen bekommen die
   Daten über die Cloud. So gibt es nie zwei Wege für dieselben Termine
   (die Doppelten und Geister von früher).
5. **KI-Anbieter sind Anschlüsse.** Die Schlüssel für Anthropic & Co.
   (bisher `data/ai_config.json`, wanderte nie mit) ziehen in die
   Zugangsdaten des Adapters — damit hat ein neues Gerät nach dem Login
   sofort eine KI. Langfristig (Hub-Plan) liegen sie auf Sashas Server, dann
   zeigt der Anschluss dorthin.

## Erste Anschlüsse

| Anschluss | speist | Brücke |
|---|---|---|
| Google-Kalender (vdirsyncer, bisher je Gerät) | `kalender` | ein Gerät (Vorgabe: das, auf dem er eingerichtet wurde) |
| KI-Anbieter (Anthropic, Mistral, …) | `assistent` | keine — jedes Gerät nutzt den Schlüssel selbst |

## Sicherheitsregeln

- Zugangsdaten nur verschlüsselt mit dem Kontoschlüssel in der Cloud.
- **Nie** in die alte Datensicherung (`scripts/daten_sichern.py` schickt
  ihre Liste im Klartext ins private GitHub-Daten-Repo) — eigene Liste, Test.
- Ohne Konto (rein lokal) bleiben Zugangsdaten nur auf dem Gerät.
- Der Kalender über die Cloud: `data/kalender/**` aus `NICHT_ABGLEICHEN`
  heraus, sobald es ein Brücken-Gerät gibt — vorher bewusst umstellen, nicht
  still.

## Historie

- **2026-10-24** — Plan nach dem Beitritt des Mini-PCs.
