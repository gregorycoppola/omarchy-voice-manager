"""Build the test-only standard-keymap keyboard in a temporary directory."""
import atexit
from pathlib import Path
import shlex
import subprocess
import tempfile


def build_keyboard():
    build = tempfile.TemporaryDirectory(prefix='keety-keyboard-test-')
    atexit.register(build.cleanup)
    source = Path(__file__).resolve().parent
    header = Path(build.name) / 'virtual-keyboard.h'
    protocol = Path(build.name) / 'virtual-keyboard.c'
    keyboard_bin = Path(build.name) / 'keys'
    subprocess.run(['wayland-scanner', 'client-header', str(source / 'virtual-keyboard-unstable-v1.xml'), str(header)], check=True)
    subprocess.run(['wayland-scanner', 'private-code', str(source / 'virtual-keyboard-unstable-v1.xml'), str(protocol)], check=True)
    flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'wayland-client', 'xkbcommon'], text=True))
    subprocess.run(['cc', str(source / 'keys.c'), str(protocol), '-I', build.name, '-o', str(keyboard_bin), *flags], check=True)
    return keyboard_bin
