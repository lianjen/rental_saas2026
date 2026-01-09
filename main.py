import os
from typing import Optional

from dotenv import load_dotenv
import streamlit as st

# ============================================
# 0. Environment Variables
# ============================================

# 載入 .env（本機開發用；Streamlit Cloud 主要用 Secrets）
load_dotenv()


def get_env(var: str, default: Optional[str] = None) -> Optional[str]:
    """統一從 os.environ、st.secrets root 和 st.secrets['supabase'] 讀環境變數。"""
    # 1. 系統環境變數
    value = os.getenv(var)
    if value:
        return value

    # 2. Streamlit Secrets 根層
    try:
        value = st.secrets[var]  # type: ignore[index]
        if value:
            return value
    except Exception:
        pass

    # 3. Streamlit Secrets 裡的 [supabase] 區塊
    try:
        supa_cfg = st.secrets["supabase"]  # type: ignore[index]
        value = supa_cfg.get(var)  # type: ignore[union-attr]
        if value:
            return value
    except Exception:
        pass

    return default


# 驗證必要環境變數
REQUIRED_VARS = ["SUPABASE_URL", "SUPABASE_KEY"]

missing_vars = [var for var in REQUIRED_VARS if not get_env(var)]

if missing_vars:
    st.error(f"❌ 缺少必要環境變數: {', '.join(missing_vars)}")
    st.info("請在 Streamlit Cloud 的 Secrets 或本機 .env 中設定這些變數（可參考 .env.example）")
    st.stop()

# 讀取全域配置（允許從 env / secrets 覆蓋預設值）
APP_CONFIG = {
    "title": get_env("APP_TITLE", "幸福之家 Pro"),
    "version": get_env("APP_VERSION", "v14.2"),
    "environment": get_env("ENVIRONMENT", "production"),
    "log_level": get_env("LOG_LEVEL", "INFO"),
}

# ============================================
# 1. Page Config - 必須是第一個 Streamlit 命令
# ============================================
st.set_page_config(
    page_title=APP_CONFIG["title"],
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================
# 2. Load CSS
# ============================================


def load_css(filename: str) -> None:
    """載入外部 CSS 檔案。"""
    try:
        with open(filename, encoding="utf-8") as f:
            css = f.read()
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        # 本機或部署時沒有 CSS 檔案不影響主流程
        pass
    except Exception as e:
        st.warning(f"載入 CSS 時發生錯誤: {e}")


css_path = os.path.join("assets", "style.css")
load_css(css_path)

# ============================================
# 3. Database
# ============================================

from services.db import SupabaseDB  # noqa: E402


@st.cache_resource
def get_db() -> SupabaseDB:
    """初始化並快取資料庫連線。"""
    return SupabaseDB()


# ============================================
# 4. Main Function
# ============================================


def main() -> None:
    # 初始化資料庫
    try:
        db = get_db()
    except Exception as e:
        st.error(f"資料庫連線失敗: {e}")
        st.stop()

    # ============ 側邊欄 ============
    with st.sidebar:
        st.title(f"🏠 {APP_CONFIG['title']}")
        st.caption(f"Nordic Edition {APP_CONFIG['version']} · {APP_CONFIG['environment']}")

        menu = st.radio(
            "功能選單",
            [
                "📊 儀表板",
                "💰 租金管理",
                "📝 追蹤功能",
                "👥 房客管理",
                "⚡ 電費管理",
                "💸 支出記錄",
                "📬 通知管理",
                "⚙️ 系統設定",
            ],
            label_visibility="collapsed",
        )

    # ============ 動態載入 Views (Lazy Loading) ============
    try:
        if menu == "📊 儀表板":
            from views import dashboard  # noqa: E402

            dashboard.render(db)
        elif menu == "💰 租金管理":
            from views import rent  # noqa: E402

            rent.render(db)
        elif menu == "📝 追蹤功能":
            from views import tracking  # noqa: E402

            tracking.render(db)
        elif menu == "👥 房客管理":
            from views import tenants  # noqa: E402

            tenants.render(db)
        elif menu == "⚡ 電費管理":
            from views import electricity  # noqa: E402

            electricity.render(db)
        elif menu == "💸 支出記錄":
            from views import expenses  # noqa: E402

            expenses.render(db)
        elif menu == "📬 通知管理":
            from views import notifications  # noqa: E402

            notifications.render(db)
        elif menu == "⚙️ 系統設定":
            from views import settings  # noqa: E402

            settings.render(db)
    except Exception as e:
        st.error(f"載入頁面時發生錯誤: {e}")
        st.exception(e)


# ============================================
# 5. Entry Point
# ============================================

if __name__ == "__main__":
    main()
