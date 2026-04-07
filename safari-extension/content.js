// content.js — injected into every page at document_start.
// Handles: dark mode CSS, toolbar colour (theme-color meta), volume relay.

(function () {

  // ── Dark mode ───────────────────────────────────────────────────────────────

  const DARK_STYLE_ID = '__se_dark';

  function luminance(r, g, b) {
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

  function pageIsAlreadyDark() {
    const bg = getComputedStyle(document.documentElement).backgroundColor;
    const rgb = parseRgb(bg);
    if (!rgb) return false;
    return luminance(...rgb) < 0.3;
  }

  function siteHasNativeDark() {
    // Only reliable after stylesheets are loaded
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
    document.getElementById(DARK_STYLE_ID)?.remove();
    document.documentElement.style.removeProperty('color-scheme');

    if (!enabled) return;

    // Run detection after styles are loaded so we get accurate results
    const run = () => {
      // If the page is already dark, don't touch it
      if (pageIsAlreadyDark()) return;

      if (siteHasNativeDark()) {
        // Site has its own dark mode — just tell it to use dark
        document.documentElement.style.colorScheme = 'dark';
      } else {
        // No native dark mode — apply invert filter
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
        const target = document.head || document.documentElement;
        target.prepend(style);
      }
    };

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', run, { once: true });
    } else {
      run();
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

  // ── Apply individual setting (avoids overwriting unrelated settings) ─────────

  function applySetting(key, value) {
    if (key === 'darkMode')     applyDarkMode(value);
    if (key === 'toolbarColor') applyToolbarColor(value);
    if (key === 'volume')       applyVolume(value);
  }

  function applyAll(settings) {
    applyDarkMode(settings.darkMode ?? false);
    applyToolbarColor(settings.toolbarColor ?? null);
    applyVolume(settings.volume ?? 1.0);
  }

  // ── Listen for messages from background.js ──────────────────────────────────

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.action === 'applyAll')     applyAll(msg.settings);
    if (msg.action === 'applySetting') applySetting(msg.key, msg.value);
  });

  // ── Bootstrap ────────────────────────────────────────────────────────────────

  chrome.runtime.sendMessage({ action: 'getSettings' }, (settings) => {
    if (settings) applyAll(settings);
  });

})();

