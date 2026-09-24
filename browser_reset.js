// Local extension control only; no page contents or URLs leave this operation.
async function inspectResetWindow() {
  const windows = await chrome.windows.getAll({populate: true, windowTypes: ['normal']});
  const focused = windows.filter(w => w.focused && !w.incognito);
  if (focused.length !== 1) throw new Error('The selected browser is not connected or is private');
  return {windowId: focused[0].id};
}

async function resetWindowTabs(windowId) {
  const windows = await chrome.windows.getAll({populate: true, windowTypes: ['normal']});
  const target = windows.find(w => w.id === windowId && w.focused && !w.incognito);
  if (!target) throw new Error('The selected browser changed focus or closed');
  const control = await chrome.tabs.getCurrent();
  if (!control) throw new Error('Browser control tab unavailable');
  const oldTabs = target.tabs.map(t => t.id).filter(id => id !== control.id);
  const blank = await chrome.tabs.create({windowId, url: 'about:blank', active: true});
  if (blank.windowId !== windowId) throw new Error('Blank tab opened in the wrong window');
  // Never retry this mutation automatically; a failure may be partial.
  if (oldTabs.length) await chrome.tabs.remove(oldTabs);
  const remaining = await chrome.tabs.query({windowId});
  const expected = control.windowId === windowId ? [blank.id, control.id] : [blank.id];
  if (remaining.length !== expected.length || remaining.some(t => !expected.includes(t.id)))
    throw new Error('Some tabs remain open; check the browser before trying again');
  return {windowId, tabId: blank.id, closed: oldTabs.length,
          closeControl: control.windowId === windowId};
}

if (typeof module !== 'undefined') module.exports = {inspectResetWindow, resetWindowTabs};
