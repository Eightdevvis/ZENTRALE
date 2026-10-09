# core/werkzeug_eintrag.py
#
# Wie EIN Werkzeug-Eintrag aussieht (die Felder und ihre Bedeutung). Die
# Einträge selbst stehen in core/werkzeug_register.py und, für die Skills pdf
# und word, in core/werkzeug_pdf_word.py.
#
# 2026-10-08 aus core/werkzeug_register.py hierher gezogen, wörtlich: das
# Register stand an der Riesen-Grenze (1.500 Zeilen, memory/system/
# bauplan_kern.md), und neue Einträge in einer eigenen Datei brauchen die
# Klasse, ohne das Register zu importieren (das wäre ein Kreis — das Register
# hängt sie an seine Liste).
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md).

from dataclasses import dataclass
from typing import Callable


@dataclass
class Werkzeug:
    """Ein Werkzeug. Die Reihenfolge der Einträge unten IST die Reihenfolge,
    in der die Schienen sie ans Modell geben.

    name            Der Name, den der Kern spricht (englisch, kanonisch).
    parameter       JSON-Schema der Argumente — der Vertrag mit Python, für
                    beide Schienen gleich.
    klein, gross    Beschreibung auf dieser Schiene; None = dort nicht
                    angeboten. Die Beschreibung ist ANREDE und gehört der
                    Schiene, deshalb zwei Texte.
    klein_name      Alter deutscher Name auf der klein-Schiene (lies_news …);
                    der Kern übersetzt ihn mit kanonisch().
    erlaubnis       False = nie fragen, True = immer, oder eine Funktion
                    f(args) -> bool (nur mit Argumenten gefragt).
    frage           f(args) -> str: die Ja/Nein-Frage, die Sasha sieht.
                    Fehlt sie, kommt eine allgemeine.
    immer_erlaubbar Darf Sasha dieses Werkzeug „immer" erlauben (core/
                    erlaubnis.py, Geltungsbereiche)? False für alles, was
                    löscht oder überschreibt, und für Kernakten.
    alltag          Was das Werkzeug tut, in Alltagswörtern, für Sashas
                    Liste unter /erlaubnis („termine eintragen").
    nur_einmal      f(args) -> bool: True = dieser Aufruf braucht ein
                    eigenes Ja, ein früheres „immer"/„für dieses Gespräch"
                    gilt nicht, und angeboten wird nur „einmal".
    terminal        Das Ergebnis IST die Antwort, danach keine Runde mehr
                    (Behandlung in werkzeug_schleife.run_tool).
    in_der_schleife Hat keinen Ausführer, die Schleife erledigt es selbst
                    (antwort, ask_choice).
    ausfuehrer      f(args) -> str, angemeldet von ki_werkzeuge.
    gross_parameter Schema NUR für die gross-Schiene, wenn sie mehr kann
                    (2026-10-08: Kennungen, Ende und Ort im Kalender). Es
                    darf nur ERGÄNZEN: jedes klein-Feld bleibt, Pflichtfelder
                    dürfen höchstens wegfallen — so versteht der Ausführer
                    beide (tests/test_profil.py). klein bleibt byte-gleich.
    schreibt        Verändert Sashas Daten (Kalender, Notizen, Ablage …).
    beweis          Nur bei schreibt: was der Ausführer NACH dem Schreiben
                    nachliest und als Beleg zurückgibt (2026-10-08, „Belege
                    statt OK"). Der Ausführer liefert dafür einen
                    werkzeug_befund.Befund mit `beleg`; der Test
                    (tests/test_werkzeug_belege.py) prüft jedes.
    """
    name: str
    parameter: dict
    klein: str | None = None
    gross: str | None = None
    klein_name: str | None = None
    erlaubnis: bool | Callable[[dict], bool] = False
    frage: Callable[[dict], str] | None = None
    immer_erlaubbar: bool = True
    alltag: str | None = None
    nur_einmal: Callable[[dict], bool] | None = None
    terminal: bool = False
    in_der_schleife: bool = False
    ausfuehrer: Callable[[dict], str] | None = None
    gross_parameter: dict | None = None
    schreibt: bool = False
    beweis: str | None = None

    def beschreibung(self, schiene: str) -> str | None:
        return getattr(self, schiene)

    def parameter_auf(self, schiene: str) -> dict:
        if schiene == "gross" and self.gross_parameter is not None:
            return self.gross_parameter
        return self.parameter

    def name_auf(self, schiene: str) -> str:
        if schiene == "klein" and self.klein_name:
            return self.klein_name
        return self.name
