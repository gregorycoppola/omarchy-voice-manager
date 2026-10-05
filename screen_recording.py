"""Explicit start/stop controls for Omarchy's screen recorder."""
import json
import subprocess
import threading
import time
from personal_store import DEFAULT_DATA
from settings import Settings

_LOCK = threading.Lock()
_PENDING = None


def active():
    result = subprocess.run(['omarchy-capture-screenrecording-process'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=5)
    if result.returncode not in (0, 1):
        raise RuntimeError('Could not determine screen recording state')
    return result.returncode == 0


def execute_recording(action, run):
    global _PENDING
    with_webcam = action != 'start_without_webcam'
    if action == 'start_without_webcam':
        action = 'start'
    with _LOCK:
        if _PENDING is not None and _PENDING.poll() is None:
            raise RuntimeError('The previous recording command is still starting or saving. Please wait.')
        running = active()
        if action == 'start' and running:
            return 'A screen recording is already running'
        if action == 'stop' and not running:
            return 'No screen recording is running'
        if action not in ('start', 'stop'):
            raise ValueError('Unknown recording action')
        args = ['omarchy', 'screenrecord']
        if action == 'start':
            settings = Settings(DEFAULT_DATA / 'settings.json')
            if settings.error:
                raise RuntimeError(settings.error)
            monitor = settings.screen_recording_monitor
            if monitor:
                monitors = json.loads(run(['hyprctl', 'monitors', '-j']))
                if not isinstance(monitor, str) or not any(
                        m.get('name') == monitor and not m.get('disabled') for m in monitors):
                    raise RuntimeError('Your preferred recording monitor is not connected')
                # JSON quoting also quotes a Lua string safely for connector names.
                run(['hyprctl', 'dispatch', 'hl.dsp.focus({ monitor = ' + json.dumps(monitor) + ' })'])
            args += ['--fullscreen']
            if with_webcam:
                args += ['--with-webcam']
            args += ['--with-microphone-audio']
        else:
            args += ['--stop-recording']
        # Omarchy spawns a long-lived recorder; inherited pipes must not keep us waiting.
        # Stop can also spend minutes finalizing a large video.
        process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, start_new_session=True)
        _PENDING = process
        threading.Thread(target=process.wait, daemon=True).start()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if active() == (action == 'start'):
                return (('Screen recording started with webcam and microphone' if with_webcam
                         else 'Screen recording started without webcam, with microphone') if action == 'start'
                        else 'Screen recording stopped; Omarchy is saving the video')
            if process.poll() is not None:
                raise RuntimeError('Omarchy did not reach the requested recording state')
            time.sleep(0.1)
        raise RuntimeError('Recording command sent, but its state could not be confirmed')
