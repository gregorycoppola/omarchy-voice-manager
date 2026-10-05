"""Shared command runtime. The Omarchy bar provides the text and argument picker."""
from copy import deepcopy
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from uuid import uuid4

from gi.repository import Gio, GLib

from browser_connection import connection
from command_store import CommandStore
import personal_store
from command_catalog import GRAMMAR, INTENTS, NO_LEARN_COMMANDS, COMMAND_SUGGESTIONS, TERMINAL_CLASSES
from diagnostics import append_event, LOG_PATH
from intent_matching import IntentMatcher
from grammar_engine import normalize
from dataset_source import PROVIDER
from corrections import Corrections
from os_actions import (capture_window_context, window_target, execute_command,
                        tile_open_windows, tile_on_monitor, hide_windows, hide_current_window, tile_terminals, tile_browsers, tile_apps, move_other_screen, maximize_current_window,
                        show_selected_window, show_all_windows, terminal_close_target, close_terminal, all_terminal_targets, close_terminals, TERMINAL_CLOSE_INTENTS)
from os_actions import focus_named_window, move_app_other_screen, list_open_windows, open_window_entries, focus_listed_window
from window_vocabulary import inject_windows, terminal_suggestions, window_action_suggestions
from installed_apps import discover_installed_apps, app_suggestions
from open_arguments import parse_open, supports_open
from launch_options import open_with_options
from window_resolution import WindowResolution, needs_window_resolution
from os_actions import tile_selected_windows, close_selected_window, prepare_browser_context, fullscreen_selected_browser, open_installed_app, close_browser_tabs
from screen_recording import execute_recording
from url_entry import normalize_url
from websites import Websites
from site_history import SiteHistory
from os_actions import open_url_in_browser_window
from window_resolution import identity
from system_actions import SYSTEM_ACTIONS, SESSION_END_ACTIONS, execute_system
from os_actions import move_window_workspace, switch_workspace
from settings import Settings
from desktop_commands import DESKTOP_COMMANDS, execute_desktop
from os_actions import run as run_os
from terminal_activity import terminal_has_jobs
from layout_history import LayoutHistory

APP_ID = 'io.github.gregorycoppola.Skipper'
DATA = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'skipper'
STATUS = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp')) / f'skipper-{os.getuid()}-status.json'


class VoiceRuntime(Gio.Application):
    def __init__(self, data=DATA, status_path=STATUS, show_on_start=False):
        super().__init__(application_id=APP_ID)
        self.data = Path(data)
        self.diagnostic_path = LOG_PATH if self.data == DATA else self.data / 'commands.jsonl'
        self.command_store = None
        self.history_error = ''
        try:
            self.command_store = CommandStore(self.diagnostic_path.parent / 'command-history.sqlite3')
            self.command_store.import_log(self.diagnostic_path)
            personal_store.initialize(self.data)
        except (OSError, ValueError, sqlite3.Error):
            self.command_store = None
            self.history_error = 'Command history is unavailable; commands can still run.'
        self.status_path = Path(status_path)
        self.layout_history = LayoutHistory(self.status_path.with_name(f'skipper-{os.getuid()}-layouts.json'), run_os)
        self.started = False
        self.show_on_start = show_on_start
        self.busy = False
        self.quit_when_finished = False
        self.pending = None
        self.pending_correction = None
        self.pending_written = None
        self.refreshing_written = False
        self.site_history = SiteHistory()
        self.sequence = None
        self.window_resolution = None
        self.window_choices = {}
        self.panel_epoch = 0
        self.session = uuid4().hex
        self.diagnostic_recording = None
        self.state = dict(state='Ready', message='Super + R to choose a command.', transcript='',
                          intent=None, intent_label='', monitor='', confirmation=None, clarification=None, correction=None, written_entry=None, window_list=[], input_source='written', written='', completed_at=0,
                          layout_history=self.layout_history.info())
        for name, signature, callback in (
            ('choose-window', 's', self.choose_window),
            ('correct-command', 's', self.correct_command),
            ('type-command', None, self.type_command),
            ('submit-written', 's', self.submit_written),
            ('manage-website', 's', self.manage_website),
            ('begin-website', 's', self.begin_website),
            ('load-audio', 's', self.load_audio),
            ('load-controls', 's', self.load_controls),
            ('search-files', 's', self.search_files),
            ('website-back', 's', self.website_back),
            ('show-correction', None, self.show_correction),
            ('focus-listed-window', 's', self.focus_listed_window),
            ('dismiss-window-list', None, self.dismiss_window_list),
            ('confirm', 's', self.confirm), ('cancel', 's', self.cancel),
            ('quit', None, self.request_quit), ('show', None, self.show),
            ('layout-back', None, lambda: self.navigate_layout(-1)),
            ('layout-forward', None, lambda: self.navigate_layout(1)),
            ('layout-save', None, self.save_layout),
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
        GLib.timeout_add_seconds(2, self.publish)
        GLib.timeout_add(500, self.refresh_written)
        GLib.timeout_add(500, self.poll_layout_history)
        self.publish()
        if self.show_on_start:
            self.show()
        self.update('Ready', 'Super + R to choose a command.')

    def update(self, state, message):
        if state == 'Error':
            self.sequence = None
        append_event('state', path=self.diagnostic_path, session=self.session, recording=self.diagnostic_recording,
                     state=state, message=message)
        self.state.update(state=state, message=message)
        self.publish()

    def publish(self):
        self.state['layout_history'] = self.layout_history.info()
        payload = self.state | dict(updated=time.time(), session=self.session,
                                    panel_epoch=self.panel_epoch)
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

    def poll_layout_history(self):
        if not self.busy:
            try:
                if self.layout_history.observe():
                    self.publish()
            except (OSError, ValueError, RuntimeError) as exc:
                print(f'Could not observe window layout: {exc}', file=sys.stderr)
        return True

    def save_layout(self):
        if self.busy:
            return
        try:
            added = self.layout_history.save_current()
            info = self.layout_history.info()
            self.update('Ready', f'View {info["position"]} of {info["count"]} saved.' if added
                        else 'This view is already saved.')
        except (OSError, ValueError, RuntimeError) as exc:
            self.update('Error', f'Could not save view: {exc}')

    def navigate_layout(self, direction):
        if self.busy:
            return
        self.busy = True
        self.update('Working', 'Restoring previous view…' if direction < 0 else 'Restoring next view…')
        def restore():
            try:
                message = self.layout_history.step(direction)
                GLib.idle_add(self.finish_layout_navigation, 'Ready', message)
            except (OSError, ValueError, RuntimeError) as exc:
                GLib.idle_add(self.finish_layout_navigation, 'Error', f'Could not restore view: {exc}')
        threading.Thread(target=restore, daemon=True).start()

    def finish_layout_navigation(self, state, message):
        self.busy = False
        self.state['completed_at'] = time.time()
        self.update(state, message)

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








    def interpret(self, text, context=None, commands=True, path=None, source='written', expected_command=None):
        """Shared text interpretation for the picker and future speech adapters."""
        try:
            if commands and (context or {}).get('confirmation_token'):
                GLib.idle_add(self.answer_confirmation, context['confirmation_token'], text)
                return
            matcher = IntentMatcher(self.data / 'aliases.json')
            windows = inject_windows(context) if commands else None
            apps = discover_installed_apps(for_picker=True) if commands else None
            expansions = windows.expansions + apps.expansions if commands else ()
            from picker_windows import parse as parse_picker, resolve_target, VERBS
            picker_result = parse_picker(text, context) if commands else None
            result = ((parse_open(text, matcher, expansions) if source == "written" else None) or picker_result or matcher.parse(text, expansions, use_corrections=source == "speech")) if commands else None
            if (commands and source == 'written' and normalize(text).split(' ')[0] in VERBS
                    and picker_result is None and result.method != 'exact'):
                if expected_command is not None:
                    raise RuntimeError('The queued window selection changed. Remaining steps stopped.')
                GLib.idle_add(self.written_error, text, 'Choose a specific window and complete its arguments.')
                return
            if expected_command is not None and (not result or result.command != expected_command):
                raise RuntimeError('A queued command no longer has its original meaning. Remaining steps stopped.')
            append_event('parsed', path=self.diagnostic_path, session=self.session, recording=str(path) if path else None,
                         input_source=source, written=result.correction['meant'] if result and result.correction else text,
                         result=result.to_dict() if result else None,
                         command=result.command if result else None, matcher_error=matcher.error)
            if commands and result and result.command and self.command_store:
                try:
                    self.command_store.record(result.correction['meant'] if result.correction else text,
                                              result.command, source)
                except (OSError, sqlite3.Error):
                    self.history_error = 'Could not save command history.'
            GLib.idle_add(self.recognized, text, result, source)
            if not commands:
                GLib.idle_add(self.complete, 'Ready', 'Transcript updated. No command was run.')
                return
            command = result.command
            if result.intent and result.intent.type == 'picker_tile_pair':
                args = dict(result.intent.arguments)
                selected = [resolve_target(context, args[key]) for key in ('first', 'second')]
                if any(target is None for target in selected):
                    raise RuntimeError('A selected window is no longer available.')
                message = tile_selected_windows(context, selected)
                GLib.idle_add(self.complete, 'Ready', message)
                return
            if result.intent and result.intent.type.startswith('picker_'):
                args = dict(result.intent.arguments)
                target = resolve_target(context, args['window'])
                if target is None:
                    raise RuntimeError('That window is no longer available.')
                verb = result.intent.type.removeprefix('picker_')
                if verb == 'close':
                    settings = Settings(self.data / 'settings.json')
                    if (settings.confirm_terminal_close and target.get('class', '').lower() in TERMINAL_CLASSES
                            and terminal_has_jobs(target) is not False):
                        GLib.idle_add(self.offer_confirmation, 'close:current_window', target, text, False)
                        return
                    message = close_selected_window(target)
                elif verb in ('show', 'move'):
                    workspace = int(args['workspace'])
                    if args.get('monitor'):
                        monitor = next((m for m in json.loads(run_os(['hyprctl', 'monitors', '-j']))
                                        if m.get('name') == args['monitor'] and not m.get('disabled')), None)
                        if not monitor or monitor.get('activeWorkspace', {}).get('id') != workspace:
                            raise RuntimeError('The destination monitor changed. Choose it again.')
                    message = move_window_workspace(target, workspace)
                    if verb == 'show':
                        focus_named_window(target)
                        message = 'Brought the selected window to this workspace.'
                else:
                    message = {'focus': focus_named_window, 'maximize': maximize_current_window,
                               'minimize': lambda t: hide_current_window({'active': t})}[verb](target)
                GLib.idle_add(self.complete, 'Ready', message)
                return
            if not command:
                if source == 'written':
                    GLib.idle_add(self.written_error, text, result.reason or 'No clear command. Try different wording.')
                    return
                GLib.idle_add(self.offer_correction, text, context, str(path))
                return
            if command == 'browser:prompt_url':
                GLib.idle_add(self.offer_url_entry)
                return
            if command == 'browser:prompt_website':
                GLib.idle_add(self.offer_website_entry)
                return
            if command in SYSTEM_ACTIONS:
                GLib.idle_add(self.handle_system_action, command, text)
                return
            if result.launch_options is not None:
                app = apps.targets.get(dict(result.intent.arguments).get('desktop'))
                GLib.idle_add(self.complete, 'Ready', open_with_options(command, result.launch_options, context, app))
                return
            if result.intent.type in ('open_browser_and_tile', 'open_browser_fullscreen'):
                context = prepare_browser_context(context, require_focused=result.intent.type == 'open_browser_and_tile')
            if result.intent.type == 'open_installed_app':
                app = apps.targets[dict(result.intent.arguments)['desktop']]
                GLib.idle_add(self.complete, 'Ready', open_installed_app(app))
                return
            if result.intent.type in ('list_windows', 'list_terminals', 'list_browsers', 'list_x'):
                terminals_only = result.intent.type == 'list_terminals'
                browsers_only = result.intent.type == 'list_browsers'
                x_only = result.intent.type == 'list_x'
                entries = (open_window_entries(application='x') if x_only
                           else open_window_entries(browsers_only=True) if browsers_only
                           else open_window_entries(terminals_only=terminals_only))
                category = 'X windows' if x_only else 'browser windows' if browsers_only else 'terminal windows' if terminals_only else 'windows'
                message = f'{len(entries)} open {category}'
                if not entries:
                    name = 'X windows' if x_only else 'browsers' if browsers_only else 'terminals' if terminals_only else 'windows'
                    message = f'There are no open {name}.'
                GLib.idle_add(self.show_window_list, message, entries)
                return
            if result.intent.type == 'list_application':
                application = dict(result.intent.arguments)['application']
                entries = open_window_entries(application=application)
                message = (f'{len(entries)} open {application} windows' if entries
                           else f'There are no open {application} windows.')
                GLib.idle_add(self.show_window_list, message, entries)
                return
            if needs_window_resolution(result.intent):
                resolution = WindowResolution(result.intent, context)
                GLib.idle_add(self.resolve_windows, resolution)
                return
            if result.intent.type in ('focus_window', 'move_named_window', 'move_named_window_workspace', 'maximize_named_window', 'hide_named_window'):
                key = dict(result.intent.arguments)['window']
                action = {'focus_window': focus_named_window, 'move_named_window': move_other_screen,
                          'move_named_window_workspace': lambda target: move_window_workspace(target, int(dict(result.intent.arguments)['workspace'])),
                          'maximize_named_window': maximize_current_window,
                          'hide_named_window': lambda target: hide_current_window({'active': target})}[result.intent.type]
                message = action(windows.targets[key])
                GLib.idle_add(self.complete, 'Ready', message)
                return
            named_close = result.intent.type == 'close_named_window'
            learn = source == 'speech' and result.method == 'fuzzy' and not named_close and command not in NO_LEARN_COMMANDS
            target = windows.targets[dict(result.intent.arguments)['window']] if named_close else None
            if command == 'terminals:close':
                target = all_terminal_targets(context)
                settings = Settings(self.data / 'settings.json')
                if settings.confirm_terminal_close and any(terminal_has_jobs(t) is not False for t in target):
                    GLib.idle_add(self.offer_confirmation, command, target, text, False)
                    return
            if named_close or command in TERMINAL_CLOSE_INTENTS:
                if not named_close:
                    target = terminal_close_target(command, context)
                settings = Settings(self.data / 'settings.json')
                if (settings.confirm_terminal_close and target.get('class', '').lower() in TERMINAL_CLASSES
                        and terminal_has_jobs(target) is not False):
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
            GLib.idle_add(self.complete, 'Error', f'Could not complete command: {exc}')

    def recognized(self, text, result, source='speech'):
        if source == 'written' and result and result.command:
            self.pending_written = None
            self.state['written_entry'] = None
        self.state.update(input_source=source, written=(result.correction['meant'] if result and result.correction else text),
                          transcript=text, intent=result.intent.to_dict() if result and result.intent else None,
                          intent_label=result.selected.label if result and result.selected else '')
        self.publish()

    def show_window_list(self, message, entries):
        if self.sequence and self.sequence['remaining']:
            self.complete('Ready', message)
            return
        self.sequence = None
        self.busy = False
        # Keep the monitor captured when the voice/typed command began.
        if not self.state.get('monitor'):
            self.state['monitor'] = self.focused_monitor()
        self.state['window_list'] = entries
        self.panel_epoch += 1
        self.update('WindowList', message)

    def dismiss_window_list(self):
        if self.state.get('state') == 'WindowList':
            self.state['window_list'] = []
            self.complete('Ready', 'Window list closed.')

    def focus_listed_window(self, address):
        if self.state.get('state') != 'WindowList' or not any(
                item.get('address') == address for item in self.state.get('window_list', [])):
            return
        entry = next(item for item in self.state['window_list'] if item['address'] == address)
        # The chooser holds exclusive keyboard focus. Remove it before asking
        # Hyprland to focus a regular window on this or another workspace.
        self.state['window_list'] = []
        self.busy = True
        self.update('Working', 'Focusing selected window…')
        GLib.timeout_add(150, self.finish_focus_listed_window, address, entry)

    def finish_focus_listed_window(self, address, entry):
        try:
            message = focus_listed_window(address, expected=entry)
            self.complete('Ready', message)
        except Exception as exc:
            self.complete('Error', f'Could not focus window: {exc}')
        return False

    def command_suggestions(self, context):
        from picker_windows import suggestions
        apps = discover_installed_apps(for_picker=True)
        return (terminal_suggestions(context) + window_action_suggestions(context)
                + app_suggestions(apps) + suggestions(context))

    def static_suggestions(self, context):
        workspace = (context or {}).get('active', {}).get('workspace', {}).get('id')
        active = (context or {}).get('active', {})
        rows = []
        for row in COMMAND_SUGGESTIONS:
            command = row['command']
            if supports_open(command) or command in {'browser_fullscreen', 'browser:open_fullscreen', 'browser:open_tile'}:
                continue  # App opening is offered only by installed desktop entries.
            if command == 'close:current_window' and not active.get('address'):
                continue
            if ((command.startswith(('close:', 'hide:')) and command != 'close:current_window')
                    or command in {'terminals:close', 'browser:close_tabs', 'terminals:hide',
                                   'apps:hide', 'windows:tile_current_browser'}):
                continue  # Open-window commands below supply the relevant targets.
            if command == 'window:hide' and (type(workspace) is not int or workspace <= 0
                                              or active.get('class') == APP_ID):
                continue
            rows.append(row)
        return rows

    def type_command(self):
        if self.pending and not self.busy:
            self.panel_epoch += 1
            self.update('Confirm', 'Press Y or Enter for Yes; N or Escape for No.')
            return
        if self.busy or self.pending_written or self.sequence:
            return
        self.cancel()
        context = capture_window_context()
        self.diagnostic_recording = None
        self.pending_written = dict(token=uuid4().hex, context=deepcopy(context))
        dynamic = self.command_suggestions(context)
        counts = {}
        if self.command_store:
            try:
                counts = self.command_store.written_counts()
            except (OSError, sqlite3.Error):
                self.history_error = 'Could not read command use counts.'
        self.state.update(written_entry=dict(token=self.pending_written['token'], text='', error=self.history_error,
                                             suggestions=self.static_suggestions(context), counts=counts,
                                             dynamic_suggestions=dynamic),
                          input_source='written', written='', transcript='', intent=None, intent_label='',
                          monitor=self.focused_monitor())
        self.panel_epoch += 1
        self.update('TextEntry', 'Type a command and press Enter.')

    def offer_url_entry(self):
        self.busy = False
        self.pending_written = dict(token=uuid4().hex, kind='url')
        self.state.update(written_entry=dict(token=self.pending_written['token'], kind='url',
                                             text='', error='', history=[], suggestions=[],
                                             dynamic_suggestions=[]), monitor=self.focused_monitor())
        self.panel_epoch += 1
        self.update('TextEntry', 'Enter a URL and press Enter to open it.')
        if self.quit_when_finished:
            self.request_quit()

    def begin_website(self, payload):
        if self.busy or not self.pending_written or self.pending_written.get('kind'):
            return
        try:
            request = json.loads(payload)
            if not isinstance(request, dict) or request.get('token') != self.pending_written['token']:
                return
            mode = request.get('mode')
            if mode not in ('new', 'existing'):
                return
            parent = (deepcopy(self.pending_written), deepcopy(self.state['written_entry']))
            parent[1]['text'] = str(request.get('text', ''))[:2000]
            self.offer_website_entry(mode, parent, str(request.get("initial_text", ""))[:2000])
        except (ValueError, TypeError):
            return

    def website_back(self, token):
        if self.busy or not self.pending_written or self.pending_written['token'] != token:
            return
        parent = self.pending_written.get('parent')
        if parent:
            self.pending_written, self.state['written_entry'] = deepcopy(parent)
            self.panel_epoch += 1
            self.update('TextEntry', 'Choose a command and press Tab.')

    def offer_website_entry(self, mode='new', parent=None, initial_text=''):
        try:
            websites = Websites(self.data).view()
        except (OSError, ValueError) as exc:
            self.complete('Error', str(exc))
            return
        self.busy = False
        context = (parent[0].get('context') or {}) if parent else {}
        clients = [c for c in context.get('clients', []) if c.get('mapped', True)
                   and c.get('class', '').lower() in {'chromium', 'chrome', 'google-chrome', 'google-chrome-stable'}
                   and c.get('stableId') and c.get('pid')]
        active = context.get('active') or {}
        target = deepcopy(active) if active.get('class', '').lower() in {'chromium', 'chrome', 'google-chrome', 'google-chrome-stable'} and active.get('stableId') and active.get('pid') else None
        if target is None and len(clients) == 1:
            target = clients[0]
        choices = {uuid4().hex: deepcopy(c) for c in clients} if mode == 'existing' and target is None else {}
        self.pending_written = dict(token=uuid4().hex, kind='website', mode=mode,
                                    target=deepcopy(target), browser_choices=choices, parent=parent, site_draft=initial_text)
        self.state['written_entry'] = dict(token=self.pending_written['token'], kind='website',
            text='' if mode == 'existing' and target is None else initial_text, error='', history=[], suggestions=[], dynamic_suggestions=[],
            most_visited=[], history_loading=True, mode=mode,
            needs_browser=mode == 'existing' and target is None,
            target_label=target.get('title', 'Browser') if target else '',
            browser_choices=[dict(id=key, name=value.get('title') or value.get('class'),
                                  url=key, source='Workspace ' + str(value.get('workspace', {}).get('id', '?')),
                                  browserChoice=True, saved=False)
                             for key, value in choices.items()], **websites)
        if not self.state.get('monitor'):
            self.state['monitor'] = self.focused_monitor()
        self.panel_epoch += 1
        self.update('TextEntry', 'Choose a website. Tab accepts; Enter opens it.')
        self.refresh_site_history(self.pending_written['token'])
        if self.quit_when_finished:
            self.request_quit()

    def manage_website(self, payload):
        if self.busy or not self.pending_written or self.pending_written.get('kind') != 'website':
            return
        try:
            request = json.loads(payload)
            if not isinstance(request, dict) or request.get('token') != self.pending_written['token']:
                return
            if request.get('operation') == 'import_history':
                self.refresh_site_history(request['token'], force=True)
                return
            websites = Websites(self.data)
            if request.get('operation') == 'save':
                websites.save(request.get('name', ''), request.get('url'), request.get('id'))
            elif request.get('operation') == 'remove':
                websites.remove(request.get('id'))
            else:
                raise ValueError('Unknown website action.')
            self.state['written_entry'].update(websites.view(), error='')
            self.publish()
        except (OSError, ValueError) as exc:
            self.written_error(self.state['written_entry'].get('text', ''), str(exc))

    def refresh_site_history(self, token, force=False):
        self.state['written_entry']['history_loading'] = True
        self.publish()
        def refresh():
            try:
                view = self.site_history.refresh(force=force)
            except Exception:
                view = dict(most_visited=[], history_message='Could not read browser history. Enter a web address.')
            GLib.idle_add(self.website_history_imported, token, view, '')
        threading.Thread(target=refresh, daemon=True).start()

    def website_history_imported(self, token, view, message):
        if not self.pending_written or self.pending_written['token'] != token:
            return
        self.state['written_entry'].update(view, history_loading=False)
        self.publish()

    def submit_url(self, text):
        website = self.pending_written.get('kind') == 'website'
        try:
            if website and self.state['written_entry'].get('needs_browser'):
                target = self.pending_written.get('browser_choices', {}).get(text)
                if target is None:
                    raise ValueError('Choose a connected Chrome/Chromium window, or go back and use a new browser.')
                previous = (deepcopy(self.pending_written), deepcopy(self.state['written_entry']))
                self.pending_written['parent'] = previous
                self.pending_written['target'] = deepcopy(target)
                self.state['written_entry'].update(needs_browser=False, text=self.pending_written.get('site_draft', ''),
                    target_label=target.get('title', 'Browser'))
                self.pending_written['token'] = uuid4().hex
                self.state['written_entry']['token'] = self.pending_written['token']
                self.panel_epoch += 1
                self.update('TextEntry', 'Choose a website. Tab accepts; Enter opens it.')
                self.refresh_site_history(self.pending_written['token'])
                return
            url = Websites(self.data).resolve(text) if website else normalize_url(text)
        except (OSError, ValueError) as exc:
            self.written_error(text if isinstance(text, str) else '', str(exc))
            return
        self.busy = True
        self.state['written_entry']['text'] = text
        self.update('Working', 'Opening URL…')
        existing = website and self.pending_written.get('mode') == 'existing'
        target = deepcopy(self.pending_written.get('target'))
        def launch():
            try:
                if existing:
                    open_url_in_browser_window(url, target)
                else:
                    run_os(['omarchy', 'launch', 'browser', *(['--new-window'] if website else []), url])
            except Exception as exc:
                GLib.idle_add(self.written_error, text, f'Could not open URL: {exc}')
                return
            warning = ''
            if website:
                try:
                    Websites(self.data).remember(url)
                except (OSError, ValueError):
                    warning = ' Could not save this site to recents.'
            GLib.idle_add(self.url_opened, website, warning, existing)
        threading.Thread(target=launch, daemon=True).start()

    def url_opened(self, website=False, warning='', existing=False):
        self.pending_written = None
        self.state['written_entry'] = None
        self.complete('Ready', ('Opened website in the selected browser window.' if existing else 'Opened website in a new browser window.' if website else 'Opened URL in your browser.') + warning)

    def refresh_written(self):
        if not self.pending_written or self.busy or self.refreshing_written:
            return True
        if self.pending_written.get('kind') in ('url', 'website'):
            return True
        self.refreshing_written = True
        token = self.pending_written['token']
        def capture():
            try:
                context = capture_window_context()
                dynamic = self.command_suggestions(context)
            except Exception:
                context, dynamic = None, []
            GLib.idle_add(self.apply_written_refresh, token, context, dynamic)
        threading.Thread(target=capture, daemon=True).start()
        return True

    def apply_written_refresh(self, token, context, dynamic):
        self.refreshing_written = False
        if self.busy or not self.pending_written or self.pending_written['token'] != token:
            return
        # Keep the original focused window, but refresh available named targets.
        captured = self.pending_written['context'] or {}
        captured['clients'] = deepcopy((context or {}).get('clients', []))
        captured['monitors'] = deepcopy((context or {}).get('monitors', []))
        self.pending_written['context'] = captured
        entry = self.state['written_entry']
        if entry['dynamic_suggestions'] != dynamic:
            entry.update(dynamic_suggestions=dynamic)
            self.publish()

    def load_audio(self, payload):
        try:
            request = json.loads(payload)
            direction = request.get('direction')
            pending = self.pending_written
            if (self.busy or not pending or pending.get('kind') or direction not in ('input', 'output')
                    or request.get('token') != pending['token']):
                return
            loading = pending.setdefault('audio_loading', set())
            if direction in loading:
                return
            loading.add(direction)
            token = pending['token']
            states = self.state['written_entry'].setdefault('audio', {})
            if direction not in states:
                states[direction] = dict(rows=[], loading=True, error='')
                self.publish()
            def capture():
                from audio_devices import snapshot
                try:
                    rows, error = snapshot(direction), ''
                except (RuntimeError, ValueError, KeyError, TypeError) as exc:
                    rows, error = [], str(exc)
                GLib.idle_add(self.audio_loaded, token, direction, rows, error)
            threading.Thread(target=capture, daemon=True).start()
        except (ValueError, TypeError, AttributeError):
            return

    def audio_loaded(self, token, direction, rows, error):
        pending = self.pending_written
        if not pending or pending['token'] != token:
            return False
        pending.get('audio_loading', set()).discard(direction)
        pending.setdefault('audio_choices', {})[direction] = {row['id']: row['identity'] for row in rows}
        view = [dict(id=row['id'], text=row['text'], label=row['label'],
                     detail=row['detail'], current=row['current']) for row in rows]
        self.state['written_entry'].setdefault('audio', {})[direction] = dict(rows=view, loading=False, error=error)
        self.publish()
        return False

    def submit_audio(self, selection):
        if (not isinstance(selection, dict) or selection.get('direction') not in ('input', 'output')
                or not isinstance(selection.get('id'), str)):
            self.written_error('', 'Choose an audio device from the list.')
            return
        identity = self.pending_written.get('audio_choices', {}).get(selection.get('direction'), {}).get(selection.get('id'))
        if identity is None:
            self.written_error('', 'That device is no longer available. Choose it again.')
            return
        self.busy = True
        self.pending_written = None
        self.state['written_entry'] = None
        self.update('Working', 'Changing the default audio device…')
        def change():
            from audio_devices import set_default
            try:
                message = set_default(identity)
                GLib.idle_add(self.complete, 'Ready', message)
            except (RuntimeError, ValueError, KeyError, TypeError) as exc:
                GLib.idle_add(self.complete, 'Error', str(exc))
        threading.Thread(target=change, daemon=True).start()

    def load_controls(self, token):
        pending = self.pending_written
        if self.busy or not pending or pending.get('kind') or pending['token'] != token or pending.get('controls_loading'):
            return
        pending['controls_loading'] = True
        if 'controls' not in self.state['written_entry']:
            self.state['written_entry']['controls'] = dict(rows=[], loading=True, error='')
            self.publish()
        def capture():
            from system_controls import snapshot
            try:
                rows, error = snapshot(), ''
            except Exception:
                rows, error = [], 'System controls are unavailable.'
            GLib.idle_add(self.controls_loaded, token, rows, error)
        threading.Thread(target=capture, daemon=True).start()

    def controls_loaded(self, token, rows, error):
        pending = self.pending_written
        if not pending or pending['token'] != token:
            return False
        pending['controls_loading'] = False
        pending['control_choices'] = {row['id']: row['selection'] for row in rows if row['available']}
        self.state['written_entry']['controls'] = dict(loading=False, error=error,
            rows=[{key: row[key] for key in ('id', 'verb', 'label', 'text', 'detail', 'available')} for row in rows])
        self.publish()
        return False

    def submit_control(self, key):
        selection = self.pending_written.get('control_choices', {}).get(key) if isinstance(key, str) else None
        if selection is None:
            self.written_error('', 'That system control is unavailable. Choose an available option.')
            return
        self.busy = True
        self.pending_written = None
        self.state['written_entry'] = None
        self.update('Working', 'Setting the requested system state…')
        def change():
            from system_controls import execute
            try:
                GLib.idle_add(self.complete, 'Ready', execute(selection))
            except Exception as exc:
                GLib.idle_add(self.complete, 'Error', f'Could not set the requested state: {exc}')
        threading.Thread(target=change, daemon=True).start()

    def search_files(self, payload):
        try:
            request = json.loads(payload)
            pending = self.pending_written
            if (self.busy or not pending or pending.get('kind')
                    or request.get('token') != pending['token']):
                return
            query = request.get('query', '')
            if not isinstance(query, str) or len(query) > 2000:
                return
            query = query.strip()
            previous = getattr(self, '_file_search_cancel', None)
            if previous is not None:
                previous.set()
            cancel = threading.Event()
            self._file_search_cancel = cancel
            generation = uuid4().hex
            pending['file_generation'] = generation
            pending['file_choices'] = {}
            token = pending['token']
            self.state['written_entry']['files'] = dict(query=query, rows=[], loading=True, error='', limited=False)
            self.publish()
            def capture():
                from file_search import search
                try:
                    rows, limited = search(query, cancel)
                    error = ''
                except (OSError, RuntimeError, ValueError) as exc:
                    rows, limited, error = [], False, str(exc)
                if not cancel.is_set():
                    GLib.idle_add(self.files_loaded, token, generation, query, rows, limited, error)
            threading.Thread(target=capture, daemon=True).start()
        except (ValueError, TypeError, AttributeError):
            return

    def files_loaded(self, token, generation, query, rows, limited, error):
        pending = self.pending_written
        if not pending or pending['token'] != token or pending.get('file_generation') != generation:
            return False
        pending['file_choices'] = {row['id']: row['identity'] for row in rows}
        self.state['written_entry']['files'] = dict(query=query, loading=False, error=error, limited=limited,
            rows=[{key: row[key] for key in ('id', 'label', 'detail', 'text')} for row in rows])
        self.publish()
        return False

    def submit_file(self, selection):
        captured = self.pending_written.get('file_choices', {}).get(selection) if isinstance(selection, str) else None
        if captured is None:
            self.written_error('', 'Choose a file from the current search results.')
            return
        self.busy = True
        self.pending_written = None
        self.state['written_entry'] = None
        self.update('Working', 'Opening the selected file…')
        def launch():
            from file_search import open_file
            try:
                GLib.idle_add(self.complete, 'Ready', open_file(captured))
            except (OSError, RuntimeError, ValueError) as exc:
                GLib.idle_add(self.complete, 'Error', str(exc))
        threading.Thread(target=launch, daemon=True).start()

    def submit_written(self, payload):
        if self.busy or not self.pending_written:
            return
        try:
            request = json.loads(payload)
            if not isinstance(request, dict) or request.get('token') != self.pending_written['token']:
                return
            if 'audio' in request and not self.pending_written.get('kind'):
                self.submit_audio(request['audio'])
                return
            if 'file' in request and not self.pending_written.get('kind'):
                self.submit_file(request['file'])
                return
            if 'control' in request and not self.pending_written.get('kind'):
                self.submit_control(request['control'])
                return
            if self.pending_written.get('kind') in ('url', 'website'):
                self.submit_url(request.get('text'))
                return
            if 'steps' in request:
                self.submit_sequence(request['steps'])
                return
            text = request.get('text')
            normalized = normalize(text) if isinstance(text, str) else ''
            if normalized.split(' ')[0] in ('enable', 'disable', 'connect', 'disconnect'):
                self.written_error(text, 'Choose an available system control, then press Enter.')
                return
            if normalized == 'open file' or normalized.startswith('open file '):
                self.written_error(text, 'Search for a file in Open → file, then select a result.')
                return
            if normalized.startswith(('switch audio output', 'switch microphone')):
                self.written_error(text, 'Select a device from the audio list, then press Enter.')
                return
            mode = next((mode for mode in ('new', 'existing') if normalized in {
                f'open website in {mode} browser', f'open web site in {mode} browser',
                f'open a website in a {mode} browser', f'open a website in an {mode} browser',
                f'open a web site in a {mode} browser', f'open a web site in an {mode} browser',
                f'open website in an {mode} browser', f'open website in a {mode} browser'}), None)
            if mode:
                self.begin_website(json.dumps(dict(token=request['token'], mode=mode, text=text)))
                return
            if not isinstance(text, str) or not text.strip() or len(text) > 2000:
                self.written_error('', 'Type a command, up to 2000 characters.')
                return
            text = text.strip()
            context = self.pending_written['context']
            append_event('written_input', path=self.diagnostic_path, session=self.session,
                         text=text, context=context, input_source='written')
            self.busy = True
            self.state['written_entry']['text'] = text
            self.update('Working', 'Understanding your written command…')
            threading.Thread(target=self.interpret, args=(text, context), daemon=True).start()
        except ValueError:
            self.written_error('', 'Could not read the typed command.')

    def submit_sequence(self, steps):
        if (not isinstance(steps, list) or not 1 <= len(steps) <= 20
                or any(not isinstance(text, str) or not text.strip() or len(text) > 2000 for text in steps)):
            self.written_error('', 'Use 1–20 commands, each up to 2000 characters.')
            return
        context = self.pending_written['context']
        matcher = IntentMatcher(self.data / 'aliases.json')
        windows = inject_windows(context)
        apps = discover_installed_apps(for_picker=True)
        expansions = windows.expansions + apps.expansions
        prepared = []
        for index, text in enumerate(steps, 1):
            from picker_windows import parse as parse_picker, VERBS
            result = parse_open(text.strip(), matcher, expansions) or parse_picker(text.strip(), context) or matcher.parse(text.strip(), expansions, use_corrections=False)
            if result.method != 'exact' and normalize(text).split(' ')[0] in VERBS:
                self.written_error('', f'Step {index}: choose a specific window and complete its arguments.')
                return
            if not result.command:
                self.written_error('', f'Step {index} is not a recognized command. Nothing ran.')
                return
            prepared.append((text.strip(), result.command))
        self.sequence = dict(remaining=prepared, total=len(prepared), index=0)
        self.pending_written = None
        self.state['written_entry'] = None
        self.next_sequence_step(context)

    def next_sequence_step(self, context=None):
        if not self.sequence:
            return False
        text, expected = self.sequence['remaining'].pop(0)
        self.sequence['index'] += 1
        self.busy = True
        self.update('Working', f"Step {self.sequence['index']} of {self.sequence['total']}: {text}")
        def execute_step():
            current = context if context is not None else capture_window_context()
            self.interpret(text, current, expected_command=expected)
        threading.Thread(target=execute_step, daemon=True).start()
        return False

    def written_error(self, text, message):
        self.busy = False
        if self.pending_written:
            self.state['written_entry'].update(text=text, error=message)
            self.panel_epoch += 1
            self.update('TextEntry', message)

    def offer_correction(self, heard, context, recording):
        self.busy = False
        if not heard.strip():
            self.complete('Ready', 'No command entered. Please try again.')
            return
        token = uuid4().hex
        self.pending_correction = dict(token=token, heard=heard, context=deepcopy(context), recording=recording)
        self.state['correction'] = dict(token=token, heard=heard, preview=None, error='')
        self.panel_epoch += 1
        self.update('Correction', f'I heard “{heard}”, but I wasn’t sure what you meant.')
        self.show_correction()
        if self.quit_when_finished:
            self.request_quit()

    def show_correction(self):
        if self.pending_correction:
            self.show()

    def correct_command(self, payload):
        if self.busy or not self.pending_correction:
            return
        try:
            request = json.loads(payload)
            pending = self.pending_correction
            if not isinstance(request, dict) or request.get('token') != pending['token']:
                return
            said, meant = request.get('said', ''), request.get('meant', '')
            if not isinstance(said, str) or not isinstance(meant, str):
                raise ValueError('Enter text for the spoken words and intended command.')
            said, meant = said.strip(), meant.strip() or said.strip()
            if not said or max(len(said), len(meant)) > 2000:
                raise ValueError('Enter the words you said (up to 2000 characters).')
            windows = inject_windows(pending['context'])
            result = IntentMatcher(self.data / 'aliases.json').parse(meant, windows.expansions, use_corrections=False)
            if not result.intent or result.method not in ('exact', 'alias'):
                raise ValueError('I still cannot identify one action. Try a supported command, such as “tile all windows”.')
            preview = dict(said=said, meant=meant, intent=result.intent.to_dict(), label=result.selected.label)
            if request.get('operation') == 'preview':
                self.state['correction'].update(preview=preview, error='')
                self.publish()
                return
            if request.get('operation') != 'save':
                raise ValueError('Unknown correction operation.')
            if preview != self.state['correction'].get('preview'):
                raise ValueError('Check the intended action before saving.')
            Corrections(self.data / 'corrections.json').save_wording(
                pending['heard'], said, meant, result, pending['recording'])
            append_event('correction_saved', path=self.diagnostic_path, session=self.session,
                         recording=pending['recording'], heard=pending['heard'], said=said,
                         meant=meant, intent=result.intent.to_dict())
            self.pending_correction = None
            self.state['correction'] = None
            self.complete('Ready', 'Correction saved. Say the command again to use it.')
        except (ValueError, OSError, TypeError) as exc:
            self.state['correction'].update(preview=None, error=str(exc))
            self.publish()

    @staticmethod
    def execute(command, context=None, target=None):
        if command.startswith('workspace:switch:'):
            return switch_workspace(int(command.rsplit(':', 1)[1]))
        if command.startswith('window:move-workspace:'):
            return move_window_workspace(window_target(context), int(command.rsplit(':', 1)[1]))
        if command in SYSTEM_ACTIONS:
            return execute_system(command)
        if command in ("screenrecord:start", "screenrecord:start_without_webcam", "screenrecord:stop"):
            return execute_recording(command.split(":")[1], run_os)
        if ':tile-monitor:' in command:
            category, _, number = command.split(':')
            return tile_on_monitor(category, int(number))
        if command == 'terminals:close':
            return close_terminals(target if target is not None else all_terminal_targets(context))
        if command in DESKTOP_COMMANDS:
            return execute_desktop(command, run_os, context)
        if command == 'close:current_window':
            return close_selected_window(target or window_target(context))
        if command == 'window:hide':
            return hide_current_window(context)
        if command.startswith('show-all:'):
            return show_all_windows(context, command.split(':', 1)[1])
        if command.startswith('move-app:'):
            return move_app_other_screen(command.split(':', 1)[1], context)
        if command in {'terminals:hide', 'apps:hide'}:
            return hide_windows(context, command.split(':', 1)[0])
        if command in ('windows:tile', 'windows'):
            return tile_open_windows(context)
        if command in {'terminals:tile', 'browsers:tile', 'apps:tile'}:
            return {'terminals:tile': tile_terminals, 'browsers:tile': tile_browsers, 'apps:tile': tile_apps}[command](context)
        if command in ('move:other_screen', 'maximize:current_window'):
            action = move_other_screen if command == 'move:other_screen' else maximize_current_window
            return action(window_target(context))
        if target is not None:
            return (close_terminal(target) if target.get('class', '').lower() in TERMINAL_CLASSES
                    else close_selected_window(target))
        return execute_command(command)

    def resolve_windows(self, resolution):
        self.window_resolution = resolution
        self.busy = False
        try:
            question = resolution.advance()
            if question is None:
                self.window_resolution = None
                self.window_choices = {}
                self.state['clarification'] = None
                self.busy = True
                showing = resolution.intent.type == 'show_application'
                hiding = resolution.intent.type == 'hide_application'
                closing = resolution.intent.type == 'close_window'
                clearing_tabs = resolution.intent.type == 'close_browser_tabs'
                fullscreen = resolution.intent.type == 'open_browser_fullscreen'
                self.update('Working', 'Showing the selected window…' if showing else 'Hiding the selected window…' if hiding else 'Closing tabs in the selected browser…' if clearing_tabs else 'Closing the selected window…' if closing else 'Opening the browser in full screen…' if fullscreen else 'Tiling the selected windows…')
                threading.Thread(target=self.run_show_selection if showing else self.run_hide_selection if hiding else self.run_close_browser_tabs if clearing_tabs else self.run_close_selection if closing else self.run_browser_fullscreen if fullscreen else self.run_tile_pair, args=(resolution,), daemon=True).start()
                return
            self.window_choices = {}
            choices = []
            for index, target in enumerate(question.candidates):
                token = uuid4().hex
                self.window_choices[token] = (question, index)
                title = ' '.join((target.get('title') or target['class']).split())[:100]
                workspace = target.get('workspace', {}).get('name') or target.get('workspace', {}).get('id')
                choices.append(dict(token=token, label=f'{index + 1}. {title} · Workspace {workspace}'))
            self.state['clarification'] = dict(prompt=question.prompt, choices=choices)
            self.panel_epoch += 1
            self.update('Choose', question.prompt)
        except Exception as exc:
            self.window_resolution = None
            self.window_choices = {}
            self.state['clarification'] = None
            self.complete('Error', str(exc))

    def choose_window(self, token):
        if self.busy or not self.window_resolution or token not in self.window_choices:
            return
        resolution = self.window_resolution
        question, index = self.window_choices[token]
        resolution.choose(question, index)
        self.resolve_windows(resolution)

    def run_show_selection(self, resolution):
        try:
            message = show_selected_window(resolution.resolved['window'])
            GLib.idle_add(self.complete, 'Ready', message)
        except Exception as exc:
            GLib.idle_add(self.complete, 'Error', f'Could not show the selected window: {exc}')

    def run_hide_selection(self, resolution):
        try:
            message = hide_current_window({'active': resolution.resolved['window']})
            GLib.idle_add(self.complete, 'Ready', message)
        except Exception as exc:
            GLib.idle_add(self.complete, 'Error', f'Could not hide the selected window: {exc}')

    def run_close_browser_tabs(self, resolution):
        try:
            message = close_browser_tabs(resolution.resolved['window'])
            GLib.idle_add(self.complete, 'Ready', message)
        except Exception as exc:
            GLib.idle_add(self.complete, 'Error', f'Could not close browser tabs: {exc}')

    def run_browser_fullscreen(self, resolution):
        try:
            message = fullscreen_selected_browser(resolution.context, resolution.resolved['window'])
            GLib.idle_add(self.complete, 'Ready', message)
        except Exception as exc:
            GLib.idle_add(self.complete, 'Error', f'Could not open the browser in full screen: {exc}')

    def run_close_selection(self, resolution):
        try:
            message = close_selected_window(resolution.resolved['window'])
            GLib.idle_add(self.complete, 'Ready', message)
        except Exception as exc:
            GLib.idle_add(self.complete, 'Error', f'Could not close the selected window: {exc}')

    def run_tile_pair(self, resolution):
        try:
            message = tile_selected_windows(resolution.context,
                [resolution.resolved[slot] for slot in ('first', 'second')])
            GLib.idle_add(self.complete, 'Ready', message)
        except Exception as exc:
            GLib.idle_add(self.complete, 'Error', f'Could not tile the selected windows: {exc}')

    def handle_system_action(self, command, text):
        # Ending or suspending the session is the end of a queued command batch.
        self.sequence = None
        if command in SESSION_END_ACTIONS:
            self.busy = False
            token = uuid4().hex
            self.pending = (token, command, None, text, False)
            label = SYSTEM_ACTIONS[command][0]
            self.state['confirmation'] = dict(token=token, title=f'{label} this computer?',
                detail='This ends your session and closes application windows. Save your work first.')
            self.panel_epoch += 1
            self.update('Confirm', 'Press Enter / Y to continue, or Escape / N to cancel.')
        else:
            self.busy = True
            self.update('Working', f'{SYSTEM_ACTIONS[command][0]} requested…')
            threading.Thread(target=self.run_confirmed,
                             args=((None, command, None, text, False),), daemon=True).start()

    def offer_confirmation(self, command, target, text, learn):
        self.busy = False
        token = uuid4().hex
        self.pending = (token, command, target, text, learn)
        batch = command == 'terminals:close'
        self.state['confirmation'] = dict(token=token,
            title=f'Close all {len(target)} terminals?' if batch else 'Close this terminal?',
            detail='Across all workspaces. Only terminals captured when this command started.' if batch
                else ' '.join((target.get('title') or target['class']).split())[:120])
        self.panel_epoch += 1
        self.update('Confirm', 'Closing may stop programs running in these terminals.' if batch
                    else 'Closing may stop programs running in this terminal.')
        if self.quit_when_finished:
            self.request_quit()

    def answer_confirmation(self, token, text):
        if not self.pending or self.pending[0] != token:
            return
        self.busy = False
        answers = PROVIDER['language_policy'].get('confirmation_responses', {})
        answer = normalize(text)
        if answer in answers.get('yes', []):
            self.confirm(token)
        elif answer in answers.get('no', []):
            self.cancel(token)
        else:
            self.panel_epoch += 1
            self.update('Confirm', 'Please answer yes or no, or use Y / N on the keyboard.')

    def confirm(self, token):
        if self.busy or not self.pending or token != self.pending[0]:
            return
        pending = self.pending
        self.pending = None
        self.state['confirmation'] = None
        self.busy = True
        self.update('Working', f'{SYSTEM_ACTIONS[pending[1]][0]} requested…' if pending[1] in SYSTEM_ACTIONS
                    else 'Closing the confirmed terminals…' if pending[1] == 'terminals:close'
                    else 'Closing the confirmed terminal…')
        threading.Thread(target=self.run_confirmed, args=(pending,), daemon=True).start()

    def run_confirmed(self, pending):
        _, command, target, text, learn = pending
        try:
            if learn:
                IntentMatcher(self.data / 'aliases.json').learn(text, command)
            message = self.execute(command, target=target)
            GLib.idle_add(self.complete, 'Ready', message)
        except Exception as exc:
            GLib.idle_add(self.complete, 'Error', f'Could not complete system action: {exc}' if command in SYSTEM_ACTIONS
                          else f'Could not close terminal: {exc}')

    def cancel(self, token=None):
        if token in (None, '') or (self.pending and token == self.pending[0]):
            self.sequence = None
        if self.pending_written and token in (None, '', self.pending_written['token']):
            is_url = self.pending_written.get('kind') in ('url', 'website')
            self.sequence = None
            self.pending_written = None
            self.state['written_entry'] = None
            self.update('Ready', 'URL entry cancelled.' if is_url else 'Written command cancelled.')
        if self.pending_correction and token in (None, '', self.pending_correction['token']):
            self.pending_correction = None
            self.state['correction'] = None
            self.update('Ready', 'Correction cancelled. Nothing was saved or run.')
        if self.window_resolution and token in (None, ''):
            self.window_resolution = None
            self.window_choices = {}
            self.state['clarification'] = None
            self.update('Ready', 'Window selection cancelled.')
        if self.pending and (token is None or token == self.pending[0]):
            system_action = self.pending[1] in SYSTEM_ACTIONS
            self.pending = None
            self.state['confirmation'] = None
            self.update('Ready', 'System action cancelled.' if system_action else 'Terminal close cancelled.')

    def complete(self, state, message):
        if state == 'Ready':
            try:
                self.layout_history.observe(force=True)
            except (OSError, ValueError, RuntimeError) as exc:
                print(f'Could not record window layout: {exc}', file=sys.stderr)
        if self.sequence:
            if state == 'Ready' and self.sequence['remaining'] and not self.quit_when_finished:
                self.busy = True
                GLib.idle_add(self.next_sequence_step)
                return
            if state == 'Ready':
                message = f"Finished {self.sequence['total']} commands. " + message
            self.sequence = None
        self.busy = False
        self.state['completed_at'] = time.time()
        self.update(state, message)
        if self.quit_when_finished:
            self.request_quit()


    def request_quit(self):
        self.sequence = None
        if self.busy:
            self.quit_when_finished = True
            return
        self.pending = None
        self.pending_correction = None
        self.state['correction'] = None
        self.state['confirmation'] = None
        self.window_resolution = None
        self.window_choices = {}
        self.state['clarification'] = None
        self.pending_written = None
        self.state['written_entry'] = None
        self.update('Stopped', 'Skipper is stopped.')
        connection.close()
        self.quit()


if __name__ == '__main__':
    os.umask(0o077)
    app = VoiceRuntime(show_on_start='--show' in sys.argv)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: (app.request_quit(), False)[1])
    raise SystemExit(app.run([arg for arg in sys.argv if arg != '--show']))
