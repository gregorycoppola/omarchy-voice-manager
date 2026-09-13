"""Measure actual PCM amplitude and draw a scrolling microphone meter."""
from collections import deque
import math

import gi
gi.require_version("Gtk", "4.0")
gi.require_foreign("cairo")
from gi.repository import Gtk


def pcm_level(pcm):
    import numpy as np
    if not pcm:
        return 0.0, -90.0
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
    rms = float(np.sqrt(np.mean(samples * samples)))
    db = max(-90.0, 20 * math.log10(max(rms, 1e-9)))
    return min(1.0, max(0.0, (db + 60) / 60)), db


class LevelMeter(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self.set_content_height(64)
        self.set_hexpand(True)
        self.levels = deque([0.0] * 64, maxlen=64)
        self.active = False
        self.set_draw_func(self.draw)
        self.set_tooltip_text("Microphone amplitude over the last few seconds")

    def reset(self):
        self.levels = deque([0.0] * 64, maxlen=64)
        self.active = True
        self.queue_draw()

    def push(self, level):
        self.levels.append(level)
        self.queue_draw()

    def draw(self, _, cr, width, height):
        cr.set_source_rgb(0.075, 0.095, 0.12)
        cr.paint()
        step = (width - 24) / len(self.levels)
        for i, level in enumerate(self.levels):
            bar = max(2, level * (height - 22))
            if self.active:
                cr.set_source_rgb(0.20 + level * 0.15, 0.55 + level * 0.35, 0.70 + level * 0.2)
            else:
                cr.set_source_rgb(0.25, 0.36, 0.42)
            cr.rectangle(12 + i * step, (height - bar) / 2, max(1, step - 3), bar)
            cr.fill()
