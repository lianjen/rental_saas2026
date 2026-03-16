"""Compatibility tests for services.session_manager - v1.0.0."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from services.session_manager import SessionManager
from utils.session_keys import SessionKeys


class ServicesSessionManagerCompatTests(TestCase):
    def setUp(self) -> None:
        self.fake_streamlit = SimpleNamespace(session_state={})

        patcher_service = patch("services.session_manager.st", self.fake_streamlit)
        patcher_utils = patch("utils.session_manager.st", self.fake_streamlit)

        self.addCleanup(patcher_service.stop)
        self.addCleanup(patcher_utils.stop)

        patcher_service.start()
        patcher_utils.start()

    def test_init_populates_legacy_authenticated_key(self) -> None:
        SessionManager.init()

        self.assertIn(SessionKeys.AUTHENTICATED_LEGACY, self.fake_streamlit.session_state)
        self.assertFalse(self.fake_streamlit.session_state[SessionKeys.AUTHENTICATED_LEGACY])

    def test_set_user_syncs_legacy_authenticated_key(self) -> None:
        SessionManager.init()

        SessionManager.set_user(
            {
                "id": "user-1",
                "email": "user@example.com",
                "role": "admin",
                "access_token": "access-token",
                "refresh_token": "refresh-token",
            }
        )

        self.assertTrue(self.fake_streamlit.session_state[SessionKeys.IS_AUTHENTICATED])
        self.assertTrue(self.fake_streamlit.session_state[SessionKeys.AUTHENTICATED_LEGACY])

    def test_clear_resets_legacy_authenticated_key(self) -> None:
        SessionManager.init()
        SessionManager.set_user(
            {
                "id": "user-1",
                "email": "user@example.com",
                "role": "admin",
                "access_token": "access-token",
                "refresh_token": "refresh-token",
            }
        )

        SessionManager.clear()

        self.assertFalse(self.fake_streamlit.session_state[SessionKeys.IS_AUTHENTICATED])
        self.assertFalse(self.fake_streamlit.session_state[SessionKeys.AUTHENTICATED_LEGACY])
