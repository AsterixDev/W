# FortiGuard Auto-Login + Firewall Bypass

Silently handles your college FortiGuard WiFi so you can stop thinking about it:

1. **Auto-login** — detects when the captive portal kicks in and logs you back in automatically
2. **Keepalive** — sends periodic pings to the portal so your session *never* expires (no more 4-hour countdowns)
3. **SSH tunnel** — routes your browser traffic through an external server, bypassing FortiGuard web filtering entirely
4. **DNS-over-HTTPS** — encrypts DNS queries via cloudflared to defeat DNS-based blocks (no external server needed)

**Requirements:** Python 3.10+, no third-party packages.

---

## Quick start

```bash
# Runs indefinitely — prompts for password (safer than passing it on the command line)
python3 fortiguard_login.py -u your_username@college.edu

# All flags
python3 fortiguard_login.py -u your_username -p 'yourpass' --interval 90

# One-shot: login once and exit
python3 fortiguard_login.py -u your_username --once

# Verbose output (shows keepalive pings, portal HTML, etc.)
python3 fortiguard_login.py -u your_username -v
```

---

## Bypass FortiGuard web filtering

FortiGuard blocks websites by category (social media, gaming, VPNs, etc.).
Two options to defeat this — pick based on what you have available.

---

### Option A — SSH SOCKS5 tunnel (best, bypasses everything)

**What it does:** Creates a tunnel between your machine and an external server. All your browser traffic exits from *that* server's IP, completely invisible to FortiGuard — bypasses both DNS filtering and HTTPS inspection.

**Step 1 — Get a free VPS (Oracle Cloud Free Tier)**

A VPS is just a Linux server in a data centre you control. Oracle's free tier is genuinely free forever (not a trial):

1. Sign up at **cloud.oracle.com/free** — use a personal email
2. Create an instance: Compute → Instances → Create Instance
   - Image: **Ubuntu 22.04**
   - Shape: **VM.Standard.A1.Flex** (ARM, free tier) — set 1 OCPU, 6 GB RAM
   - Under "Add SSH keys": upload your existing public key (`~/.ssh/id_rsa.pub`) or generate a new one
3. Once running, note the **Public IP address**
4. Allow SSH inbound in the Security List (port 22 is open by default)
5. Test: `ssh ubuntu@<your-vps-ip>` — if it connects, you're good

> **Alternative if you have a Raspberry Pi at home:** Use it as the "VPS".
> You'll need to enable SSH on the Pi and set up port forwarding (port 22) on your home router,
> plus a free Dynamic DNS service (e.g. duckdns.org) since your home IP changes.
> This is free but more involved to set up.

**Step 2 — Run the script with your VPS**

```bash
python3 fortiguard_login.py \
  -u your_username@college.edu \
  --ssh-host <your-vps-ip> \
  --ssh-user ubuntu \
  --ssh-identity ~/.ssh/id_rsa    # omit if using default key
```

This:
- Logs into the FortiGuard portal and keeps the session alive
- Maintains an SSH SOCKS5 proxy on `localhost:1080`
- Auto-restarts the tunnel if it drops

**Step 3 — Point your browser at the proxy**

The tunnel is running on port 1080, but your browser needs to be told to use it.

*Firefox (recommended — no root needed):*
1. Settings → General → scroll to Network Settings → Settings…
2. Manual proxy configuration
3. SOCKS Host: `127.0.0.1`, Port: `1080`, SOCKS v5
4. Check **"Proxy DNS when using SOCKS v5"** ← important, this also defeats DNS filtering
5. OK

*System-wide on macOS (affects all apps):*
```bash
# Enable (run once)
sudo networksetup -setsocksfirewallproxy Wi-Fi 127.0.0.1 1080
sudo networksetup -setsocksfirewallproxystate Wi-Fi on

# Disable when not on college WiFi
sudo networksetup -setsocksfirewallproxystate Wi-Fi off
```

**Verify it's working:**
```bash
curl --socks5 127.0.0.1:1080 https://ipinfo.io
# Should show your VPS's IP, not your college's IP
```

---

### Option B — DNS-over-HTTPS via cloudflared (no VPS needed, partial bypass)

Defeats blocks that rely on DNS filtering (~60-70% of FortiGuard blocks). Does **not** bypass HTTPS deep-packet inspection.

**Install cloudflared:**
```bash
brew install cloudflare/cloudflare/cloudflared
```

**Run with DoH enabled:**
```bash
python3 fortiguard_login.py -u your_username --doh
```

**Point macOS DNS at the local proxy** (one-time, run while on college WiFi):
```bash
sudo networksetup -setdnsservers Wi-Fi 127.0.0.1
```

Revert when you leave:
```bash
sudo networksetup -setdnsservers Wi-Fi empty
```

---

## Run automatically at login (macOS launchd)

Create `~/Library/LaunchAgents/com.user.fortiguard-autologin.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.user.fortiguard-autologin</string>

  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/Users/YOU/fortiguard_login.py</string>
    <string>-u</string>  <string>YOUR_USERNAME</string>
    <string>-p</string>  <string>YOUR_PASSWORD</string>
    <!-- Optional: add SSH tunnel flags -->
    <!-- <string>--ssh-user</string>  <string>ubuntu</string>   -->
    <!-- <string>--ssh-host</string>  <string>1.2.3.4</string>  -->
    <!-- <string>--ssh-identity</string>  <string>/Users/YOU/.ssh/id_rsa</string>  -->
  </array>

  <key>RunAtLoad</key>   <true/>
  <key>KeepAlive</key>   <true/>

  <key>StandardOutPath</key>  <string>/tmp/fortiguard.log</string>
  <key>StandardErrorPath</key><string>/tmp/fortiguard.log</string>
</dict>
</plist>
```

```bash
# Load the agent (starts now and on every future login)
launchctl load ~/Library/LaunchAgents/com.user.fortiguard-autologin.plist

# View logs
tail -f /tmp/fortiguard.log

# Stop
launchctl unload ~/Library/LaunchAgents/com.user.fortiguard-autologin.plist
```

> **Tip — avoid putting your password in the plist:**
> Store it in a file readable only by you:
> ```bash
> echo 'YOUR_PASSWORD' > ~/.fortiguard_pass && chmod 600 ~/.fortiguard_pass
> ```
> Then replace the `<string>YOUR_PASSWORD</string>` line with a shell wrapper:
> ```xml
> <key>ProgramArguments</key>
> <array>
>   <string>/bin/bash</string>
>   <string>-c</string>
>   <string>/usr/bin/python3 /Users/YOU/fortiguard_login.py -u USER -p "$(cat ~/.fortiguard_pass)"</string>
> </array>
> ```

---

## All flags

```
Authentication:
  -u, --username      Portal username (required)
  -p, --password      Portal password (prompted if omitted)

Behaviour:
  -i, --interval SEC  Seconds between connectivity checks (default: 60)
  --once              Login once and exit
  --no-keepalive      Disable keepalive pings (for debugging)
  --probe-url URL     URL used to detect captive portal
  -v, --verbose       Verbose / debug output

SSH SOCKS5 tunnel:
  --ssh-host HOST     SSH server hostname or IP
  --ssh-user USER     SSH username
  --ssh-port PORT     SSH port (default: 22)
  --ssh-identity FILE Path to SSH private key
  --socks-port PORT   Local SOCKS5 port (default: 1080)

DNS-over-HTTPS:
  --doh               Start cloudflared proxy-dns
  --doh-port PORT     Local DoH proxy port (default: 5053)
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Login failed" repeatedly | Run with `-v`. Check the portal URL is reachable. |
| Login succeeds but keepalive not found | Run with `-v` — the script will log the portal response. Some older firmware doesn't embed the keepalive URL; the session will auto-renew on expiry instead. |
| SSH tunnel starts but browsing is slow | Try `--socks-port 1081` in case 1080 is blocked by the college firewall. Port 443 usually works: `--ssh-port 443` (must configure sshd on VPS to also listen on 443). |
| cloudflared starts but blocked sites still don't load | The block is not DNS-based. You need the SSH tunnel (Option A). |
| curl/git not going through tunnel | Set `ALL_PROXY=socks5h://127.0.0.1:1080` in your shell profile. |
