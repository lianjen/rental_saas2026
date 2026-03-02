"""
幸福之家 Pro - 租賃管理系統
Nordic Edition v15.1 (Service Architecture + Auth Gatekeeper + Cookie Persistence)
✅ 完全移除 db 依賴
✅ 使用 Service 架構
✅ 動態載入頁面模組
✅ Supabase Auth 認證系統
✅ 登入守門員機制
✅ Session 自動刷新
✅ Cookie 持久化（F5 刷新不登出）
✅ 角色權限管理
✅ 完整錯誤處理
"""

import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
import streamlit as st

# ============================================
# 0. Environment Variables
# ============================================

load_dotenv()


def get_env(var: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(var)
    if value:
        return value
    try:
        value = st.secrets[var]  # type: ignore[index]
        if value:
            return value
    except Exception:
        pass
    try:
        supa_cfg = st.secrets["supabase"]  # type: ignore[index]
        value = supa_cfg.get(var)  # type: ignore[union-attr]
        if value:
            return value
    except Exception:
        pass
    return default


def get_supabase_url():
    return get_env("SUPABASE_URL") or get_env("url")


def get_supabase_key():
    return get_env("SUPABASE_KEY") or get_env("key")


SUPABASE_URL = get_supabase_url()
SUPABASE_KEY = get_supabase_key()

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ 缺少必要環境變數: SUPABASE_URL 或 SUPABASE_KEY")
    st.info("請在 .streamlit/secrets.toml 中設定 [supabase] 區塊")
    st.code("""
[supabase]
url = "https://xxxxx.supabase.co"
key = "eyJhbGciOi..."
    """)
    st.stop()

APP_CONFIG = {
    "title":       get_env("APP_TITLE", "幸福之家 Pro"),
    "version":     get_env("APP_VERSION", "v15.1"),
    "environment": get_env("ENVIRONMENT", "production"),
    "log_level":   get_env("LOG_LEVEL", "INFO"),
    "dev_mode":    get_env("DEV_MODE", "false").lower() == "true",
}

# ============================================
# 1. Page Config
# ============================================
st.set_page_config(
    page_title=APP_CONFIG["title"],
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================
# 2. Logging
# ============================================
logging.basicConfig(
    level=getattr(logging, APP_CONFIG["log_level"].upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"啟動應用程式: {APP_CONFIG['title']} {APP_CONFIG['version']}")

# ============================================
# 3. Load CSS
# ============================================

def load_css(filename: str) -> None:
    try:
        with open(filename, encoding="utf-8") as f:
            css = f.read()
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        logger.warning(f"CSS 檔案不存在: {filename}")
    except Exception as e:
        logger.error(f"載入 CSS 失敗: {e}")


load_css(os.path.join("assets", "style.css"))

# ============================================
# 4. Imports
# ============================================
try:
    from utils.session_manager import session_manager
    from services.auth_service import AuthService
    logger.info("✅ Session Manager 和 Auth Service 載入成功")
except ImportError as e:
    logger.error(f"❌ 無法載入核心模組: {e}")
    st.error(f"❌ 系統模組載入失敗: {e}")
    st.stop()

from services.base_db import BaseDBService  # noqa: E402

# ============================================
# 5. Database Health Check
# ============================================

@st.cache_resource(ttl=300)
def check_database_health() -> bool:
    try:
        db = BaseDBService()
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            return cur.fetchone()[0] == 1
    except Exception as e:
        logger.error(f"❌ DB 健康檢查失敗: {e}")
        return False


# ============================================
# 6. Cookie 輔助函數
# ============================================

def _try_restore_from_cookie() -> bool:
    """
    F5 刷新後，嘗試從 Cookie 讀取 refresh_token 带還原 Session。
    還原成功返回 True，否則 False。
    """
    try:
        from utils.cookie_manager import load_auth_cookie
        cookie = load_auth_cookie()
        if not cookie or not cookie.get("refresh_token"):
            logger.debug("🍪 Cookie 沒有 refresh_token，需要登入")
            return False

        logger.info("🍪 Cookie 發現 refresh_token，嘗試還原 Session...")
        auth_service = AuthService()
        new_session  = auth_service.refresh_session(cookie["refresh_token"])

        if not new_session:
            logger.warning("⚠️ refresh_token 已失效，清除 Cookie")
            from utils.cookie_manager import clear_auth_cookie
            clear_auth_cookie()
            return False

        session_manager.login(
            access_token  = new_session["access_token"],
            refresh_token = new_session["refresh_token"],
            user_data     = new_session["user"],
            expires_at    = new_session.get("expires_at"),
        )
        from utils.cookie_manager import save_auth_cookie
        save_auth_cookie(new_session["access_token"], new_session["refresh_token"])

        logger.info(f"✅ Session 從 Cookie 還原成功: {session_manager.get_user_email()}")
        return True

    except Exception as e:
        logger.error(f"❌ Cookie 還原 Session 失敗: {e}", exc_info=True)
        return False


def _sync_cookie() -> None:
    """登入或 Token 刷新後，同步最新 Token 到 Cookie"""
    try:
        from utils.cookie_manager import save_auth_cookie, load_auth_cookie
        at = st.session_state.get("access_token",  "")
        rt = st.session_state.get("refresh_token", "")
        if not at or not rt:
            return
        cookie = load_auth_cookie()
        if not cookie or cookie.get("refresh_token") != rt:
            save_auth_cookie(at, rt)
            logger.debug("🔄 Cookie 已同步")
    except Exception as e:
        logger.debug(f"Cookie 同步失敗: {e}")


def _clear_cookie() -> None:
    try:
        from utils.cookie_manager import clear_auth_cookie
        clear_auth_cookie()
    except Exception as e:
        logger.debug(f"Cookie 清除失敗: {e}")


# ============================================
# 7. Session Refresh Handler
# ============================================

def handle_session_refresh() -> bool:
    try:
        if not session_manager.check_session_timeout():
            return True

        auth_service  = AuthService()
        refresh_token = st.session_state.get("refresh_token")
        if not refresh_token:
            return False

        new_session = auth_service.refresh_session(refresh_token)
        if new_session:
            st.session_state["access_token"]  = new_session["access_token"]
            st.session_state["refresh_token"] = new_session["refresh_token"]
            st.session_state["expires_at"]    = new_session.get("expires_at")
            st.session_state["last_activity"] = datetime.now()
            logger.info("✅ Session 已自動刷新")
            return True
        return False

    except Exception as e:
        logger.error(f"❌ Session 刷新異常: {e}", exc_info=True)
        return False


# ============================================
# 8. Permission Check
# ============================================

def check_page_permission(page_name: str) -> bool:
    user_role = session_manager.get_user_role()
    if user_role == "admin":
        return True
    restricted = ["用戶管理", "系統設定"]
    for r in restricted:
        if r in page_name:
            logger.warning(f"⚠️ 權限拒絕: {session_manager.get_user_email()} → {page_name}")
            return False
    return True


# ============================================
# 9. Main (Gatekeeper + Cookie Restore)
# ============================================

def main() -> None:
    session_manager.init()

    if not session_manager.is_authenticated():
        if _try_restore_from_cookie():
            pass  # 還原成功，直接往下執行
        else:
            render_login_page()
            return

    if not handle_session_refresh():
        st.warning("⏱️ 登入已過期，請重新登入")
        _clear_cookie()
        session_manager.logout()
        st.rerun()
        return

    _sync_cookie()
    render_main_app()


# ============================================
# 10. Login Page
# ============================================

def render_login_page() -> None:
    try:
        from views.login_view import render as render_login
        render_login()
    except ImportError as e:
        logger.error(f"❌ 登入頁面載入失敗: {e}")
        st.error("❌ 無法載入登入頁面")
        if APP_CONFIG["dev_mode"]:
            st.exception(e)
    except Exception as e:
        logger.error(f"❌ 登入頁面渲染失敗: {e}")
        st.error(f"❌ {e}")
        if APP_CONFIG["dev_mode"]:
            st.exception(e)


# ============================================
# 11. Main App
# ============================================

def render_main_app() -> None:
    db_healthy = False
    try:
        db_healthy = check_database_health()
        if not db_healthy:
            st.warning("⚠️ 資料庫連線異常")
    except Exception as e:
        logger.error(f"DB 檢查異常: {e}")

    render_sidebar(db_healthy)
    render_main_content()


def render_sidebar(db_healthy: bool) -> None:
    with st.sidebar:
        st.title(f"🏠 {APP_CONFIG['title']}")
        st.caption(f"Nordic Edition {APP_CONFIG['version']}")
        if APP_CONFIG["dev_mode"]:
            st.caption("🔧 開發模式")
        st.divider()
        render_user_card()
        st.divider()
        menu = render_menu()
        st.session_state["current_menu"] = menu
        render_system_status(db_healthy)


def _parse_expires_at(raw) -> Optional[datetime]:
    try:
        if isinstance(raw, (int, float)):
            return datetime.fromtimestamp(raw, tz=timezone.utc)
        if isinstance(raw, str):
            dt = datetime.fromisoformat(raw.replace('Z', '+00:00'))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        if isinstance(raw, datetime):
            return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    except Exception as e:
        logger.debug(f"_parse_expires_at 失敗: {e}")
    return None


def render_user_card() -> None:
    with st.container(border=True):
        user_name  = session_manager.get_user_name()
        user_email = session_manager.get_user_email()
        user_role  = session_manager.get_user_role()

        st.markdown(f"**👤 {user_name}**")
        st.caption(f"📧 {user_email}")
        if user_role == "admin":
            st.caption("🏷️ 角色: 👨‍💼 管理員")
        else:
            st.caption("🏷️ 角色: 👤 用戶")

        login_time = st.session_state.get("login_time")
        if login_time:
            try:
                if isinstance(login_time, str):
                    login_time = datetime.fromisoformat(login_time)
                secs = int((datetime.now() - login_time).total_seconds())
                st.caption(f"⏱️ 已登入: {secs // 3600}h {(secs % 3600) // 60}m")
            except Exception:
                pass

        expires_dt = _parse_expires_at(st.session_state.get("expires_at"))
        if expires_dt:
            try:
                rem = (expires_dt - datetime.now(tz=timezone.utc)).total_seconds()
                if rem > 0:
                    st.caption(f"🔑 Token: {int(rem // 3600)}h {int((rem % 3600) // 60)}m")
                else:
                    st.caption("🔑 Token: 即將刷新")
            except Exception:
                pass

        st.divider()
        if st.button("🚪 登出", use_container_width=True, type="secondary"):
            handle_logout()


def handle_logout() -> None:
    try:
        AuthService().logout()
        logger.info(f"✅ 用戶 {session_manager.get_user_email()} 已登出")
    except Exception as e:
        logger.error(f"Supabase 登出失敗: {e}")
    _clear_cookie()
    session_manager.logout()
    st.success("✅ 已登出")
    st.rerun()


def render_menu() -> str:
    user_role  = session_manager.get_user_role()
    menu_items = [
        "📊 儀表板",
        "👥 房客管理",
        "💰 租金管理",
        "📋 繳費追蹤",
        "⚡ 電費管理",
        "💸 支出記錄",
        "📱 LINE 綁定",
        "📬 通知管理",
    ]
    if user_role == "admin":
        menu_items.extend(["⚙️ 系統設定", "👨‍💼 用戶管理"])

    current = st.session_state.get("current_menu", menu_items[0])
    if current not in menu_items:
        current = menu_items[0]

    return st.radio(
        "功能選單",
        menu_items,
        index=menu_items.index(current),
        label_visibility="collapsed",
    )


def render_system_status(db_healthy: bool) -> None:
    with st.expander("🔧 系統狀態", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            st.success("✅ 資料庫") if db_healthy else st.error("❌ 資料庫")
        with c2:
            env = APP_CONFIG["environment"]
            # ✅ 不在 f-string 內嵌激活表達式，避免 Python 3.13 surrogate 錯誤
            env_icon = "🚀" if env == "production" else "🔧"
            st.info(f"{env_icon} {env.capitalize()}")
        st.caption(f"Version: {APP_CONFIG['version']}")
        if get_env("LINE_CHANNEL_ACCESS_TOKEN"):
            st.success("✅ LINE Bot")
        else:
            st.warning("⚠️ LINE Bot")
        st.caption(f"👤 {session_manager.get_user_email()}")
        if APP_CONFIG["dev_mode"]:
            st.divider()
            if st.button("🔄 清除快取"):
                st.cache_data.clear()
                st.cache_resource.clear()
                st.rerun()


def render_main_content() -> None:
    menu = st.session_state.get("current_menu", "📊 儀表板")
    if not check_page_permission(menu):
        st.error("❌ 權限不足")
        return

    PAGE_MODULES = {
        "📊 儀表板":       "dashboard",
        "👥 房客管理":     "tenants",
        "💰 租金管理":     "rent",
        "📋 繳費追蹤":     "tracking",
        "⚡ 電費管理":     "electricity",
        "💸 支出記錄":     "expenses",
        "📱 LINE 綁定":    "line_binding",
        "📬 通知管理":     "notifications",
        "⚙️ 系統設定":     "settings",
        "👨‍💼 用戶管理":  "user_management",
    }
    page_module = PAGE_MODULES.get(menu)
    if not page_module:
        st.error(f"❌ 未知頁面: {menu}")
        return
    load_page_module(page_module)


def load_page_module(page_module: str) -> None:
    import importlib
    try:
        module = importlib.import_module(f"views.{page_module}")
        logger.info(f"載入頁面: {page_module} ({session_manager.get_user_email()})")
        if hasattr(module, 'render'):
            module.render()
        elif hasattr(module, 'show'):
            module.show()
        else:
            st.error(f"❌ 模組 {page_module} 缺少 render()/show()")
    except ImportError as e:
        st.error(f"❌ 無法載入: {page_module}")
        logger.error(f"載入模組失敗: {page_module} - {e}", exc_info=True)
        if APP_CONFIG["dev_mode"]:
            st.exception(e)
        if st.button("🔙 返回儀表板"):
            st.session_state["current_menu"] = "📊 儀表板"
            st.rerun()
    except Exception as e:
        st.error("❌ 載入頁面失敗")
        logger.error(f"頁面渲染失敗: {page_module} - {e}", exc_info=True)
        if APP_CONFIG["dev_mode"]:
            st.exception(e)
        if st.button("🔙 返回儀表板"):
            st.session_state["current_menu"] = "📊 儀表板"
            st.rerun()


# ============================================
# 12. Entry Point
# ============================================

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"啟動失敗: {e}", exc_info=True)
        st.error("❌ 系統啟動失敗")
        if APP_CONFIG["dev_mode"]:
            st.exception(e)
        if st.button("🔄 重新啟動"):
            session_manager.logout()
            st.rerun()
