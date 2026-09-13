"""Keety's native GTK4 desktop window."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from keety import load_model
from recordings import new_recording, save_transcript
from live_audio import read_growing_wav
from level_meter import LevelMeter, pcm_level
from os_actions import execute_command
from command_catalog import GRAMMAR, INTENTS
from intent_matching import IntentMatcher
from push_to_talk import PushToTalk

DATA = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "keety/recordings"


class Keety(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.github.gregorycoppola.Keety")
        self.window = None
        self.model = None
        self.busy = False
        self.recorder = None
        self.player = None
        self.selected = None
        self.paths = []
        self.active_path = None
        self.stop_requested = False
        self.matcher = IntentMatcher(DATA.parent / "aliases.json")
        self.pending_suggestion = None
        self.ptt_held = False
        self.ptt_owned = False
        self.ptt = PushToTalk(self.ptt_press, self.ptt_release)
        action = Gio.SimpleAction.new("ptt-event", GLib.VariantType.new("s"))
        action.connect("activate", lambda _, value: self.ptt.event(value.get_string()))
        self.add_action(action)
        GLib.timeout_add(50, self.ptt.check_held)

    def do_activate(self):
        if self.window:
            self.window.present()
            return
        DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.window = Gtk.ApplicationWindow(application=self, title="Keety")
        self.window.set_default_size(760, 620)
        self.window.connect("close-request", self.on_close)
        header = Gtk.HeaderBar()
        header.set_title_widget(Gtk.Label(label="Keety · Voice commands"))
        self.window.set_titlebar(header)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ["top", "bottom", "start", "end"]:
            getattr(box, "set_margin_" + side)(16)
        # Keep every control reachable when Hyprland tiles this into a short window.
        page = Gtk.ScrolledWindow()
        page.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        page.set_child(box)
        self.window.set_child(page)
        title = Gtk.Label(label="Speak a command.", xalign=0)
        title.add_css_class("title-1")
        box.append(title)
        subtitle = Gtk.Label(label="Hold Super + R to talk. Release to transcribe and run your command.", xalign=0, wrap=True)
        subtitle.add_css_class("dim-label")
        box.append(subtitle)
        commands_label = Gtk.Label(label="Commands — Chrome · Gmail · GitHub · Discord · X / Twitter · Windows", xalign=0)
        commands_label.set_tooltip_text("Accepted phrases:\n" + "\n".join(GRAMMAR))
        box.append(commands_label)
        vocabulary = Gtk.Expander(label="Accepted commands")
        phrases = Gtk.Label(label="\n".join(GRAMMAR), xalign=0, selectable=True)
        vocabulary.set_child(phrases)
        box.append(vocabulary)
        learned = Gtk.Expander(label="Learned phrases")
        self.learned_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        learned.set_child(self.learned_list)
        box.append(learned)
        self.refresh_aliases()
        box.append(Gtk.Label(label="Records only while Super + R is held · up to 30 seconds", xalign=0))
        self.status = Gtk.Label(label="Loading local speech model…", xalign=0, wrap=True)
        self.status.set_selectable(True)
        progress = Gtk.Box(spacing=10)
        self.spinner = Gtk.Spinner()
        self.spinner.start()
        progress.append(self.spinner)
        progress.append(self.status)
        self.status.set_hexpand(True)
        box.append(progress)
        self.suggestion_dialog = Gtk.Window(
            title="Keety — Confirm command", application=self, transient_for=self.window,
            modal=True, destroy_with_parent=True, resizable=False)
        self.suggestion_dialog.set_default_size(560, 280)
        self.suggestion_dialog.connect("close-request", self.close_suggestion)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.suggestion_key)
        self.suggestion_dialog.add_controller(keys)
        self.suggestion_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        for side in ["top", "bottom", "start", "end"]:
            getattr(self.suggestion_box, "set_margin_" + side)(28)
        self.suggestion_dialog.set_child(self.suggestion_box)
        heading = Gtk.Label(label="Did you mean…?", xalign=0)
        heading.add_css_class("title-1")
        self.suggestion_box.append(heading)
        self.suggestion_label = Gtk.Label(xalign=0, wrap=True)
        self.suggestion_label.add_css_class("title-2")
        self.suggestion_box.append(self.suggestion_label)
        self.heard_label = Gtk.Label(xalign=0, wrap=True)
        self.suggestion_box.append(self.heard_label)
        confirmation = Gtk.Box(spacing=8)
        self.confirm = Gtk.Button(label="Yes — run and remember")
        self.confirm.add_css_class("suggested-action")
        self.confirm.connect("clicked", self.accept_suggestion)
        confirmation.append(self.confirm)
        self.reject = Gtk.Button(label="No")
        self.reject.connect("clicked", self.dismiss_suggestion)
        confirmation.append(self.reject)
        self.suggestion_box.append(confirmation)
        self.suggestion_dialog.set_default_widget(self.reject)
        self.meter = LevelMeter()
        box.append(self.meter)
        self.level_label = Gtk.Label(label="Microphone idle · everything stays on this computer", xalign=0)
        self.level_label.add_css_class("dim-label")
        box.append(self.level_label)
        self.history = Gtk.DropDown()
        self.history.connect("notify::selected", self.select_recording)
        box.append(self.history)
        self.text = Gtk.TextView(editable=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.text.set_top_margin(16)
        self.text.set_bottom_margin(16)
        self.text.set_left_margin(16)
        self.text.set_right_margin(16)
        scroll = Gtk.ScrolledWindow(vexpand=True, min_content_height=120)
        scroll.set_child(self.text)
        scroll.add_css_class("card")
        box.append(scroll)
        actions = Gtk.Box(spacing=12)
        self.copy = Gtk.Button(label="Copy text")
        self.copy.connect("clicked", self.copy_text)
        actions.append(self.copy)
        self.play = Gtk.Button(label="Play recording")
        self.play.connect("clicked", self.play_recording)
        actions.append(self.play)
        self.retry = Gtk.Button(label="Transcribe again")
        self.retry.connect("clicked", self.retry_transcription)
        self.retry.set_sensitive(False)
        actions.append(self.retry)
        folder = Gtk.Button(label="Open folder")
        folder.connect("clicked", self.open_folder)
        actions.append(folder)
        box.append(actions)
        location = Gtk.Label(label=str(DATA), xalign=0, selectable=True, wrap=True)
        location.add_css_class("dim-label")
        box.append(location)
        self.refresh_history()
        self.window.present()
        threading.Thread(target=self.prepare, daemon=True).start()

    def prepare(self):
        try:
            self.model, _ = load_model(4)
            GLib.idle_add(self.ready)
        except Exception as exc:
            GLib.idle_add(self.status.set_text, f"Could not load model: {exc}")

    def ready(self):
        self.spinner.stop()
        self.retry.set_sensitive(self.selected is not None)
        self.status.set_text(self.matcher.error or "Ready. Hold Super + R to speak.")
        if self.ptt_held:
            self.begin_ptt()

    def ptt_press(self):
        self.ptt_held = True
        if self.model is None:
            self.status.set_text("Loading model… keep holding Super + R.")
            return
        self.begin_ptt()

    def begin_ptt(self):
        if self.busy:
            self.status.set_text("Still finishing the previous take. Release and hold Super + R again.")
            return
        self.start_recording()
        self.ptt_owned = self.recorder is not None

    def ptt_release(self):
        self.ptt_held = False
        if self.ptt_owned:
            self.ptt_owned = False
            self.stop_recording()

    def refresh_history(self, select=None):
        self.paths = sorted(DATA.glob("*.wav"), reverse=True)
        labels = [p.stem.replace("_", " ") for p in self.paths]
        self.history.set_model(Gtk.StringList.new(labels or ["No recordings yet"]))
        index = self.paths.index(select) if select in self.paths else 0
        self.history.set_selected(index)
        self.select_recording()

    def select_recording(self, *_):
        self.dismiss_suggestion()
        index = self.history.get_selected()
        self.selected = self.paths[index] if index < len(self.paths) else None
        text = "Your transcript will appear here and stay here after recording."
        if self.selected:
            transcript = self.selected.with_suffix(".txt")
            if transcript.exists():
                text = transcript.read_text()
            else:
                text = "Audio saved. No transcript yet; use Transcribe again to retry."
        self.text.get_buffer().set_text(text)
        self.copy.set_sensitive(bool(self.selected and self.selected.with_suffix(".txt").exists()))
        self.play.set_sensitive(self.selected is not None and not self.busy)
        self.retry.set_sensitive(self.selected is not None and self.model is not None and not self.busy)

    def set_busy(self, value):
        self.busy = value
        if value:
            self.dismiss_suggestion()
        self.history.set_sensitive(not value)
        self.play.set_sensitive(not value and self.selected is not None)
        self.retry.set_sensitive(not value and self.selected is not None and self.model is not None)

    def start_recording(self, *_):
        if self.busy or self.model is None:
            return
        path = None
        try:
            if self.player and self.player.poll() is None:
                self.player.terminate()
            path = new_recording(DATA)
            self.recorder = subprocess.Popen([
                "pw-record", "--rate", "16000", "--channels", "1", "--format", "s16",
                "--sample-count", "480000", str(path),
            ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        except OSError as exc:
            if path and path.stat().st_size == 0:
                path.unlink()
            self.status.set_text(f"Could not start recording: {exc}")
            return
        self.set_busy(True)
        self.active_path = path
        self.stop_requested = False
        self.meter_bytes = 0
        self.meter.reset()
        self.last_audio_at = time.monotonic()
        self.copy.set_sensitive(False)
        self.text.get_buffer().set_text("Recording your voice. Your transcript will appear automatically when recording stops.")
        self.record_start = time.monotonic()
        self.status.set_text("Recording… keep holding Super + R. Release to transcribe.")
        GLib.timeout_add(50, self.tick, path)
        threading.Thread(target=self.finish_recording,
                         args=(path, self.recorder), daemon=True).start()

    def tick(self, path):
        if self.active_path != path or not self.recorder or self.recorder.poll() is not None:
            return False
        seconds = min(30, int(time.monotonic() - self.record_start))
        if not self.stop_requested:
            self.status.set_text(f"● Recording · {seconds}s / 30s — release Super + R to transcribe")
        try:
            pcm = read_growing_wav(path)
            if pcm and len(pcm) > self.meter_bytes:
                # Display newly captured samples, not old audio or a decorative pulse.
                fresh = pcm[self.meter_bytes:]
                level, db = pcm_level(fresh[-3200:])
                self.meter_bytes = len(pcm)
                self.last_audio_at = time.monotonic()
                self.meter.push(level)
                self.level_label.set_text(f"Microphone level · {db:.0f} dBFS" if db > -60 else "Microphone connected · very quiet")
            else:
                self.meter.push(0)
                if time.monotonic() - self.last_audio_at > 2:
                    self.level_label.set_text("Waiting for microphone audio…")
        except (OSError, ValueError) as exc:
            self.level_label.set_text(f"Level display unavailable: {exc}")
        return True

    def stop_recording(self, *_):
        if self.recorder and self.recorder.poll() is None:
            self.stop_requested = True
            try:
                self.recorder.send_signal(signal.SIGINT)
            except ProcessLookupError:
                pass
        if self.busy:
            self.spinner.start()
            self.status.set_text("Stopping and transcribing…")

    def processing(self):
        self.recorder = None
        self.spinner.start()
        self.meter.active = False
        self.meter.queue_draw()
        self.level_label.set_text("Recording saved · microphone stopped")
        self.status.set_text("Audio saved. Transcribing locally…")

    def finish_recording(self, path, process):
        try:
            _, error = process.communicate(timeout=45)
            # This installed pw-record returns 1 on a requested SIGINT stop, even
            # after correctly finalizing the WAV. Validate/transcribe that audio.
            requested_stop = self.stop_requested and process.returncode == 1
            if process.returncode not in (0, -signal.SIGINT) and not requested_stop:
                raise RuntimeError(f"Recorder exited {process.returncode}: {error.strip()}")
            GLib.idle_add(self.processing)
            self.convert(path, commands=True)
        except Exception as exc:
            if process.poll() is None:
                process.kill()
                process.communicate()
            GLib.idle_add(self.finished, path, f"Recording problem: {exc}. Any captured audio is kept.")

    def convert(self, path, commands=False):
        try:
            text, metrics = save_transcript(self.model, path)
            message = f"Saved audio + transcript · {metrics['audio_seconds']:.1f}s audio · {metrics['transcribe_seconds']:.2f}s transcription"
        except Exception as exc:
            message = f"Audio kept; transcription failed: {exc}"
            GLib.idle_add(self.finished, path, message)
            return
        if commands:
            command = self.matcher.exact(text)
            if command:
                GLib.idle_add(self.show_saved_transcript, path)
                try:
                    message += " · " + execute_command(command)
                except Exception as exc:
                    message += f" · Could not complete voice command: {exc}"
            else:
                intent = self.matcher.suggest(text)
                if intent:
                    GLib.idle_add(self.offer_suggestion, path, message, text, intent)
                    return
                message += " · Unrecognized command — no action taken"
        GLib.idle_add(self.finished, path, message)

    def offer_suggestion(self, path, message, text, intent):
        self.finished(path, message + " · Waiting for command confirmation")
        self.pending_suggestion = (path, text, intent)
        self.suggestion_label.set_text(INTENTS[intent]["label"])
        self.heard_label.set_text(f'Heard: “{text.strip()}”\nYes runs this command and remembers your phrase.')
        self.window.present()
        self.suggestion_dialog.present()
        self.reject.grab_focus()

    def dismiss_suggestion(self, *args):
        self.pending_suggestion = None
        self.suggestion_dialog.set_visible(False)
        if args:
            self.status.set_text("Suggestion dismissed. Hold Super + R to try again.")

    def close_suggestion(self, *_):
        self.dismiss_suggestion(True)
        return True

    def suggestion_key(self, _, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.dismiss_suggestion(True)
            return True
        return False

    def accept_suggestion(self, *_):
        if self.busy or self.pending_suggestion is None:
            return
        path, text, intent = self.pending_suggestion
        try:
            self.matcher.learn(text, intent)
        except (OSError, ValueError) as exc:
            self.heard_label.set_text(f"Could not remember phrase: {exc}. No command was run.")
            return
        self.refresh_aliases()
        self.set_busy(True)
        self.spinner.start()
        self.status.set_text("Phrase remembered. Running command…")
        threading.Thread(target=self.run_confirmed, args=(path, intent), daemon=True).start()

    def run_confirmed(self, path, intent):
        try:
            message = "Phrase remembered · " + execute_command(intent)
        except Exception as exc:
            message = f"Phrase remembered · Could not complete voice command: {exc}"
        GLib.idle_add(self.finished, path, message)

    def refresh_aliases(self):
        while child := self.learned_list.get_first_child():
            self.learned_list.remove(child)
        for phrase, intent in sorted(self.matcher.aliases.items()):
            row = Gtk.Box(spacing=8)
            row.append(Gtk.Label(label=f'{phrase} → {INTENTS[intent]["label"]}', xalign=0, wrap=True, hexpand=True))
            forget = Gtk.Button(label="Forget")
            forget.connect("clicked", self.forget_alias, phrase)
            row.append(forget)
            self.learned_list.append(row)
        if not self.matcher.aliases:
            self.learned_list.append(Gtk.Label(label="Confirmed phrases will appear here.", xalign=0))

    def forget_alias(self, _, phrase):
        if self.busy:
            return
        try:
            self.matcher.forget(phrase)
            self.refresh_aliases()
            self.status.set_text("Learned phrase forgotten.")
        except (OSError, ValueError) as exc:
            self.status.set_text(f"Could not forget phrase: {exc}")

    def show_saved_transcript(self, path):
        self.refresh_history(path)
        self.status.set_text("Transcript saved. Running command…")

    def finished(self, path, message):
        self.recorder = None
        self.ptt_owned = False
        self.spinner.stop()
        self.meter.active = False
        self.meter.queue_draw()
        self.set_busy(False)
        self.refresh_history(path)
        self.status.set_text(message)

    def retry_transcription(self, *_):
        if self.selected and not self.busy and self.model:
            self.set_busy(True)
            self.spinner.start()
            self.status.set_text("Transcribing saved audio…")
            threading.Thread(target=self.convert, args=(self.selected,), daemon=True).start()

    def copy_text(self, *_):
        buffer = self.text.get_buffer()
        self.window.get_clipboard().set(buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False))

    def play_recording(self, *_):
        if self.selected:
            try:
                if self.player and self.player.poll() is None:
                    self.player.terminate()
                self.player = subprocess.Popen(["pw-play", str(self.selected)])
            except OSError as exc:
                self.status.set_text(f"Could not play recording: {exc}")

    def open_folder(self, *_):
        try:
            Gio.AppInfo.launch_default_for_uri(DATA.as_uri(), None)
        except GLib.Error as exc:
            self.status.set_text(f"Could not open folder: {exc}")

    def on_close(self, *_):
        if self.busy:
            self.stop_recording()
            self.status.set_text("Finishing and saving this recording. Close again when it is ready.")
            return True
        if self.player and self.player.poll() is None:
            self.player.terminate()
        self.suggestion_dialog.destroy()
        return False


if __name__ == "__main__":
    os.umask(0o077)
    raise SystemExit(Keety().run(sys.argv))
