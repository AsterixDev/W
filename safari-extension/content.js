// content.js — injected into every page at document_start.

(function () {

  const DARK_STYLE_ID = '__se_dark';

  // ── Helpers ─────────────────────────────────────────────────────────────────

  function luminance(r, g, b) {
    const toLinear = (c) => {
      const s = c / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b);
  }

  function parseRgb(css) {
    const m = css.match(/(\d+),\s*(\d+),\s*(\d+)/);
    return m ? [+m[1], +m[2], +m[3]] : null;
  }

  function pageIsAlreadyDark() {
    const bg = getComputedStyle(document.documentElement).backgroundColor;
    const rgb = parseRgb(bg);
    if (!rgb) return false;
    return luminance(...rgb) < 0.3;
  }

  function siteHasNativeDark() {
    try {
      for (const sheet of document.styleSheets) {
        for (const rule of sheet.cssRules || []) {
          if (rule.media?.mediaText?.includes('prefers-color-scheme')) return true;
        }
      }
    } catch (_) {}
    return false;
  }

  // ── Dark mode ────────────────────────────────────────────────────────────────

  function applyDarkMode(enabled) {
    document.getElementById(DARK_STYLE_ID)?.remove();
    document.documentElement.style.removeProperty('color-scheme');
    if (!enabled) return;

    const run = () => {
      if (pageIsAlreadyDark()) return; // site is already dark — leave it alone

      if (siteHasNativeDark()) {
        document.documentElement.style.colorScheme = 'dark';
      } else {
        const style = document.createElement('style');
        style.id = DARK_STYLE_ID;
        style.textContent = `
          html { filter: invert(0.9) hue-rotate(180deg) !important; background: #111 !important; }
          img, video, canvas, svg, picture, iframe, [style*="background-image"] {
            filter: invert(1) hue-rotate(180deg) !important;
          }`;
        (document.head || document.documentElement).prepend(style);
      }
    };

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', run, { once: true });
    } else {
      run();
    }
  }

  // ── Toolbar colour ───────────────────────────────────────────────────────────

  function applyToolbarColor(hex) {
    let meta = document.querySelector('meta[name="theme-color"]');
    if (!hex) { meta?.remove(); return; }
    if (!meta) {
      meta = document.createElement('meta');
      meta.name = 'theme-color';
      document.head?.appendChild(meta);
    }
    meta.content = hex;
  }

  // ── Volume boost ─────────────────────────────────────────────────────────────

  let injected = false;
  function ensureInjected() {
    if (injected) return;
    injected = true;
    const s = document.createElement('script');
    s.src = chrome.runtime.getURL('inject.js');
    (document.head || document.documentElement).appendChild(s);
    s.onload = () => s.remove();
  }
  function applyVolume(gain) {
    if (gain !== 1.0) ensureInjected();
    window.dispatchEvent(new CustomEvent('se-set-gain', { detail: gain }));
  }

  // ── Message handling ─────────────────────────────────────────────────────────

  function applyAll(s) {
    applyDarkMode(s.darkMode ?? false);
    applyToolbarColor(s.toolbarColor ?? null);
    applyVolume(s.volume ?? 1.0);
  }

  function applySetting(key, value) {
    if (key === 'darkMode')     applyDarkMode(value);
    if (key === 'toolbarColor') applyToolbarColor(value);
    if (key === 'volume')       applyVolume(value);
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg.action === 'applyAll')     applyAll(msg.settings);
    if (msg.action === 'applySetting') applySetting(msg.key, msg.value);
    if (msg.action === 'getPageState') {
      // Called by popup to check if page is already dark
      const check = () => {
        sendResponse({ alreadyDark: pageIsAlreadyDark() });
      };
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', check, { once: true });
      } else {
        check();
      }
      return true; // async
    }
  });

  // ── Bootstrap ────────────────────────────────────────────────────────────────

  chrome.runtime.sendMessage({ action: 'getSettings' }, (s) => {
    if (s) applyAll(s);
  });

})();
