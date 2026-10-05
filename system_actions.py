"""Fixed system-menu operations; never execute user-supplied shell commands."""
import subprocess
import threading


SYSTEM_ACTIONS = {
    'system:screensaver': ('Screensaver', ['omarchy', 'launch', 'screensaver', 'force']),
    'system:lock': ('Lock', ['omarchy', 'system', 'lock']),
    'system:suspend': ('Suspend', ['systemctl', 'suspend']),
    'system:logout': ('Log out', ['omarchy', 'system', 'logout']),
    'system:reboot': ('Reboot', ['omarchy', 'system', 'reboot']),
    'system:shutdown': ('Shut down', ['omarchy', 'system', 'shutdown']),
}
SESSION_END_ACTIONS = {'system:logout', 'system:reboot', 'system:shutdown'}


def execute_system(command):
    if command not in SYSTEM_ACTIONS:
        raise ValueError('Unknown system action')
    label, argv = SYSTEM_ACTIONS[command]
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        code = process.wait(timeout=.2)
    except subprocess.TimeoutExpired:
        threading.Thread(target=process.wait, daemon=True).start()
    else:
        if code:
            raise RuntimeError(f'{label} command failed (exit {code})')
    return f'{label} requested.'
