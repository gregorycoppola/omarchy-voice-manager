import unittest
from unittest.mock import Mock
from push_to_talk import PushToTalk


class PushToTalkTests(unittest.TestCase):
    def setUp(self):
        self.press = Mock()
        self.release = Mock()
        self.ptt = PushToTalk(self.press, self.release)

    def test_press_hold_and_release(self):
        self.ptt.event("123-456:1:down")
        self.ptt.event("123-456:1:down")
        self.ptt.event("123-456:2:down")
        self.press.assert_called_once()
        self.release.assert_not_called()
        self.ptt.event("123-456:3:up")
        self.ptt.event("123-456:4:up")
        self.release.assert_called_once()

    def test_release_arriving_before_press_cannot_leave_mic_open(self):
        self.ptt.event("123-456:2:up")
        self.ptt.event("123-456:1:down")
        self.press.assert_not_called()
        self.release.assert_not_called()

    def test_unrelated_and_malformed_releases_are_ignored(self):
        self.ptt.event("123-456:1:down")
        self.ptt.event("999-888:1:up")
        self.ptt.event("invalid")
        self.release.assert_not_called()
        self.ptt.event("123-456:2:up")
        self.release.assert_called_once()


if __name__ == "__main__":
    unittest.main()
