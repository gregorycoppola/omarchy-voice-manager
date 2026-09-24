"""Explicit per-user setup/removal for the Skipper companion runtime."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from install_desktop import install as install_desktop

ROOT = Path(__file__).resolve().parent
BEGIN = '-- BEGIN Skipper plugin shortcut\n'
END = '-- END Skipper plugin shortcut\n'


def digest(content):
    return hashlib.sha256(content).hexdigest()


def locations():
    home = Path.home()
    config = Path(os.environ.get('XDG_CONFIG_HOME', home / '.config'))
    data = Path(os.environ.get('XDG_DATA_HOME', home / '.local/share'))
    return home, config, data


def install_integration(root, home, config, data, *, shortcut=False, autostart=False, replace=False):
    root, home, config, data = map(Path, (root, home, config, data))
    state_path = data / 'skipper/plugin-install.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {'files': {}, 'shortcut': None}
    planned = {}
    # Generate launchers using the same escaping as the desktop installer.
    with tempfile.TemporaryDirectory() as temporary:
        temporary = Path(temporary)
        for explorer in (False, True):
            binary, desktop = install_desktop(root, temporary / 'home', temporary / 'data', explorer=explorer)
            planned[home / '.local/bin' / binary.name] = (binary.read_bytes(), 0o755)
            planned[data / 'applications' / desktop.name] = (desktop.read_bytes(), 0o644)
            if autostart and not explorer:
                planned[config / 'autostart/skipper.desktop'] = (desktop.read_bytes(), 0o644)
    block = None
    if shortcut:
        target = config / 'hypr/skipper-plugin-ptt.lua'
        planned[target] = ((root / 'config/hyprland-skipper-ptt.lua').read_bytes(), 0o644)
        written_target = config / 'hypr/skipper-plugin-written.lua'
        planned[written_target] = ((root / 'config/hyprland-skipper-written.lua').read_bytes(), 0o644)
        bindings = config / 'hypr/bindings.lua'
        # JSON strings are also valid Lua strings for normal filesystem paths.
        block = BEGIN + 'dofile(' + json.dumps(str(target)) + ')\n' + 'dofile(' + json.dumps(str(written_target)) + ')\n' + END
        current = bindings.read_text() if bindings.exists() else ''
        old_block = state.get('shortcut')
        if BEGIN in current and (not old_block or old_block['block'] not in current):
            raise RuntimeError('Existing Skipper shortcut block was edited; resolve it before setup')
        if old_block:
            current = current.replace(old_block['block'], '')
        if current and not current.endswith('\n'):
            block = '\n' + block
        planned[bindings] = ((current + block).encode(), 0o644)
    # Preflight every conflict before changing any installed file.
    for path, (content, _) in planned.items():
        if path.exists() and path.read_bytes() != content:
            owned = state['files'].get(str(path)) == digest(path.read_bytes())
            if not owned and not replace and not (shortcut and path == bindings):
                raise RuntimeError(f'{path} already exists. Review it; use --replace-existing to back it up and replace it.')
    backups = data / 'skipper/install-backups' / str(time.time_ns())
    for path, (content, mode) in planned.items():
        if path.exists() and path.read_bytes() != content:
            backup = backups / str(path).lstrip('/')
            backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copy2(path, backup)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(mode)
        if not (shortcut and path == bindings):
            state['files'][str(path)] = digest(content)
    if shortcut:
        state['shortcut'] = {'path': str(bindings), 'block': block}
    state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_path.write_text(json.dumps(state, indent=2) + '\n')
    state_path.chmod(0o600)
    return state_path


def uninstall_integration(data):
    state_path = Path(data) / 'skipper/plugin-install.json'
    if not state_path.exists():
        return ['No setup receipt found; no files removed.']
    state = json.loads(state_path.read_text())
    retained = []
    shortcut = state.get('shortcut')
    if shortcut:
        path = Path(shortcut['path'])
        if path.exists():
            text = path.read_text()
            if shortcut['block'] in text:
                path.write_text(text.replace(shortcut['block'], ''))
            elif BEGIN in text:
                retained.append(str(path))
    for filename, expected in state['files'].items():
        path = Path(filename)
        if not path.exists():
            continue
        if digest(path.read_bytes()) == expected:
            # Keep the Lua file if an edited binding might still load it.
            if retained and path.name == 'skipper-plugin-ptt.lua':
                continue
            path.unlink()
        else:
            retained.append(filename)
    if not retained:
        state_path.unlink()
    return ['Kept modified file: ' + path for path in retained]


def install_dataset(source, data):
    """Install a selected dataset snapshot; never fetch private credentials on launch."""
    source, data = Path(source).expanduser().resolve(), Path(data)
    import importlib.util
    spec = importlib.util.spec_from_file_location('skipper_setup_catalog', source / 'intent_explorer/catalog.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    catalog = module.Catalog(source)
    if 'language_policy' not in catalog.providers['skipper']:
        raise ValueError('Dataset is too old for this Skipper version')
    destination = data / 'skipper/intent-dataset'
    if source == destination.resolve():
        return catalog.revision
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Build a complete snapshot before replacing a previously installed version.
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        staged = Path(temporary) / 'dataset'
        staged.mkdir()
        for folder in ('data', 'intent_explorer'):
            shutil.copytree(source / folder, staged / folder,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for filename in ('LICENSE', 'README.md'):
            if (source / filename).is_file():
                shutil.copyfile(source / filename, staged / filename)
        (staged / 'installed-revision.txt').write_text(catalog.revision + '\n')
        backup = destination.with_name('intent-dataset.previous')
        if backup.exists():
            raise RuntimeError('Previous dataset backup exists; retain or move it before replacing the dataset')
        if destination.exists():
            destination.rename(backup)
        try:
            staged.rename(destination)
        except OSError:
            if backup.exists():
                backup.rename(destination)
            raise
    return catalog.revision


def install_public_dataset(release, data):
    """Fetch a pinned public snapshot; no credentials or moving branch dependency."""
    repository, commit = release['repository'], release['commit']
    import re
    if not repository.startswith('https://github.com/') or not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Dataset release requires a public HTTPS URL and full commit ID')
    with tempfile.TemporaryDirectory(prefix='skipper-dataset-') as temporary:
        source = Path(temporary) / 'source'
        subprocess.run(['git', 'init', '-q', str(source)], check=True)
        subprocess.run(['git', '-C', str(source), 'fetch', '--depth=1', repository, commit], check=True)
        subprocess.run(['git', '-C', str(source), 'checkout', '--detach', '-q', 'FETCH_HEAD'], check=True)
        actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != commit:
            raise ValueError('Downloaded dataset commit does not match release pin')
        return install_dataset(source, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    setup = sub.add_parser('install')
    setup.add_argument('--dataset', type=Path, help='Path to the separately obtained intent dataset checkout/snapshot')
    setup.add_argument('--text-only', action='store_true', help='Skip speech-model download; use SKIPPER_TEXT_ONLY=1 when launching')
    setup.add_argument('--shortcut', action='store_true', help='Install Super+R hold-to-talk; replaces its existing binding')
    setup.add_argument('--autostart', action='store_true', help='Start Skipper at login')
    setup.add_argument('--replace-existing', action='store_true', help='Back up and replace conflicting Skipper launchers')
    sub.add_parser('uninstall', help='Remove setup-owned integration; keep recordings, settings, model, and Python environment')
    args = parser.parse_args()
    home, config, data = locations()
    if args.command == 'uninstall':
        if shutil.which('gapplication'):
            subprocess.run(['gapplication', 'action', 'io.github.gregorycoppola.Skipper', 'quit'], capture_output=True)
        for message in uninstall_integration(data):
            print(message)
        print('Saved data, model, and Python environment retained. Remove the widget with: omarchy plugin remove greg.skipper')
    else:
        reference = json.loads((ROOT / 'dataset-reference.json').read_text())
        source = args.dataset or (Path(os.environ['OMARCHY_INTENT_DATASET']) if os.environ.get('OMARCHY_INTENT_DATASET') else None)
        if source:
            if not (source / 'intent_explorer/catalog.py').is_file():
                parser.error('Intent dataset missing at --dataset / OMARCHY_INTENT_DATASET path.')
            revision = install_dataset(source, data)
        else:
            revision = install_public_dataset(reference['release'], data)
        from personal_store import initialize
        initialize(data / 'skipper')
        print('Intent dataset installed: ' + revision)
        missing = [cmd for cmd in ('hyprctl', 'pw-record', 'gapplication') if not shutil.which(cmd)]
        if missing:
            parser.error('Install required system commands first: ' + ', '.join(missing))
        check = subprocess.run([sys.executable, '-c', "import gi; gi.require_version('Gtk', '4.0'); from gi.repository import Gtk; import cairo"], capture_output=True)
        if check.returncode:
            parser.error('System Python needs gtk4, python-gobject, and python-cairo. See README.')
        environment = data / 'skipper/venv'
        if not (environment / 'bin/python').exists():
            subprocess.run([sys.executable, '-m', 'venv', '--system-site-packages', str(environment)], check=True)
        python = environment / 'bin/python'
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(ROOT / 'requirements.lock')], check=True)
        env = dict(os.environ, SKIPPER_MODEL_DIR=str(data / 'skipper/models/parakeet-tdt-0.6b-v3-int8'))
        if not args.text_only:
            subprocess.run([str(python), str(ROOT / 'skipper.py'), 'download'], env=env, check=True)
        install_integration(ROOT, home, config, data, shortcut=args.shortcut, autostart=args.autostart, replace=args.replace_existing)
        print('Setup complete. Click Start Skipper in the bar, or run ~/.local/bin/skipper.')
    if shutil.which('hyprctl') and (args.command == 'uninstall' or args.shortcut):
        subprocess.run(['hyprctl', 'reload'], check=True)
        errors = subprocess.check_output(['hyprctl', 'configerrors'], text=True).strip()
        if errors:
            raise RuntimeError('Hyprland reported configuration errors: ' + errors)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f'Skipper setup: {exc}')
