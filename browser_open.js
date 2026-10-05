// Runs only in the trusted extension control page.
async function inspectWebsiteWindow() {
    const windows = await chrome.windows.getAll({windowTypes: ['normal']});
    const focused = windows.filter(w => w.focused && !w.incognito);
    if (focused.length !== 1) throw new Error('Selected browser is not connected or is private');
    return {windowId: focused[0].id};
}

async function openWebsiteInWindow(windowId, address) {
    const url = new URL(address);
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password)
        throw new Error('Invalid website address');
    const window = await chrome.windows.get(windowId);
    if (!window.focused || window.incognito || window.type !== 'normal')
        throw new Error('Selected browser closed or changed focus');
    const tab = await chrome.tabs.create({windowId, url: url.href, active: true});
    if (tab.windowId !== windowId) throw new Error('Website opened in the wrong window');
    return {windowId, tabId: tab.id, opened: true};
}
