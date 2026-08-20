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
- **`$mod+z` ruft ein Skript, keine i3-Regel** — `scripts/zentrale-fenster`.
  Eine Taste muss hier drei Fälle abdecken: sichtbar → weglegen, weggelegt →
  holen, gar nicht da → starten.

> **Die Korrektur vom 20.08.2026.** Die erste Fassung war eine reine i3-Regel:
> `for_window … move scratchpad` plus `bindsym $mod+z … scratchpad show`. Das
> lief einmal sauber und ging dann kaputt — Sasha: *„wenn ich modz drücke
> flackert das fenster aber schließt sich nicht"*, und die Anwesenheits-Anzeige
> behauptete, er arbeite woanders, während er direkt auf ZENTRALE schaute.
> **Beides derselbe Grund:** das Fenster hing im Scratchpad-Ast, obwohl es vor
> ihm stand.
>
> Zwei Ursachen, beide im Werkzeug:
> 1. **`for_window` feuert nach.** i3 wertet die Regeln nicht nur beim
>    Erscheinen eines Fensters aus, sondern erneut bei Fenster-Ereignissen. Eine
>    Regel mit `move scratchpad` darin kann das Fenster also jederzeit wieder
>    wegziehen. In der Regel steht jetzt nur noch, was gefahrlos wiederholbar
>    ist: schwebend, Größe, Mitte.
> 2. **`scratchpad show` legt nicht immer weg.** Ist das Fenster auf einem
>    *anderen* Workspace sichtbar, holt der Befehl es herüber. Zweimal drücken
>    schließt dann nichts, es wandert nur.
>
> Der Zustand steht deshalb explizit im Skript, statt sich aus zwei i3-Regeln zu
> ergeben, die einander widersprechen können. Nebeneffekt, der Sashas Vorgabe
> erst erfüllt: das Fenster geht beim Anmelden **sichtbar** auf — „default
> offen" statt versteckt.

> **Und die Folgekorrektur, gleicher Tag:** *„jetzt klebt es links oben in der
> ecke!"* — `move position center` zentriert auf den **Koordinatenursprung**,
> nicht auf den Bildschirm. Gemessen: `x=-643, y=-390` bei 1440×900, das Fenster
> stand also mit seiner Mitte in der Ecke. Das war die ganze Zeit falsch; sichtbar
> wurde es erst, als `move scratchpad` wegfiel — **das Einblenden hatte die Lage
> selbst gesetzt und den Fehler verdeckt.**
>
> Richtig ist `move absolute position center`, und zwar als **eigener Befehl**:
> in einer Kette mit `resize set … ppt` rechnet i3 die Mitte noch mit der alten
> Größe und setzt das Fenster an den Rand (gemessen: `x=0` statt `x=357`).
>
> Beides liegt jetzt im Skript, nicht in der i3-Regel — eine `for_window`-Regel
> läuft zu einem Zeitpunkt, an dem das Fenster noch keinen Bildschirm kennt.
> `starten()` wartet, bis es wirklich da ist, und platziert dann: **89 % Breite,
> 86 % Höhe, mittig** — fast der ganze Schirm mit einem Rand drumherum.
> Nachgemessen auf 1440×900: 1286×781 mit 77 px Rand seitlich, 60 px oben und
> unten.
>
> Der Zwischenstand 50 %/75 % (die Proportionen, die i3 einem frischen
> Scratchpad-Fenster gibt) war falsch: *„kleiner und vertikal gequetschter als
> vorher"*. Ein Dashboard mit acht Kästen nebeneinander braucht die Breite.
> Prozent statt Pixel, damit der PC-Bildschirm dasselbe Verhältnis ergibt und
> nicht eine Briefmarke in der Mitte.
>
> In der i3-Regel steht nur noch `floating enable`, und das Skript setzt es
> zusätzlich selbst: so hängt das Aussehen nicht daran, dass die Konfiguration
> eingebunden ist.

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
Es verlinkt die Unit **und den Fenster-Umschalter nach `~/.local/bin`**
(Symlinks statt Kopien, damit ein `git pull` sie mitzieht) und hängt eine
`include`-Zeile an die i3-Konfiguration, mit Sicherung daneben. Ohne den
Umschalter im PATH findet `$mod+z` nichts — `--status` sagt das ausdrücklich.

**Es weigert sich aus einem git-Worktree.** Dienst und `include` zeigen auf den
Repo-Pfad; aus einer Arbeitskopie heraus zeigten beide auf einen Ordner, den es
bald nicht mehr gibt — und ein toter `include` fällt erst beim nächsten
Anmelden auf, wenn niemand mehr an den Worktree denkt.

Nach dem Einrichten fehlen zwei Handgriffe, die Sasha selbst macht: i3 neu
laden, und den Kern-Dienst einmal starten.
