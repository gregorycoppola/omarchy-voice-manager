"""Local preferences, saved atomically with private permissions."""
import json
from pathlib import Path
import tempfile


class Settings:
    def __init__(self, path):
        self.path = Path(path)
        self.confirm_terminal_close = True
        self.error = None
        try:
            data = json.loads(self.path.read_text())
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
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=self.path.parent, delete=False) as handle:
                temporary = Path(handle.name)
                json.dump({'confirm_terminal_close': bool(value)}, handle)
                handle.write('\n')
            temporary.replace(self.path)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
        self.confirm_terminal_close = bool(value)
