import streamlit as st
import os
import streamlit.components.v1 as components # 新增這個庫用於 JavaScript 控制

# Page Config
st.set_page_config(
    page_title="幸福之家 Pro | 租務管理系統",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load CSS
def load_css(filename):
    try:
        with open(filename) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        pass

css_path = os.path.join('assets', 'style.css')
load_css(css_path)

# Database
from services.db import SupabaseDB

@st.cache_resource
def get_db():
    return SupabaseDB()

db = get_db()

# Import views
from views import dashboard, tenants, rent, electricity, expenses, tracking, settings

def main():
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
                "⚙️ 系統設定"
            ],
            label_visibility="collapsed"
        )

    # ============ 手機版救援按鈕 (如果側邊欄按鈕消失，這個可以救急) ============
    # 檢查側邊欄是否收起 (Streamlit 無法直接偵測，所以我們預設在最上方提供一個小的觸發器)
    if st.sidebar.empty: # 這是一個簡單的檢查，或是直接放一個小按鈕
        pass

    # 在主頁面頂部加入一個 JS 控制器 (為了保險起見)
    # 只有當使用者找不到側邊欄時，點擊這裡的按鈕
    col_hack, col_content = st.columns([1, 15])
    with col_hack:
       # 如果你需要一個備用的展開按鈕，解開下面這行註解
       # if st.button("☰", key="mobile_trigger", help="展開選單"):
       #     js = """<script>window.parent.document.querySelector('[data-testid="stSidebarCollapsedControl"]').click();</script>"""
       #     components.html(js, height=0)
       pass

    # ============ Views 路由 ============
    if menu == "📊 儀表板":
        dashboard.render(db)
    elif menu == "💰 租金管理":
        rent.render(db)
    elif menu == "📝 追蹤功能":
        tracking.render(db)
    elif menu == "👥 房客管理":
        tenants.render(db)
    elif menu == "⚡ 電費管理":
        electricity.render(db)
    elif menu == "💸 支出記錄":
        expenses.render(db)
    elif menu == "⚙️ 系統設定":
        settings.render(db)

if __name__ == "__main__":
    main()
