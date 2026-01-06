import streamlit as st
import time
import sys
sys.path.append('..')
from config.constants import ROOMS, PAYMENT, EXPENSE
from datetime import date
from components.cards import section_header

EXPENSE_CATEGORIES = ["維修", "雜項", "貸款", "水電費", "網路費"]

def render(db):
    section_header("💰 支出管理", "Expense Tracking")
    
    col_form, col_list = st.columns([1, 2])
    
    with col_form:
        with st.container(border=True):
            st.subheader("新增支出")
            with st.form("add_expense"):
                d = st.date_input("日期", value=date.today())
                cat = st.selectbox("分類", EXPENSE_CATEGORIES)
                amt = st.number_input("金額", min_value=0.0, step=100.0)
                desc = st.text_input("說明 (選填)")
                
                if st.form_submit_button("💾 儲存紀錄", type="primary"):
                    if db.add_expense(d.strftime("%Y-%m-%d"), cat, amt, desc):
                        st.toast("已儲存", icon="✅")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("儲存失敗")

    with col_list:
        st.subheader("最近 50 筆支出")
        df = db.get_expenses(limit=50)
        if not df.empty:
            st.dataframe(
                df, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "expense_date": "日期",
                    "category": "分類",
                    "amount": st.column_config.NumberColumn("金額", format="$%d"),
                    "description": "說明"
                }
            )
        else:
            st.info("暫無支出紀錄")