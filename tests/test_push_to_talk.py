import unittest
from unittest.mock import Mock
from push_to_talk import PushToTalk


class PushToTalkTests(unittest.TestCase):
    def setUp(self):
        self.press = Mock()
        self.release = Mock()
        self.now = 0
        self.ptt = PushToTalk(self.press, self.release, clock=lambda: self.now)

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

    def test_missing_release_expires_and_late_heartbeat_cannot_restart(self):
        self.ptt.event("123-456:1:down")
        self.now = .8
        self.ptt.check_held()
        self.release.assert_called_once()
        self.ptt.event("123-456:2:hold")
        self.ptt.check_held()
        self.press.assert_called_once()
        self.assertIsNone(self.ptt.held_session)

    def test_heartbeats_keep_a_real_hold_alive(self):
        self.ptt.event("123-456:1:down")
        for sequence in range(2, 30):
            self.now += .2
            self.ptt.event(f"123-456:{sequence}:hold")
            self.ptt.check_held()
        self.release.assert_not_called()
        self.ptt.event("123-456:30:up")
        self.release.assert_called_once()

    def test_old_heartbeat_cannot_renew_or_restart_after_release(self):
        self.ptt.event("123-456:1:down")
        self.ptt.event("123-456:3:up")
        self.ptt.event("123-456:2:hold")
        self.ptt.event("123-456:4:hold")
        self.assertIsNone(self.ptt.held_session)
        self.press.assert_called_once()

    def test_other_session_cannot_keep_recording_alive(self):
        self.ptt.event("123-456:1:down")
        self.now = .5
        self.ptt.event("999-888:1:hold")
        self.now = .8
        self.ptt.check_held()
        self.release.assert_called_once()


if __name__ == "__main__":
    unittest.main()
