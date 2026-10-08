"""Local preferences, saved atomically with private permissions."""
import personal_store
from pathlib import Path


class Settings:
    def __init__(self, path):
        self.path = Path(path)
        self.confirm_terminal_close = True
        self.error = None
        self.layout_excluded_classes = []
        self._data = {}
        try:
            data = personal_store.load(self.path)
            value = data['confirm_terminal_close']
            if type(value) is not bool:
                raise ValueError('Invalid terminal confirmation preference')
            self.confirm_terminal_close = value
            excluded = data.get('layout_excluded_classes', [])
            if not isinstance(excluded, list) or any(not isinstance(c, str) or not c for c in excluded):
                raise ValueError('Invalid layout exclusions')
            self.layout_excluded_classes = excluded
            self._data = data
        except FileNotFoundError:
            pass
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.error = f'Could not load settings: {exc}'

    def set_confirm_terminal_close(self, value):
        if self.error:
            raise ValueError(self.error)
        self._data['confirm_terminal_close'] = bool(value)
        personal_store.save(self.path, self._data)
        self.confirm_terminal_close = bool(value)

    def set_layout_excluded_classes(self, classes):
        if self.error:
            raise ValueError(self.error)
        if not isinstance(classes, list) or any(not isinstance(c, str) or not c for c in classes):
            raise ValueError('Invalid layout exclusions')
        self._data.update(confirm_terminal_close=self.confirm_terminal_close,
                          layout_excluded_classes=list(dict.fromkeys(classes)))
        personal_store.save(self.path, self._data)
        self.layout_excluded_classes = self._data['layout_excluded_classes']

    @property
    def screen_recording_monitor(self):
        return self._data.get('screen_recording_monitor')

    def set_screen_recording_monitor(self, monitor):
        if self.error:
            raise ValueError(self.error)
        if monitor is not None and (not isinstance(monitor, str) or not monitor):
            raise ValueError('Invalid recording monitor')
        self._data.update(confirm_terminal_close=self.confirm_terminal_close,
                          screen_recording_monitor=monitor)
        personal_store.save(self.path, self._data)

    @property
    def voice_cloud(self):
        return self._data.get('voice_cloud',False) is True

    def set_voice_cloud(self, enabled):
        if self.error:raise ValueError(self.error)
        if type(enabled) is not bool:raise ValueError('Cloud fallback must be on or off')
        self._data.update(confirm_terminal_close=self.confirm_terminal_close,voice_cloud=enabled)
        personal_store.save(self.path,self._data)

    @property
    def voice_debug(self):
        # Normal voice use executes; debugging is an explicit preference.
        return self._data.get('voice_debug', False) is not False

    def set_voice_debug(self, enabled):
        if self.error:
            raise ValueError(self.error)
        if type(enabled) is not bool:
            raise ValueError('Debug mode must be on or off')
        self._data.update(confirm_terminal_close=self.confirm_terminal_close, voice_debug=enabled)
        personal_store.save(self.path, self._data)
