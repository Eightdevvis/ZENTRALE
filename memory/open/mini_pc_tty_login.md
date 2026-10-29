# Mini-PC: log in on the text console instead of the graphical greeter

**Stand 2026-10-30:** Open. **Waits for Sasha** (two commands + reboot).
Found 29.10. while making the tablet usable as the only screen.

- **Why:** Plasma Login (the greeter) starts without a window when no monitor
  is attached at boot. Keystrokes then go nowhere, a blind login fails, sway
  never starts and the tablet cannot connect. Plugging in a display later only
  shows a cursor on black. Evidence: `journalctl` 29.10. 20:47 shows the
  greeter ready but no PAM attempt for `sasha` at all.
- **Prepared:** `~/.bash_profile` on the mini runs `exec sway` after a login on
  tty1 (not over SSH, not inside sway). Backup: `~/.bash_profile.before-tty-login`.
  The Bluetooth keyboard is paired + trusted, `bluetooth` and `getty@tty1` are
  enabled.
- **To do (Sasha):** disable the `plasmalogin` service, reboot, then type user
  name + password blind on the keyboard and open AVNC on the tablet.
- **Trap:** the console uses a US layout — y/z, umlauts and symbols in the
  password sit where a US keyboard has them.
- **Undo:** enable `plasmalogin` again and reboot.
- Rejected by Sasha: auto-login. Alternatives if the console route fails:
  log in from the tablet via SSH key, or auto-login + immediate lock screen.
