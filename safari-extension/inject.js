// inject.js — runs in the PAGE context (not isolated content-script world)
// so it can intercept media elements created by the page's own scripts.
// Injected as a <script> tag by content.js.

(function () {
  if (window.__safariEnhancerAudio) return; // already installed
  window.__safariEnhancerAudio = true;

  let ctx, gain;

  function ensureContext() {
    if (ctx) return;
    ctx  = new AudioContext();
    gain = ctx.createGain();
    gain.gain.value = parseFloat(
      document.documentElement.dataset.seGain || '1'
    );
    gain.connect(ctx.destination);
  }

  function hookMedia(el) {
    if (el.__seHooked) return;
    el.__seHooked = true;
    ensureContext();
    try {
      const src = ctx.createMediaElementSource(el);
      src.connect(gain);
    } catch (e) {
      // createMediaElementSource throws if the element was already captured
      // (e.g. by the page itself). Nothing we can do — skip it.
    }
  }

  // Hook all current media elements
  document.querySelectorAll('audio, video').forEach(hookMedia);

  // Watch for new ones added dynamically (YouTube, Spotify, etc.)
  new MutationObserver((muts) => {
    for (const m of muts) {
      for (const node of m.addedNodes) {
        if (!(node instanceof Element)) continue;
        if (node.tagName === 'AUDIO' || node.tagName === 'VIDEO') {
          hookMedia(node);
        }
        // also check descendants
        node.querySelectorAll?.('audio, video').forEach(hookMedia);
      }
    }
  }).observe(document, { childList: true, subtree: true });

  // Listen for gain-change events dispatched by content.js
  window.addEventListener('se-set-gain', (e) => {
    ensureContext();
    if (ctx.state === 'suspended') ctx.resume();
    gain.gain.value = e.detail;
    // Persist on element so ensureContext picks it up on re-init
    document.documentElement.dataset.seGain = String(e.detail);
  });
})();
