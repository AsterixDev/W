// popup.js

(function () {

  const darkToggle  = document.getElementById('dark-toggle');
  const darkRow     = document.getElementById('dark-row');
  const darkHint    = document.getElementById('dark-hint');
  const swatchBtns  = document.querySelectorAll('#swatches .swatch');
  const colorPicker = document.getElementById('color-picker');
  const hexInput    = document.getElementById('hex-input');
  const volSlider   = document.getElementById('vol-slider');
  const volValue    = document.getElementById('vol-value');
  const volWarning  = document.getElementById('vol-warning');

  let currentHost = null;

  // ── Helpers ──────────────────────────────────────────────────────────────────

  function normaliseHex(raw) {
    const s = raw.trim().replace(/^#/, '');
    if (/^[0-9a-fA-F]{6}$/.test(s)) return `#${s.toLowerCase()}`;
    if (/^[0-9a-fA-F]{3}$/.test(s)) return `#${s[0]}${s[0]}${s[1]}${s[1]}${s[2]}${s[2]}`;
    return null;
  }

  function saveSetting(key, value, extra = {}) {
    chrome.runtime.sendMessage({ action: 'setSetting', key, value, ...extra });
  }

  // ── Dark mode ─────────────────────────────────────────────────────────────────

  function setDarkToggleDisabled(disabled, hint) {
    darkToggle.disabled = disabled;
    darkRow.classList.toggle('disabled', disabled);
    darkHint.textContent = hint || '';
    darkHint.style.display = hint ? 'block' : 'none';
  }

  darkToggle.addEventListener('change', () => {
    if (!currentHost) return;
    saveSetting('darkMode', darkToggle.checked, { host: currentHost });
  });

  // ── Toolbar colour ────────────────────────────────────────────────────────────

  function selectSwatch(hex) {
    swatchBtns.forEach((b) => b.classList.toggle('active', b.dataset.color === hex));
    if (hex) { colorPicker.value = hex; hexInput.value = hex; }
    else hexInput.value = '';
    saveSetting('toolbarColor', hex || null);
  }

  swatchBtns.forEach((b) => b.addEventListener('click', () => selectSwatch(b.dataset.color)));

  colorPicker.addEventListener('input', () => {
    hexInput.value = colorPicker.value;
    swatchBtns.forEach((b) => b.classList.remove('active'));
    saveSetting('toolbarColor', colorPicker.value);
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

  // ── Volume ────────────────────────────────────────────────────────────────────

  function updateVolumeUI(pct) {
    volValue.textContent = pct;
    volWarning.classList.toggle('visible', pct > 500);
    const ratio = (pct - 100) / (1000 - 100);
    volSlider.style.setProperty('--slider-pct', `${(ratio * 100).toFixed(1)}%`);
  }

  volSlider.addEventListener('input', () => {
    const pct = parseInt(volSlider.value, 10);
    updateVolumeUI(pct);
    saveSetting('volume', pct / 100);
  });

  // ── Bootstrap ─────────────────────────────────────────────────────────────────

  chrome.runtime.sendMessage({ action: 'getSettings' }, (settings) => {
    if (!settings) return;
    currentHost = settings.host || null;

    // Volume
    const pct = Math.round((settings.volume ?? 1.0) * 100);
    volSlider.value = pct;
    updateVolumeUI(pct);

    // Toolbar colour
    const hex = settings.toolbarColor || '';
    if (hex) {
      colorPicker.value = hex;
      hexInput.value = hex;
      swatchBtns.forEach((b) => b.classList.toggle('active', b.dataset.color === hex));
    }

    // Dark mode — check if page is already dark first
    chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
      chrome.tabs.sendMessage(tab.id, { action: 'getPageState' }, (state) => {
        if (state?.alreadyDark) {
          darkToggle.checked = false;
          setDarkToggleDisabled(true, 'Site is already dark');
        } else {
          darkToggle.checked = !!settings.darkMode;
          setDarkToggleDisabled(false);
        }
      });
    });
  });

})();
