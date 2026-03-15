"""
Cookie Session Manager - v1.0
用途：將 Supabase refresh_token 儲存到瀏覽器 Cookie，讓 F5 刷新後能自動還原 Session。

流程：
  登入成功 → 儲存 refresh_token 到 Cookie
  F5 刷新  → 讀 Cookie → 用 refresh_token 從 Supabase 換新 Token → 還原 session_state
  登出     → 清除 Cookie
"""

import base64
import logging
from typing import Optional, Dict

import streamlit as st
from utils.session_keys import SessionKeys

logger = logging.getLogger(__name__)

# Cookie 名稱常量
_COOKIE_RT  = "_srt"   # refresh_token (short key 減少暴露)
_COOKIE_AT  = "_sat"   # access_token
_MAX_AGE    = 60 * 60 * 24 * 7  # 7 天，單位：秒


def _get_controller():
    """取得 CookieController 單例（儲在 session_state 避免重建）"""
    if SessionKeys.COOKIE_CONTROLLER not in st.session_state:
        try:
            from streamlit_cookies_controller import CookieController
            st.session_state[SessionKeys.COOKIE_CONTROLLER] = CookieController()
        except ImportError:
            logger.error("❌ streamlit-cookies-controller 未安裝，請執行: pip install streamlit-cookies-controller")
            return None
    return st.session_state[SessionKeys.COOKIE_CONTROLLER]


def _encode(value: str) -> str:
    """Base64 輕度混淡（非加密，僅防股橏）"""
    return base64.urlsafe_b64encode(value.encode()).decode()


def _decode(value: str) -> str:
    """Base64 解碼"""
    return base64.urlsafe_b64decode(value.encode()).decode()


def save_auth_cookie(access_token: str, refresh_token: str) -> bool:
    """
    登入成功後調用：將 Token 儲存到 Cookie

    Returns:
        bool: 是否儲存成功
    """
    ctrl = _get_controller()
    if ctrl is None:
        return False
    try:
        ctrl.set(_COOKIE_RT, _encode(refresh_token), max_age=_MAX_AGE)
        ctrl.set(_COOKIE_AT, _encode(access_token),  max_age=_MAX_AGE)
        logger.info("✅ Auth Cookie 已儲存")
        return True
    except Exception as e:
        logger.error(f"❌ 儲存 Auth Cookie 失敗: {e}")
        return False


def load_auth_cookie() -> Optional[Dict[str, str]]:
    """
    F5 後調用：從 Cookie 讀取 Token

    Returns:
        {"access_token": str, "refresh_token": str} 或 None
    """
    ctrl = _get_controller()
    if ctrl is None:
        return None
    try:
        raw_rt = ctrl.get(_COOKIE_RT)
        raw_at = ctrl.get(_COOKIE_AT)
        if not raw_rt:
            return None
        return {
            "refresh_token": _decode(raw_rt),
            "access_token":  _decode(raw_at) if raw_at else "",
        }
    except Exception as e:
        logger.warning(f"⚠️ 讀取 Auth Cookie 失敗: {e}")
        return None


def clear_auth_cookie() -> None:
    """登出時調用：清除 Cookie"""
    ctrl = _get_controller()
    if ctrl is None:
        return
    try:
        ctrl.remove(_COOKIE_RT)
        ctrl.remove(_COOKIE_AT)
        logger.info("✅ Auth Cookie 已清除")
    except Exception as e:
        logger.warning(f"⚠️ 清除 Auth Cookie 失敗: {e}")
