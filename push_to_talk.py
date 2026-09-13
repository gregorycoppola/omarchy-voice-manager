"""Order compositor key events and ignore repeats/unrelated releases."""
import re


class PushToTalk:
    def __init__(self, press, release):
        self.press = press
        self.release = release
        self.last_sequence = {}
        self.held_session = None

    def event(self, value):
        match = re.fullmatch(r"([0-9]+-[0-9]+):([0-9]+):(down|up)", value)
        if not match:
            return
        session, sequence, state = match.groups()
        sequence = int(sequence)
        if sequence <= self.last_sequence.get(session, -1):
            return
        self.last_sequence[session] = sequence
        if len(self.last_sequence) > 16:
            oldest = next(iter(self.last_sequence))
            if oldest != self.held_session:
                del self.last_sequence[oldest]
        if state == "down" and self.held_session is None:
            self.held_session = session
            self.press()
        elif state == "up" and session == self.held_session:
            self.held_session = None
            self.release()
