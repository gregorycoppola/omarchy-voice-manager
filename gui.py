"""Keety's native GTK4 desktop window."""
import os
import queue
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import wave

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk

from keety import load_model
from recordings import new_recording, save_transcript
from live_audio import read_growing_wav
from level_meter import LevelMeter, pcm_level
from os_actions import parse_command, execute_command
from listener import Listener
from push_to_talk import PushToTalk

DATA = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "keety/recordings"


class Keety(Gtk.Application):
    def __init__(self, hands_free_default=False):
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
        self.command_for_take = False
        self.hands_free_default = hands_free_default
        self.listener = None
        self.listener_generation = None
        self.auto_pending = 0
        self.auto_queue = queue.Queue(maxsize=3)
        self.asr_lock = threading.Lock()
        self.ptt_held = False
        self.ptt_owned = False
        self.ptt = PushToTalk(self.ptt_press, self.ptt_release)
        action = Gio.SimpleAction.new("ptt-event", GLib.VariantType.new("s"))
        action.connect("activate", lambda _, value: self.ptt.event(value.get_string()))
        self.add_action(action)
        threading.Thread(target=self.auto_worker, daemon=True).start()

    def do_activate(self):
        if self.window:
            self.window.present()
            return
        DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.window = Gtk.ApplicationWindow(application=self, title="Keety")
        self.window.set_default_size(760, 620)
        self.window.connect("close-request", self.on_close)
        header = Gtk.HeaderBar()
        header.set_title_widget(Gtk.Label(label="Keety · Local dictation"))
        self.window.set_titlebar(header)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ["top", "bottom", "start", "end"]:
            getattr(box, "set_margin_" + side)(16)
        # Keep every control reachable when Hyprland tiles this into a short window.
        page = Gtk.ScrolledWindow()
        page.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        page.set_child(box)
        self.window.set_child(page)
        title = Gtk.Label(label="Speak. Keep the words.", xalign=0)
        title.add_css_class("title-1")
        box.append(title)
        subtitle = Gtk.Label(label="Hold Super + R to talk. Release to transcribe and run your command.", xalign=0, wrap=True)
        subtitle.add_css_class("dim-label")
        box.append(subtitle)
        self.voice_commands = Gtk.CheckButton(label="Voice commands — say “open Chrome” or “bring up Chrome”")
        self.voice_commands.set_active(True)
        self.voice_commands.set_tooltip_text("When enabled, a completed utterance matching the exact grammar controls Chromium. Other speech is saved as text.")
        box.append(self.voice_commands)
        self.hands_free = Gtk.CheckButton(label="Hands-free listening — detect speech and stop after a short silence")
        self.hands_free.set_active(self.hands_free_default)
        self.hands_free.connect("toggled", self.toggle_listening)
        box.append(self.hands_free)
        controls = Gtk.Box(spacing=12)
        self.record = Gtk.Button(label="●  Record")
        self.record.add_css_class("suggested-action")
        self.record.set_sensitive(False)
        self.record.connect("clicked", self.start_recording)
        controls.append(self.record)
        self.stop = Gtk.Button(label="■  Stop")
        self.stop.set_sensitive(False)
        self.stop.connect("clicked", self.stop_recording)
        controls.append(self.stop)
        self.capture_hint = Gtk.Label(label="Up to 30 seconds per recording", xalign=0)
        controls.append(self.capture_hint)
        box.append(controls)
        self.status = Gtk.Label(label="Loading local speech model…", xalign=0, wrap=True)
        self.status.set_selectable(True)
        progress = Gtk.Box(spacing=10)
        self.spinner = Gtk.Spinner()
        self.spinner.start()
        progress.append(self.spinner)
        progress.append(self.status)
        self.status.set_hexpand(True)
        box.append(progress)
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
        self.record.set_sensitive(True)
        self.retry.set_sensitive(self.selected is not None)
        self.status.set_text("Ready. Hold Super + R to speak, or use Record / Stop.")
        if self.hands_free.get_active():
            self.start_listening()
        elif self.ptt_held:
            self.begin_ptt()

    def ptt_press(self):
        self.ptt_held = True
        if self.listener:
            self.pause_listening()
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

    def toggle_listening(self, *_):
        if self.model is None:
            return
        if self.hands_free.get_active():
            if self.busy:
                self.hands_free.set_active(False)
                self.status.set_text("Finish the current take before starting hands-free mode.")
            else:
                self.start_listening()
        else:
            self.pause_listening()

    def start_listening(self):
        if self.listener is not None:
            return
        if self.player and self.player.poll() is None:
            self.player.terminate()
        token = object()
        self.listener_generation = token
        self.listener = Listener(
            lambda pcm, score: GLib.idle_add(self.auto_level, token, pcm, score),
            lambda active: GLib.idle_add(self.auto_state, token, active),
            lambda pcm: GLib.idle_add(self.auto_take, token, pcm),
            lambda error: GLib.idle_add(self.auto_error, token, error),
        )
        self.meter.reset()
        self.record.set_sensitive(False)
        self.play.set_sensitive(False)
        self.retry.set_sensitive(False)
        self.stop.set_label("■  Pause listening")
        self.capture_hint.set_text("Stops after about 0.7s of silence")
        self.stop.set_sensitive(True)
        self.status.set_text("Starting local speech detection…")
        self.listener.start()

    def pause_listening(self):
        if self.listener:
            self.listener.stop()
        self.listener = None
        self.listener_generation = None  # prevents queued utterances from running OS actions
        if self.hands_free.get_active():
            self.hands_free.set_active(False)
        self.stop.set_label("■  Stop")
        self.capture_hint.set_text("Up to 30 seconds per recording")
        self.stop.set_sensitive(False)
        self.meter.active = False
        self.meter.queue_draw()
        self.set_busy(self.busy)
        self.level_label.set_text("Microphone paused")
        self.status.set_text("Paused. Finishing saved transcripts…" if self.busy else "Paused. Enable Hands-free listening or press Record.")

    def auto_level(self, token, pcm, score):
        if token is self.listener_generation:
            level, db = pcm_level(pcm)
            self.meter.push(level)
            self.level_label.set_text(f"Microphone · {db:.0f} dBFS · speech probability {score:.0%}")

    def auto_state(self, token, active):
        if token is self.listener_generation and not self.busy:
            self.status.set_text("● Hearing speech… pause briefly to finish your command." if active
                                 else "Listening · waiting for speech. Pause listening to mute the microphone.")

    def auto_take(self, token, pcm):
        if token is not self.listener_generation:
            return
        path = None
        try:
            path = new_recording(DATA)
            with wave.open(str(path), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(16000)
                audio.writeframes(pcm)
            self.auto_queue.put_nowait((token, path, self.voice_commands.get_active()))
            self.auto_pending += 1
            self.set_busy(True)
            self.spinner.start()
            self.status.set_text("Speech ended. Transcribing locally…")
        except Exception as exc:
            self.status.set_text(f"Could not queue transcription: {exc}. Captured audio remains saved.")

    def auto_worker(self):
        while True:
            token, path, commands = self.auto_queue.get()
            try:
                self.convert(path, commands, completion=self.auto_finished,
                             command_guard=lambda: token is self.listener_generation)
            finally:
                self.auto_queue.task_done()

    def auto_finished(self, path, message):
        self.auto_pending -= 1
        self.finished(path, message)
        if self.auto_pending:
            self.set_busy(True)
            self.spinner.start()

    def auto_error(self, token, error):
        if token is self.listener_generation:
            self.pause_listening()
            self.status.set_text(f"Hands-free listening stopped: {error}")

    def refresh_history(self, select=None):
        self.paths = sorted(DATA.glob("*.wav"), reverse=True)
        labels = [p.stem.replace("_", " ") for p in self.paths]
        self.history.set_model(Gtk.StringList.new(labels or ["No recordings yet"]))
        index = self.paths.index(select) if select in self.paths else 0
        self.history.set_selected(index)
        self.select_recording()

    def select_recording(self, *_):
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
        self.play.set_sensitive(self.selected is not None and not self.busy and self.listener is None)
        self.retry.set_sensitive(self.selected is not None and self.model is not None and not self.busy and self.listener is None)

    def set_busy(self, value):
        self.busy = value
        self.voice_commands.set_sensitive(not value)
        self.record.set_sensitive(not value and self.model is not None and self.listener is None)
        self.history.set_sensitive(not value)
        self.play.set_sensitive(not value and self.selected is not None and self.listener is None)
        self.retry.set_sensitive(not value and self.selected is not None and self.model is not None and self.listener is None)

    def start_recording(self, *_):
        if self.busy or self.model is None or self.listener is not None:
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
        self.command_for_take = self.voice_commands.get_active()
        self.stop_requested = False
        self.meter_bytes = 0
        self.meter.reset()
        self.last_audio_at = time.monotonic()
        self.copy.set_sensitive(False)
        self.text.get_buffer().set_text("Recording your voice. Your transcript will appear automatically when recording stops.")
        self.stop.set_sensitive(True)
        self.record_start = time.monotonic()
        self.status.set_text("Recording… speak now. Press Stop when finished.")
        GLib.timeout_add(50, self.tick, path)
        threading.Thread(target=self.finish_recording,
                         args=(path, self.recorder), daemon=True).start()

    def tick(self, path):
        if self.active_path != path or not self.recorder or self.recorder.poll() is not None:
            return False
        seconds = min(30, int(time.monotonic() - self.record_start))
        if not self.stop_requested:
            ending = "release Super + R to transcribe" if self.ptt_owned else "press Stop to transcribe"
            self.status.set_text(f"● Recording · {seconds}s / 30s — {ending}")
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
        if self.listener is not None:
            self.pause_listening()
            return
        if self.recorder and self.recorder.poll() is None:
            self.stop_requested = True
            try:
                self.recorder.send_signal(signal.SIGINT)
            except ProcessLookupError:
                pass
        self.stop.set_sensitive(False)
        if self.busy:
            self.spinner.start()
            self.status.set_text("Stopping and transcribing…")

    def processing(self):
        self.recorder = None
        self.stop.set_sensitive(False)
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
            self.convert(path, self.command_for_take)
        except Exception as exc:
            if process.poll() is None:
                process.kill()
                process.communicate()
            GLib.idle_add(self.finished, path, f"Recording problem: {exc}. Any captured audio is kept.")

    def convert(self, path, commands=False, completion=None, command_guard=None):
        completed = completion or self.finished
        try:
            with self.asr_lock:
                text, metrics = save_transcript(self.model, path)
            message = f"Saved audio + transcript · {metrics['audio_seconds']:.1f}s audio · {metrics['transcribe_seconds']:.2f}s transcription"
        except Exception as exc:
            message = f"Audio kept; transcription failed: {exc}"
            GLib.idle_add(completed, path, message)
            return
        if commands and (command_guard is None or command_guard()):
            command = parse_command(text)
            if command:
                GLib.idle_add(self.show_saved_transcript, path)
                try:
                    message += " · " + execute_command(command)
                except Exception as exc:
                    message += f" · Could not complete voice command: {exc}"
            else:
                message += " · No matching voice command"
        GLib.idle_add(completed, path, message)

    def show_saved_transcript(self, path):
        self.refresh_history(path)
        self.status.set_text("Transcript saved. Bringing up the browser…")

    def finished(self, path, message):
        self.recorder = None
        self.ptt_owned = False
        self.spinner.stop()
        self.meter.active = self.listener is not None
        self.meter.queue_draw()
        self.stop.set_sensitive(self.listener is not None)
        self.set_busy(False)
        self.refresh_history(path)
        self.status.set_text(message + (" · Listening for the next command" if self.listener else ""))

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
        if self.listener:
            self.pause_listening()
        if self.busy:
            self.stop_recording()
            self.status.set_text("Finishing and saving this recording. Close again when it is ready.")
            return True
        if self.player and self.player.poll() is None:
            self.player.terminate()
        return False


if __name__ == "__main__":
    os.umask(0o077)
    raise SystemExit(Keety().run(sys.argv))
