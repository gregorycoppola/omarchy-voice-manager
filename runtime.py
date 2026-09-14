"""Windowless voice runtime. The Omarchy bar owns all everyday voice UI."""
from collections import deque
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
from uuid import uuid4

from gi.repository import Gio, GLib

from audio_levels import pcm_level
from browser_connection import connection
from command_catalog import INTENTS, NO_LEARN_COMMANDS
from diagnostics import append_event, LOG_PATH
from intent_matching import IntentMatcher
from skipper import load_model
from live_audio import read_growing_wav
from os_actions import (capture_window_context, window_target, execute_command,
                        tile_open_windows, hide_windows, hide_current_window, tile_terminals, tile_browsers, tile_apps, move_other_screen, maximize_current_window,
                        terminal_close_target, close_terminal, TERMINAL_CLOSE_INTENTS)
from os_actions import focus_named_window, move_app_other_screen
from window_vocabulary import inject_windows
from push_to_talk import PushToTalk
from recordings import new_recording, save_transcript
from settings import Settings
from terminal_activity import terminal_has_jobs

APP_ID = 'io.github.gregorycoppola.Skipper'
DATA = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'skipper'
STATUS = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp')) / f'skipper-{os.getuid()}-status.json'


class VoiceRuntime(Gio.Application):
    def __init__(self, data=DATA, status_path=STATUS, show_on_start=False):
        super().__init__(application_id=APP_ID)
        self.data = Path(data)
        self.diagnostic_path = LOG_PATH if self.data == DATA else self.data / 'commands.jsonl'
        self.status_path = Path(status_path)
        self.model = None
        self.started = False
        self.show_on_start = show_on_start
        self.busy = False
        self.recorder = None
        self.stop_requested = False
        self.quit_when_finished = False
        self.pending = None
        self.ptt_held = False
        self.panel_epoch = 0
        self.session = uuid4().hex
        self.diagnostic_recording = None
        self.levels = deque([0.0] * 48, maxlen=48)
        self.state = dict(state='Loading', message='Loading local speech model…', transcript='',
                          intent=None, intent_label='', monitor='', confirmation=None, completed_at=0)
        self.ptt = PushToTalk(self.press, self.release)
        for name, signature, callback in (
            ('ptt-event', 's', lambda value: self.ptt.event(value)),
            ('confirm', 's', self.confirm), ('cancel', 's', self.cancel),
            ('quit', None, self.request_quit), ('show', None, self.show),
            ('retry', 's', self.retry),
        ):
            action = Gio.SimpleAction.new(name, GLib.VariantType.new(signature) if signature else None)
            action.connect('activate', lambda _, value, fn=callback: fn(value.unpack()) if value else fn())
            self.add_action(action)

    def do_activate(self):
        if self.started:
            self.show()
            return
        self.started = True
        self.hold()
        GLib.timeout_add(50, self.ptt.check_held)
        GLib.timeout_add_seconds(2, self.publish)
        self.publish()
        if self.show_on_start:
            self.show()
        threading.Thread(target=self.prepare, daemon=True).start()

    def prepare(self):
        try:
            model, _ = load_model(4)
            GLib.idle_add(self.ready, model, None)
        except Exception as exc:
            GLib.idle_add(self.ready, None, str(exc))

    def ready(self, model, error):
        self.model = model
        self.update('Error' if error else 'Ready', error or 'Hold Super + R to speak.')
        if self.ptt_held and model:
            self.start_recording()

    def update(self, state, message):
        append_event('state', path=self.diagnostic_path, session=self.session, recording=self.diagnostic_recording,
                     state=state, message=message)
        self.state.update(state=state, message=message)
        self.publish()

    def publish(self):
        payload = self.state | dict(updated=time.time(), session=self.session,
                                    panel_epoch=self.panel_epoch, levels=list(self.levels))
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=self.status_path.parent, delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(payload, handle)
            temporary.replace(self.status_path)
        except OSError as exc:
            print(f'Could not publish Skipper status: {exc}', file=sys.stderr)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
        return True

    def show(self):
        self.state['monitor'] = self.focused_monitor()
        self.panel_epoch += 1
        self.publish()

    @staticmethod
    def focused_monitor():
        try:
            monitors = json.loads(subprocess.check_output(['hyprctl', 'monitors', '-j'], timeout=2))
            return next((m['name'] for m in monitors if m.get('focused')), '')
        except (OSError, ValueError, subprocess.SubprocessError):
            return ''

    def press(self):
        self.ptt_held = True
        if self.model is None:
            self.show()
            return
        if self.busy:
            return
        self.start_recording()

    def release(self):
        self.ptt_held = False
        self.stop_recording()

    def start_recording(self):
        if self.busy or self.model is None:
            return
        self.cancel()
        # Capture the target before publishing the event that reveals the popup.
        context = capture_window_context()
        self.state['monitor'] = self.focused_monitor()
        try:
            path = new_recording(self.data / 'recordings')
            self.diagnostic_recording = str(path)
            append_event('recording_started', path=self.diagnostic_path, session=self.session, recording=str(path),
                         active_window=context.get('active'), context=context)
            process = subprocess.Popen([
                'pw-record', '--rate', '16000', '--channels', '1', '--format', 's16',
                '--sample-count', '480000', str(path),
            ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        except OSError as exc:
            self.panel_epoch += 1
            self.update('Error', f'Could not record: {exc}')
            return
        self.recorder = process
        self.busy = True
        self.stop_requested = False
        self.levels = deque([0.0] * 48, maxlen=48)
        self.meter_bytes = 0
        self.record_start = time.monotonic()
        self.state.update(transcript='', intent=None, intent_label='')
        self.panel_epoch += 1
        self.update('Recording', 'Keep holding Super + R. Release to transcribe.')
        GLib.timeout_add(100, self.tick, path, process)
        threading.Thread(target=self.finish_recording, args=(path, process, context), daemon=True).start()

    def tick(self, path, process):
        if self.recorder is not process or process.poll() is not None or self.stop_requested:
            return False
        if time.monotonic() - self.record_start >= 30:
            self.stop_recording()
            return False
        try:
            pcm = read_growing_wav(path)
            fresh = pcm[self.meter_bytes:] if pcm else b''
            self.levels.append(pcm_level(fresh[-3200:])[0] if fresh else 0.0)
            if pcm:
                self.meter_bytes = len(pcm)
        except (OSError, ValueError):
            self.levels.append(0.0)
        self.publish()
        return True

    def stop_recording(self):
        if self.recorder and self.recorder.poll() is None and not self.stop_requested:
            self.stop_requested = True
            try:
                self.recorder.send_signal(signal.SIGINT)
            except ProcessLookupError:
                pass
            self.update('Working', 'Saving and transcribing…')

    def finish_recording(self, path, process, context):
        try:
            _, error = process.communicate(timeout=45)
            if process.returncode not in (0, -signal.SIGINT) and not (self.stop_requested and process.returncode == 1):
                raise RuntimeError(f'Recorder exited {process.returncode}: {error.strip()}')
            GLib.idle_add(self.update, 'Working', 'Transcribing locally…')
            self.transcribe(path, context, commands=True)
        except Exception as exc:
            if process.poll() is None:
                process.kill()
                process.communicate()
            GLib.idle_add(self.complete, 'Error', f'Audio kept; recording failed: {exc}')

    def transcribe(self, path, context=None, commands=False):
        self.diagnostic_recording = str(path)
        try:
            text, _ = save_transcript(self.model, path)
            append_event('transcript', path=self.diagnostic_path, session=self.session, recording=str(path),
                         text=text, commands_enabled=commands)
            matcher = IntentMatcher(self.data / 'aliases.json')
            windows = inject_windows(context) if commands else None
            result = matcher.parse(text, windows.expansions) if commands else None
            append_event('parsed', path=self.diagnostic_path, session=self.session, recording=str(path),
                         result=result.to_dict() if result else None,
                         command=result.command if result else None, matcher_error=matcher.error)
            GLib.idle_add(self.recognized, text, result)
            if not commands:
                GLib.idle_add(self.complete, 'Ready', 'Transcript updated. No command was run.')
                return
            command = result.command
            if not command:
                choices = '; '.join(dict.fromkeys(c.label for c in result.candidates[:3]))
                GLib.idle_add(self.complete, 'Ready', 'Ambiguous command — use a more specific name: ' + choices if result.status == 'ambiguous'
                              else 'Unrecognized command — no action taken.')
                return
            if result.intent.type in ('focus_window', 'move_named_window', 'maximize_named_window'):
                key = dict(result.intent.arguments)['window']
                action = {'focus_window': focus_named_window, 'move_named_window': move_other_screen,
                          'maximize_named_window': maximize_current_window}[result.intent.type]
                message = action(windows.targets[key])
                GLib.idle_add(self.complete, 'Ready', message)
                return
            named_close = result.intent.type == 'close_named_window'
            learn = result.method == 'fuzzy' and not named_close and command not in NO_LEARN_COMMANDS
            target = windows.targets[dict(result.intent.arguments)['window']] if named_close else None
            if named_close or command in TERMINAL_CLOSE_INTENTS:
                if not named_close:
                    target = terminal_close_target(command, context)
                settings = Settings(self.data / 'settings.json')
                if settings.confirm_terminal_close and terminal_has_jobs(target) is not False:
                    GLib.idle_add(self.offer_confirmation, command, target, text, learn)
                    return
            warning = ''
            if learn:
                try:
                    matcher.learn(text, command)
                except (OSError, ValueError) as exc:
                    warning = f' · Could not remember phrase: {exc}'
            message = self.execute(command, context, target)
            GLib.idle_add(self.complete, 'Ready', message + warning)
        except Exception as exc:
            GLib.idle_add(self.complete, 'Error', f'Could not complete voice command: {exc}. Audio is kept.')

    def recognized(self, text, result):
        self.state.update(transcript=text, intent=result.intent.to_dict() if result and result.intent else None,
                          intent_label=result.selected.label if result and result.selected else '')
        self.publish()

    @staticmethod
    def execute(command, context=None, target=None):
        if command == 'window:hide':
            return hide_current_window(context)
        if command.startswith('move-app:'):
            return move_app_other_screen(command.split(':', 1)[1], context)
        if command in {'terminals:hide', 'apps:hide'}:
            return hide_windows(context, command.split(':', 1)[0])
        if command == 'windows:tile':
            return tile_open_windows(context)
        if command in {'terminals:tile', 'browsers:tile', 'apps:tile'}:
            return {'terminals:tile': tile_terminals, 'browsers:tile': tile_browsers, 'apps:tile': tile_apps}[command](context)
        if command in ('move:other_screen', 'maximize:current_window'):
            action = move_other_screen if command == 'move:other_screen' else maximize_current_window
            return action(window_target(context))
        if target is not None:
            return close_terminal(target)
        return execute_command(command)

    def offer_confirmation(self, command, target, text, learn):
        self.busy = False
        self.recorder = None
        token = uuid4().hex
        self.pending = (token, command, target, text, learn)
        self.state['confirmation'] = dict(token=token, title='Close this terminal?',
            detail=' '.join((target.get('title') or target['class']).split())[:120])
        self.panel_epoch += 1
        self.update('Confirm', 'Closing may stop programs running in this terminal.')
        if self.quit_when_finished:
            self.request_quit()

    def confirm(self, token):
        if self.busy or not self.pending or token != self.pending[0]:
            return
        pending = self.pending
        self.pending = None
        self.state['confirmation'] = None
        self.busy = True
        self.update('Working', 'Closing the confirmed terminal…')
        threading.Thread(target=self.run_confirmed, args=(pending,), daemon=True).start()

    def run_confirmed(self, pending):
        _, command, target, text, learn = pending
        try:
            if learn:
                IntentMatcher(self.data / 'aliases.json').learn(text, command)
            message = self.execute(command, target=target)
            GLib.idle_add(self.complete, 'Ready', message)
        except Exception as exc:
            GLib.idle_add(self.complete, 'Error', f'Could not close terminal: {exc}')

    def cancel(self, token=None):
        if self.pending and (token is None or token == self.pending[0]):
            self.pending = None
            self.state['confirmation'] = None
            self.update('Ready', 'Terminal close cancelled.')

    def complete(self, state, message):
        self.busy = False
        self.recorder = None
        self.state['completed_at'] = time.time()
        self.update(state, message)
        if self.quit_when_finished:
            self.request_quit()

    def retry(self, stem):
        if self.busy or self.model is None or Path(stem).name != stem:
            return
        path = self.data / 'recordings' / (stem + '.wav')
        if not path.is_file():
            return
        self.cancel()
        self.busy = True
        self.show()
        self.update('Working', 'Transcribing saved audio…')
        threading.Thread(target=self.transcribe, args=(path,), daemon=True).start()

    def request_quit(self):
        if self.busy:
            self.quit_when_finished = True
            self.stop_recording()
            return
        self.pending = None
        self.state['confirmation'] = None
        self.update('Stopped', 'Skipper is stopped.')
        connection.close()
        self.quit()


if __name__ == '__main__':
    os.umask(0o077)
    app = VoiceRuntime(show_on_start='--show' in sys.argv)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: (app.request_quit(), False)[1])
    raise SystemExit(app.run([arg for arg in sys.argv if arg != '--show']))
