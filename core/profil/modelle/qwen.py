# core/profil/modelle/qwen.py
#
# Das Profil für qwen über die Cloud (qwen-plus & Co., DashScope, OpenAI-
# kompatibel). Gebaut und gemessen in der Nacht 09./10.10.2026 mit dem
# Prüfstand (memory/ki/modell_profile.md: was half, was nicht, Zahlen).
#
# Jede Strategie steht hier mit ihrem Grund. Was nicht half, steht NICHT
# hier, sondern in der Doku — sonst zahlt qwen für Text, der nichts bringt.

import re as _re

import nutzer_angaben

NAME = "qwen"


# ── Arbeitsweise: zuerst handeln, dann reden (Runde 1) ──────────────────
# Grundmessung 09.10. (ohne Profil): qwen-plus kündigte an statt zu tun
# („ändere ich ihn direkt … Möchtest du die Änderung jetzt durchführen?"),
# antwortete über den Kalender, ohne nachzulesen („nur ein Parkour-Termin"),
# erfand Daten („Ferien 12.–31. Oktober, steht in der amtlichen
# Ferienordnung") und meldete Erledigtes, das nie lief („Du hast nyam
# gelöscht"). Die gross-Regeln stehen weiter unten im langen Kopf; ein
# kleineres Modell folgt dem, was ganz vorn und ganz hinten steht, deutlich
# eher (Anthropic/OpenAI-Leitfäden: Regeln an Anfang und Ende, kurz, im
# Imperativ). Deshalb dieselben Pflichten als knappe Liste VOR die Persona —
# und als Erinnerung ans Ende jeder Nachricht.
# Geschärft in den Runden 3 (breiter suchen), 6/7 (Suche ohne Zeitraum, „Was
# ansteht" ist nicht der Kalender, Ende nicht erfinden, „halb X" als Regel
# mit neutralen Beispielen — ein Beispiel mit Fall-Werten hatte „halb sieben"
# zu 19:30 gemacht) und 10 (nicht mehr als verlangt, Suchtreffer kennzeichnen,
# Quelle nennen).
_ARBEITSWEISE_VORLAGE = """## Arbeitsweise (gilt vor allem anderen)

1. Will {nutzer} etwas im Kalender (eintragen, verschieben, ändern, löschen, ausfallen lassen) und sind Tag und Uhrzeit klar: ruf SOFORT das Werkzeug. Nicht ankündigen, nicht fragen „soll ich?" — die Ja/Nein-Frage stellt ZENTRALE selbst, bevor etwas geschrieben wird.
2. Sagt {nutzer} „ok", „ja", „mach", „passt" auf deinen Vorschlag: führ ihn JETZT mit Werkzeugen aus.
3. Bevor du einen bestehenden Termin änderst oder etwas über den Kalender sagst: read_calendar — für einen bestimmten Termin oder eine Serie mit 'suche' (Stichwort) und OHNE 'zeitraum'. Der Block „Was ansteht" zeigt nur heute und morgen, nie den ganzen Kalender. Findet die Stichwort-Suche nichts, lies den Zeitraum ohne 'suche' (Titel heißen oft anders), bevor du sagst, es gibt ihn nicht. Kennungen (#r…, #t…) schreibst du nur aus einem Werkzeug-Ergebnis ab, nie ausgedacht, und nie in den Text an {nutzer}.
4. „Eingetragen", „gelöscht", „korrigiert", „erledigt" sagst du NUR, wenn in DIESEM Zug ein Werkzeug-Ergebnis mit [ergebnis: ok] dazu da ist. Sonst sag, was noch nicht passiert ist.
5. Was kein Werkzeug geliefert und {nutzer} nicht gesagt hat (Ferien, Semesterdaten, Öffnungszeiten, das Ende einer Serie), ist „weiß ich nicht" — nie als Tatsache, nie „habe ich geholt", nie als ausgedachtes Datum in einem Werkzeug. Suchtreffer (web_search) sind nicht gelesen: ein Datum daraus nur mit „laut Suchtreffer, nicht nachgelesen" — oder erst die Seite lesen. Braucht eine neue Serie ein Ende (bis), das {nutzer} nicht genannt hat: frag „bis wann?".
6. Uhrzeiten: „halb X" ist eine halbe Stunde VOR X — halb sechs = 17:30, halb neun = 20:30 (abends; morgens 5:30/8:30). „viertel nach fünf" = 17:15, „dreiviertel sechs" = 17:45. Verschiebt {nutzer} nur den Beginn, wandert das Ende mit (gleiche Dauer): 17:00–18:00 „ab jetzt um halb sechs" → time 17:30, ende 18:30.
7. Du änderst nur, was {nutzer} verlangt. Vorschlagen darfst du; eingetragen oder gelöscht wird nichts darüber hinaus. Sagt {er} „nur nachschauen": schau nach und sag, was du gefunden hast (mit Quelle) — eintragen nichts.
8. Antwort danach kurz: was jetzt im Kalender steht (Titel, Tag, Uhrzeit). Hast du etwas von einer Seite gelesen, nenn ihre Adresse als Quelle. Keine Pläne, was du gleich tun wirst — entweder tun oder lassen."""

_ERINNERUNG_VORLAGE = ("(Für dich, nicht von {nutzer}: erst Werkzeug, dann Antwort. Erledigt ist nur, "
              "was in diesem Zug mit [ergebnis: ok] zurückkam.)")


# Platzhalter ({nutzer}, {er} …) wie in gross (core/nutzer_angaben.py,
# Erststart 2026-10-09): eingesetzt bei jedem Bau, wie gross.system().
def system(text: str) -> str:
    return nutzer_angaben.einsetzen(_ARBEITSWEISE_VORLAGE) + "\n\n" + text


def erinnerung(verlauf: list = ()) -> str:
    text = nutzer_angaben.einsetzen(_ERINNERUNG_VORLAGE)
    uhr = uhrzeiten(_letzte_nachricht(verlauf))
    return f"{text}\n{uhr}" if uhr else text


# ── Uhrzeiten vorrechnen (Runde 12) ─────────────────────────────────────
# Regel 6 („halb X = eine halbe Stunde vor X") reichte nicht: im
# Abschlusslauf machte qwen aus „halb sieben" wieder 19:30 (f03), obwohl die
# Regel mit Beispielen dastand. Was Python sicher rechnen kann, rechnet
# Python: steht in der neuesten Nachricht eine Umgangs-Uhrzeit, kommt die
# Übersetzung als Zeile in die Erinnerung am Ende („halb sieben" = 6:30 oder
# 18:30) — welche der beiden, entscheidet qwen aus dem Zusammenhang.
_ZAHL = {"eins": 1, "ein": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "fuenf": 5,
         "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11,
         "zwölf": 12, "zwoelf": 12}
_UHR = _re.compile(r"\b(halb|viertel nach|viertel vor|dreiviertel)\s+(\d{1,2}|"
                   + "|".join(_ZAHL) + r")\b")


def uhrzeiten(text: str) -> str:
    """„halb sieben" → '„halb sieben“ = 6:30 oder 18:30'; mehrere mit ' · '."""
    raus = []
    for art, zahl in _UHR.findall((text or "").casefold()):
        n = int(zahl) if zahl.isdigit() else _ZAHL[zahl]
        if not 1 <= n <= 12:
            continue
        stunde, minute = {"halb": (n - 1, 30), "viertel nach": (n, 15),
                          "viertel vor": (n - 1, 45), "dreiviertel": (n - 1, 45)}[art]
        stunde = stunde or 12
        raus.append(f"„{art} {zahl}“ = {stunde}:{minute:02d} oder "
                    f"{stunde + 12 if stunde < 12 else 0}:{minute:02d}")
    if not raus:
        return ""
    return "Uhrzeiten in dieser Nachricht: " + " · ".join(dict.fromkeys(raus)) + "."


def _letzte_nachricht(verlauf) -> str:
    for m in reversed(list(verlauf or [])):
        if m.get("role") == "user":
            return str(m.get("content") or "")
    return ""
