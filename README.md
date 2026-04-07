# FortiGuard Auto-Login

Silently re-authenticates your machine to a FortiGuard/FortiGate captive portal
whenever your college WiFi session expires.

## How it works

1. Every N seconds (default 60) it probes a plain-HTTP URL.
2. If a captive-portal redirect is detected, it fetches the FortiGuard login
   page, extracts the hidden `magic` token, and POSTs your credentials.
3. If login succeeds it logs the event and goes back to monitoring.

No browser required; runs entirely in the background.

---

## Quick start

```bash
# Run interactively (password prompted — keeps it out of shell history)
python3 fortiguard_login.py -u your_username@college.edu

# Specify all options
python3 fortiguard_login.py -u your_username -p 'yourpass' --interval 90

# One-shot: login once and exit
python3 fortiguard_login.py -u your_username --once

# Verbose / debug output
python3 fortiguard_login.py -u your_username -v
```

---

## Run automatically on boot (Linux systemd)

```bash
# 1. Copy the script somewhere permanent
sudo cp fortiguard_login.py /opt/

# 2. Edit the service file — set your username, password, and username for User=
#    Then copy to systemd
sudo cp fortiguard-autologin.service /etc/systemd/system/

# 3. Enable and start
sudo systemctl daemon-reload
sudo systemctl enable --now fortiguard-autologin.service

# 4. Check logs
journalctl -u fortiguard-autologin.service -f
```

> **Tip — avoid putting your password in the service file:**
> Store it in a file readable only by your user:
>
> ```bash
> echo 'YOUR_PASSWORD' > ~/.fortiguard_pass
> chmod 600 ~/.fortiguard_pass
> ```
>
> Then change the service `ExecStart` to:
> ```
> ExecStart=/bin/bash -c '/usr/bin/python3 /opt/fortiguard_login.py \
>     -u YOUR_USER -p "$(cat /home/YOU/.fortiguard_pass)" --interval 60'
> ```

---

## macOS (launchd)

Create `~/Library/LaunchAgents/com.user.fortiguard-autologin.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>             <string>com.user.fortiguard-autologin</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/usr/local/bin/fortiguard_login.py</string>
    <string>-u</string> <string>YOUR_USERNAME</string>
    <string>-p</string> <string>YOUR_PASSWORD</string>
  </array>
  <key>RunAtLoad</key>         <true/>
  <key>KeepAlive</key>         <true/>
  <key>StandardOutPath</key>   <string>/tmp/fortiguard.log</string>
  <key>StandardErrorPath</key> <string>/tmp/fortiguard.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.user.fortiguard-autologin.plist
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Login failed" repeatedly | Run with `-v` and note the portal URL. Some portals need a custom `--probe-url`. |
| Login succeeds but drops again fast | Shorten `--interval` (e.g. `30`). Some portals have a short idle timeout. |
| Script doesn't detect the portal | The portal may serve its page inline without a redirect. Run `curl -L http://captive.apple.com/` on the affected machine and inspect the output. |

---

## Requirements

Python 3.8+ — no third-party packages needed (uses only the stdlib).
