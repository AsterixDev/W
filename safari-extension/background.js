// ── Defaults ─────────────────────────────────────────────────────────────────

const DEFAULTS = {
  darkMode: false,
  toolbarColor: null,   // null = don't touch the toolbar
  volume: 1.0,          // 1.0 = 100%, 10.0 = 1000%
};

// ── Install → write defaults ──────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(Object.keys(DEFAULTS), (stored) => {
    const toWrite = {};
    for (const [key, def] of Object.entries(DEFAULTS)) {
      if (!(key in stored)) toWrite[key] = def;
    }
    if (Object.keys(toWrite).length) chrome.storage.local.set(toWrite);
  });
});

// ── Push settings to a tab's content script ──────────────────────────────────

function pushToTab(tabId) {
  chrome.storage.local.get(Object.keys(DEFAULTS), (settings) => {
    chrome.tabs.sendMessage(tabId, { action: 'applyAll', settings })
      .catch(() => {}); // tab may not have the content script yet — ignore
  });
}

// Re-push whenever the user navigates to a new page (content script reloads)
chrome.tabs.onUpdated.addListener((tabId, info) => {
  if (info.status === 'loading') pushToTab(tabId);
});

// ── Message relay from popup ──────────────────────────────────────────────────
// The popup sends { action, key, value } to update a single setting and
// immediately apply it to the active tab.

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.action === 'setSetting') {
    chrome.storage.local.set({ [msg.key]: msg.value }, () => {
      // Send only the changed setting — avoids overwriting other settings
      // with stale values from a race condition in storage reads
      chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
        if (tab) {
          chrome.tabs.sendMessage(tab.id, {
            action: 'applySetting',
            key: msg.key,
            value: msg.value,
          }).catch(() => {});
        }
      });
    });
    sendResponse({ ok: true });
  }

  if (msg.action === 'getSettings') {
    chrome.storage.local.get(Object.keys(DEFAULTS), sendResponse);
    return true; // keep channel open for async response
  }
});
