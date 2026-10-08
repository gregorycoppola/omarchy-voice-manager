"""Local stdio connection to the installed Playwright browser extension.

Only fixed browser scripts and registry/validated window IDs are sent. The connection
configuration stays outside the repo; responses containing browser data/tokens
are never logged. No model or language interpretation is involved here.
"""
import atexit
import json
import os
from pathlib import Path
import selectors
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parent
CONFIG = Path.home() / '.config/skipper/browser-connection.json'
EXTENSION = 'chrome-extension://mmlmfjhmonkocbjadbfplnigmagldckm/'


class BrowserConnection:
    def __init__(self):
        self.process = None
        self.selector = None
        self.buffer = b''
        self.sequence = 0
        self.lock = threading.Lock()
        atexit.register(self.close)

    def close(self):
        if self.process:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            self.process.stdout.close()
            self.process = None
        if self.selector:
            self.selector.close()
            self.selector = None
        self.buffer = b''

    def send(self, value):
        self.process.stdin.write(json.dumps(dict(jsonrpc='2.0', **value)).encode() + b'\n')
        self.process.stdin.flush()

    def request(self, method, params):
        self.sequence += 1
        self.send(dict(id=self.sequence, method=method, params=params))
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if not self.selector.select(min(1, max(0, deadline-time.monotonic()))):
                continue
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                raise RuntimeError('Browser connection closed')
            self.buffer += chunk
            if len(self.buffer) > 8 * 1024 * 1024:
                raise RuntimeError('Browser response too large')
            while b'\n' in self.buffer:
                line, self.buffer = self.buffer.split(b'\n', 1)
                message = json.loads(line)
                if message.get('id') != self.sequence:
                    continue
                result = message.get('result', {})
                if 'error' in message or result.get('isError'):
                    raise RuntimeError('Browser action failed; check the local extension connection')
                return result
        raise RuntimeError('Browser connection timed out; check the Playwright extension in Chromium')

    def connect(self):
        try:
            entry = json.loads(CONFIG.read_text())
        except (OSError, ValueError):
            raise RuntimeError('Browser connection is not configured: ~/.config/skipper/browser-connection.json') from None
        if '--extension' not in entry['args']:
            raise RuntimeError('Skipper requires the regular-browser extension connection')
        self.process = subprocess.Popen([entry['command'], *entry['args']],
            env=dict(os.environ, **entry.get('env', {})), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.request('initialize', dict(protocolVersion='2024-11-05', capabilities={},
            clientInfo=dict(name='Skipper browser commands', version='1')))
        self.send(dict(method='notifications/initialized'))

    def _select_site_tab(self, site, function):
        with self.lock:
            try:
                if self.process is None or self.process.poll() is not None:
                    self.close()
                    self.connect()
                # Retain one extension control page. Use its existing permissions
                # to select tabs without reading any website contents.
                script = (ROOT / 'browser_tabs.js').read_text().split("if (typeof module")[0]
                code = '''async (page) => {
                  const prefix = PREFIX;
                  let control = page.context().pages().find(p => p.url().startsWith(prefix));
                  if (!control) {
                    control = await page.context().newPage();
                    await control.goto(prefix + 'status.html');
                  }
                  return await control.evaluate(async (site) => {
                    SCRIPT
                    return await FUNCTION(site);
                  }, SITE);
                }'''.replace('PREFIX', json.dumps(EXTENSION)).replace('SCRIPT', script).replace('FUNCTION', function).replace('SITE', json.dumps(site))
                result = self.request('tools/call', dict(name='browser_run_code_unsafe', arguments={'code': code}))
                for content in result.get('content', []):
                    if content.get('type') != 'text':
                        continue
                    section = content['text'].split('### Result\n', 1)
                    if len(section) == 2:
                        value, _ = json.JSONDecoder().raw_decode(section[1].lstrip())
                        if isinstance(value, dict) and type(value.get('reused')) is bool and isinstance(value.get('tabId'), int):
                            return value
                raise RuntimeError('Browser did not confirm the selected tab')
            except Exception:
                self.close()
                # Do not retry mutations automatically: a timed-out request may
                # already have opened a tab. The next command queries tabs anew.
                raise

    def tab_picker(self, selected=None):
        """List normal-profile tab metadata, or activate a previously listed tab."""
        with self.lock:
            try:
                if self.process is None or self.process.poll() is not None:
                    self.close()
                    self.connect()
                code = """async (page) => {
                    const prefix = PREFIX;
                    let control = page.context().pages().find(p => p.url().startsWith(prefix));
                    if (!control) {
                        control = await page.context().newPage();
                        await control.goto(prefix + 'status.html');
                    }
                    return await control.evaluate(async (selected) => {
                        if (selected) {
                            const tab = await chrome.tabs.get(selected.tabId);
                            if (tab.incognito || tab.windowId !== selected.windowId ||
                                (tab.pendingUrl || tab.url || '') !== selected.url)
                                throw new Error('Tab changed; list browser tabs again');
                            await chrome.tabs.update(tab.id, {active: true});
                            await chrome.windows.update(tab.windowId, {focused: true});
                            const current = await chrome.tabs.get(tab.id);
                            const window = await chrome.windows.get(tab.windowId);
                            return {focused: current.active && window.focused};
                        }
                        const windows = await chrome.windows.getAll({populate:true, windowTypes:['normal']});
                        return {tabs: windows.filter(w => !w.incognito).flatMap(w =>
                            (w.tabs || []).filter(t => !(t.url || '').startsWith('chrome-extension://'))
                            .map(t => ({tabId:t.id, windowId:w.id, title:t.title || 'Untitled tab',
                                url:t.pendingUrl || t.url || '', favicon:t.favIconUrl || '', active:t.active, index:t.index}))) };
                    }, SELECTED);
                }""".replace('PREFIX', json.dumps(EXTENSION)).replace('SELECTED', json.dumps(selected))
                result = self.request('tools/call', dict(name='browser_run_code_unsafe', arguments={'code': code}))
                for content in result.get('content', []):
                    if content.get('type') == 'text':
                        section = content['text'].split('### Result\n', 1)
                        if len(section) == 2:
                            value, _ = json.JSONDecoder().raw_decode(section[1].lstrip())
                            if isinstance(value, dict) and (value.get('focused') is True if selected else isinstance(value.get('tabs'), list)):
                                return value
                raise RuntimeError('Browser did not confirm the tab request')
            except Exception:
                self.close()
                raise

    def bring_up(self, site):
        return self._select_site_tab(site, 'bringUpSite')

    def open_another(self, site):
        return self._select_site_tab(site, 'openAnotherSiteTab')

    def reset_tabs(self, focus_target, verify_target):
        """Bind the native selection to a focused extension window before clearing it."""
        with self.lock:
            try:
                if self.process is None or self.process.poll() is not None:
                    self.close()
                    self.connect()
                script = (ROOT / 'browser_reset.js').read_text().split('if (typeof module')[0]

                def invoke(phase, window_id=None):
                    code = '''async (page) => {
                      const prefix = PREFIX;
                      const phase = PHASE;
                      let control = page.context().pages().find(p => p.url().startsWith(prefix));
                      if (!control && phase === 'prepare') {
                        control = await page.context().newPage();
                        await control.goto(prefix + 'status.html');
                      }
                      if (!control) throw new Error('Browser control page closed');
                      if (phase === 'prepare') return {prepared: true};
                      const result = await control.evaluate(async ({phase, windowId}) => {
                        SCRIPT
                        return phase === 'inspect' ? await inspectResetWindow() : await resetWindowTabs(windowId);
                      }, {phase, windowId: WINDOW_ID});
                      // Close our own control tab from Playwright, after its evaluate
                      // finishes, so the selected window contains just the blank tab.
                      if (result.closeControl) await control.close();
                      return result;
                    }'''.replace('PREFIX', json.dumps(EXTENSION)).replace('PHASE', json.dumps(phase)).replace('SCRIPT', script).replace('WINDOW_ID', json.dumps(window_id))
                    result = self.request('tools/call', dict(name='browser_run_code_unsafe', arguments={'code': code}))
                    for content in result.get('content', []):
                        if content.get('type') == 'text':
                            section = content['text'].split('### Result\n', 1)
                            if len(section) == 2:
                                value, _ = json.JSONDecoder().raw_decode(section[1].lstrip())
                                if isinstance(value, dict):
                                    return value
                    raise RuntimeError('Browser did not confirm the tab operation')

                if invoke('prepare').get('prepared') is not True:
                    raise RuntimeError('Browser control page unavailable')
                focus_target()
                selected = invoke('inspect')
                if type(selected.get('windowId')) is not int:
                    raise RuntimeError('Browser window identity unavailable')
                verify_target()
                result = invoke('reset', selected['windowId'])
                if (result.get('windowId') != selected['windowId']
                        or type(result.get('tabId')) is not int or type(result.get('closed')) is not int):
                    raise RuntimeError('Browser did not confirm closing tabs')
                return result
            except Exception:
                self.close()
                raise

    def open_url_in_window(self, url, focus_target, verify_target):
        """Create a tab only after native and extension window focus agree."""
        from url_entry import normalize_url
        url = normalize_url(url)
        with self.lock:
            try:
                if self.process is None or self.process.poll() is not None:
                    self.close()
                    self.connect()
                script = (ROOT / 'browser_open.js').read_text()

                def invoke(phase, window_id=None):
                    code = '''async (page) => {
                        const prefix = PREFIX;
                        const phase = PHASE;
                        let control = page.context().pages().find(p => p.url().startsWith(prefix));
                        if (!control && phase === 'prepare') {
                            control = await page.context().newPage();
                            await control.goto(prefix + 'status.html');
                        }
                        if (!control) throw new Error('Browser control page closed');
                        if (phase === 'prepare') return {prepared: true};
                        return await control.evaluate(async ({phase, windowId, url}) => {
                            SCRIPT
                            return phase === 'inspect' ? await inspectWebsiteWindow()
                                : await openWebsiteInWindow(windowId, url);
                        }, {phase, windowId: WINDOW_ID, url: URL_VALUE});
                    }'''.replace('PREFIX', json.dumps(EXTENSION)).replace('PHASE', json.dumps(phase)).replace('SCRIPT', script).replace('WINDOW_ID', json.dumps(window_id)).replace('URL_VALUE', json.dumps(url))
                    result = self.request('tools/call', dict(name='browser_run_code_unsafe', arguments={'code': code}))
                    for content in result.get('content', []):
                        if content.get('type') == 'text':
                            section = content['text'].split('### Result\n', 1)
                            if len(section) == 2:
                                value, _ = json.JSONDecoder().raw_decode(section[1].lstrip())
                                if isinstance(value, dict):
                                    return value
                    raise RuntimeError('Browser did not confirm the website operation')

                if invoke('prepare').get('prepared') is not True:
                    raise RuntimeError('Browser control page unavailable')
                focus_target()
                selected = invoke('inspect')
                if type(selected.get('windowId')) is not int:
                    raise RuntimeError('Browser window identity unavailable')
                verify_target()
                result = invoke('open', selected['windowId'])
                if (result.get('windowId') != selected['windowId']
                        or type(result.get('tabId')) is not int or result.get('opened') is not True):
                    raise RuntimeError('Browser did not confirm opening the website')
                return result
            except Exception:
                # Never retry a mutation: a timed-out call may have opened its tab.
                self.close()
                raise


connection = BrowserConnection()
