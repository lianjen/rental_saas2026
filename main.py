import streamlit as st
import os

# 設定頁面配置
st.set_page_config(
    page_title="幸福之家 Pro | 租務管理系統",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 載入自定義 CSS
def load_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        pass  # 容錯處理

css_path = os.path.join("assets", "style.css")
load_css(css_path)

# 初始化資料庫
from services.db import SupabaseDB

@st.cache_resource
def get_db():
    return SupabaseDB()

db = get_db()

# 引入所有 Views
from views import dashboard, tenants, rent, electricity, expenses, tracking, settings

def main():
    with st.sidebar:
        st.title("🏠 幸福之家 Pro")
        st.markdown("<div style='font-size: 0.8rem; color: #888; margin-bottom: 20px;'>Nordic Edition v14.1</div>", unsafe_allow_html=True)
        
        menu = st.radio(
            "功能選單",
            [
                "📊 儀表板",
                "💵 租金收繳",
                "📅 繳費追蹤",
                "👥 房客管理",
                "⚡ 電費管理",
                "💰 支出管理",
                "⚙️ 系統設置"
            ],
            label_visibility="collapsed"
        )
        
    # 路由邏輯
    if menu == "📊 儀表板":
        dashboard.render(db)
    elif menu == "💵 租金收繳":
        rent.render(db)
    elif menu == "📅 繳費追蹤":
        tracking.render(db)
    elif menu == "👥 房客管理":
        tenants.render(db)
    elif menu == "⚡ 電費管理":
        electricity.render(db)
    elif menu == "💰 支出管理":
        expenses.render(db)
    elif menu == "⚙️ 系統設置":
        settings.render(db)

if __name__ == "__main__":
    main()

