"""
電費管理 - 簡化穩定版
完全使用 db 現有方法,無子模組依賴
"""

import streamlit as st
import pandas as pd
from datetime import date
from typing import Dict, List
import logging

# 安全 import
try:
    from components.cards import section_header, metric_card, empty_state, data_table, info_card
except ImportError:
    def section_header(title, icon="", divider=True):
        st.markdown(f"### {icon} {title}")
        if divider:
            st.divider()
    
    def metric_card(label, value, icon="", color="normal"):
        st.metric(label, value)
    
    def empty_state(msg, icon="", desc=""):
        st.info(f"{icon} {msg}")
    
    def data_table(df, key="table"):
        st.dataframe(df, use_container_width=True, key=key)
    
    def info_card(title, content, icon="", type="info"):
        st.info(f"{icon} {title}: {content}")

try:
    from config.constants import ROOMS
except ImportError:
    class ROOMS:
        ALL_ROOMS = ["1A", "1B", "2A", "2B", "3A", "3B", "3C", "3D", "4A", "4B", "4C", "4D"]
        SHARING_ROOMS = ["2A", "2B", "3A", "3B", "3C", "3D", "4A", "4B", "4C", "4D"]
        EXCLUSIVE_ROOMS = ["1A", "1B"]

logger = logging.getLogger(__name__)

# ============== 計算邏輯 ==============

def calculate_electricity_charges(
    taipower_bills: List[Dict],
    room_readings: Dict[str, float]
) -> Dict:
    """
    計算電費
    
    Args:
        taipower_bills: [{'floor_label', 'amount', 'kwh'}, ...]
        room_readings: {'房號': 度數, ...}
    
    Returns:
        計費結果字典
    """
    # 計算總計
    total_amount = sum(bill['amount'] for bill in taipower_bills)
    total_kwh = sum(bill['kwh'] for bill in taipower_bills)
    
    if total_kwh <= 0:
        return None
    
    # 單位電價
    unit_price = round(total_amount / total_kwh, 2)
    
    # 房間總度數
    total_room_kwh = sum(room_readings.values())
    
    # 公用電
    public_kwh = max(0, total_kwh - total_room_kwh)
    
    # 分攤房間數
    sharing_rooms = [r for r in room_readings.keys() if r in ROOMS.SHARING_ROOMS]
    sharing_count = len(sharing_rooms)
    
    # 每間分攤
    shared_per_room = round(public_kwh / sharing_count, 2) if sharing_count > 0 else 0
    
    # 計算各房間
    results = []
    for room, kwh in room_readings.items():
        is_sharing = room in ROOMS.SHARING_ROOMS
        room_type = "分攤房間" if is_sharing else "獨立房間"
        
        shared_kwh = shared_per_room if is_sharing else 0
        total_room_kwh = kwh + shared_kwh
        charge = round(total_room_kwh * unit_price)
        
        results.append({
            '房號': room,
            '類型': room_type,
            '使用度數': round(kwh, 2),
            '公用分攤': round(shared_kwh, 2),
            '總度數': round(total_room_kwh, 2),
            '應繳金額': charge
        })
    
    total_charge = sum(r['應繳金額'] for r in results)
    
    return {
        'unit_price': unit_price,
        'public_kwh': public_kwh,
        'shared_per_room': shared_per_room,
        'total_charge': total_charge,
        'taipower_amount': total_amount,
        'difference': total_charge - total_amount,
        'details': results
    }


# ============== Tab 1: 計費期間 ==============

def render_period_tab(db):
    """計費期間管理"""
    section_header("計費期間管理", "📅")
    
    # 建立新期間
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        year = st.number_input(
            "年份",
            min_value=2020,
            max_value=2030,
            value=date.today().year,
            key="period_year"
        )
    
    with col2:
        month_start = st.selectbox(
            "開始月",
            range(1, 13),
            index=date.today().month - 1,
            key="period_start"
        )
    
    with col3:
        month_end = st.selectbox(
            "結束月",
            range(1, 13),
            index=date.today().month % 12,
            key="period_end"
        )
    
    with col4:
        st.write("")
        st.write("")
        if st.button("➕ 建立", type="primary"):
            if month_end <= month_start:
                st.error("❌ 結束月必須大於開始月")
            else:
                ok, msg, period_id = db.add_electricity_period(year, month_start, month_end)
                if ok:
                    st.success(msg)
                    st.session_state.current_period_id = period_id
                    st.rerun()
                else:
                    st.error(msg)
    
    st.divider()
    
    # 顯示期間列表
    section_header("現有期間", "📋", divider=False)
    
    periods = db.get_all_periods()
    
    if not periods:
        empty_state("尚未建立期間", "📅", "請先建立一個計費期間")
        return
    
    # 選擇期間
    period_options = {
        f"{p['period_year']}/{p['period_month_start']}-{p['period_month_end']} (ID: {p['id']})": p['id']
        for p in periods
    }
    
    selected = st.selectbox(
        "選擇計費期間",
        list(period_options.keys()),
        key="selected_period"
    )
    
    if selected:
        period_id = period_options[selected]
        st.session_state.current_period_id = period_id
        
        col_del, col_info = st.columns([1, 3])
        
        with col_del:
            if st.button("🗑️ 刪除期間", type="secondary"):
                if st.session_state.get('confirm_delete_period'):
                    ok, msg = db.delete_electricity_period(period_id)
                    if ok:
                        st.success(msg)
                        if 'current_period_id' in st.session_state:
                            del st.session_state.current_period_id
                        del st.session_state.confirm_delete_period
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.session_state.confirm_delete_period = True
                    st.warning("⚠️ 再按一次確認刪除")
        
        with col_info:
            st.info(f"✅ 當前選中: ID {period_id}")


# ============== Tab 2: 計算電費 ==============

def render_calculation_tab(db):
    """計算電費"""
    
    if 'current_period_id' not in st.session_state:
        info_card("請先選擇期間", "請前往「計費期間」Tab 選擇一個期間", "⚠️", "warning")
        return
    
    period_id = st.session_state.current_period_id
    
    st.info(f"📅 當前期間 ID: {period_id}")
    
    st.divider()
    
    # === 步驟 1: 台電帳單 ===
    section_header("步驟 1: 輸入台電帳單", "📄")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**1F 台電單**")
        f1_amount = st.number_input("金額 (元)", min_value=0, value=0, step=100, key="f1_amt")
        f1_kwh = st.number_input("度數", min_value=0.0, value=0.0, step=10.0, key="f1_kwh")
    
    with col2:
        st.markdown("**2-4F 台電單**")
        f2_amount = st.number_input("金額 (元)", min_value=0, value=0, step=100, key="f2_amt")
        f2_kwh = st.number_input("度數", min_value=0.0, value=0.0, step=10.0, key="f2_kwh")
    
    # 儲存到 session_state
    if 'taipower_bills' not in st.session_state:
        st.session_state.taipower_bills = {}
    
    if st.button("💾 儲存台電單"):
        st.session_state.taipower_bills[period_id] = [
            {'floor_label': '1F', 'amount': f1_amount, 'kwh': f1_kwh},
            {'floor_label': '2-4F', 'amount': f2_amount, 'kwh': f2_kwh}
        ]
        st.success("✅ 已儲存")
    
    # 顯示已儲存的
    if period_id in st.session_state.get('taipower_bills', {}):
        bills = st.session_state.taipower_bills[period_id]
        total_amt = sum(b['amount'] for b in bills)
        total_kwh = sum(b['kwh'] for b in bills)
        
        st.write("**已儲存:**")
        col_a, col_b = st.columns(2)
        with col_a:
            metric_card("總金額", f"${total_amt:,}", "💰")
        with col_b:
            metric_card("總度數", f"{total_kwh:.0f} 度", "⚡")
    
    st.divider()
    
    # === 步驟 2: 房間讀數 ===
    section_header("步驟 2: 輸入房間讀數", "🔢")
    
    # 分 4 列顯示
    room_readings = {}
    rows = [ROOMS.ALL_ROOMS[i:i+3] for i in range(0, len(ROOMS.ALL_ROOMS), 3)]
    
    for row_rooms in rows:
        cols = st.columns(3)
        for col, room in zip(cols, row_rooms):
            with col:
                reading = st.number_input(
                    f"**{room}**",
                    min_value=0.0,
                    value=0.0,
                    step=10.0,
                    key=f"reading_{room}"
                )
                room_readings[room] = reading
    
    if st.button("💾 儲存讀數"):
        if 'room_readings' not in st.session_state:
            st.session_state.room_readings = {}
        st.session_state.room_readings[period_id] = room_readings
        st.success("✅ 已儲存")
    
    st.divider()
    
    # === 步驟 3: 計算 ===
    section_header("步驟 3: 計算電費", "🧮")
    
    if st.button("🚀 開始計算", type="primary"):
        # 取得資料
        bills = st.session_state.get('taipower_bills', {}).get(period_id)
        readings = st.session_state.get('room_readings', {}).get(period_id)
        
        if not bills:
            st.error("❌ 請先輸入台電帳單")
            return
        
        if not readings or all(v == 0 for v in readings.values()):
            st.error("❌ 請先輸入房間讀數")
            return
        
        # 計算
        result = calculate_electricity_charges(bills, readings)
        
        if not result:
            st.error("❌ 計算失敗")
            return
        
        # 顯示摘要
        st.markdown(f"""
### 📊 計算結果

**基本資訊**
- 台電金額: ${result['taipower_amount']:,} 元
- 單位電價: ${result['unit_price']:.2f} 元/度
- 公用電度數: {result['public_kwh']:.2f} 度
- 每間分攤: {result['shared_per_room']:.2f} 度

**收費總計**
- 房間總計: ${result['total_charge']:,} 元
- 與台電差異: ${result['difference']:+,.0f} 元
""")
        
        # 顯示明細
        st.divider()
        st.write("**各房間明細**")
        details_df = pd.DataFrame(result['details'])
        data_table(details_df, key="calc_details")
        
        # 儲存結果
        st.divider()
        if st.button("💾 儲存計費結果"):
            ok, msg = db.save_electricity_record(period_id, result['details'])
            if ok:
                st.success(msg)
                st.balloons()
            else:
                st.error(msg)
        
        # 匯出
        csv = details_df.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            "📥 下載 CSV",
            csv,
            f"electricity_{period_id}.csv",
            "text/csv"
        )


# ============== Tab 3: 繳費記錄 ==============

def render_records_tab(db):
    """繳費記錄"""
    section_header("繳費記錄", "📜")
    
    if 'current_period_id' not in st.session_state:
        info_card("請先選擇期間", "請前往「計費期間」Tab 選擇一個期間", "⚠️", "warning")
        return
    
    period_id = st.session_state.current_period_id
    
    # 取得記錄
    df = db.get_electricity_payment_record(period_id)
    
    if df is None or df.empty:
        empty_state("尚無記錄", "📭", "請先在「計算電費」Tab 完成計算並儲存")
        return
    
    # 顯示統計
    summary = db.get_electricity_payment_summary(period_id)
    
    if summary:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            metric_card("應收總額", f"${summary.get('total_due', 0):,}", "💰", "normal")
        
        with col2:
            metric_card("已收金額", f"${summary.get('total_paid', 0):,}", "✅", "success")
        
        with col3:
            metric_card("未收金額", f"${summary.get('total_balance', 0):,}", "⚠️", "warning")
    
    st.divider()
    
    # 顯示記錄
    st.write(f"共 {len(df)} 筆記錄")
    data_table(df, key="payment_records")
    
    # 快速更新
    st.divider()
    section_header("快速標記", "⚡", divider=False)
    
    unpaid_df = df[df['payment_status'] == '未繳']
    
    if not unpaid_df.empty:
        for idx, row in unpaid_df.iterrows():
            col_info, col_btn = st.columns([4, 1])
            
            with col_info:
                st.write(f"**{row['room_number']}** | ${row['amount_due']:,} 元")
            
            with col_btn:
                if st.button("✅", key=f"pay_{idx}"):
                    ok, msg = db.update_electricity_payment(
                        period_id,
                        row['room_number'],
                        '已繳',
                        row['amount_due'],
                        date.today()
                    )
                    if ok:
                        st.success("✅")
                        st.rerun()
                    else:
                        st.error(msg)
    else:
        st.success("✅ 全部已繳清")


# ============== 主函數 ==============

def render(db):
    """主渲染函數"""
    st.title("⚡ 電費管理")
    
    tab1, tab2, tab3 = st.tabs(["📅 計費期間", "🧮 計算電費", "📜 繳費記錄"])
    
    with tab1:
        render_period_tab(db)
    
    with tab2:
        render_calculation_tab(db)
    
    with tab3:
        render_records_tab(db)
