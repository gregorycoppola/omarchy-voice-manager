import unittest
from terminal_activity import classify_terminal


def process(pid, parent, name, **changes):
    return dict(pid=pid, parent=parent, name=name, group=changes.get('group',pid),
                foreground=changes.get('foreground',pid), tty='pts/1', state=changes.get('state','S'))


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.processes = {10:process(10,1,'foot'), 20:process(20,10,'bash')}

    def classify(self, args=()):
        return classify_terminal(10, self.processes, lambda _: args)

    def test_idle_interactive_shell(self):
        self.assertFalse(self.classify())
        self.assertFalse(self.classify(['--noprofile','--norc','-i']))

    def test_foreground_background_and_stopped_jobs(self):
        for state in ('R','S','T'):
            self.processes[30] = process(30,20,'sleep',state=state)
            self.assertTrue(self.classify())

    def test_foreground_group_with_no_visible_child(self):
        self.processes[20]['foreground'] = 30
        self.assertTrue(self.classify())

    def test_direct_app_and_shell_script(self):
        self.assertTrue(self.classify(['-c', 'sleep 30']))
        self.processes[20]['name'] = 'vim'
        self.assertTrue(self.classify())

    def test_zombie_does_not_count_as_running(self):
        self.processes[30] = process(30,20,'sleep',state='Z')
        self.assertFalse(self.classify())

    def test_missing_or_shared_terminal_is_unknown(self):
        self.assertIsNone(classify_terminal(99,self.processes,lambda _: []))
        self.processes[30] = process(30,10,'bash')
        self.assertIsNone(self.classify())

    def test_busy_shell_builtin_is_not_assumed_idle(self):
        self.processes[20]['state'] = 'R+'
        self.assertIsNone(self.classify())
