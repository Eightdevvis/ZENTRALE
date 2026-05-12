#!/usr/bin/env bash
# =============================================================================
# emergency_exit.sh
# -----------------------------------------------------------------------------
# Notaus-Skript fuer den Pi-Kiosk. Wird per XFCE-Tastenkuerzel
# Ctrl+Alt+Esc gefeuert (siehe install_xfce_autostart.sh).
#
# WAS PASSIERT:
# 1. lightdm wird gestoppt -> X-Server, xfce4-session, xfwm4, xfdesktop
#    und der Firefox-Kiosk sterben in einem Schwung. Der Pi landet auf
#    einer Konsole (TTY1).
# 2. `chvt 1` schaltet aktiv auf TTY1, damit der User sofort den
#    Login-Prompt sieht und sich nicht erst durch tote VTs klicken muss.
# 3. zentrale.service / whisper.service / tts.service laufen ABSICHTLICH
#    WEITER. Das Backend stoert nicht, und vom TTY aus kann der User
#    sie gezielt stoppen / inspizieren, ohne dass die Tastenkombi sie
#    blind plattgemacht hat.
#
# VORAUSSETZUNG:
# Passwordless sudo fuer 'systemctl stop lightdm' und 'chvt 1' fuer
# den ausfuehrenden User. Setup: scripts/install_pi_sudoers.sh.
#
# ENTSORGUNG / WIEDER ZUM KIOSK:
#   sudo systemctl start lightdm    # X + Kiosk kommen wieder hoch
# =============================================================================

set -uo pipefail

# Logging in das User-Home, damit man nachvollziehen kann ob der
# Hotkey wirklich gefeuert hat (XFCE-Shortcuts schlucken stderr).
LOG="$HOME/.zentrale_emergency.log"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] emergency_exit gefeuert" >> "$LOG"

# Erst Konsole sichtbar machen, BEVOR wir lightdm killen.
# Sonst sieht der User kurz nichts und denkt der Pi haengt.
# `-n` (non-interactive) damit sudo niemals nach Passwort fragt –
# ohne sudoers-Eintrag schlaegt das hier sofort fehl statt zu blockieren.
if ! sudo -n /usr/bin/chvt 1 2>>"$LOG"; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] chvt 1 fehlgeschlagen (sudoers?)" >> "$LOG"
fi

# Den X-Stack komplett runterfahren. lightdm raeumt alle Child-Prozesse
# der X-Session inklusive Firefox-Kiosk auf.
if ! sudo -n /bin/systemctl stop lightdm 2>>"$LOG"; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] systemctl stop lightdm fehlgeschlagen (sudoers?)" >> "$LOG"
    exit 1
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] lightdm gestoppt, Pi ist auf TTY1" >> "$LOG"
