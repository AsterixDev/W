#!/usr/bin/env python3
"""
FortiGuard Captive Portal Auto-Login + Firewall Bypass
-------------------------------------------------------
• Monitors connectivity and automatically re-authenticates to the
  FortiGuard captive portal whenever your session expires.
• Sends periodic keepalive pings so the portal session never times out.
• Optional SSH SOCKS5 tunnel to bypass FortiGuard web filtering entirely.
• Optional DNS-over-HTTPS via cloudflared to defeat DNS-based blocks.
"""

import argparse
import http.client
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
import ssl
from typing import NamedTuple

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("fortiguard")

# ── Constants ─────────────────────────────────────────────────────────────────

# HTTP (not HTTPS) probe — captive portals can only intercept plain HTTP
PROBE_URL = "http://captive.apple.com/hotspot-detect.html"
PROBE_EXPECT = "Success"

DEFAULT_INTERVAL = 60          # seconds between connectivity checks
REQUEST_TIMEOUT = 10           # seconds per HTTP request
KEEPALIVE_DEFAULT_INTERVAL = 60  # seconds between keepalive pings


# ── Result type ───────────────────────────────────────────────────────────────

class LoginResult(NamedTuple):
    success: bool
    keepalive_url: str | None = None
    keepalive_interval: int = KEEPALIVE_DEFAULT_INTERVAL


# ── SSL helper ────────────────────────────────────────────────────────────────

def _ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


# ── Captive portal detection ──────────────────────────────────────────────────

def _no_redirect_opener() -> urllib.request.OpenerDirector:
    """Opener that does NOT follow redirects so we can detect them."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    return urllib.request.build_opener(
        NoRedirect(),
        urllib.request.HTTPSHandler(context=_ssl_ctx()),
    )


def detect_portal() -> tuple[bool, str | None]:
    """
    Returns (needs_login, portal_url).
    needs_login is True when a captive portal redirect was detected.
    """
    opener = _no_redirect_opener()
    try:
        resp = opener.open(PROBE_URL, timeout=REQUEST_TIMEOUT)
        body = resp.read(512).decode("utf-8", errors="replace")
        if PROBE_EXPECT in body:
            return False, None
        if _is_fortiguard_body(body):
            return True, resp.geturl()
        return False, None

    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            portal_url = e.headers.get("Location", "")
            log.debug("Redirect detected → %s", portal_url)
            return True, portal_url
        return False, None

    except (urllib.error.URLError, http.client.RemoteDisconnected, OSError) as e:
        log.warning("Probe failed (%s) — assuming no network yet", e)
        return False, None


def _is_fortiguard_body(html: str) -> bool:
    markers = ["fgtauth", "fortiguard", "fortigate", "FortiToken", "magic"]
    lower = html.lower()
    return any(m.lower() in lower for m in markers)


# ── FortiGuard login ──────────────────────────────────────────────────────────

def _fetch_login_page(url: str) -> tuple[str, dict[str, str], str]:
    """
    Fetch the login page.
    Returns (form_action, hidden_fields, response_html).
    """
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; fortiguard-autologin/1.0)"},
    )
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ssl_ctx()))
    with opener.open(req, timeout=REQUEST_TIMEOUT) as resp:
        html = resp.read(65536).decode("utf-8", errors="replace")
        final_url = resp.geturl()

    form_action = _parse_form_action(html, final_url)
    hidden = _parse_hidden_fields(html)
    return form_action, hidden, html


def _parse_form_action(html: str, base_url: str) -> str:
    m = re.search(r'<form[^>]+action=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if not m:
        return base_url
    return urllib.parse.urljoin(base_url, m.group(1))


def _parse_hidden_fields(html: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for m in re.finditer(r'<input[^>]+type=["\']hidden["\'][^>]*>', html, re.IGNORECASE):
        tag = m.group(0)
        name_m = re.search(r'name=["\']([^"\']+)["\']', tag, re.IGNORECASE)
        val_m = re.search(r'value=["\']([^"\']*)["\']', tag, re.IGNORECASE)
        if name_m:
            fields[name_m.group(1)] = val_m.group(1) if val_m else ""
    return fields


# ── Keepalive parsing ─────────────────────────────────────────────────────────

def _parse_keepalive_info(html: str, base_url: str) -> tuple[str | None, int]:
    """
    Parse the post-login HTML/JS for a keepalive URL and interval.

    FortiGate firmware embeds one of:
      var keepaliveURL = "https://gw/keepalive?magic=XXX";
      var magic = "XXX";   (URL constructed as base + /keepalive?magic=XXX)
      setInterval(fn, 60000);

    Returns (keepalive_url, interval_seconds).
    """
    keepalive_url: str | None = None

    # Pattern 1 — explicit keepalive URL in JS string
    m = re.search(r'["\']([^"\']*keepalive[^"\']*magic[^"\']*)["\']', html, re.IGNORECASE)
    if m:
        keepalive_url = urllib.parse.urljoin(base_url, m.group(1))

    # Pattern 2 — magic token as a JS variable, construct URL from gateway
    if not keepalive_url:
        m = re.search(r'["\']?magic["\']?\s*[=:]\s*["\']([0-9a-fA-F]+)["\']', html)
        if not m:
            # Also try hidden field value if magic wasn't in JS
            m = re.search(r'name=["\']magic["\'][^>]*value=["\']([^"\']+)["\']', html, re.IGNORECASE)
            if not m:
                m = re.search(r'value=["\']([^"\']+)["\'][^>]*name=["\']magic["\']', html, re.IGNORECASE)
        if m:
            magic = m.group(1)
            parsed = urllib.parse.urlparse(base_url)
            keepalive_url = f"{parsed.scheme}://{parsed.netloc}/keepalive?magic={magic}"

    # Extract interval from setInterval(fn, milliseconds)
    interval = KEEPALIVE_DEFAULT_INTERVAL
    m = re.search(r'setInterval\s*\([^,]+,\s*(\d+)\s*\)', html)
    if m:
        ms = int(m.group(1))
        if ms >= 1000:
            interval = max(30, ms // 1000)  # never ping faster than every 30s

    return keepalive_url, interval


# ── Keepalive sender ──────────────────────────────────────────────────────────

def _do_keepalive(url: str) -> bool:
    """Send a single keepalive GET. Returns True on HTTP 2xx."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; fortiguard-autologin/1.0)"},
    )
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ssl_ctx()))
    try:
        with opener.open(req, timeout=REQUEST_TIMEOUT) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


class KeepaliveThread(threading.Thread):
    def __init__(self, url: str, interval: int) -> None:
        super().__init__(daemon=True, name="keepalive")
        self.url = url
        self.interval = interval
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        log.info("Keepalive thread started (every %ds → %s)", self.interval, self.url)
        while not self._stop.wait(timeout=self.interval):
            ok = _do_keepalive(self.url)
            if ok:
                log.debug("Keepalive ping OK")
            else:
                log.warning("Keepalive ping failed — session may have expired")


# ── Login ─────────────────────────────────────────────────────────────────────

def do_login(portal_url: str, username: str, password: str) -> LoginResult:
    """Perform the FortiGuard login POST. Returns a LoginResult."""
    try:
        form_action, hidden, _page_html = _fetch_login_page(portal_url)
    except Exception as e:
        log.error("Could not fetch login page from %s: %s", portal_url, e)
        return LoginResult(success=False)

    payload = {**hidden, "username": username, "password": password}
    log.debug("Posting to %s with fields: %s", form_action, list(payload.keys()))

    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(
        form_action,
        data=data,
        method="POST",
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; fortiguard-autologin/1.0)",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": portal_url,
        },
    )
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ssl_ctx()))
    try:
        with opener.open(req, timeout=REQUEST_TIMEOUT) as resp:
            body = resp.read(32768).decode("utf-8", errors="replace")
            final_url = resp.geturl()
            success = (
                "loginok" in body.lower()
                or "disclaimer_accept" in body.lower()
                or _probe_success()
            )
            if success:
                ka_url, ka_interval = _parse_keepalive_info(body, final_url)
                return LoginResult(success=True, keepalive_url=ka_url, keepalive_interval=ka_interval)
            return LoginResult(success=False)

    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            loc = e.headers.get("Location", "")
            if "fgtauth" not in loc and "login" not in loc.lower():
                # Redirect away from portal → likely success
                if _probe_success():
                    # No body to parse keepalive from; caller will warn
                    return LoginResult(success=True)
        log.error("Login POST returned HTTP %s", e.code)
        return LoginResult(success=False)
    except Exception as e:
        log.error("Login POST failed: %s", e)
        return LoginResult(success=False)


def _probe_success() -> bool:
    time.sleep(2)
    needs_login, _ = detect_portal()
    return not needs_login


# ── SSH SOCKS5 tunnel ─────────────────────────────────────────────────────────

def _get_local_ip() -> str:
    """Return this machine's LAN IP (the address other devices on WiFi see)."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


class SshTunnelThread(threading.Thread):
    """
    Maintains a persistent SSH SOCKS5 tunnel.
    Restarts automatically on connection drop (acts as a lightweight autossh).

    When bind_host="0.0.0.0" the proxy is reachable from other devices on the
    same network (e.g. an Android phone configured to use this machine as proxy).
    """
    def __init__(
        self,
        user: str,
        host: str,
        port: int = 22,
        local_port: int = 1080,
        identity_file: str | None = None,
        bind_host: str = "127.0.0.1",
    ) -> None:
        super().__init__(daemon=True, name="ssh-tunnel")
        self.user = user
        self.host = host
        self.port = port
        self.local_port = local_port
        self.identity_file = identity_file
        self.bind_host = bind_host
        self._stop = threading.Event()
        self._proc: subprocess.Popen | None = None

    def stop(self) -> None:
        self._stop.set()
        if self._proc:
            self._proc.terminate()

    def _build_cmd(self) -> list[str]:
        # "bind_host:port" tells SSH which interface to listen on.
        # 127.0.0.1 → Mac only; 0.0.0.0 → whole LAN (needed for Android).
        bind_spec = f"{self.bind_host}:{self.local_port}"
        cmd = [
            "ssh",
            "-D", bind_spec,
            "-N",                              # no remote command
            "-o", "ExitOnForwardFailure=yes",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",     # drops after 90s silence
            "-o", "StrictHostKeyChecking=accept-new",
            "-p", str(self.port),
        ]
        if self.identity_file:
            cmd += ["-i", self.identity_file]
        cmd.append(f"{self.user}@{self.host}")
        return cmd

    def run(self) -> None:
        while not self._stop.is_set():
            log.info(
                "Starting SSH SOCKS5 tunnel → %s@%s:%d (listening on %s:%d)",
                self.user, self.host, self.port, self.bind_host, self.local_port,
            )
            try:
                self._proc = subprocess.Popen(
                    self._build_cmd(),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                _, err = self._proc.communicate()
                if err:
                    log.warning("SSH stderr: %s", err.decode(errors="replace").strip())
            except FileNotFoundError:
                log.error("'ssh' not found — install OpenSSH client")
                break
            except Exception as e:
                log.error("SSH tunnel error: %s", e)

            if not self._stop.is_set():
                log.info("SSH tunnel died — restarting in 10s")
                self._stop.wait(timeout=10)


def _configure_env_proxy(socks_port: int, no_proxy_host: str | None = None) -> None:
    """
    Set env-var proxy so child processes (curl, git, etc.) route through the tunnel.
    urllib.request.build_opener() does NOT inherit these, so do_login() is unaffected.
    """
    proxy = f"socks5h://127.0.0.1:{socks_port}"
    for var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
                "ALL_PROXY", "all_proxy"):
        os.environ[var] = proxy
    if no_proxy_host:
        existing = os.environ.get("no_proxy", "")
        hosts = set(filter(None, existing.split(",")))
        hosts.add(no_proxy_host)
        os.environ["no_proxy"] = ",".join(hosts)
        os.environ["NO_PROXY"] = os.environ["no_proxy"]
    log.info("Env proxy set to %s (no_proxy: %s)", proxy, os.environ.get("no_proxy", ""))


# ── cloudflared DNS-over-HTTPS ────────────────────────────────────────────────

def _start_cloudflared(port: int) -> "subprocess.Popen | None":
    if not shutil.which("cloudflared"):
        log.error(
            "cloudflared not found — install with: brew install cloudflare/cloudflare/cloudflared"
        )
        return None
    try:
        proc = subprocess.Popen(
            [
                "cloudflared", "proxy-dns",
                "--port", str(port),
                "--upstream", "https://1.1.1.1/dns-query",
                "--upstream", "https://8.8.8.8/dns-query",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        log.info(
            "cloudflared proxy-dns started (pid=%d, port=%d)\n"
            "  → To route system DNS through it run:\n"
            "      sudo networksetup -setdnsservers Wi-Fi 127.0.0.1\n"
            "  → To revert later:\n"
            "      sudo networksetup -setdnsservers Wi-Fi empty",
            proc.pid, port,
        )
        return proc
    except Exception as e:
        log.error("Could not start cloudflared: %s", e)
        return None


class CloudflaredWatchdog(threading.Thread):
    """Keeps cloudflared running; restarts it if it crashes."""
    def __init__(self, port: int = 5053) -> None:
        super().__init__(daemon=True, name="cloudflared-watchdog")
        self.port = port
        self._stop = threading.Event()
        self._proc: "subprocess.Popen | None" = None

    def stop(self) -> None:
        self._stop.set()
        if self._proc:
            self._proc.terminate()

    def run(self) -> None:
        while not self._stop.is_set():
            if self._proc is None or self._proc.poll() is not None:
                self._proc = _start_cloudflared(self.port)
                if self._proc is None:
                    break  # binary not found — no point retrying
            self._stop.wait(timeout=30)


# ── Main watch loop ───────────────────────────────────────────────────────────

def watch(
    username: str,
    password: str,
    interval: int = DEFAULT_INTERVAL,
    no_keepalive: bool = False,
    bypass_threads: list[threading.Thread] | None = None,
) -> None:
    """
    Continuously monitor connectivity and re-login whenever the captive
    portal kicks in. Manages keepalive thread lifecycle.
    """
    _keepalive_thread: KeepaliveThread | None = None
    _all_threads: list[threading.Thread] = list(bypass_threads or [])

    def _shutdown(sig, frame):
        log.info("Shutting down …")
        if _keepalive_thread:
            _keepalive_thread.stop()
        for t in _all_threads:
            if hasattr(t, "stop"):
                t.stop()  # type: ignore[attr-defined]
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    log.info("Watching for FortiGuard portal (check every %ds) …", interval)

    while True:
        needs_login, portal_url = detect_portal()

        if needs_login:
            log.warning("Captive portal detected — logging in …")

            # Stop any running keepalive before re-login
            if _keepalive_thread and _keepalive_thread.is_alive():
                _keepalive_thread.stop()
                _keepalive_thread.join(timeout=2)
                _keepalive_thread = None

            if not portal_url:
                log.warning("No redirect URL captured; will retry next cycle.")
            else:
                result = do_login(portal_url, username, password)
                if result.success:
                    log.info("Login successful.")
                    if not no_keepalive:
                        if result.keepalive_url:
                            _keepalive_thread = KeepaliveThread(
                                result.keepalive_url,
                                result.keepalive_interval,
                            )
                            _keepalive_thread.start()
                            _all_threads.append(_keepalive_thread)
                        else:
                            log.warning(
                                "No keepalive URL found in portal response. "
                                "Session may expire after the portal timeout. "
                                "Run with -v to inspect the portal HTML."
                            )
                else:
                    log.error(
                        "Login failed. Check your credentials.\n"
                        "  Portal URL: %s\n"
                        "  Run with -v for verbose output.",
                        portal_url,
                    )
        else:
            log.debug("Connected.")

        time.sleep(interval)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Auto-login to a FortiGuard/FortiGate captive portal with optional firewall bypass.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic — prompts for password
  %(prog)s -u student@college.edu

  # With SSH SOCKS5 tunnel to bypass FortiGuard web filtering
  %(prog)s -u student@college.edu --ssh-user ubuntu --ssh-host 1.2.3.4

  # Share the proxy with your Android phone too
  %(prog)s -u student@college.edu --ssh-user ubuntu --ssh-host 1.2.3.4 --share-proxy

  # With SSH tunnel using a specific key file
  %(prog)s -u student@college.edu --ssh-user ubuntu --ssh-host 1.2.3.4 \\
           --ssh-identity ~/.ssh/my_vps_key

  # DNS-over-HTTPS only (no VPS needed)
  %(prog)s -u student@college.edu --doh

  # One-shot login and exit
  %(prog)s -u student@college.edu --once
""",
    )

    # Auth
    auth = parser.add_argument_group("Authentication")
    auth.add_argument("-u", "--username", required=True, help="Portal username")
    auth.add_argument(
        "-p", "--password", default=None,
        help="Portal password (omit to be prompted securely)",
    )

    # Behaviour
    beh = parser.add_argument_group("Behaviour")
    beh.add_argument(
        "-i", "--interval", type=int, default=DEFAULT_INTERVAL, metavar="SEC",
        help=f"Seconds between connectivity checks (default: {DEFAULT_INTERVAL})",
    )
    beh.add_argument("--once", action="store_true", help="Login once and exit")
    beh.add_argument(
        "--no-keepalive", action="store_true",
        help="Disable automatic keepalive pings (useful for debugging)",
    )
    beh.add_argument(
        "--probe-url", default=PROBE_URL,
        help="URL used to detect captive portal (default: %(default)s)",
    )

    # SSH tunnel
    ssh = parser.add_argument_group(
        "SSH SOCKS5 tunnel (bypasses FortiGuard web filtering)"
    )
    ssh.add_argument("--ssh-host", metavar="HOST", help="SSH server hostname/IP")
    ssh.add_argument("--ssh-user", metavar="USER", help="SSH username")
    ssh.add_argument("--ssh-port", type=int, default=22, metavar="PORT", help="SSH port (default: 22)")
    ssh.add_argument("--ssh-identity", metavar="FILE", help="Path to SSH private key file")
    ssh.add_argument(
        "--socks-port", type=int, default=1080, metavar="PORT",
        help="Local SOCKS5 port (default: 1080)",
    )
    ssh.add_argument(
        "--share-proxy", action="store_true",
        help=(
            "Bind the SOCKS5 proxy on all interfaces (0.0.0.0) so other devices "
            "on the same WiFi (e.g. your Android phone) can use it. "
            "Point Android's WiFi proxy to this machine's IP and --socks-port."
        ),
    )

    # DoH
    doh = parser.add_argument_group(
        "DNS-over-HTTPS (bypasses DNS-based FortiGuard blocks, no VPS needed)"
    )
    doh.add_argument(
        "--doh", action="store_true",
        help="Start cloudflared proxy-dns (must be installed: brew install cloudflare/cloudflare/cloudflared)",
    )
    doh.add_argument(
        "--doh-port", type=int, default=5053, metavar="PORT",
        help="Local DoH proxy port (default: 5053)",
    )

    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    if args.verbose:
        log.setLevel(logging.DEBUG)

    global PROBE_URL
    PROBE_URL = args.probe_url

    if args.password is None:
        import getpass
        args.password = getpass.getpass(f"Password for {args.username}: ")

    # ── Start bypass threads ──────────────────────────────────────────────────

    bypass_threads: list[threading.Thread] = []

    if args.ssh_host:
        if not args.ssh_user:
            parser.error("--ssh-host requires --ssh-user")
        bind_host = "0.0.0.0" if args.share_proxy else "127.0.0.1"
        tunnel = SshTunnelThread(
            user=args.ssh_user,
            host=args.ssh_host,
            port=args.ssh_port,
            local_port=args.socks_port,
            identity_file=args.ssh_identity,
            bind_host=bind_host,
        )
        tunnel.start()
        bypass_threads.append(tunnel)
        # Give SSH a moment to establish before the first login attempt
        time.sleep(3)
        _configure_env_proxy(args.socks_port, no_proxy_host=args.ssh_host)
        if args.share_proxy:
            local_ip = _get_local_ip()
            log.info(
                "Proxy shared on LAN → SOCKS5 %s:%d\n"
                "  Android setup: WiFi → long-press your network → Modify → Advanced\n"
                "    Proxy: Manual\n"
                "    Hostname: %s\n"
                "    Port:     %d\n"
                "  For DNS bypass on Android: Settings → Network & internet\n"
                "    → Private DNS → Private DNS provider hostname\n"
                "    → enter: 1dot1dot1dot1.cloudflare-dns.com",
                local_ip, args.socks_port, local_ip, args.socks_port,
            )

    if args.doh:
        watchdog = CloudflaredWatchdog(port=args.doh_port)
        watchdog.start()
        bypass_threads.append(watchdog)

    # ── One-shot mode ─────────────────────────────────────────────────────────

    if args.once:
        needs_login, portal_url = detect_portal()
        if not needs_login:
            log.info("Already connected — nothing to do.")
            sys.exit(0)
        if not portal_url:
            log.error("Captive portal detected but no redirect URL captured.")
            sys.exit(1)
        result = do_login(portal_url, args.username, args.password)
        if result.success:
            log.info("Login successful.")
            if result.keepalive_url:
                log.info("Keepalive URL: %s (interval: %ds)", result.keepalive_url, result.keepalive_interval)
        sys.exit(0 if result.success else 1)

    # ── Watch mode ────────────────────────────────────────────────────────────

    watch(
        args.username,
        args.password,
        interval=args.interval,
        no_keepalive=args.no_keepalive,
        bypass_threads=bypass_threads,
    )


if __name__ == "__main__":
    main()
