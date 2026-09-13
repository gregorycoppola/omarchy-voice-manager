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
from gi.repository import Gio, GLib, Gtk

from keety import load_model
from recordings import new_recording, save_transcript
from live_audio import read_growing_wav

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
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        for side in ["top", "bottom", "start", "end"]:
            getattr(box, "set_margin_" + side)(24)
        self.window.set_child(box)
        title = Gtk.Label(label="Speak. Keep the words.", xalign=0)
        title.add_css_class("title-1")
        box.append(title)
        subtitle = Gtk.Label(label="Live words while you speak. Everything stays on this computer.", xalign=0, wrap=True)
        subtitle.add_css_class("dim-label")
        box.append(subtitle)
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
        controls.append(Gtk.Label(label="Up to 30 seconds per recording", xalign=0))
        box.append(controls)
        self.status = Gtk.Label(label="Loading local speech model…", xalign=0, wrap=True)
        self.status.set_selectable(True)
        box.append(self.status)
        self.history = Gtk.DropDown()
        self.history.connect("notify::selected", self.select_recording)
        box.append(self.history)
        self.text = Gtk.TextView(editable=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.text.set_top_margin(16)
        self.text.set_bottom_margin(16)
        self.text.set_left_margin(16)
        self.text.set_right_margin(16)
        scroll = Gtk.ScrolledWindow(vexpand=True, min_content_height=180)
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
        self.record.set_sensitive(True)
        self.retry.set_sensitive(self.selected is not None)
        self.status.set_text("Ready. Press Record when you want to speak.")

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
        self.play.set_sensitive(self.selected is not None and not self.busy)
        self.retry.set_sensitive(self.selected is not None and self.model is not None and not self.busy)

    def set_busy(self, value):
        self.busy = value
        self.record.set_sensitive(not value and self.model is not None)
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
        self.copy.set_sensitive(False)
        self.text.get_buffer().set_text("Listening… words will appear as you speak.")
        self.stop.set_sensitive(True)
        self.record_start = time.monotonic()
        self.status.set_text("Recording… speak now. Press Stop when finished.")
        GLib.timeout_add(250, self.tick)
        preview_stop = threading.Event()
        preview = threading.Thread(target=self.preview_recording, args=(path, preview_stop), daemon=True)
        preview.start()
        threading.Thread(target=self.finish_recording,
                         args=(path, self.recorder, preview_stop, preview), daemon=True).start()

    def tick(self):
        if not self.recorder or self.recorder.poll() is not None:
            return False
        seconds = min(30, int(time.monotonic() - self.record_start))
        self.status.set_text(f"Recording · {seconds}s / 30s · live preview may revise earlier words")
        return True

    def stop_recording(self, *_):
        if self.recorder and self.recorder.poll() is None:
            try:
                self.recorder.send_signal(signal.SIGINT)
            except ProcessLookupError:
                pass
        self.stop.set_sensitive(False)

    def processing(self):
        self.recorder = None
        self.stop.set_sensitive(False)
        self.status.set_text("Audio saved. Transcribing locally…")

    def preview_recording(self, path, stop):
        import numpy as np
        last_length = 0
        while not stop.wait(1.0):
            try:
                pcm = read_growing_wav(path)
                if not pcm or len(pcm) < 24000 or len(pcm) <= last_length:
                    continue
                last_length = len(pcm)
                samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
                text = self.model.recognize(samples, sample_rate=16000)
                if not stop.is_set():
                    GLib.idle_add(self.show_preview, path, text)
            except Exception as exc:
                # Preserve recording/final transcription even if preview is unavailable.
                print(f"Live preview unavailable: {exc}", file=sys.stderr, flush=True)
                GLib.idle_add(self.show_preview, path, "Live preview unavailable. Your final transcript will appear after Stop.")
                return

    def show_preview(self, path, text):
        if self.active_path == path and self.recorder is not None:
            self.text.get_buffer().set_text(text or "Listening…")

    def finish_recording(self, path, process, preview_stop, preview):
        try:
            _, error = process.communicate(timeout=45)
            preview_stop.set()
            preview.join()  # Serialize preview and final inference on the loaded model.
            if process.returncode not in (0, -signal.SIGINT):
                raise RuntimeError(error.strip() or f"Recorder exited {process.returncode}")
            GLib.idle_add(self.processing)
            self.convert(path)
        except Exception as exc:
            preview_stop.set()
            preview.join()
            if process.poll() is None:
                process.kill()
                process.communicate()
            GLib.idle_add(self.finished, path, f"Recording problem: {exc}. Any captured audio is kept.")

    def convert(self, path):
        try:
            _, metrics = save_transcript(self.model, path)
            message = f"Saved audio + transcript · {metrics['audio_seconds']:.1f}s audio · {metrics['transcribe_seconds']:.2f}s transcription"
        except Exception as exc:
            message = f"Audio kept; transcription failed: {exc}"
        GLib.idle_add(self.finished, path, message)

    def finished(self, path, message):
        self.recorder = None
        self.stop.set_sensitive(False)
        self.set_busy(False)
        self.refresh_history(path)
        self.status.set_text(message)

    def retry_transcription(self, *_):
        if self.selected and not self.busy and self.model:
            self.set_busy(True)
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
        return False


if __name__ == "__main__":
    os.umask(0o077)
    raise SystemExit(Keety().run(sys.argv))
