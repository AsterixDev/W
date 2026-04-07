// ── Defaults ─────────────────────────────────────────────────────────────────

const DEFAULTS = {
  darkModeHosts: {},   // { "example.com": true } — per-domain dark mode
  toolbarColor: null,
  volume: 1.0,
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function hostname(url) {
  try { return new URL(url).hostname; } catch { return null; }
}

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

function pushToTab(tabId, tabUrl) {
  chrome.storage.local.get(Object.keys(DEFAULTS), (s) => {
    const host = hostname(tabUrl);
    const darkMode = host ? !!(s.darkModeHosts?.[host]) : false;
    chrome.tabs.sendMessage(tabId, {
      action: 'applyAll',
      settings: { darkMode, toolbarColor: s.toolbarColor, volume: s.volume },
    }).catch(() => {});
  });
}

chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (info.status === 'loading') pushToTab(tabId, tab.url);
});

// ── Message relay ─────────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {

  if (msg.action === 'setSetting') {
    if (msg.key === 'darkMode') {
      // Store per-domain
      chrome.storage.local.get('darkModeHosts', (s) => {
        const hosts = s.darkModeHosts || {};
        if (msg.value) hosts[msg.host] = true;
        else delete hosts[msg.host];
        chrome.storage.local.set({ darkModeHosts: hosts }, () => {
          chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
            if (tab) chrome.tabs.sendMessage(tab.id, {
              action: 'applySetting', key: 'darkMode', value: msg.value,
            }).catch(() => {});
          });
        });
      });
    } else {
      chrome.storage.local.set({ [msg.key]: msg.value }, () => {
        chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
          if (tab) chrome.tabs.sendMessage(tab.id, {
            action: 'applySetting', key: msg.key, value: msg.value,
          }).catch(() => {});
        });
      });
    }
    sendResponse({ ok: true });
  }

  if (msg.action === 'getSettings') {
    chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
      const host = hostname(tab?.url || '');
      chrome.storage.local.get(Object.keys(DEFAULTS), (s) => {
        sendResponse({
          darkMode: host ? !!(s.darkModeHosts?.[host]) : false,
          toolbarColor: s.toolbarColor,
          volume: s.volume,
          host,
        });
      });
    });
    return true;
  }
});
