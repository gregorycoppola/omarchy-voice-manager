"""Local stdio connection to the installed Playwright browser extension.

Only fixed code from browser_tabs.js and registry entries are sent. The connection
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
CONFIG = Path.home() / '.config/keety/browser-connection.json'
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
            raise RuntimeError('Browser connection is not configured: ~/.config/keety/browser-connection.json') from None
        if '--extension' not in entry['args']:
            raise RuntimeError('Keety requires the regular-browser extension connection')
        self.process = subprocess.Popen([entry['command'], *entry['args']],
            env=dict(os.environ, **entry.get('env', {})), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.request('initialize', dict(protocolVersion='2024-11-05', capabilities={},
            clientInfo=dict(name='Keety browser commands', version='1')))
        self.send(dict(method='notifications/initialized'))

    def bring_up(self, site):
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
                    return await bringUpSite(site);
                  }, SITE);
                }'''.replace('PREFIX', json.dumps(EXTENSION)).replace('SCRIPT', script).replace('SITE', json.dumps(site))
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


connection = BrowserConnection()
