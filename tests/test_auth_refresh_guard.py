"""
auth refresh guard tests - v1.0.0
驗證失效 refresh_token 的阻擋與清除邏輯。
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import utils.auth_refresh_guard as auth_refresh_guard


class AuthRefreshGuardTest(unittest.TestCase):
    def test_mark_failed_then_is_blocked(self):
        fake_streamlit = SimpleNamespace(session_state={})

        with patch.object(auth_refresh_guard, "st", fake_streamlit):
            auth_refresh_guard.AuthRefreshGuard.mark_failed("rt-123", "cookie_restore")

            self.assertTrue(auth_refresh_guard.AuthRefreshGuard.is_blocked("rt-123"))
            self.assertFalse(auth_refresh_guard.AuthRefreshGuard.is_blocked("rt-456"))
            self.assertEqual(
                fake_streamlit.session_state[
                    auth_refresh_guard.AuthRefreshGuard.FAILED_SOURCE_KEY
                ],
                "cookie_restore",
            )

    def test_clear_removes_failed_marker(self):
        fake_streamlit = SimpleNamespace(session_state={})

        with patch.object(auth_refresh_guard, "st", fake_streamlit):
            auth_refresh_guard.AuthRefreshGuard.mark_failed("rt-123", "session_refresh")
            auth_refresh_guard.AuthRefreshGuard.clear()

            self.assertFalse(auth_refresh_guard.AuthRefreshGuard.is_blocked("rt-123"))
            self.assertEqual(fake_streamlit.session_state, {})


if __name__ == "__main__":
    unittest.main()
