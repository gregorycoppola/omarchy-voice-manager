"""Local preferences, saved atomically with private permissions."""
import personal_store
from pathlib import Path


class Settings:
    def __init__(self, path):
        self.path = Path(path)
        self.confirm_terminal_close = True
        self.error = None
        try:
            data = personal_store.load(self.path)
            value = data['confirm_terminal_close']
            if type(value) is not bool:
                raise ValueError('Invalid terminal confirmation preference')
            self.confirm_terminal_close = value
        except FileNotFoundError:
            pass
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.error = f'Could not load settings: {exc}'

    def set_confirm_terminal_close(self, value):
        if self.error:
            raise ValueError(self.error)
        personal_store.save(self.path, {'confirm_terminal_close': bool(value)})
        self.confirm_terminal_close = bool(value)
