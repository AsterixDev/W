#!/usr/bin/env python3
"""
FortiGuard Captive Portal Auto-Login
Monitors network connectivity and automatically re-authenticates
when the FortiGuard captive portal intercepts traffic.
"""

import argparse
import http.client
import logging
import re
import signal
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
import ssl

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

# How long to wait between connectivity checks (seconds)
DEFAULT_INTERVAL = 60

# How long before giving up on a single HTTP request (seconds)
REQUEST_TIMEOUT = 10

# ── Captive portal detection ──────────────────────────────────────────────────

def _no_redirect_opener() -> urllib.request.OpenerDirector:
    """Return an opener that does NOT follow redirects, so we can detect them."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None  # suppress redirect

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(
        NoRedirect(),
        urllib.request.HTTPSHandler(context=ctx),
    )


def detect_portal() -> tuple[bool, str | None]:
    """
    Returns (needs_login, portal_url).
    needs_login is True when a captive portal redirect was detected.
    portal_url is the redirect target (the FortiGuard login page URL).
    """
    opener = _no_redirect_opener()
    try:
        resp = opener.open(PROBE_URL, timeout=REQUEST_TIMEOUT)
        body = resp.read(512).decode("utf-8", errors="replace")
        # If we got a real response with the expected content, we're online
        if PROBE_EXPECT in body:
            return False, None
        # Unexpected body without a redirect → probably still a portal page
        # served inline (some FortiGates do this)
        if _is_fortiguard_body(body):
            # No clean redirect URL available here; try logging in via the
            # current response URL
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
    """Heuristic: does the HTML look like a FortiGuard login form?"""
    markers = ["fgtauth", "fortiguard", "fortigate", "FortiToken", "magic"]
    lower = html.lower()
    return any(m.lower() in lower for m in markers)


# ── FortiGuard login ──────────────────────────────────────────────────────────

def _fetch_login_page(url: str) -> tuple[str, dict[str, str]]:
    """
    Fetch the FortiGuard login page and return (form_action, hidden_fields).
    hidden_fields includes the 'magic' anti-CSRF token.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; fortiguard-autologin/1.0)"},
    )
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
    with opener.open(req, timeout=REQUEST_TIMEOUT) as resp:
        html = resp.read(65536).decode("utf-8", errors="replace")
        final_url = resp.geturl()

    form_action = _parse_form_action(html, final_url)
    hidden = _parse_hidden_fields(html)
    return form_action, hidden


def _parse_form_action(html: str, base_url: str) -> str:
    m = re.search(r'<form[^>]+action=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if not m:
        # Fall back: POST to the same URL
        return base_url
    action = m.group(1)
    # Resolve relative URLs
    return urllib.parse.urljoin(base_url, action)


def _parse_hidden_fields(html: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for m in re.finditer(
        r'<input[^>]+type=["\']hidden["\'][^>]*>', html, re.IGNORECASE
    ):
        tag = m.group(0)
        name_m = re.search(r'name=["\']([^"\']+)["\']', tag, re.IGNORECASE)
        val_m = re.search(r'value=["\']([^"\']*)["\']', tag, re.IGNORECASE)
        if name_m:
            fields[name_m.group(1)] = val_m.group(1) if val_m else ""
    return fields


def do_login(portal_url: str, username: str, password: str) -> bool:
    """
    Perform the FortiGuard login POST.  Returns True on apparent success.
    """
    try:
        form_action, hidden = _fetch_login_page(portal_url)
    except Exception as e:
        log.error("Could not fetch login page from %s: %s", portal_url, e)
        return False

    payload = {**hidden, "username": username, "password": password}
    log.debug("Posting to %s with fields: %s", form_action, list(payload.keys()))

    data = urllib.parse.urlencode(payload).encode()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

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
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
    try:
        with opener.open(req, timeout=REQUEST_TIMEOUT) as resp:
            body = resp.read(4096).decode("utf-8", errors="replace")
            # FortiGate typically returns "loginok" or redirects away from the
            # portal on success.
            if "loginok" in body.lower() or "disclaimer_accept" in body.lower():
                return True
            # If the probe URL now works, we succeeded
            return _probe_success()
    except urllib.error.HTTPError as e:
        # A redirect away from the portal often means success
        if e.code in (301, 302, 303, 307, 308):
            loc = e.headers.get("Location", "")
            if "fgtauth" not in loc and "login" not in loc.lower():
                return _probe_success()
        log.error("Login POST returned HTTP %s", e.code)
        return False
    except Exception as e:
        log.error("Login POST failed: %s", e)
        return False


def _probe_success() -> bool:
    """Quick connectivity probe after login attempt."""
    time.sleep(2)
    needs_login, _ = detect_portal()
    return not needs_login


# ── Main loop ─────────────────────────────────────────────────────────────────

def watch(username: str, password: str, interval: int = DEFAULT_INTERVAL) -> None:
    """
    Continuously monitor connectivity and re-login whenever the captive
    portal kicks in.
    """
    log.info("Watching for FortiGuard portal (check every %ds) …", interval)

    def _shutdown(sig, frame):
        log.info("Shutting down.")
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    while True:
        needs_login, portal_url = detect_portal()

        if needs_login:
            log.warning("Captive portal detected — logging in …")
            if portal_url:
                ok = do_login(portal_url, username, password)
                if ok:
                    log.info("Login successful.")
                else:
                    log.error(
                        "Login failed. Check your credentials or portal URL.\n"
                        "  Portal URL: %s",
                        portal_url,
                    )
            else:
                log.warning("Portal redirect URL not captured; will retry next cycle.")
        else:
            log.debug("Connected.")

        time.sleep(interval)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Auto-login to a FortiGuard/FortiGate captive portal.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive password prompt (recommended — avoids shell history)
  %(prog)s -u student@college.edu

  # All flags explicit
  %(prog)s -u student@college.edu -p MyP@ss -i 90

  # One-shot (login once and exit)
  %(prog)s -u student@college.edu --once
""",
    )
    parser.add_argument("-u", "--username", required=True, help="Portal username")
    parser.add_argument(
        "-p",
        "--password",
        default=None,
        help="Portal password (omit to be prompted securely)",
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        metavar="SECONDS",
        help=f"Seconds between connectivity checks (default: {DEFAULT_INTERVAL})",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Login once and exit instead of watching continuously",
    )
    parser.add_argument(
        "--probe-url",
        default=PROBE_URL,
        help="URL used to detect captive portal (default: %(default)s)",
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

    if args.once:
        needs_login, portal_url = detect_portal()
        if not needs_login:
            log.info("Already connected — nothing to do.")
            return
        if not portal_url:
            log.error("Captive portal detected but no redirect URL captured.")
            sys.exit(1)
        ok = do_login(portal_url, args.username, args.password)
        sys.exit(0 if ok else 1)
    else:
        watch(args.username, args.password, args.interval)


if __name__ == "__main__":
    main()
