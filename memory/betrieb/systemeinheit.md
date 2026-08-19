# ZENTRALE als Systemeinheit

`deploy/zentrale-kern.service` · `deploy/i3/zentrale.conf` ·
`scripts/zentrale-systemeinheit` · `core/melden.py`

## Warum

Sasha, 19.08.2026:

> *„ich will dass zentrale nich mehr nur nen terminal is das ich ansteuer, ich
> will dass wir es zur systemeinheit machen. zentrale autostartet mit der
> maschine und ist default offen. mit cmd+z kann ich immer auf sie wechseln
> egal was ich sonst grad mache."*

Das ist die Konsequenz aus dem Takt. Seit `core/takt.py` kann ZENTRALE von
sich aus sprechen — nur lief das Backend als **Kind der TUI**: `zentrale-tui`
startete beides, und `q` nahm beides mit. Damit war jede Initiative an ein
offenes Fenster gebunden. Sie konnte nur mahnen, wenn ohnehin jemand
hinschaute, also genau dann, wenn man sie am wenigsten braucht.

## Die drei Teile

**1. Der Kern läuft immer** — `zentrale-kern.service`, ein **Benutzer**-Dienst
(kein System-Dienst): ZENTRALE meldet sich auf dem Desktop und liest das Theme
aus `~/.config/zentrale/`, sie gehört also zur Sitzung. Eingehängt an
`default.target`, weil `graphical-session.target` unter i3 nicht zuverlässig
erreicht wird — dieselbe Kombination, die bei `zentrale-themed.service` seit
Wochen läuft.

> **Genau ein Backend pro Rechner.** `deploy/zentrale-pc.service` (System-Dienst)
> macht dasselbe; beide zusammen streiten sich um `:5000`. Der Einrichter warnt,
> wenn er den anderen aktiv findet.

**2. Das Fenster liegt im Scratchpad** — `deploy/i3/zentrale.conf`, per
`include` aus der i3-Konfiguration gezogen (i3 ≥ 4.20), damit die Regeln
versioniert im Repo liegen statt verstreut in einer Konfiguration.

- Erkannt wird über **`window_role`**, nicht über die Fensterklasse:
  xfce4-terminal vergibt für jedes Fenster dieselbe Klasse, ein Match darauf
  würde jedes beliebige Terminal ins Scratchpad ziehen.
- `--disable-server` ist nötig: xfce4-terminal läuft sonst als ein einziger
  Server-Prozess und hängt neue Fenster dort an — die Rolle ginge verloren.
- `$mod+z` ist fest an **ZENTRALEs** Fenster gebunden, nicht an „das nächste im
  Scratchpad": der Scratchpad kann mehrere Fenster halten und blättert bei
  wiederholtem Drücken durch. Ein zweiter Druck legt sie wieder weg.
- `$mod+Shift+z` startet das Fenster nach, falls es mal weg ist.

**3. `start_tui.sh` hängt sich an, statt zu killen.** Vorher hat das Skript ein
laufendes Backend „zurückgeholt", also abgeschossen und neu gestartet. Gegen
einen Dienst wäre das ein Kampf: jede TUI würde ihn killen, systemd startet ihn
neu, und der Takt-Tageszustand wäre bei jedem Fensteröffnen frisch. Jetzt gilt:
antwortet auf `:5000` etwas Gesundes, hängen wir uns dran und fassen es nicht
an — weder beim Start noch beim Beenden. `q` schließt nur noch das Fenster.
`ZENTRALE_TUI_FRESH=1` erzwingt den alten Weg (Entwicklung: die TUI soll gegen
**neuen** Backend-Code laufen).

## Die Benachrichtigung — `core/melden.py`

Ohne sie endet ihre Initiative an der Fensterkante: eine Terminerinnerung, die
man erst nach dem Termin liest, ist keine. Der Takt schickt seine Meldung
deshalb zusätzlich als Desktop-Benachrichtigung (`notify-send`).

**Nur wenn sie nicht ohnehin dasteht.** `sichtbar()` fragt i3 und liefert drei
Antworten, und die dritte ist die wichtige:

| Antwort | Bedeutung | Folge |
|---|---|---|
| `True` | Fenster offen auf einem angezeigten Workspace | **kein** Popup |
| `False` | im Scratchpad, oder auf einem verlassenen Workspace | Popup |
| `None` | kein i3, kein Fenster, i3 antwortet nicht | Popup |

`None` heißt *„weiß ich nicht"* und ist etwas anderes als `False`. Wer nicht
weiß, ob der Benutzer hinschaut, benachrichtigt ihn — eine verpasste
Erinnerung ist teurer als ein überflüssiges Popup.

**Zwei Fallen, beide auf der Maschine geprüft:**

- `window_role` steht in **`window_properties`**, nicht am Knoten selbst.
- **`visible` gibt es im Baum nicht** — nur in `get_workspaces`. Ein Blick in
  den Baum liefert `None`, und `bool(None)` hätte dauerhaft „unsichtbar"
  bedeutet: sie hätte gemeldet, während er sie ansieht. Deshalb werden beide
  Abfragen gestellt.

Als Benutzer-Dienst ist **`DISPLAY` nicht gesetzt** — `melden.py` fällt auf
`:0` zurück, die Unit setzt es zusätzlich. Ohne das fiele `notify-send` genau
dann stumm auf die Nase, wenn ZENTRALE als Systemeinheit läuft, also immer.

Abschaltbar mit `ZENTRALE_NOTIFY=0`.

## Einrichten

`scripts/zentrale-systemeinheit` — idempotent, mit `--status` und `--zurueck`.
Es verlinkt die Unit (Symlink statt Kopie, damit ein `git pull` sie mitzieht)
und hängt eine `include`-Zeile an die i3-Konfiguration, mit Sicherung daneben.

**Es weigert sich aus einem git-Worktree.** Dienst und `include` zeigen auf den
Repo-Pfad; aus einer Arbeitskopie heraus zeigten beide auf einen Ordner, den es
bald nicht mehr gibt — und ein toter `include` fällt erst beim nächsten
Anmelden auf, wenn niemand mehr an den Worktree denkt.

Nach dem Einrichten fehlen zwei Handgriffe, die Sasha selbst macht: i3 neu
laden, und den Kern-Dienst einmal starten.
