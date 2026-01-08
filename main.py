import streamlit as st
import os

# ============================================
# 1. Page Config - 必須是第一個 Streamlit 命令
# ============================================
st.set_page_config(
    page_title="幸福之家 Pro",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# 2. Load CSS
# ============================================
def load_css(filename):
    """載入外部 CSS 檔案"""
    try:
        with open(filename, encoding='utf-8') as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        pass
    except Exception as e:
        st.warning(f"載入 CSS 時發生錯誤: {e}")

css_path = os.path.join('assets', 'style.css')
load_css(css_path)

# ============================================
# 3. Database
# ============================================
from services.db import SupabaseDB

@st.cache_resource
def get_db():
    """初始化並快取資料庫連線"""
    return SupabaseDB()

# ============================================
# 4. Main Function
# ============================================
def main():
    # 初始化資料庫
    try:
        db = get_db()
    except Exception as e:
        st.error(f"資料庫連線失敗: {e}")
        st.stop()
    
    # ============ 側邊欄 ============
    with st.sidebar:
        st.title("🏠 幸福之家 Pro")
        st.caption("Nordic Edition v14.2")
        
        menu = st.radio(
            "功能選單",
            [
                "📊 儀表板",
                "💰 租金管理",
                "📝 追蹤功能",
                "👥 房客管理",
                "⚡ 電費管理",
                "💸 支出記錄",
                "📬 通知管理",  # ← 新增
                "⚙️ 系統設定"
            ],
            label_visibility="collapsed"
        )
    
    # ============ 動態載入 Views (Lazy Loading) ============
    try:
        if menu == "📊 儀表板":
            from views import dashboard
            dashboard.render(db)
        elif menu == "💰 租金管理":
            from views import rent
            rent.render(db)
        elif menu == "📝 追蹤功能":
            from views import tracking
            tracking.render(db)
        elif menu == "👥 房客管理":
            from views import tenants
            tenants.render(db)
        elif menu == "⚡ 電費管理":
            from views import electricity
            electricity.render(db)
        
