// Runs in the installed extension's page, where Chrome's tabs API is available.
// The caller supplies only an entry from Keety's fixed site registry.
async function bringUpSite(site) {
  const windows = (await chrome.windows.getAll({populate: true, windowTypes: ['normal']}))
    .filter(w => !w.incognito && w.tabs.some(t => !t.url?.startsWith('chrome-extension://')));
  const matches = windows.flatMap(w => w.tabs.map(t => ({...t, focusedWindow: w.focused})))
    .filter(t => {
      try {
        const url = new URL(t.pendingUrl || t.url);
        return url.protocol === 'https:' && url.hostname === site.host;
      } catch { return false; }
    })
    .sort((a, b) => Number(Boolean(b.focusedWindow)) - Number(Boolean(a.focusedWindow))
      || (b.lastAccessed || 0) - (a.lastAccessed || 0) || a.id - b.id);
  let tab = matches[0];
  const reused = Boolean(tab);
  if (!tab) {
    windows.sort((a, b) => Number(Boolean(b.focused)) - Number(Boolean(a.focused))
      || Math.max(0, ...b.tabs.map(t => t.lastAccessed || 0))
       - Math.max(0, ...a.tabs.map(t => t.lastAccessed || 0)) || a.id - b.id);
    if (windows.length) {
      tab = await chrome.tabs.create({windowId: windows[0].id, url: site.url, active: true});
    } else {
      const window = await chrome.windows.create({url: site.url, type: 'normal', focused: true});
      tab = window.tabs[0];
    }
  }
  await chrome.tabs.update(tab.id, {active: true});
  await chrome.windows.update(tab.windowId, {focused: true});
  const selected = await chrome.tabs.get(tab.id);
  if (!selected.active) throw new Error('Could not activate website tab');
  return {reused, tabId: selected.id, windowId: selected.windowId};
}

if (typeof module !== 'undefined') module.exports = {bringUpSite};
