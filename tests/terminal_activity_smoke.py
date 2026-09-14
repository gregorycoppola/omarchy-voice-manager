"""Check real Foot process trees using disposable idle and busy terminal windows."""
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from terminal_activity import terminal_has_jobs

for command, expected in [(['bash','--noprofile','--norc','-i'], False), (['sleep','20'], True)]:
    terminal = subprocess.Popen(['foot','--app-id=io.github.gregorycoppola.Skipper.ActivityTest', *command],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            assert terminal.poll() is None, 'Test terminal exited unexpectedly'
            actual = terminal_has_jobs({'pid':terminal.pid})
            if actual is expected:
                break
            time.sleep(.1)
        else:
            raise AssertionError((command[0], expected, actual))
    finally:
        terminal.terminate()
        terminal.wait(timeout=3)
print('PASS: real idle Foot shell needs no confirmation; running command does')
