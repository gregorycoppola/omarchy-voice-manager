"""Ordered hold-to-talk messages with a short, renewable recording lease."""
import re
import time


class PushToTalk:
    LEASE_SECONDS = 0.7

    def __init__(self, press, release, clock=time.monotonic):
        self.press = press
        self.release = release
        self.clock = clock
        self.last_sequence = {}
        self.held_session = None
        self.deadline = 0

    def event(self, value):
        match = re.fullmatch(r"([0-9]+-[0-9]+):([0-9]+):(down|hold|up)", value)
        if not match:
            return
        session, sequence, state = match.groups()
        sequence = int(sequence)
        if sequence <= self.last_sequence.get(session, -1):
            return
        self.last_sequence[session] = sequence
        if len(self.last_sequence) > 16:
            for old in list(self.last_sequence):
                if old not in (session, self.held_session):
                    del self.last_sequence[old]
                    break
        if state == "down" and self.held_session is None:
            self.held_session = session
            self.deadline = self.clock() + self.LEASE_SECONDS
            self.press()
        elif session == self.held_session:
            if state == "hold":
                self.deadline = self.clock() + self.LEASE_SECONDS
            elif state == "up":
                self.held_session = None
                self.release()

    def check_held(self):
        if self.held_session is not None and self.clock() >= self.deadline:
            self.held_session = None
            self.release()
        return True  # GLib timer keeps checking while the app is open
