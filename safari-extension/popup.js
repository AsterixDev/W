// popup.js — drives all three sections of the popup UI.

(function () {

  // ── Helpers ─────────────────────────────────────────────────────────────────

  function saveSetting(key, value) {
    chrome.runtime.sendMessage({ action: 'setSetting', key, value });
  }

  // Validate & normalise a hex colour string → '#rrggbb' or null
  function normaliseHex(raw) {
    const s = raw.trim().replace(/^#/, '');
    if (/^[0-9a-fA-F]{6}$/.test(s)) return `#${s.toLowerCase()}`;
    if (/^[0-9a-fA-F]{3}$/.test(s)) {
      return `#${s[0]}${s[0]}${s[1]}${s[1]}${s[2]}${s[2]}`;
    }
    return null;
  }

  // ── Elements ─────────────────────────────────────────────────────────────────

  const darkToggle  = document.getElementById('dark-toggle');
  const swatchBtns  = document.querySelectorAll('#swatches .swatch');
  const colorPicker = document.getElementById('color-picker');
  const hexInput    = document.getElementById('hex-input');
  const volSlider   = document.getElementById('vol-slider');
  const volValue    = document.getElementById('vol-value');
  const volWarning  = document.getElementById('vol-warning');

  // ── Dark Mode ─────────────────────────────────────────────────────────────────

  darkToggle.addEventListener('change', () => {
    saveSetting('darkMode', darkToggle.checked);
  });

  // ── Toolbar Colour ────────────────────────────────────────────────────────────

  function selectSwatch(hex) {
    swatchBtns.forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.color === hex);
    });
    if (hex) {
      colorPicker.value = hex;
      hexInput.value    = hex;
    } else {
      hexInput.value = '';
    }
    saveSetting('toolbarColor', hex || null);
  }

  swatchBtns.forEach((btn) => {
    btn.addEventListener('click', () => selectSwatch(btn.dataset.color));
  });

  colorPicker.addEventListener('input', () => {
    const hex = colorPicker.value;
    hexInput.value = hex;
    swatchBtns.forEach((b) => b.classList.remove('active'));
    saveSetting('toolbarColor', hex);
  });

  hexInput.addEventListener('input', () => {
    const hex = normaliseHex(hexInput.value);
    if (!hex) return;
    colorPicker.value = hex;
    swatchBtns.forEach((b) => b.classList.remove('active'));
    saveSetting('toolbarColor', hex);
  });

  hexInput.addEventListener('blur', () => {
    const hex = normaliseHex(hexInput.value);
    hexInput.value = hex ?? '';
    if (hex) saveSetting('toolbarColor', hex);
  });

  // ── Volume Boost ──────────────────────────────────────────────────────────────

  function updateVolumeUI(pct) {
    volValue.textContent = pct;
    volWarning.classList.toggle('visible', pct > 500);
    // Update filled-track CSS variable
    const ratio = (pct - 100) / (1000 - 100); // 0–1
    volSlider.style.setProperty('--slider-pct', `${(ratio * 100).toFixed(1)}%`);
  }

  volSlider.addEventListener('input', () => {
    const pct = parseInt(volSlider.value, 10);
    updateVolumeUI(pct);
    saveSetting('volume', pct / 100);
  });

  // ── Bootstrap: load saved settings into UI ───────────────────────────────────

  chrome.runtime.sendMessage({ action: 'getSettings' }, (settings) => {
    if (!settings) return;

    // Dark mode
    darkToggle.checked = !!settings.darkMode;

    // Toolbar colour
    const hex = settings.toolbarColor || '';
    if (hex) {
      colorPicker.value = hex;
      hexInput.value    = hex;
      swatchBtns.forEach((btn) => {
        btn.classList.toggle('active', btn.dataset.color === hex);
      });
    }

    // Volume
    const pct = Math.round((settings.volume ?? 1.0) * 100);
    volSlider.value = pct;
    updateVolumeUI(pct);
  });

})();
