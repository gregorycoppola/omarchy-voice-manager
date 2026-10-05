"""Layout navigation should restore surviving windows and preserve redo history."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from layout_history import LayoutHistory


def window(number, x, workspace='1'):
    return {'address': f'0x{number:x}', 'pid': number, 'class': 'foot',
            'stableId': str(number), 'mapped': True, 'workspace': {'name': workspace},
            'at': [x, 30], 'size': [500, 400], 'floating': True,
            'fullscreen': 0, 'fullscreenClient': 0}


class FakeHyprland:
    def __init__(self):
        self.clients = [window(1, 10), window(2, 600)]
        self.focus = '0x1'
        self.commands = []

    def run(self, argv):
        if argv == ['hyprctl', 'clients', '-j']:
            return json.dumps(self.clients)
        if argv == ['hyprctl', 'activewindow', '-j']:
            return json.dumps({'address': self.focus})
        if argv == ['hyprctl', 'monitors', '-j']:
            return '[]'
        command = argv[-1]
        self.commands.append(command)
        address = re.search(r'window = "address:(0x[0-9a-f]+)"', command)
        if not address:
            return 'ok'
        client = next(client for client in self.clients if client['address'] == address.group(1))
        workspace = re.search(r'workspace = "([^"]+)"', command)
        if workspace:
            client['workspace']['name'] = workspace.group(1)
        if 'hl.dsp.window.resize' in command:
            client['size'] = [int(value) for value in re.findall(r'[xy] = (-?\d+)', command)]
        if 'hl.dsp.window.move' in command and not workspace:
            client['at'] = [int(value) for value in re.findall(r'[xy] = (-?\d+)', command)]
        if 'hl.dsp.focus' in command:
            self.focus = client['address']
        return 'ok'


class LayoutHistoryTest(unittest.TestCase):
    def test_back_forward_skip_closed_and_reload(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = FakeHyprland()
            path = Path(folder) / 'layouts.json'
            history = LayoutHistory(path, fake.run, settle_seconds=0)
            self.assertTrue(history.observe())
            fake.clients[0]['at'] = [300, 90]
            fake.clients[0]['workspace']['name'] = '2'
            history.observe(force=True)
            self.assertEqual(history.info()['count'], 2)
            history = LayoutHistory(path, fake.run, settle_seconds=0)
            fake.clients.pop(1)
            self.assertIn('skipped 1 closed', history.step(-1))
            self.assertEqual(fake.clients[0]['at'], [10, 30])
            self.assertEqual(fake.clients[0]['workspace']['name'], '1')
            self.assertTrue(history.info()['can_forward'])
            history.step(1)
            self.assertEqual(fake.clients[0]['at'], [300, 90])
            self.assertEqual(fake.clients[0]['workspace']['name'], '2')

    def test_new_view_discards_forward_branch(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = FakeHyprland()
            history = LayoutHistory(Path(folder) / 'layouts.json', fake.run)
            history.observe()
            fake.clients[0]['at'][0] = 100
            history.observe(force=True)
            history.step(-1)
            fake.clients[0]['at'][0] = 200
            history.observe(force=True)
            self.assertEqual(history.info(), {'can_back': True, 'can_forward': False,
                                               'position': 2, 'count': 2})


if __name__ == '__main__':
    unittest.main()
