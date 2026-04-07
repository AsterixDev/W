# College WiFi Auto-Login + Website Unblock

Your college WiFi kicks you out every few hours and blocks websites you need.
This tool fixes both — automatically. Set it up once, forget about it.

> **Want all the technical details?** See [README-alt.md](README-alt.md).

---

## What do you want to fix?

**Pick your situation:**

- **"Just stop the annoying login page"** → [Section A](#section-a--stop-the-login-page) — 5 minutes, nothing extra needed
- **"Also unblock websites"** → [Section B](#section-b--unblock-websites) — 15 minutes, requires a free server (we'll get one)

You can do both. Start with A, add B later if you want.

---

## Section A — Stop the login page

Every time the college WiFi makes you log in, this script detects it and logs you back in automatically. It also keeps sending tiny "I'm still here" pings so your session never expires — no more 4-hour countdowns.

### On your Mac

**Step 1 — Check Python is installed**

Open Terminal and run:
```bash
python3 --version
```
If you see a version number, you're good. If not, download Python from python.org.

**Step 2 — Run the script**

```bash
python3 fortiguard_login.py -u YOUR_COLLEGE_EMAIL
```

Replace `YOUR_COLLEGE_EMAIL` with your actual login. It will ask for your password — type it in (nothing will appear on screen, that's normal).

The script is now watching in the background. Every time the login page appears, it logs you in automatically.

**Step 3 — Make it start automatically when you open your Mac**

You don't want to remember to run this every time. Do this once:

1. **Open TextEdit**, then go to Format → Make Plain Text
2. **Paste this in**, replacing `YOUR_USERNAME`, `YOUR_PASSWORD`, and `YOUR_NAME` with your actual details:

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
    <string>/Users/YOUR_NAME/fortiguard_login.py</string>
    <string>-u</string> <string>YOUR_USERNAME</string>
    <string>-p</string> <string>YOUR_PASSWORD</string>
  </array>
  <key>RunAtLoad</key> <true/>
  <key>KeepAlive</key> <true/>
  <key>StandardOutPath</key> <string>/tmp/fortiguard.log</string>
  <key>StandardErrorPath</key> <string>/tmp/fortiguard.log</string>
</dict>
</plist>
```

3. **Save the file** as `com.user.fortiguard-autologin.plist` inside the folder:
   `~/Library/LaunchAgents/`
   *(Press Cmd+Shift+G in the save dialog and paste that path if you can't find it)*

4. **Activate it** by running this in Terminal:
```bash
launchctl load ~/Library/LaunchAgents/com.user.fortiguard-autologin.plist
```

That's it. It will now start itself every time you log into your Mac.

To check if it's running:
```bash
tail -f /tmp/fortiguard.log
```
You should see messages like `[INFO] Watching for FortiGuard portal`.

To stop it:
```bash
launchctl unload ~/Library/LaunchAgents/com.user.fortiguard-autologin.plist
```

---

### On your Android phone (no Mac needed)

Termux is a free app that lets your Android phone run the same script as your Mac.

**Step 1 — Install Termux**

Install it from **F-Droid** (not the Play Store — the Play Store version is outdated):
- Go to f-droid.org/packages/com.termux on your phone's browser
- Download and install the APK

**Step 2 — Set up and run**

Open Termux and paste these three commands one at a time:
```bash
pkg update && pkg install python git
```
```bash
git clone https://github.com/YOUR_USERNAME/W.git && cd W
```
```bash
python fortiguard_login.py -u YOUR_COLLEGE_EMAIL
```

**Step 3 — Keep it alive when you lock your screen**

By default Android pauses Termux when you lock your phone. Fix this:
- Run this command first: `termux-wake-lock`
- Then start the script as normal

Or: swipe down on the Termux notification → tap and hold → turn off "Pause when screen off".

---

## Section B — Unblock websites

FortiGuard blocks certain websites by category (social media, research sites, etc.). To get around this, you need to route your traffic through a server outside the college network — like sending your internet requests through a friend's house instead of the college gate.

There are two ways:

| | Option 1: VPN (WireGuard) | Option 2: Encrypted DNS |
|---|---|---|
| **Bypasses** | Everything | DNS-based blocks only (~60-70%) |
| **Needs a server?** | Yes (free) | No |
| **Works on Android?** | Yes, standalone | Yes, built into Android |
| **Setup time** | ~15 min | ~5 min |

**Not sure which to pick?** Start with Option 2 (no server needed). If sites are still blocked, do Option 1.

---

### Option 1 — VPN via WireGuard (bypasses everything)

WireGuard is a VPN app. When it's on, all your internet traffic goes through your server first — FortiGuard sees encrypted gibberish and can't block anything.

#### First: Get a free server

A server here means a computer in a data centre that's always on and has a normal internet connection. Oracle gives you one free forever — not a trial, actually free.

1. Go to **cloud.oracle.com/free** and sign up with a personal email
2. Once logged in, go to **Compute → Instances → Create Instance**
3. Change these settings:
   - **Image**: click "Change Image" → pick **Ubuntu 22.04**
   - **Shape**: click "Change Shape" → pick **VM.Standard.A1.Flex** → set 1 OCPU and 6 GB RAM
   - **SSH keys**: click "Upload public key file" → upload the file at `~/.ssh/id_rsa.pub` on your Mac
     *(If that file doesn't exist, run `ssh-keygen` in Terminal first and press Enter through all prompts)*
4. Click **Create**. Wait about 2 minutes.
5. Copy the **Public IP address** shown on the instance page.
6. Test the connection from your Mac:
   ```bash
   ssh ubuntu@YOUR_SERVER_IP
   ```
   If it connects, type `exit`. You're ready.

#### Set up WireGuard on your server

From your Mac, run this one command (it does everything automatically):
```bash
ssh ubuntu@YOUR_SERVER_IP "bash -s" < setup_wireguard_vps.sh
```

This installs WireGuard on your server and generates a **QR code** in your terminal.

> **Oracle users — one extra step:** Oracle's firewall also needs to be opened manually.
> Go to OCI Console → **Networking → Virtual Cloud Networks → your VCN → Security Lists → Default Security List → Add Ingress Rule**
> Set: Source `0.0.0.0/0`, Protocol `UDP`, Port `51820`
> The script will remind you of this when it finishes.

#### Connect your Android phone

1. Install **WireGuard** from the Play Store (free, made by the WireGuard project)
2. Open it → tap **+** → **Scan from QR code**
3. Scan the QR code that appeared in your terminal
4. Toggle the tunnel **ON**

All your Android traffic now bypasses FortiGuard. Toggle it off when you leave campus.

> If you missed the QR code, show it again with:
> ```bash
> ssh ubuntu@YOUR_SERVER_IP
> qrencode -t ansiutf8 < ~/android-wireguard.conf
> ```

#### Connect your Mac browser (via the script)

Run the script with your server details:
```bash
python3 fortiguard_login.py -u YOUR_COLLEGE_EMAIL \
  --ssh-host YOUR_SERVER_IP \
  --ssh-user ubuntu
```

This handles the portal login AND creates a private tunnel to your server. Now tell your browser to use it:

**Firefox** (easiest, no admin password needed):
1. Settings → scroll to the bottom → **Network Settings** → **Settings…**
2. Select **Manual proxy configuration**
3. Fill in: SOCKS Host = `127.0.0.1`, Port = `1080`, type = **SOCKS v5**
4. **Check** "Proxy DNS when using SOCKS v5"
5. Click OK

**Everywhere on your Mac** (requires admin password):
```bash
sudo networksetup -setsocksfirewallproxy Wi-Fi 127.0.0.1 1080
sudo networksetup -setsocksfirewallproxystate Wi-Fi on
```
Turn it off when you leave campus:
```bash
sudo networksetup -setsocksfirewallproxystate Wi-Fi off
```

#### Use Mac + Android at the same time

Add `--share-proxy` to the script command:
```bash
python3 fortiguard_login.py -u YOUR_COLLEGE_EMAIL \
  --ssh-host YOUR_SERVER_IP --ssh-user ubuntu \
  --share-proxy
```

The script will print your Mac's local IP address and exact steps for Android. On Android:
1. Settings → Wi-Fi → **tap and hold** your college network → **Modify network**
2. Expand **Advanced options**
3. Proxy → **Manual**
4. Enter the hostname and port the script printed
5. Save

---

### Option 2 — Encrypted DNS (no server, partial bypass)

Your device looks up website addresses using DNS — like checking a phone book to find a website's location. FortiGuard controls that phone book and removes entries for blocked sites.

Encrypted DNS (called DNS-over-HTTPS) uses a different, encrypted phone book that FortiGuard can't tamper with. It bypasses about 60-70% of blocks. Sites that are blocked in other ways won't be unlocked by this alone.

**On Android** — no app needed, it's built in:
1. Settings → **Network & internet → Advanced → Private DNS**
2. Select **Private DNS provider hostname**
3. Type: `1dot1dot1dot1.cloudflare-dns.com`
4. Save

Done. This stays active on any WiFi, not just college WiFi.

**On Mac** — install cloudflared first:
```bash
brew install cloudflare/cloudflare/cloudflared
```

Then run the script with `--doh`:
```bash
python3 fortiguard_login.py -u YOUR_COLLEGE_EMAIL --doh
```

One-time command to point your Mac at the local encrypted DNS (run while on college WiFi):
```bash
sudo networksetup -setdnsservers Wi-Fi 127.0.0.1
```

Revert when you leave campus:
```bash
sudo networksetup -setdnsservers Wi-Fi empty
```

---

## Is it working?

**Auto-login working?**
Just wait for the login page to appear normally. It should disappear and reconnect within a few seconds. Or check the log:
```bash
tail -f /tmp/fortiguard.log
```
Look for a line saying `Login successful`.

**VPN tunnel working?**
Open this website in your browser: **https://ipinfo.io**
- If it shows your server's IP (not a college IP) — it's working
- Or run in Terminal: `curl --socks5 127.0.0.1:1080 https://ipinfo.io`

**WireGuard on Android working?**
Open **https://ipinfo.io** in your Android browser.
The IP shown should match your server's IP, not your college's.

---

## Something went wrong?

| What's happening | What to do |
|---|---|
| "Login failed" keeps appearing | Double-check your username and password. Run with `-v` at the end of the command to see more detail. |
| Login works but the session still expires | The script couldn't find the keepalive signal on your college's portal. It will re-login when it expires — you just won't get the full 4 hours. Run with `-v` to investigate. |
| VPN tunnel is working but some sites are still blocked | A small number of blocks don't go through the tunnel if the app bypasses the proxy. Use the system-wide proxy setting, not just Firefox. |
| SSH tunnel starts but internet is slow | Your college might be throttling port 22. Try adding `--ssh-port 443` to the command (you'll also need to configure your server to accept SSH on port 443 — see README-alt.md). |
| Encrypted DNS option isn't unblocking sites | The block isn't DNS-based. You need Option 1 (WireGuard/SSH tunnel). |
| Android proxy isn't working | Make sure both your Mac and Android are on the **same WiFi network**. |

---

## All options (cheat sheet)

```
-u, --username      Your college login email (required)
-p, --password      Your password (leave this out — it will ask you securely)
-i, --interval      How often to check the connection, in seconds (default: 60)
--once              Login once and quit instead of watching continuously
--no-keepalive      Don't send keepalive pings (for testing only)
-v, --verbose       Show detailed logs of what the script is doing

-- Unblock websites via server tunnel --
--ssh-host          Your server's IP address
--ssh-user          Your server's username (usually: ubuntu)
--ssh-port          Your server's SSH port (default: 22, try 443 if slow)
--ssh-identity      Path to your SSH key file (default: ~/.ssh/id_rsa)
--socks-port        Local tunnel port (default: 1080, change if blocked)
--share-proxy       Let other devices on the same WiFi use the tunnel too

-- Encrypted DNS --
--doh               Turn on encrypted DNS via cloudflared
--doh-port          Port for the local DNS proxy (default: 5053)
```
