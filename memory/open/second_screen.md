# Tablet as second screen for the mini-PC: state and leftovers

**Stand 2026-10-30:** Works (tested 29.10.: image, touch, keyboard via
Tailscale). Leftovers below.

- **How it runs:** `/usr/local/bin/second-screen on|off|status` on the mini
  creates a sway headless output (1280×800, scale 1, right of the real display)
  and serves it with wayvnc on port 5900 (user unit `second-screen-vnc`).
  Autostart: last line of `~/.config/sway/config` (`exec second-screen on`),
  backup `config.before-second-screen`.
- **Security:** VNC has no password. firewalld opens it only because
  `tailscale0` is in zone `trusted`; zone `public` (Wi-Fi) stays closed.
  Never open 5900 in `public`.
- **Tablet:** Tailscale (always-on VPN, battery unrestricted) + AVNC with
  auto-connect, address `100.116.117.3:5900`.
- **Script source lives only on the mini.** Not in any repo yet — decide where
  it belongs (e.g. `deploy/` here). Copy of the source is at the end of this file.
- **Not done:** button in the ZENTRALE app (phone/tablet) that opens the
  second-screen mode directly (Sasha's idea, 28.10.).
- **AR glasses:** when plugged in after login, run `second-screen on` once so
  the tablet output moves next to them.
- Depends on [mini_pc_tty_login.md](mini_pc_tty_login.md) for use without a
  monitor and on [mini_pc_network.md](mini_pc_network.md) without the laptop.

## Script source (29.10.2026)

```bash
#!/usr/bin/env bash
# second-screen — use a tablet as a second display under sway.
#   on      create a virtual output right of the main display and serve it via VNC
#   off     stop VNC, remove the virtual output
#   status  show what is running and which addresses the tablet can connect to
# Size can be overridden: SECOND_SCREEN_SIZE=1600x1000 second-screen on
# VNC is only reachable where the firewall opens port 5900
# (Tailscale interface in zone "trusted"), never on public/university Wi-Fi.
set -euo pipefail

SIZE="${SECOND_SCREEN_SIZE:-1280x800}"
PORT=5900
UNIT=second-screen-vnc
runtime="/run/user/$(id -u)"

# When called over SSH the sway variables are missing → take them from the runtime dir.
export SWAYSOCK="${SWAYSOCK:-$(ls "$runtime"/sway-ipc.*.sock 2>/dev/null | head -1)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-$(ls "$runtime" | grep -E '^wayland-[0-9]+$' | head -1)}"
[[ -n "$SWAYSOCK" ]] || { echo "second-screen: sway is not running" >&2; exit 1; }

virtual_output() { swaymsg -t get_outputs -r | jq -r '.[] | select(.name|startswith("HEADLESS")) | .name' | head -1; }

case "${1:-status}" in
  on)
    name=$(virtual_output)
    if [[ -z "$name" ]]; then swaymsg create_output >/dev/null; name=$(virtual_output); fi
    # place right of the real display (no monitor attached: at 0)
    x=$(swaymsg -t get_outputs -r | jq '[.[] | select(.active and (.name|startswith("HEADLESS")|not)) | .rect.x + .rect.width] | max // 0')
    swaymsg output "$name" mode "$SIZE" scale 1 position "$x" 0 >/dev/null
    systemctl --user stop "$UNIT" 2>/dev/null || true
    systemctl --user reset-failed "$UNIT" 2>/dev/null || true
    systemd-run --user --quiet --unit="$UNIT" \
      --setenv=WAYLAND_DISPLAY="$WAYLAND_DISPLAY" --setenv=SWAYSOCK="$SWAYSOCK" \
      wayvnc -o "$name" 0.0.0.0 "$PORT"
    sleep 1
    "$0" status
    ;;
  off)
    systemctl --user stop "$UNIT" 2>/dev/null || true
    name=$(virtual_output)
    [[ -n "$name" ]] && swaymsg output "$name" unplug >/dev/null
    echo "second-screen: off"
    ;;
  status)
    name=$(virtual_output)
    echo "virtual output: ${name:-none}"
    echo "VNC: $(systemctl --user is-active "$UNIT" 2>/dev/null || true)"
    echo "Connect the tablet (AVNC) to port $PORT at:"
    ip=$(ip -4 -o addr show tailscale0 2>/dev/null | awk '{print $4}' | cut -d/ -f1 || true)
    echo "  tailscale0  ${ip:-not connected}"
    ;;
  *) echo "usage: second-screen on|off|status" >&2; exit 2 ;;
esac
```
