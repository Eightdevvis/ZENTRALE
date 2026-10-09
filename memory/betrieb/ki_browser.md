# Browser der KI einrichten (Chromium ohne Fenster)

Seit 2026-10-09 kann die KI Webseiten in einem echten Browser bedienen
(`browser_open` & Co., [../ki/ki_system.md](../ki/ki_system.md) Abschnitt
„Browser"). Das braucht zwei Dinge auf dem Rechner, auf dem das **Backend**
läuft — nicht auf dem, an dem du tippst.

Fehlt eins davon, passiert nichts Schlimmes: die KI bekommt „Browser nicht
eingerichtet" (Fehler `B-NICHT-EINGERICHTET`), sagt dir das und nimmt
stattdessen das einfache Seite-Laden.

## Die zwei Schritte

1. **Das Paket ins venv von ZENTRALE.** Es heißt `playwright` und steht
   auskommentiert in `requirements.txt` (optional — darum nicht automatisch
   dabei). Installier es mit dem pip aus dem venv, nicht mit dem des Systems.
2. **Chromium dazu herunterladen.** Das Paket bringt ein eigenes
   Kommando mit, das Browser nachlädt — dort nur Chromium verlangen, nicht
   alle Browser. Es landen ~110 MB im Cache-Ordner deines Benutzers
   (`~/.cache/ms-playwright`). Aufrufen über das Python aus dem venv, als
   Modul.

Danach das Backend neu starten. Prüfen: die KI im Chat eine Seite im Browser
öffnen lassen — sie fragt dich einmal „Soll ich im Browser … öffnen?".

## Fallen

- **Fehlende Systembibliotheken.** Meldet die KI „dem System fehlen
  Bibliotheken, die Chromium braucht": dasselbe Kommando hat einen eigenen
  Unterbefehl, der die Abhängigkeiten des Systems nachinstalliert — der
  braucht Root-Rechte. Vorher lesen, was er installieren will.
- **Der Pi.** Chromium auf dem Pi geht (ARM64 wird geliefert), kostet aber
  einige hundert MB Arbeitsspeicher, solange eine Seite offen ist. Nach 10
  Minuten ohne Klick schließt ZENTRALE den Browser von selbst. Läuft das
  Backend ohnehin auf dem PC, braucht der Pi nichts davon.
- **Nach einem Update des Pakets** will es oft eine neue Chromium-Fassung —
  Schritt 2 dann wiederholen (die Meldung sagt „Chromium für den Browser ist
  nicht heruntergeladen").
- **Abschottung.** Chromium startet zuerst mit seiner eigenen Abschottung.
  Erlaubt Ubuntu die nicht, läuft er ohne, mit einer Zeile im Log
  („Chromium läuft ohne eigene Abschottung"). Der Browser bleibt trotzdem
  eingeschränkt: kein Zugriff aufs eigene Netz, keine Downloads, nur Seiten,
  die du erlaubt hast.

## Einstellung

| Schlüssel | Standard | Wozu |
|---|---|---|
| `browser_lokal_erlaubt` | aus | Auch Adressen im eigenen Rechner/Netz (localhost, 192.168.…). Nur für Tests mit eigenem Server — im Alltag aus lassen: sonst könnte eine fremde Seite den Browser auf dein Dashboard schicken. |
