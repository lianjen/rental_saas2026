"""
電費管理 - 完整重構版
特性:
- 狀態機管理流程
- 完整錯誤處理
- 資料驗證
- 匯出功能
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime
from typing import Dict, Optional
import sys
sys.path.append('..')

from components.cards import (
    section_header, metric_card, empty_state, 
    data_table, info_card, loading_spinner
)
from config.constants import ROOMS

# 動態匯入子模組
try:
    from .electricity.calculator import ElectricityCalculator, format_charge_summary, export_charge_details
    from .electricity.storage import ElectricityStorage, create_electricity_tables
except ImportError:
    # 如果子模組不存在,使用簡化版
    st.warning("⚠️ 電費子模組未安裝,部分功能可能受限")
    ElectricityCalculator = None
    ElectricityStorage = None


# ============== 初始化 ==============

def initialize_electricity_module(db):
    """初始化電費模組"""
    if 'electricity_initialized' not in st.session_state:
        try:
            # 建立資料表 (僅首次)
            if ElectricityStorage:
                create_electricity_tables(db)
            st.session_state.electricity_initialized = True
        except Exception as e:
            st.error(f"❌ 初始化失敗: {e}")


def get_calculator():
    """取得計算器實例"""
    if 'calculator' not in st.session_state:
        st.session_state.calculator = ElectricityCalculator(
            sharing_rooms=ROOMS.SHARING_ROOMS,
            exclusive_rooms=ROOMS.EXCLUSIVE_ROOMS
        )
    return st.session_state.calculator


def get_storage(db):
    """取得資料存取實例"""
    if 'storage' not in st.session_state:
        st.session_state.storage = ElectricityStorage(db)
    return st.session_state.storage


# ============== Tab 1: 計費期間管理 ==============

def render_period_tab(db):
    """計費期間 Tab"""
    section_header("建立計費期間", "📅")
    
    storage = get_storage(db)
    
    # 建立新期間
    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    
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
            "開始月份",
            list(range(1, 13)),
            key="period_month_start"
        )
    
    with col3:
        month_end = st.selectbox(
            "結束月份",
            list(range(1, 13)),
            index=1,
            key="period_month_end"
        )
    
    with col4:
        st.write("")
        st.write("")
        if st.button("➕ 建立期間", type="primary"):
            if month_end <= month_start:
                st.error("❌ 結束月份必須大於開始月份")
            else:
                ok, period_id, msg = storage.create_period(year, month_start, month_end)
                if ok:
                    st.success(msg)
                    st.session_state.current_period_id = period_id
                    st.rerun()
                else:
                    st.warning(msg)
    
    st.divider()
    
    # 顯示期間列表
    section_header("歷史期間", "📋", divider=False)
    
    df_periods = storage.get_periods(limit=20)
    
    if df_periods.empty:
        empty_state(
            "尚未建立計費期間",
            "📅",
            "請先建立一個計費期間"
        )
    else:
        # 格式化顯示
        display_df = df_periods.copy()
        display_df['period'] = display_df.apply(
            lambda x: f"{x['period_year']}/{x['period_month_start']}-{x['period_month_end']}",
            axis=1
        )
        display_df['created_at'] = pd.to_datetime(display_df['created_at']).dt.strftime('%Y-%m-%d')
        
        # 選擇當前期間
        selected_period = st.selectbox(
            "選擇計費期間",
            display_df['period'].tolist(),
            key="selected_period_display"
        )
        
        # 儲存選中的期間 ID
        selected_idx = display_df[display_df['period'] == selected_period].index[0]
        st.session_state.current_period_id = int(display_df.loc[selected_idx, 'id'])
        
        st.info(f"✅ 當前期間: {selected_period} (ID: {st.session_state.current_period_id})")


# ============== Tab 2: 計算電費 ==============

def render_calculation_tab(db):
    """計算 Tab"""
    
    # 檢查是否已選擇期間
    if 'current_period_id' not in st.session_state:
        info_card(
            "請先建立計費期間",
            "請前往「計費期間」Tab 建立或選擇一個期間",
            "⚠️",
            "warning"
        )
        return
    
    storage = get_storage(db)
    calculator = get_calculator()
    period_id = st.session_state.current_period_id
    
    # 取得期間資訊
    period_info = storage.get_period_by_id(period_id)
    if not period_info:
        st.error("❌ 期間不存在")
        return
    
    st.info(f"📅 計費期間: {period_info['year']}/{period_info['month_start']}-{period_info['month_end']}")
    
    st.divider()
    
    # ====== 步驟 1: 輸入台電單據 ======
    section_header("步驟 1: 輸入台電單據", "📄")
    
    col1, col2 = st.columns(2)
    
    # 1F 台電單
    with col1:
        st.markdown("**1F 台電單**")
        floor1_amount = st.number_input(
            "金額 (元)",
            min_value=0,
            value=0,
            step=100,
            key="floor1_amount"
        )
        floor1_kwh = st.number_input(
            "度數",
            min_value=0.0,
            value=0.0,
            step=10.0,
            key="floor1_kwh"
        )
        
        if st.button("💾 儲存 1F", key="save_floor1"):
            ok, msg = storage.save_taipower_bill(period_id, "1F", floor1_amount, floor1_kwh)
            if ok:
                st.success(msg)
            else:
                st.error(msg)
    
    # 2-4F 台電單
    with col2:
        st.markdown("**2-4F 台電單**")
        floor2_amount = st.number_input(
            "金額 (元)",
            min_value=0,
            value=0,
            step=100,
            key="floor2_amount"
        )
        floor2_kwh = st.number_input(
            "度數",
            min_value=0.0,
            value=0.0,
            step=10.0,
            key="floor2_kwh"
        )
        
        if st.button("💾 儲存 2-4F", key="save_floor2"):
            ok, msg = storage.save_taipower_bill(period_id, "2-4F", floor2_amount, floor2_kwh)
            if ok:
                st.success(msg)
            else:
                st.error(msg)
    
    # 顯示已儲存的台電單
    df_bills = storage.get_taipower_bills(period_id)
    if not df_bills.empty:
        st.write("**已儲存的台電單:**")
        st.dataframe(df_bills, use_container_width=True)
        
        # 計算總計
        total_amount = df_bills['amount'].sum()
        total_kwh = df_bills['kwh'].sum()
        
        col_a, col_b = st.columns(2)
        with col_a:
            metric_card("台電總金額", f"${total_amount:,}", icon="💰", color="normal")
        with col_b:
            metric_card("台電總度數", f"{total_kwh:.0f} 度", icon="⚡", color="normal")
    
    st.divider()
    
    # ====== 步驟 2: 輸入房間讀數 ======
    section_header("步驟 2: 輸入房間電錶讀數", "🔢")
    
    # 取得上期讀數 (用於驗證)
    previous_readings = storage.get_previous_readings(period_id)
    
    # 批量輸入
    reading_date = st.date_input(
        "抄表日期",
        value=date.today(),
        key="reading_date"
    )
    
    # 分 4 列顯示
    room_readings = {}
    rows = [ROOMS.ALL_ROOMS[i:i+3] for i in range(0, len(ROOMS.ALL_ROOMS), 3)]
    
    for row_rooms in rows:
        cols = st.columns(3)
        for col, room in zip(cols, row_rooms):
            with col:
                # 顯示上期讀數
                prev_reading = previous_readings.get(room, 0)
                if prev_reading > 0:
                    st.caption(f"上期: {prev_reading:.0f} 度")
                
                reading = st.number_input(
                    f"**{room}** 讀數",
                    min_value=0.0,
                    value=prev_reading,
                    step=10.0,
                    key=f"reading_{room}"
                )
                room_readings[room] = reading
    
    # 批量儲存
    col_save, col_clear = st.columns([3, 1])
    
    with col_save:
        if st.button("💾 批量儲存讀數", type="primary"):
            with st.spinner("儲存中..."):
                success_count = 0
                for room, reading in room_readings.items():
                    ok, msg = storage.save_meter_reading(
                        period_id, room, reading, reading_date
                    )
                    if ok:
                        success_count += 1
                
                if success_count == len(room_readings):
                    st.success(f"✅ 已儲存 {success_count} 個房間的讀數")
                else:
                    st.warning(f"⚠️ 僅儲存 {success_count}/{len(room_readings)} 個房間")
    
    with col_clear:
        if st.button("🗑️ 清除輸入"):
            for room in ROOMS.ALL_ROOMS:
                st.session_state[f"reading_{room}"] = 0.0
            st.rerun()
    
    st.divider()
    
    # ====== 步驟 3: 計算電費 ======
    section_header("步驟 3: 計算電費", "🧮")
    
    if st.button("🚀 開始計算", type="primary"):
        # 取得資料
        df_bills = storage.get_taipower_bills(period_id)
        meter_readings = storage.get_meter_readings(period_id)
        
        # 驗證資料完整性
        if df_bills.empty:
            st.error("❌ 請先輸入台電單據")
            return
        
        if not meter_readings:
            st.error("❌ 請先輸入房間讀數")
            return
        
        if len(meter_readings) < len(ROOMS.ALL_ROOMS):
            st.warning(f"⚠️ 部分房間未輸入讀數 ({len(meter_readings)}/{len(ROOMS.ALL_ROOMS)})")
        
        # 驗證讀數
        valid, errors = calculator.validate_readings(meter_readings, previous_readings)
        if not valid:
            st.error("❌ 讀數驗證失敗:")
            for error in errors:
                st.write(f"- {error}")
            return
        
        # 執行計算
        try:
            total_amount = df_bills['amount'].sum()
            total_kwh = df_bills['kwh'].sum()
            
            result = calculator.calculate_all_rooms(
                total_amount,
                total_kwh,
                meter_readings
            )
            
            # 顯示摘要
            st.markdown(format_charge_summary(result))
            
            # 顯示明細
            st.divider()
            section_header("計費明細", "📊", divider=False)
            
            details_df = pd.DataFrame(export_charge_details(result))
            data_table(details_df, key="charge_details")
            
            # 儲存結果
            st.divider()
            if st.button("💾 儲存計費結果"):
                ok, msg = storage.save_charge_results(period_id, result)
                if ok:
                    st.success(msg)
                    st.balloons()
                else:
                    st.error(msg)
            
            # 匯出功能
            col_export1, col_export2 = st.columns(2)
            
            with col_export1:
                csv = details_df.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    "📥 下載 CSV",
                    csv,
                    f"electricity_{period_info['year']}_{period_info['month_start']}.csv",
                    "text/csv"
                )
            
            with col_export2:
                # Excel 匯出 (需要 openpyxl)
                try:
                    import io
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        details_df.to_excel(writer, index=False, sheet_name='電費明細')
                    
                    st.download_button(
                        "📥 下載 Excel",
                        buffer.getvalue(),
                        f"electricity_{period_info['year']}_{period_info['month_start']}.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                except ImportError:
                    st.info("ℹ️ Excel 匯出需安裝 openpyxl")
        
        except Exception as e:
            st.error(f"❌ 計算失敗: {str(e)}")


# ============== Tab 3: 歷史記錄 ==============

def render_records_tab(db):
    """記錄 Tab"""
    section_header("歷史計費記錄", "📜")
    
    storage = get_storage(db)
    df_history = storage.get_charge_history(limit=20)
    
    if df_history.empty:
        empty_state(
            "尚無歷史記錄",
            "📜",
            "完成計費後會顯示在這裡"
        )
    else:
        # 格式化顯示
        display_df = df_history.copy()
        display_df['期間'] = display_df.apply(
            lambda x: f"{x['period_year']}/{x['period_month_start']}-{x['period_month_end']}",
            axis=1
        )
        display_df['單位電價'] = display_df['unit_price'].apply(lambda x: f"${x:.2f}")
        display_df['公用電'] = display_df['public_kwh'].apply(lambda x: f"{x:.2f} 度")
        display_df['總收費'] = display_df['total_charge'].apply(lambda x: f"${x:,}")
        display_df['台電金額'] = display_df['taipower_amount'].apply(lambda x: f"${x:,}")
        display_df['差異'] = display_df['difference'].apply(lambda x: f"${x:+,}")
        display_df['建立日期'] = pd.to_datetime(display_df['created_at']).dt.strftime('%Y-%m-%d')
        
        show_cols = ['期間', '單位電價', '公用電', '總收費', '台電金額', '差異', '建立日期']
        data_table(display_df[show_cols], key="history_records")


# ============== 主渲染函數 ==============

def render(db):
    """主渲染函數"""
    st.title("⚡ 電費管理")
    
    # 初始化
    initialize_electricity_module(db)
    
    # 檢查子模組
    if not ElectricityCalculator or not ElectricityStorage:
        st.error("❌ 電費子模組未安裝,請聯繫管理員")
        return
    
    # Tabs
    tab1, tab2, tab3 = st.tabs(["📅 計費期間", "🧮 計算電費", "📜 歷史記錄"])
    
    with tab1:
        render_period_tab(db)
    
    with tab2:
        render_calculation_tab(db)
    
    with tab3:
        render_records_tab(db)
