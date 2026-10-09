# tui/ansichten/chat_strom.py
#
# Mixin `StromSteuerung` des Chats: WOHIN eine laufende Antwort schreibt und
# dass „antwort läuft" nie stehen bleibt (2026-10-09).
#
# 1. Hängen: Sasha sah nach einem Browser-Zug weiter „answering …", obwohl
#    das Backend fertig war und kein Strom-Thread mehr lebte. Ein Thread, der
#    stirbt, bevor er AI["streaming"] zurücksetzt (Ausnahme vor dem try oder
#    im Abschluss), hinterlässt genau das — und sperrt Senden und Wechseln.
#    Deshalb: ai_stream setzt das Flag in einem eigenen äußeren finally
#    (strom_aus), und der Haupt-Loop fragt jedes Bild `waechter()`: Flag an,
#    aber kein Strom-Thread am Leben → zurücksetzen, Hinweis, Verlauf neu.
#
# 2. Wechseln während einer Antwort (wie bei Claude Web): die Antwort läuft
#    im Hintergrund weiter und landet in IHREM Gespräch. Sie schreibt in
#    `strom_ziel()`: das ist AI selbst, solange ihr Gespräch vor Sasha liegt
#    (AI["strom_hier"]), sonst ein Puffer (AI["strom_puffer"]) mit denselben
#    Schlüsseln. Wechselt Sasha weg, wandert die Ansicht in den Puffer;
#    kommt er zurück, wieder heraus — er sieht den Stand live weiter.
#    Senden in einem ANDEREN Gespräch bleibt gesperrt, solange sie läuft:
#    das Backend hat EINE Erlaubnis-Frage (core/state.py) und EIN „für dieses
#    Gespräch" (core/erlaubnis.py) — zwei Züge zugleich könnten sich die
#    Antworten auf Erlaubnis-Fragen gegenseitig wegnehmen.

import threading

from .basis import api_call

# Was zur Ansicht EINES Gesprächs gehört und mit dem Strom wandert.
ANSICHT = ("gid", "titel", "projekt", "log", "n", "n_server", "spuren",
           "answer", "reflect", "denken", "perm", "gestoppt", "pruefung",
           "antwort_live", "abbruch_live", "denk_t0", "denk_ende", "denk_log_n",
           "warnungen", "wechsel")


class StromSteuerung:

    # ── Wohin schreibt der Strom? ──────────────────────────────────────
    def strom_ziel(self):
        """AI, wenn das Gespräch der laufenden Antwort offen ist, sonst ihr
        Puffer. Unter AI_LOCK aufrufen."""
        AI = self.AI
        if AI.get("strom_hier", True) or AI.get("strom_puffer") is None:
            return AI
        return AI["strom_puffer"]

    def strom_laeuft_hier(self):
        """Läuft gerade eine Antwort im OFFENEN Gespräch?"""
        AI = self.AI
        return bool(AI["streaming"] and AI.get("strom_hier", True))

    def strom_woanders(self):
        """Läuft eine Antwort in einem anderen Gespräch? -> ihr Puffer oder None."""
        AI = self.AI
        if AI["streaming"] and not AI.get("strom_hier", True):
            return AI.get("strom_puffer")
        return None

    def strom_gid(self):
        """Gespräch der laufenden Antwort (None: keine, oder noch neu)."""
        AI = self.AI
        if not AI["streaming"]:
            return None
        return AI.get("gid") if AI.get("strom_hier", True) else (AI.get("strom_puffer") or {}).get("gid")

    def strom_titel(self):
        p = self.strom_woanders()
        t = " ".join(str((p or {}).get("titel") or "").split())
        return t or "das andere gespräch"

    def warte_text(self):
        """Hinweis, wenn Sasha woanders senden will, solange sie antwortet."""
        return "warte, „%s“ antwortet noch" % self.strom_titel()

    def markiert(self, eintraege):
        """Gesprächsliste für Leiste/Liste: „…" am Gespräch, in dem die
        Antwort im Hintergrund läuft; ● wo sie fertig wurde oder etwas
        fragt — nie verschluckt. -> neue Liste (Kopien, wo markiert)."""
        AI = self.AI
        p = self.strom_woanders()
        laeuft = p.get("gid") if p else None
        fragt = bool(p and p.get("perm"))
        ungesehen = AI.get("ungesehen") or set()
        raus = []
        for e in eintraege:
            gid = e.get("id")
            if gid and (gid in ungesehen or gid == laeuft):
                e = dict(e, laeuft=(gid == laeuft and not fragt),
                         ungelesen=e.get("ungelesen") or gid in ungesehen
                         or (gid == laeuft and fragt))
            raus.append(e)
        return raus

    # ── Weg- und zurückwechseln (unter AI_LOCK) ────────────────────────
    def strom_wegstellen(self):
        """Das offene Gespräch ist das der laufenden Antwort, Sasha geht
        weg: seine Ansicht in den Puffer, AI für das nächste frei."""
        AI = self.AI
        AI["strom_puffer"] = {k: AI.get(k) for k in ANSICHT}
        AI["strom_hier"] = False
        AI["answer"], AI["perm"] = None, None
        AI["reflect"], AI["denken"] = "", ""
        AI["denk_t0"], AI["denk_ende"] = None, None
        AI.pop("pruefung", None)
        AI.pop("antwort_live", None)
        AI.pop("abbruch_live", None)
        AI.pop("warnungen", None)
        AI.pop("wechsel", None)

    def strom_zurueckholen(self):
        """Sasha kommt ins Gespräch der laufenden Antwort zurück: der Puffer
        wird wieder die Ansicht — mit allem, was inzwischen einlief."""
        AI = self.AI
        p = AI.pop("strom_puffer", None) or {}
        for k in ANSICHT:
            if k in p:
                AI[k] = p[k]
        AI["strom_hier"] = True
        AI["scroll"] = 0
        AI.setdefault("ungesehen", set()).discard(AI.get("gid"))

    # ── Ende und Wächter ───────────────────────────────────────────────
    def strom_aus(self, nachladen=False):
        """Der Strom ist vorbei, egal wie (äußeres finally von ai_stream):
        Flag aus, Puffer weg. Wirft nie. nachladen: der Abschluss ist
        schiefgegangen → den Verlauf frisch vom Server holen."""
        AI, AI_LOCK = self.AI, self.AI_LOCK
        aktiv_setzen = None
        try:
            with AI_LOCK:
                p = AI.pop("strom_puffer", None)
                woanders = not AI.get("strom_hier", True)
                if woanders and p is not None:
                    # Fertig im Hintergrund: ● an seinem Gespräch, bis Sasha
                    # es öffnet (das Backend hat es schon „gelesen" gesetzt).
                    if p.get("gid"):
                        AI.setdefault("ungesehen", set()).add(p["gid"])
                    if p.get("perm"):
                        AI["msg"] = "„%s“ hat auf eine antwort gewartet — vorbei" % (
                            " ".join(str(p.get("titel") or "").split()) or "gespräch")
                # Während der Antwort wurde nur angeschaut, nicht beim
                # Backend gewechselt (siehe chat_gespraeche.gespraech_oeffnen):
                # jetzt nachholen, damit das nächste Senden dort ankommt.
                if AI.pop("aktiv_nachholen", False) and woanders:
                    aktiv_setzen = AI.get("gid")
        except Exception:
            pass
        if aktiv_setzen:
            try:
                api_call("/api/gespraeche/aktiv", "POST", {"id": aktiv_setzen})
            except Exception:              # strom_aus wirft nie (s. o.)
                pass
        with AI_LOCK:
            AI["strom_hier"] = True
            AI["strom_thread"] = None
            AI["streaming"] = False
        if nachladen:
            threading.Thread(target=self.verlauf_laden, args=(self.AI.get("gid"),),
                             daemon=True).start()

    def waechter(self):
        """Haupt-Loop, jedes Bild: AI["streaming"] an, aber kein Strom-Thread
        lebt mehr → die Anzeige hing. Zurücksetzen, sagen, neu laden.
        -> True, wenn zurückgesetzt wurde."""
        AI, AI_LOCK = self.AI, self.AI_LOCK
        with AI_LOCK:
            if not AI["streaming"]:
                return False
            t = AI.get("strom_thread")
            if t is not None and (t.ident is None or t.is_alive()):
                return False                  # läuft noch (oder startet gerade)
            AI["answer"], AI["perm"], AI["reflect"] = None, None, ""
            AI["strom"] = None
            AI["msg"] = "die antwort hing in der anzeige — zurückgesetzt, verlauf neu geladen"
        self.strom_aus(nachladen=True)
        return True
