"""
Auth refresh guard - v1.0.0
用途：避免同一個失效的 refresh_token 在 Streamlit rerun 中被重複重試。
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Optional

import streamlit as st

logger = logging.getLogger(__name__)


class AuthRefreshGuard:
    """記錄最近一次失敗的 refresh_token，避免重複刷新。"""

    FAILED_TOKEN_HASH_KEY = "_failed_refresh_token_hash"
    FAILED_SOURCE_KEY = "_failed_refresh_source"
    FAILED_AT_KEY = "_failed_refresh_at"

    @staticmethod
    def _hash_token(refresh_token: str) -> str:
        return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()

    @classmethod
    def is_blocked(cls, refresh_token: Optional[str]) -> bool:
        if not refresh_token:
            return False
        return (
            st.session_state.get(cls.FAILED_TOKEN_HASH_KEY)
            == cls._hash_token(refresh_token)
        )

    @classmethod
    def mark_failed(cls, refresh_token: Optional[str], source: str) -> None:
        if not refresh_token:
            return
        st.session_state[cls.FAILED_TOKEN_HASH_KEY] = cls._hash_token(refresh_token)
        st.session_state[cls.FAILED_SOURCE_KEY] = source
        st.session_state[cls.FAILED_AT_KEY] = datetime.now().isoformat()
        logger.info(f"🧯 已標記失效 refresh_token: source={source}")

    @classmethod
    def clear(cls) -> None:
        had_state = cls.FAILED_TOKEN_HASH_KEY in st.session_state
        st.session_state.pop(cls.FAILED_TOKEN_HASH_KEY, None)
        st.session_state.pop(cls.FAILED_SOURCE_KEY, None)
        st.session_state.pop(cls.FAILED_AT_KEY, None)
        if had_state:
            logger.debug("✅ 已清除 refresh_token 失敗標記")
