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
    return rgb ? luminance(...rgb) < 0.3 : false;
  }

  function siteHasNativeDark() {
    try {
      for (const sheet of document.styleSheets)
        for (const rule of sheet.cssRules || [])
          if (rule.media?.mediaText?.includes('prefers-color-scheme')) return true;
    } catch (_) {}
    return false;
  }

  // ── Dark mode ────────────────────────────────────────────────────────────────

  function applyDarkMode(enabled) {
    document.getElementById(DARK_STYLE_ID)?.remove();
    document.documentElement.style.removeProperty('color-scheme');
    if (!enabled) return;

    if (siteHasNativeDark()) {
      // Site has its own dark palette — just switch it
      document.documentElement.style.colorScheme = 'dark';
      return;
    }

    // Apply invert immediately so there's no flash of white
    const style = document.createElement('style');
    style.id = DARK_STYLE_ID;
    style.textContent = `
      html { filter: invert(0.9) hue-rotate(180deg) !important; background: #111 !important; }
      img, video, canvas, svg, picture, iframe, [style*="background-image"] {
        filter: invert(1) hue-rotate(180deg) !important;
      }`;
    (document.head || document.documentElement).prepend(style);

    // After page loads, remove it if the page was already dark
    const undoIfDark = () => {
      if (pageIsAlreadyDark()) {
        document.getElementById(DARK_STYLE_ID)?.remove();
        document.documentElement.style.removeProperty('color-scheme');
      }
    };
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', undoIfDark, { once: true });
    } else {
      undoIfDark();
    }
  }

  // ── Toolbar colour ───────────────────────────────────────────────────────────
  // document.head may not exist at document_start — wait for it.

  function applyToolbarColor(hex) {
    const doInsert = () => {
      let meta = document.querySelector('meta[name="theme-color"]');
      if (!hex) { meta?.remove(); return; }
      if (!meta) {
        meta = document.createElement('meta');
        meta.name = 'theme-color';
        document.head.appendChild(meta);
      }
      meta.content = hex;
    };

    if (document.head) {
      doInsert();
    } else {
      const obs = new MutationObserver(() => {
        if (document.head) { obs.disconnect(); doInsert(); }
      });
      obs.observe(document.documentElement, { childList: true });
    }
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
    if (msg.action === 'applyAll')     { applyAll(msg.settings); }
    if (msg.action === 'applySetting') { applySetting(msg.key, msg.value); }
    if (msg.action === 'getPageState') {
      const respond = () => sendResponse({ alreadyDark: pageIsAlreadyDark() });
      if (document.readyState === 'loading')
        document.addEventListener('DOMContentLoaded', respond, { once: true });
      else
        respond();
      return true;
    }
  });

  // ── Bootstrap ────────────────────────────────────────────────────────────────

  chrome.runtime.sendMessage({ action: 'getSettings' }, (s) => {
    if (s) applyAll(s);
  });

})();
