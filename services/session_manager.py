"""
全域會話狀態管理
統一 st.session_state 的讀寫，避免各處打錯字
"""
import streamlit as st
from typing import Optional, Dict
from datetime import datetime
import logging

from utils.session_keys import SessionKeys

logger = logging.getLogger(__name__)


class SessionManager:
    """Streamlit Session State 統一管理器"""
    
    # 會話鍵值常量（防止打錯字）
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
    def init():
        """初始化會話狀態"""
        if SessionManager.AUTHENTICATED not in st.session_state:
            st.session_state[SessionManager.AUTHENTICATED] = False
            st.session_state[SessionManager.USER_ID] = None
            st.session_state[SessionManager.USER_EMAIL] = None
            st.session_state[SessionManager.USER_NAME] = None
            st.session_state[SessionManager.USER_ROLE] = "landlord"
            st.session_state[SessionManager.ACCESS_TOKEN] = None
            st.session_state[SessionManager.REFRESH_TOKEN] = None
            st.session_state[SessionManager.LOGIN_TIME] = None
            st.session_state[SessionManager.EXPIRES_AT] = None
            logger.info("✅ Session State 已初始化")
    
    @staticmethod
    def login(user_data: Dict):
        """設定登入狀態"""
        st.session_state[SessionManager.AUTHENTICATED] = True
        st.session_state[SessionManager.USER_ID] = user_data["id"]
        st.session_state[SessionManager.USER_EMAIL] = user_data["email"]
        st.session_state[SessionManager.USER_NAME] = user_data.get("name", "用戶")
        st.session_state[SessionManager.USER_ROLE] = user_data.get("role", "landlord")
        st.session_state[SessionManager.ACCESS_TOKEN] = user_data["access_token"]
        st.session_state[SessionManager.REFRESH_TOKEN] = user_data["refresh_token"]
        st.session_state[SessionManager.LOGIN_TIME] = datetime.now()
        st.session_state[SessionManager.EXPIRES_AT] = user_data.get("expires_at")
        
        logger.info(f"✅ 用戶登入: {user_data['email']}")
    
    @staticmethod
    def logout():
        """清除登入狀態"""
        email = st.session_state.get(SessionManager.USER_EMAIL, "未知")
        
        st.session_state[SessionManager.AUTHENTICATED] = False
        st.session_state[SessionManager.USER_ID] = None
        st.session_state[SessionManager.USER_EMAIL] = None
        st.session_state[SessionManager.USER_NAME] = None
        st.session_state[SessionManager.ACCESS_TOKEN] = None
        st.session_state[SessionManager.REFRESH_TOKEN] = None
        st.session_state[SessionManager.LOGIN_TIME] = None
        
        logger.info(f"✅ 用戶登出: {email}")
    
    @staticmethod
    def is_authenticated() -> bool:
        """檢查是否已登入"""
        return st.session_state.get(SessionManager.AUTHENTICATED, False)
    
    @staticmethod
    def get_user_id() -> Optional[str]:
        """取得當前用戶 ID"""
        return st.session_state.get(SessionManager.USER_ID)
    
    @staticmethod
    def get_user_email() -> Optional[str]:
        """取得當前用戶 Email"""
        return st.session_state.get(SessionManager.USER_EMAIL)
    
    @staticmethod
    def get_user_name() -> str:
        """取得當前用戶名稱"""
        return st.session_state.get(SessionManager.USER_NAME, "用戶")
    
    @staticmethod
    def get_user_role() -> str:
        """取得當前用戶角色"""
        return st.session_state.get(SessionManager.USER_ROLE, "landlord")
    
    @staticmethod
    def check_session_timeout() -> bool:
        """
        檢查 Session 是否超時
        
        Returns:
            True = 已超時, False = 仍有效
        """
        if not SessionManager.is_authenticated():
            return False
        
        expires_at = st.session_state.get(SessionManager.EXPIRES_AT)
        if not expires_at:
            return False
        
        # 檢查是否過期（提前 5 分鐘刷新）
        from datetime import datetime, timedelta
        expiry_time = datetime.fromtimestamp(expires_at)
        
        if datetime.now() >= expiry_time - timedelta(minutes=5):
            logger.warning("⏱️ Session 即將過期，需要刷新")
            return True
        
        return False
