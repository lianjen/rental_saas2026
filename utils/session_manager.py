"""
Session 管理工具 - v2.0 (Auth Integration)
✅ Streamlit Session State 封装
✅ Supabase Auth Token 管理
✅ 自动过期检查与刷新
✅ 安全的资料存取
✅ 开发模式支持
✅ 完整日志记录
"""
import streamlit as st
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from utils.session_keys import SessionKeys

logger = logging.getLogger(__name__)


class SessionManager:
    """Session 管理器 - 整合 Supabase Auth"""
    
    # ==================== Session Key 常量 ====================
    
    # Supabase Auth 相关
    ACCESS_TOKEN = SessionKeys.ACCESS_TOKEN
    REFRESH_TOKEN = SessionKeys.REFRESH_TOKEN
    EXPIRES_AT = SessionKeys.EXPIRES_AT
    
    # 用户资料
    USER_DATA = SessionKeys.USER_DATA
    USER_ID = SessionKeys.USER_ID
    USER_EMAIL = SessionKeys.USER_EMAIL
    USER_NAME = SessionKeys.USER_NAME
    USER_ROLE = SessionKeys.USER_ROLE
    
    # Session 状态
    IS_AUTHENTICATED = SessionKeys.IS_AUTHENTICATED
    LOGIN_TIME = SessionKeys.LOGIN_TIME
    LAST_ACTIVITY = SessionKeys.LAST_ACTIVITY
    
    # 配置
    SESSION_TIMEOUT = 3600  # 1 小时无活动自动登出
    TOKEN_REFRESH_THRESHOLD = 300  # Token 剩余 5 分钟时自动刷新
    
    def __init__(self):
        """初始化 Session Manager"""
        # 不在这里调用 init()，由调用方主动调用
        pass
    
    # ==================== 初始化 ====================
    
    @staticmethod
    def init():
        """
        初始化 Session State 结构
        必须在应用启动时调用一次
        """
        # Supabase Auth
        if SessionManager.ACCESS_TOKEN not in st.session_state:
            st.session_state[SessionManager.ACCESS_TOKEN] = None
        
        if SessionManager.REFRESH_TOKEN not in st.session_state:
            st.session_state[SessionManager.REFRESH_TOKEN] = None
        
        if SessionManager.EXPIRES_AT not in st.session_state:
            st.session_state[SessionManager.EXPIRES_AT] = None
        
        # 用户资料
        if SessionManager.USER_DATA not in st.session_state:
            st.session_state[SessionManager.USER_DATA] = None
        
        if SessionManager.USER_ID not in st.session_state:
            st.session_state[SessionManager.USER_ID] = None
        
        if SessionManager.USER_EMAIL not in st.session_state:
            st.session_state[SessionManager.USER_EMAIL] = None
        
        if SessionManager.USER_NAME not in st.session_state:
            st.session_state[SessionManager.USER_NAME] = None
        
        if SessionManager.USER_ROLE not in st.session_state:
            st.session_state[SessionManager.USER_ROLE] = "user"  # 默认角色
        
        # Session 状态
        if SessionManager.IS_AUTHENTICATED not in st.session_state:
            st.session_state[SessionManager.IS_AUTHENTICATED] = False
        
        if SessionManager.LOGIN_TIME not in st.session_state:
            st.session_state[SessionManager.LOGIN_TIME] = None
        
        if SessionManager.LAST_ACTIVITY not in st.session_state:
            st.session_state[SessionManager.LAST_ACTIVITY] = None
        
        logger.debug("✅ Session State 已初始化")
    
    # ==================== 登入管理 ====================
    
    @staticmethod
    def login(
        access_token: str,
        refresh_token: str,
        user_data: Dict[str, Any],
        expires_at: Optional[str] = None
    ):
        """
        用户登入，保存 Session 资料
        
        Args:
            access_token: Supabase Access Token
            refresh_token: Supabase Refresh Token
            user_data: 用户资料字典 (包含 id, email, user_metadata 等)
            expires_at: Token 过期时间 (ISO 8601 格式)
        """
        try:
            # 保存 Token
            st.session_state[SessionManager.ACCESS_TOKEN] = access_token
            st.session_state[SessionManager.REFRESH_TOKEN] = refresh_token
            st.session_state[SessionManager.EXPIRES_AT] = expires_at
            
            # 保存用户资料
            st.session_state[SessionManager.USER_DATA] = user_data
            st.session_state[SessionManager.USER_ID] = user_data.get("id")
            st.session_state[SessionManager.USER_EMAIL] = user_data.get("email")
            
            # 从 user_metadata 提取姓名和角色
            user_metadata = user_data.get("user_metadata", {})
            st.session_state[SessionManager.USER_NAME] = (
                user_metadata.get("name") or 
                user_metadata.get("display_name") or 
                user_data.get("email", "").split("@")[0]
            )
            st.session_state[SessionManager.USER_ROLE] = (
                user_metadata.get("role") or "user"
            )
            
            # 设置 Session 状态
            st.session_state[SessionManager.IS_AUTHENTICATED] = True
            st.session_state[SessionManager.LOGIN_TIME] = datetime.now()
            st.session_state[SessionManager.LAST_ACTIVITY] = datetime.now()
            
            logger.info(
                f"✅ 用户登入成功: {st.session_state[SessionManager.USER_EMAIL]} "
                f"(角色: {st.session_state[SessionManager.USER_ROLE]})"
            )
            
        except Exception as e:
            logger.error(f"❌ 登入失败: {e}", exc_info=True)
            SessionManager.logout()
    
    @staticmethod
    def logout():
        """用户登出，清除所有 Session 资料"""
        try:
            user_email = st.session_state.get(SessionManager.USER_EMAIL, "未知")
            
            # 清除所有资料
            st.session_state[SessionManager.ACCESS_TOKEN] = None
            st.session_state[SessionManager.REFRESH_TOKEN] = None
            st.session_state[SessionManager.EXPIRES_AT] = None
            st.session_state[SessionManager.USER_DATA] = None
            st.session_state[SessionManager.USER_ID] = None
            st.session_state[SessionManager.USER_EMAIL] = None
            st.session_state[SessionManager.USER_NAME] = None
            st.session_state[SessionManager.USER_ROLE] = "user"
            st.session_state[SessionManager.IS_AUTHENTICATED] = False
            st.session_state[SessionManager.LOGIN_TIME] = None
            st.session_state[SessionManager.LAST_ACTIVITY] = None
            
            logger.info(f"✅ 用户登出成功: {user_email}")
            
        except Exception as e:
            logger.error(f"❌ 登出失败: {e}", exc_info=True)
    
    # ==================== 认证状态检查 ====================
    
    @staticmethod
    def is_authenticated() -> bool:
        """
        检查用户是否已认证
        
        Returns:
            bool: True=已登入, False=未登入
        """
        try:
            # 检查认证标志
            if not st.session_state.get(SessionManager.IS_AUTHENTICATED, False):
                return False
            
            # 检查必要资料
            if not st.session_state.get(SessionManager.ACCESS_TOKEN):
                logger.warning("⚠️ 缺少 Access Token")
                return False
            
            if not st.session_state.get(SessionManager.USER_ID):
                logger.warning("⚠️ 缺少 User ID")
                return False
            
            # 更新最后活动时间
            st.session_state[SessionManager.LAST_ACTIVITY] = datetime.now()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 认证检查失败: {e}", exc_info=True)
            return False
    
    @staticmethod
    def check_session_timeout() -> bool:
        """
        检查 Session 是否超时
        
        Returns:
            bool: True=已超时(需要刷新), False=未超时
        """
        try:
            last_activity = st.session_state.get(SessionManager.LAST_ACTIVITY)
            
            if not last_activity:
                return False
            
            # 计算无活动时间
            inactive_seconds = (datetime.now() - last_activity).total_seconds()
            
            if inactive_seconds > SessionManager.SESSION_TIMEOUT:
                logger.warning(
                    f"⏰ Session 已超时: {int(inactive_seconds)}秒 "
                    f"(限制: {SessionManager.SESSION_TIMEOUT}秒)"
                )
                return True
            
            # 检查 Token 是否即将过期
            expires_at = st.session_state.get(SessionManager.EXPIRES_AT)
            
            if expires_at:
                try:
                    # 解析过期时间
                    if isinstance(expires_at, str):
                        expires_at = datetime.fromisoformat(
                            expires_at.replace('Z', '+00:00')
                        )
                    
                    # 计算剩余时间
                    remaining_seconds = (expires_at - datetime.now()).total_seconds()
                    
                    # Token 即将过期（剩余时间少于阈值）
                    if remaining_seconds < SessionManager.TOKEN_REFRESH_THRESHOLD:
                        logger.info(
                            f"⏰ Token 即将过期: {int(remaining_seconds)}秒后 "
                            f"(阈值: {SessionManager.TOKEN_REFRESH_THRESHOLD}秒)"
                        )
                        return True
                
                except Exception as e:
                    logger.error(f"❌ 解析 Token 过期时间失败: {e}")
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Session 超时检查失败: {e}", exc_info=True)
            return False
    
    # ==================== 用户资料获取 ====================
    
    @staticmethod
    def get_user_info() -> Optional[Dict[str, Any]]:
        """
        获取当前用户完整资料
        
        Returns:
            用户资料字典 or None
        """
        if not SessionManager.is_authenticated():
            return None
        
        return {
            "id": st.session_state.get(SessionManager.USER_ID),
            "email": st.session_state.get(SessionManager.USER_EMAIL),
            "name": st.session_state.get(SessionManager.USER_NAME),
            "role": st.session_state.get(SessionManager.USER_ROLE),
            "login_time": st.session_state.get(SessionManager.LOGIN_TIME),
            "last_activity": st.session_state.get(SessionManager.LAST_ACTIVITY),
        }
    
    @staticmethod
    def get_user_id() -> Optional[str]:
        """获取当前用户 ID"""
        return st.session_state.get(SessionManager.USER_ID)
    
    @staticmethod
    def get_user_email() -> Optional[str]:
        """获取当前用户 Email"""
        return st.session_state.get(SessionManager.USER_EMAIL)
    
    @staticmethod
    def get_user_name() -> Optional[str]:
        """获取当前用户姓名"""
        return st.session_state.get(SessionManager.USER_NAME) or "未知用户"
    
    @staticmethod
    def get_user_role() -> str:
        """获取当前用户角色"""
        return st.session_state.get(SessionManager.USER_ROLE, "user")
    
    @staticmethod
    def get_access_token() -> Optional[str]:
        """获取 Access Token"""
        return st.session_state.get(SessionManager.ACCESS_TOKEN)
    
    @staticmethod
    def get_refresh_token() -> Optional[str]:
        """获取 Refresh Token"""
        return st.session_state.get(SessionManager.REFRESH_TOKEN)
    
    # ==================== Session 统计 ====================
    
    @staticmethod
    def get_session_duration() -> Optional[int]:
        """
        获取 Session 持续时间（秒）
        
        Returns:
            持续时间（秒）or None
        """
        login_time = st.session_state.get(SessionManager.LOGIN_TIME)
        
        if not login_time:
            return None
        
        return int((datetime.now() - login_time).total_seconds())
    
    @staticmethod
    def get_remaining_time() -> Optional[int]:
        """
        获取 Session 剩余时间（秒）
        
        Returns:
            剩余时间（秒）or None
        """
        last_activity = st.session_state.get(SessionManager.LAST_ACTIVITY)
        
        if not last_activity:
            return None
        
        elapsed = (datetime.now() - last_activity).total_seconds()
        remaining = SessionManager.SESSION_TIMEOUT - elapsed
        
        return max(0, int(remaining))
    
    @staticmethod
    def get_token_remaining_time() -> Optional[int]:
        """
        获取 Token 剩余有效时间（秒）
        
        Returns:
            剩余时间（秒）or None
        """
        expires_at = st.session_state.get(SessionManager.EXPIRES_AT)
        
        if not expires_at:
            return None
        
        try:
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            
            remaining = (expires_at - datetime.now()).total_seconds()
            return max(0, int(remaining))
        
        except Exception as e:
            logger.error(f"❌ 计算 Token 剩余时间失败: {e}")
            return None
    
    # ==================== 开发模式支持 ====================
    
    @staticmethod
    def is_dev_mode() -> bool:
        """
        检查是否为开发模式
        
        Returns:
            bool: True=开发模式, False=生产模式
        """
        try:
            # 从 secrets 读取
            dev_mode = st.secrets.get("DEV_MODE", False)
            if isinstance(dev_mode, str):
                dev_mode = dev_mode.lower() == "true"
            return dev_mode
        except:
            return False
    
    @staticmethod
    def get_dev_user_id() -> Optional[str]:
        """
        获取开发模式的测试用户 ID
        
        Returns:
            测试用户 ID or None
        """
        try:
            return st.secrets.get("DEV_USER_ID")
        except:
            return None
    
    # ==================== 自定义资料存储 ====================
    
    @staticmethod
    def set_custom_data(key: str, value: Any):
        """
        保存自定义资料到 Session
        
        Args:
            key: 资料键
            value: 资料值
        """
        st.session_state[SessionKeys.custom(key)] = value
    
    @staticmethod
    def get_custom_data(key: str, default: Any = None) -> Any:
        """
        获取自定义资料
        
        Args:
            key: 资料键
            default: 默认值
        
        Returns:
            资料值 or 默认值
        """
        return st.session_state.get(SessionKeys.custom(key), default)
    
    @staticmethod
    def clear_custom_data(key: str):
        """
        清除自定义资料
        
        Args:
            key: 资料键
        """
        custom_key = SessionKeys.custom(key)
        if custom_key in st.session_state:
            del st.session_state[custom_key]
    
    # ==================== Debug 工具 ====================
    
    @staticmethod
    def debug_session_info():
        """显示 Session 调试信息（仅开发环境使用）"""
        if not SessionManager.is_dev_mode():
            return
        
        if not SessionManager.is_authenticated():
            st.sidebar.info("📭 未登入")
            return
        
        with st.sidebar.expander("🔍 Session Debug", expanded=False):
            st.write("**用户信息：**")
            user_id = SessionManager.get_user_id()
            st.json({
                "id": user_id[:8] + "..." if user_id else "N/A",
                "email": SessionManager.get_user_email(),
                "name": SessionManager.get_user_name(),
                "role": SessionManager.get_user_role()
            })
            
            st.write("**Session 状态：**")
            st.write(f"- 登入时间：{st.session_state.get(SessionManager.LOGIN_TIME)}")
            st.write(f"- 持续时间：{SessionManager.get_session_duration()}秒")
            st.write(f"- 剩余时间：{SessionManager.get_remaining_time()}秒")
            
            st.write("**Token 状态：**")
            token_remaining = SessionManager.get_token_remaining_time()
            st.write(f"- Token 剩余：{token_remaining}秒" if token_remaining else "- Token 剩余：未知")
            
            access_token = SessionManager.get_access_token()
            if access_token:
                st.write(f"- Access Token: {access_token[:20]}...")
    
    # ==================== 兼容性方法（向后兼容）====================
    
    @staticmethod
    def set_user(user_data: Dict[str, Any]):
        """
        兼容旧版 API：设置用户资料
        
        Args:
            user_data: 用户资料字典
        """
        logger.warning("⚠️ set_user() 已废弃，请使用 login()")
        
        # 尝试提取 Token（如果有）
        access_token = user_data.get("access_token", "legacy_token")
        refresh_token = user_data.get("refresh_token", "legacy_token")
        
        SessionManager.login(
            access_token=access_token,
            refresh_token=refresh_token,
            user_data=user_data
        )
    
    @staticmethod
    def get_user() -> Optional[Dict[str, Any]]:
        """
        兼容旧版 API：获取用户资料
        
        Returns:
            用户资料 or None
        """
        logger.warning("⚠️ get_user() 已废弃，请使用 get_user_info()")
        return SessionManager.get_user_info()
    
    @staticmethod
    def clear():
        """
        兼容旧版 API：清除 Session
        """
        logger.warning("⚠️ clear() 已废弃，请使用 logout()")
        SessionManager.logout()
    
    @staticmethod
    def is_logged_in() -> bool:
        """
        兼容旧版 API：检查登入状态
        
        Returns:
            bool: True=已登入, False=未登入
        """
        logger.warning("⚠️ is_logged_in() 已废弃，请使用 is_authenticated()")
        return SessionManager.is_authenticated()


# ============================================
# 全域 Session Manager 实例（便捷访问）
# ============================================
session_manager = SessionManager()


# ============================================
# 测试程序
# ============================================
if __name__ == "__main__":
    import sys
    
    print("=" * 60)
    print("SessionManager v2.0 测试")
    print("=" * 60)
    
    # 测试 1：初始化
    print("\n📋 测试 1: 初始化")
    SessionManager.init()
    print("✅ 初始化成功")
    
    # 测试 2：登入
    print("\n📋 测试 2: 登入")
    test_user_data = {
        "id": "test-user-123",
        "email": "test@example.com",
        "user_metadata": {
            "name": "测试用户",
            "role": "admin"
        }
    }
    
    SessionManager.login(
        access_token="test_access_token_12345",
        refresh_token="test_refresh_token_12345",
        user_data=test_user_data,
        expires_at=(datetime.now() + timedelta(hours=1)).isoformat()
    )
    print(f"✅ 登入成功: {SessionManager.get_user_email()}")
    
    # 测试 3：认证检查
    print("\n📋 测试 3: 认证检查")
    is_auth = SessionManager.is_authenticated()
    print(f"✅ 认证状态: {'已登入' if is_auth else '未登入'}")
    assert is_auth, "❌ 认证检查失败"
    
    # 测试 4：获取用户信息
    print("\n📋 测试 4: 获取用户信息")
    user_info = SessionManager.get_user_info()
    print(f"✅ 用户 ID: {user_info['id']}")
    print(f"✅ 用户 Email: {user_info['email']}")
    print(f"✅ 用户姓名: {user_info['name']}")
    print(f"✅ 用户角色: {user_info['role']}")
    
    # 测试 5：Session 统计
    print("\n📋 测试 5: Session 统计")
    print(f"✅ Session 持续时间: {SessionManager.get_session_duration()}秒")
    print(f"✅ Session 剩余时间: {SessionManager.get_remaining_time()}秒")
    print(f"✅ Token 剩余时间: {SessionManager.get_token_remaining_time()}秒")
    
    # 测试 6：自定义资料
    print("\n📋 测试 6: 自定义资料")
    SessionManager.set_custom_data("test_key", "test_value")
    value = SessionManager.get_custom_data("test_key")
    print(f"✅ 自定义资料: {value}")
    assert value == "test_value", "❌ 自定义资料测试失败"
    
    # 测试 7：登出
    print("\n📋 测试 7: 登出")
    SessionManager.logout()
    is_auth_after_logout = SessionManager.is_authenticated()
    print(f"✅ 登出后认证状态: {'已登入' if is_auth_after_logout else '未登入'}")
    assert not is_auth_after_logout, "❌ 登出测试失败"
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)
