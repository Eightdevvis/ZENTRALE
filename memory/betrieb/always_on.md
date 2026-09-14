# Always-on: der PC ist der Kern zuhause

**Entscheidung 2026-09-14.** Der ZENTRALE-PC läuft **permanent**. Er ist der
Kern, der zuhause steht — dort wird die Hardware gebunkert (GPU, Modelle,
Daten), und von unterwegs greift Sasha per **SSH / WAN** darauf zu. Der PC
geht nicht mehr aus, wenn niemand da ist.

## Was damit wegfällt

- **Wake-on-LAN vom Pi.** Es gibt nichts mehr zu wecken. Der WoL-Teil in
  `deployment.md` ist damit Geschichte (bleibt als Doku stehen, wird nicht
  mehr gebraucht).
- **Das Heimkomm-Ritual am Pi** (Autostart-xterm mit `zentrale-unlock`, das
  auf den LUKS-Prompt wartet). Der PC steht ja schon.
- **Jede Form von Suspend/Hibernate/Auto-Off am PC.** Das ist der aktuelle
  Blocker: „der PC geht dauernd schlafen" — muss hart aus (logind,
  Desktop-Power-Settings, DPMS ist Anzeige-Sache und egal).

## Was bleibt

- **Disk bleibt verschlüsselt.** Kein TPM-/Tang-Auto-Unlock, aus denselben
  Gründen wie in `sicherheit.md`. Always-on ändert nichts am Klauschutz-Modell,
  nur die Uptime.
- **Dropbear-Unlock im Initramfs bleibt stehen** — jetzt ausschließlich für
  **ungeplante Neustarts** (Stromausfall, Kernel-Update, Absturz). Dann steht
  der PC am LUKS-Prompt und muss über `:2222` aufgeschlossen werden, vom Pi
  oder von unterwegs. Details `auto_unlock.md`. Wird später angeschaut, nicht
  jetzt.

## Offen (später)

- **Wie der WAN-Zugang aussieht** (Port-Forward, Tunnel, VPN — nicht
  entschieden). Bis dahin: Hotspot + `find-pc` wie in
  `../system/topologie.md`.
- Ob der Dropbear-Unlock auch über den WAN-Weg erreichbar sein soll (sonst
  hilft bei einem Reboot in Abwesenheit nur der Pi).

## Reihenfolge jetzt

Die Verkabelung steht komplett — was fehlt, ist Nutzbarkeit. Prioritäten
(Stand 2026-09-14) stehen in `../ueberblick.md` → „Prioritäten". Kurz:
**1.** Pi↔PC-Pipe stabil (nichts schläft, nichts geht aus, KI ohne Knöpfe
erreichbar), **2.** Tutor-Kerngedanke (hängt an der Wand, merkt Anwesenheit,
spricht von sich aus), **3.** KI-Assistent (Memory-Struktur, Tool-Calls).
