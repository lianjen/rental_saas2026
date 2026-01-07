import streamlit as st
from services.db import get_db

st.set_page_config(
    page_title="連振租賃管理",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 先註解掉 CSS，恢復後再開啟
# css_path = os.path.join('assets', 'style.css')
# load_css(css_path)

from views import dashboard, tenants, rent, electricity, expenses, tracking, settings

def main():
    db = get_db()
    
    with st.sidebar:
        st.title("🏠 租賃管理")
        
        menu = st.radio(
            "選單",
            [
                "📊 儀表板",
                "💰 租金管理",
                "📝 追蹤功能",
                "👥 房客管理",
                "⚡ 電費管理",
                "💸 支出記錄",
                "⚙️ 系統設定"
            ]
        )
    
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
