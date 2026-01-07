import streamlit as st
import os

# Page Config
st.set_page_config(
    page_title="幸福之家 Pro | 租務管理系統",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 先暫時停用 CSS，確認是不是 CSS 造成的問題
# def load_css(filename):
#     try:
#         with open(filename) as f:
#             st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
#     except FileNotFoundError:
#         pass
# 
# css_path = os.path.join('assets', 'style.css')
# load_css(css_path)

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
