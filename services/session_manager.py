"""
Legacy session manager compatibility wrapper - v3.0.0

Keep the old import path ``services.session_manager`` working while delegating
all real behavior to ``utils.session_manager``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import streamlit as st

from utils.session_keys import SessionKeys
from utils.session_manager import SessionManager as ModernSessionManager


def _sync_legacy_authenticated_flag() -> None:
    """Mirror the modern auth flag to the legacy ``authenticated`` key."""
    st.session_state[SessionKeys.AUTHENTICATED_LEGACY] = bool(
        st.session_state.get(SessionKeys.IS_AUTHENTICATED, False)
    )


class SessionManager:
    """
    Backward-compatible facade for older modules.

    Notes:
    - New code should import ``utils.session_manager`` directly.
    - This wrapper exists only to avoid breaking unknown legacy paths.
    """

    AUTHENTICATED = SessionKeys.AUTHENTICATED_LEGACY
    USER_ID = SessionKeys.USER_ID
    USER_EMAIL = SessionKeys.USER_EMAIL
    USER_NAME = SessionKeys.USER_NAME
    USER_ROLE = SessionKeys.USER_ROLE
    ACCESS_TOKEN = SessionKeys.ACCESS_TOKEN
    REFRESH_TOKEN = SessionKeys.REFRESH_TOKEN
    LOGIN_TIME = SessionKeys.LOGIN_TIME
    EXPIRES_AT = SessionKeys.EXPIRES_AT

    @staticmethod
    def init() -> None:
        ModernSessionManager.init()
        _sync_legacy_authenticated_flag()

    @staticmethod
    def login(user_data: Dict[str, Any]) -> None:
        ModernSessionManager.set_user(user_data)
        _sync_legacy_authenticated_flag()

    @staticmethod
    def logout() -> None:
        ModernSessionManager.logout()
        _sync_legacy_authenticated_flag()

    @staticmethod
    def is_authenticated() -> bool:
        value = ModernSessionManager.is_authenticated()
        _sync_legacy_authenticated_flag()
        return value

    @staticmethod
    def get_user_id() -> Optional[str]:
        return ModernSessionManager.get_user_id()

    @staticmethod
    def get_user_email() -> Optional[str]:
        return ModernSessionManager.get_user_email()

    @staticmethod
    def get_user_name() -> Optional[str]:
        return ModernSessionManager.get_user_name()

    @staticmethod
    def get_user_role() -> str:
        return ModernSessionManager.get_user_role()

    @staticmethod
    def check_session_timeout() -> bool:
        return ModernSessionManager.check_session_timeout()

    @staticmethod
    def set_user(user_data: Dict[str, Any]) -> None:
        ModernSessionManager.set_user(user_data)
        _sync_legacy_authenticated_flag()

    @staticmethod
    def get_user() -> Optional[Dict[str, Any]]:
        return ModernSessionManager.get_user()

    @staticmethod
    def clear() -> None:
        ModernSessionManager.clear()
        _sync_legacy_authenticated_flag()

    @staticmethod
    def is_logged_in() -> bool:
        value = ModernSessionManager.is_logged_in()
        _sync_legacy_authenticated_flag()
        return value


session_manager = SessionManager()

__all__ = ["SessionManager", "session_manager"]
