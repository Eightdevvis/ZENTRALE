# Wo ein Zustand lebt: Hub, Standort, App (Sasha, 2026-10-29)

Sashas Bild: ein Geschäftsmann mit Standorten (Küste, Inland) und
Arbeitern (Apps). Daraus drei Orte für jeden Zustand — vor jedem Entwurf
fragen, an welchen er gehört:

| Ort | Was dort lebt | Was dort NIE lebt |
|---|---|---|
| **Hub / Konto** — „die Pforte der Pforten", eine nackte Hülle | Anmeldung, Mitte, Rechte, Steckplätze | keine Einstellung irgendeiner App |
| **Standort (Knoten/Gerät)** | welche Apps hier stationiert sind (`abgleich_apps`, beim Einrichten gefragt: „was planst du hier?"); wie viel man von nicht stationierten Apps sieht (z. B. ihre Nachrichten im Postfach); echte Geräte-Eigenschaften (Bildschirm, Hardware) | wie eine App arbeitet |
| **App-Instanz** | ALLES über die App: Einstellungen (z. B. die Quelle eines Kalenders), Daten, Gedächtnis — synct mit den Daten der App, ist auf jedem Standort, an dem sie stationiert ist, **1:1 dieselbe** | — |

- Dieselbe App an zwei Standorten ist derselbe Arbeiter: was man im
  Inland mit ihr gemacht hat, weiß sie an der Küste.
- Soll sie irgendwo anders arbeiten (z. B. Daten aus Google statt aus der
  ZENTRALE-Cloud), ist das eine **zweite App-Instanz** — beide dürfen
  gleichzeitig laufen. Nie eine Instanz, die je Standort anders ist.
- Prüffrage bei jedem Entwurf: *Kann sich das zwischen Geräten
  unterscheiden?* Wenn ja: ist es „welche Apps hier" oder eine
  Geräte-Eigenschaft? Sonst gehört es in die App-Instanz. Neue
  Geräte-Sonderfälle nur mit Sashas Zustimmung.
- Anlass: ein Kalender-Schalter „Google oder Cloud je Gerät" (1f32e6a),
  umgebaut zur Einstellung der Kalender-App.
