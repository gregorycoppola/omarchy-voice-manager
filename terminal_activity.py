"""Detect an idle shell versus running jobs without reading terminal contents."""
from pathlib import Path
import subprocess

SHELLS = {'sh', 'bash', 'zsh', 'fish', 'dash', 'ksh', 'nu'}
IDLE_SHELL_FLAGS = {'-l', '-i', '-il', '-li', '--login', '--interactive', '--noprofile', '--norc'}


def process_snapshot():
    output = subprocess.run(
        ['ps', '-e', '-o', 'pid=,ppid=,pgid=,tpgid=,tty=,stat=,comm='],
        capture_output=True, text=True, check=True, timeout=2).stdout
    processes = {}
    for line in output.splitlines():
        pid, parent, group, foreground, tty, state, name = line.split(maxsplit=6)
        processes[int(pid)] = dict(pid=int(pid), parent=int(parent), group=int(group),
                                   foreground=int(foreground), tty=tty, state=state, name=name)
    return processes


def classify_terminal(pid, processes, shell_args):
    """False = idle prompt, True = job/app, None = cannot determine safely."""
    if pid not in processes:
        return None
    children = [p for p in processes.values() if p['parent'] == pid and not p['state'].startswith('Z')]
    # Shared terminal servers / multi-window processes cannot be resolved per window here.
    if len(children) != 1:
        return None
    shell = children[0]
    if shell['name'].lstrip('-') not in SHELLS:
        return True  # e.g. a terminal launched directly into vim, ssh, or tmux
    if any(arg not in IDLE_SHELL_FLAGS for arg in shell_args(shell['pid'])):
        return True  # shell running a script or -c command
    if any(p['parent'] == shell['pid'] and not p['state'].startswith('Z') for p in processes.values()):
        return True  # includes foreground, background, and stopped jobs
    if shell['tty'] == '?' or shell['foreground'] <= 0:
        return None
    if shell['group'] != shell['foreground']:
        return True
    if not shell['state'].startswith('S'):
        return None  # busy shell builtin or a transitional snapshot
    return False


def terminal_has_jobs(target):
    try:
        pid = target.get('pid')
        if type(pid) is not int or pid <= 0:
            return None
        def arguments(shell_pid):
            raw = (Path('/proc') / str(shell_pid) / 'cmdline').read_bytes()
            if not raw:
                raise ValueError('Shell exited during inspection')
            return [part.decode(errors='replace') for part in raw.split(b'\0')[1:] if part]
        return classify_terminal(pid, process_snapshot(), arguments)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
