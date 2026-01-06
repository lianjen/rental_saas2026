import streamlit as st
import time
import sys
sys.path.append('..')
from datetime import date, datetime
from components.cards import section_header
from config.constants import ROOMS, PAYMENT, EXPENSE

ALL_ROOMS = ["1A", "1B", "2A", "2B", "3A", "3B", "3C", "3D", "4A", "4B", "4C", "4D"]

def render(db):
    section_header("📅 繳費追蹤", "Payment Tracking")
    
    tab1, tab2 = st.tabs(["🔍 繳費排程查詢", "📝 標記已繳"])
    
    with tab1:
        c1, c2, c3 = st.columns(3)
        room_filter = c1.selectbox("房號篩選", ["全部"] + ALL_ROOMS)
        status_filter = c2.selectbox("狀態篩選", ["全部", "未繳", "已繳"])
        year_filter = c3.number_input("年份", value=datetime.now().year)
        
        df = db.get_payment_schedule(
            room=room_filter if room_filter != "全部" else None,
            status=status_filter if status_filter != "全部" else None,
            year=year_filter
        )
        
        if not df.empty:
            st.dataframe(
                df, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "amount": st.column_config.NumberColumn("金額", format="$%d"),
                    "paid_amount": st.column_config.NumberColumn("已付", format="$%d"),
                    "status": "狀態"
                }
            )
        else:
            st.info("無符合條件的資料")

    with tab2:
        st.markdown("##### 快速標記未繳項目")
        unpaid = db.get_payment_schedule(status="未繳")
        
        if unpaid.empty:
            st.success("🎉 太棒了！目前所有帳單皆已繳清。")
        else:
            # 製作選項清單
            options = {
                f"{r['room_number']} {r['tenant_name']} - {r['payment_month']}月 (${r['amount']:.0f})": r['id'] 
                for _, r in unpaid.iterrows()
            }
            
            selected_label = st.selectbox("選擇待繳項目", list(options.keys()))
            selected_id = options[selected_label]
            
            # 找到該筆資料的預設金額
            target_row = unpaid[unpaid['id'] == selected_id].iloc[0]
            default_amount = float(target_row['amount'])
            
            with st.form("mark_paid_form"):
                c1, c2 = st.columns(2)
                paid_d = c1.date_input("繳費日期", value=date.today())
                paid_a = c2.number_input("實收金額", value=default_amount, step=100.0)
                note = st.text_input("備註")
                
                if st.form_submit_button("✅ 標記為已繳", type="primary"):
                    ok, msg = db.mark_payment_done(selected_id, paid_d.strftime("%Y-%m-%d"), paid_a, note)
                    if ok:
                        st.toast(msg, icon="✅")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.toast(msg, icon="❌")