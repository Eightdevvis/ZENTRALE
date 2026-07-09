# Tutor-Roleplay-Features — Über-Nacht-Bau (2026-07-09) + Entscheidungs-Log

Sasha hat den Tutor-Prompt auf ein reiches **Roleplay-Framing** umgestellt (gegen
qwen validiert, `tutor_langs._ZH_PROMPT`) und darin viele neue Features skizziert
(`prompts/tutor_generisch-fallback.md`, sein „Sasha Stil"-Draft). Auftrag: über
Nacht alle Features durchbauen, bei Unsicherheit selbst entscheiden + hier
dokumentieren, morgen gemeinsam reviewen.

## Leitplanken (gelten für alles)
- **Live-Prompt bleibt in der Zielsprache** (Deutsch → qwen antwortet deutsch,
  verifiziert). Roleplay-Framing ja, aber pro Sprache in ihrer Sprache.
- **Jede Fähigkeit braucht ein Tool.** Ohne Tool spielt die KI die Aktion als
  Text vor (Regie-Anweisung) — das wollen wir nicht. Frame gewährt nur, was ein
  Tool/State hat.
- **Kurz + kein Fake-Lob/-Mensch** bleibt (getunt). Neue Features dürfen das
  nicht regressieren → nach Prompt-Änderungen gegen echtes qwen gegentesten.
- **Content (Filme/Musik/Bilder)** kann ich nicht lizenzieren → Mechanik bauen,
  Content-Lücke markieren.

## Bau-Reihenfolge (Abhängigkeiten)
1. Reichere Gesten + Mimik (express erweitern + Persona-Animation)
2. Soziale Batterie / Stimmung (State + Decay + Kopplung an Mimik)
3. Vokabel-Feinmodell (pro-Wort-Vertrautheit + neue Strukturen)
4. Visuelle Vokabel-Hilfe (Gedanken-Bubble: Übersetzung jetzt, Bild später)
5. Presence im Hintergrund (brain.py PRESENCE_DETECTED → Zimmer/Anquatschen)
6. Lokale Landes-News (Zeitung/TV-News-Tool, an core/news.py angelehnt)
7. Musik (Tool + mixer.music + Bibliothek nach Stimmung)
8. TV + Film-Mediathek (TV-Objekt + Tool + Bibliothek nach Stimmung/Level)

## Entscheidungen (wird beim Bauen ergänzt)

### 1. Reichere Gesten + Mimik + Schlafen ✅
- **express-Tool** erweitert: Haltungen +`sleep`; Gesten +`arms_up`/`cross_arms`/
  `shrug`; NEU **Mimik** (anhaltend): `happy`/`sad`/`surprised`/`tired`/`neutral`.
  Ein Enum, geroutet in `tutor_session.set_expression` (Stance|Geste|Face).
- `tutor_session._expr` hat jetzt `face`; `room_state()` liefert es; das Fenster
  pollt + `Persona.set_face`. `set_face()` auch direkt aufrufbar (für Feature 2,
  Stimmung→Mimik).
- Render: `sleep` = auf der Couch, Augen zu, „zzz"; `cross_arms` = Arme waagerecht
  vor der Brust; Mimik ändert Augen (überrascht=weit, müde/schlaf=zu) + Mund
  (happy=breit, sad=runter, surprised=O, tired=Strich).
- **Entscheidung/Annahme:** Mimik ist ein eigener anhaltender Zustand (nicht
  one-shot), damit Feature 2 (Batterie) sie treiben kann. Gesten bleiben one-shot.
- **Offen/Review:** die Sprite-Optik ist simpel (Primitive) — reicht funktional,
  könnte man später hübscher machen.
