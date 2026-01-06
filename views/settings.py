import streamlit as st
import sys
sys.path.append('..')
from config.constants import ROOMS, PAYMENT, EXPENSE
from components.cards import section_header

def render(db):
    section_header("⚙️ 系統設置", "System Settings")
    
    st.info("目前使用 Supabase 雲端資料庫，資料已自動備份於雲端。")
    
    st.subheader("📥 資料匯出")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("下載房客資料 (CSV)", use_container_width=True):
            df = db.get_tenants()
            st.download_button("點此下載", df.to_csv(index=False).encode('utf-8-sig'), "tenants.csv", "text/csv")
            
    with c2:
        if st.button("下載收支紀錄 (CSV)", use_container_width=True):
            df = db.get_expenses(limit=1000)
            st.download_button("點此下載", df.to_csv(index=False).encode('utf-8-sig'), "expenses.csv", "text/csv")