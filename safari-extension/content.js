// content.js — injected into every page at document_start.
// Handles: dark mode CSS, toolbar colour (theme-color meta), volume relay.

(function () {

  // ── Dark mode ───────────────────────────────────────────────────────────────

  const DARK_STYLE_ID = '__se_dark';

  function luminance(r, g, b) {
    // Relative luminance per WCAG formula
    const toLinear = (c) => {
      const s = c / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b);
  }

  function parseRgb(cssColor) {
    const m = cssColor.match(/(\d+),\s*(\d+),\s*(\d+)/);
    return m ? [+m[1], +m[2], +m[3]] : null;
  }

  function pageIsLight() {
    const bg = getComputedStyle(document.documentElement).backgroundColor;
    const rgb = parseRgb(bg);
    if (!rgb) return true; // assume light if we can't tell
    return luminance(...rgb) > 0.5;
  }

  function siteHasNativeDark() {
    // Check if any stylesheet contains a prefers-color-scheme: dark rule
    try {
      for (const sheet of document.styleSheets) {
        for (const rule of sheet.cssRules || []) {
          if (rule.media?.mediaText?.includes('prefers-color-scheme')) return true;
        }
      }
    } catch (_) { /* cross-origin sheet — skip */ }
    return false;
  }

  function applyDarkMode(enabled) {
    // Remove any existing dark style we injected
    document.getElementById(DARK_STYLE_ID)?.remove();
    document.documentElement.style.removeProperty('color-scheme');

    if (!enabled) return;

    if (siteHasNativeDark()) {
      // Let the site's own dark palette handle it — zero artifacts
      document.documentElement.style.colorScheme = 'dark';
    } else {
      // Invert + hue-rotate the page; un-invert images/video so they look right
      const style = document.createElement('style');
      style.id = DARK_STYLE_ID;
      style.textContent = `
        html {
          filter: invert(0.9) hue-rotate(180deg) !important;
          background: #111 !important;
        }
        img, video, canvas, svg, picture, iframe,
        [style*="background-image"] {
          filter: invert(1) hue-rotate(180deg) !important;
        }
      `;
      // Insert as early as possible
      const target = document.head || document.documentElement;
      target.prepend(style);
    }
  }

  // ── Toolbar colour ──────────────────────────────────────────────────────────

  function applyToolbarColor(hex) {
    let meta = document.querySelector('meta[name="theme-color"]');
    if (!hex) {
      meta?.remove();
      return;
    }
    if (!meta) {
      meta = document.createElement('meta');
      meta.name = 'theme-color';
      document.head?.appendChild(meta);
    }
    meta.content = hex;
  }

  // ── Volume boost relay ──────────────────────────────────────────────────────
  // inject.js runs in page context and holds the AudioContext.
  // We communicate with it via CustomEvents.

  let injected = false;

  function ensureInjected() {
    if (injected) return;
    injected = true;
    const script = document.createElement('script');
    script.src = chrome.runtime.getURL('inject.js');
    (document.head || document.documentElement).appendChild(script);
    script.onload = () => script.remove();
  }

  function applyVolume(gain) {
    if (gain !== 1.0) ensureInjected();
    window.dispatchEvent(new CustomEvent('se-set-gain', { detail: gain }));
  }

  // ── Apply all settings at once ──────────────────────────────────────────────

  function applyAll(settings) {
    applyDarkMode(settings.darkMode ?? false);
    applyToolbarColor(settings.toolbarColor ?? null);
    applyVolume(settings.volume ?? 1.0);
  }

  // ── Listen for messages from background.js ──────────────────────────────────

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.action === 'applyAll') applyAll(msg.settings);
  });

  // ── Bootstrap: fetch current settings and apply immediately ────────────────

  chrome.runtime.sendMessage({ action: 'getSettings' }, (settings) => {
    if (settings) applyAll(settings);
  });

})();
