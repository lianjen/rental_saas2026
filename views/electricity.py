"""
電費管理 - v4.4 Complete (含通知功能)

✅ v3.1 功能：
  - 三種通知模式：不發送 | 手動發送 | 自動發送
  - 電費帳單通知功能
  - 催繳日期設定

✅ v4.0 重構：
  - 使用 Service 架構替代直接 DB 操作
  - 完整的錯誤處理
  - 更好的日誌記錄

✅ v4.1 修正：
  - 適配 Supabase 表結構（使用 electricity_readings）
  - 修正中英文欄位名稱混用問題

✅ v4.2 修正：
  - 計算後自動儲存完整計費資訊到資料庫
  - 確保「計算電費」與「繳費記錄」數據一致

✅ v4.3 補充：
  - 恢復完整的通知設定功能
  - 催繳日期設定
  - LINE 通知發送（手動/自動）

✅ v4.4 修正：
  - [UI] fallback data_table: use_container_width → width='stretch'（移除棄用警告）
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
import logging

# ✅ 使用 Service 架構
from services.electricity_service import ElectricityService
from services.notification_service import NotificationService
from services.tenant_service import TenantService

# 安全 import components
try:
    from components.cards import section_header, metric_card, empty_state, data_table, info_card
except ImportError:
    def section_header(title, icon="", divider=True):
        st.markdown(f"### {icon} {title}")
        if divider:
            st.divider()

    def metric_card(label, value, delta="", icon="", color="normal"):
        st.metric(label, value, delta)

    def empty_state(msg, icon="", desc=""):
        st.info(f"{icon} {msg}")
        if desc:
            st.caption(desc)

    def data_table(df, key="table"):
        # ✅ Streamlit 新版建議：use_container_width=True → width="stretch"
        st.dataframe(df, width="stretch", key=key)

    def info_card(title, content, icon="", type="info"):
        st.info(f"{icon} {title}: {content}")

# 安全 import constants
try:
    from config.constants import ROOMS
except ImportError:
    class ROOMS:
        ALL_ROOMS = ["1A", "1B", "2A", "2B", "3A", "3B", "3C", "3D", "4A", "4B", "4C", "4D"]
        SHARING_ROOMS = ["2A", "2B", "3A", "3B", "3C", "3D", "4A", "4B", "4C", "4D"]
        EXCLUSIVE_ROOMS = ["1A", "1B"]

logger = logging.getLogger(__name__)


# ============== 樓層配置 ==============
FLOOR_CONFIG = {
    '1F': {
        'label': '1F 台電單',
        'rooms': ['1A', '1B'],
        'is_independent': True
    },
    '2F': {
        'label': '2F 台電單',
        'rooms': ['2A', '2B'],
        'is_independent': False
    },
    '3F': {
        'label': '3F 台電單',
        'rooms': ['3A', '3B', '3C', '3D'],
        'is_independent': False
    },
    '4F': {
        'label': '4F 台電單',
        'rooms': ['4A', '4B', '4C', '4D'],
        'is_independent': False
    }
}


# ============== 計算邏輯 ==============
def calculate_electricity_charges(
    taipower_bills: List[Dict],
    room_readings: Dict[str, float]
) -> Dict:
    """
    計算電費 - v4.0

    Args:
        taipower_bills: [{'floor_label': '1F', 'amount': 1000, 'kwh': 100}, ...]
        room_readings: {'1A': 50.5, '2A': 30.2, ...}

    Returns:
        計費結果字典
    """
    try:
        # === Step 1: 分離 1F 和 2F~4F ===
        floor_1f = None
        floors_2f_4f = []

        for bill in taipower_bills:
            if bill['floor_label'] == '1F':
                floor_1f = bill
            else:
                floors_2f_4f.append(bill)

        # === Step 2: 計算 2F~4F 合併數據 ===
        if floors_2f_4f:
            merged_amount = sum(bill['amount'] for bill in floors_2f_4f)
            merged_kwh = sum(bill['kwh'] for bill in floors_2f_4f)
            merged_unit_price = round(merged_amount / merged_kwh, 2) if merged_kwh > 0 else 0
        else:
            merged_amount = 0
            merged_kwh = 0
            merged_unit_price = 0

        # === Step 3: 計算 2A~4D 私用電與公用電 ===
        sharing_rooms_usage = sum(
            room_readings.get(room, 0)
            for room in ROOMS.SHARING_ROOMS
        )

        public_kwh = max(0, merged_kwh - sharing_rooms_usage)

        # === Step 4: 計算分攤（10間）===
        sharing_rooms_with_reading = [
            room for room in ROOMS.SHARING_ROOMS
            if room_readings.get(room, 0) > 0
        ]

        sharing_count = len(sharing_rooms_with_reading)
        shared_per_room = int(round(public_kwh / sharing_count)) if sharing_count > 0 else 0

        # === Step 5: 處理結果 ===
        results = []

        # --- 處理 1F (1A/1B) 完全獨立 ---
        if floor_1f and floor_1f['kwh'] > 0:
            floor_1f_unit_price = round(floor_1f['amount'] / floor_1f['kwh'], 2)

            for room in ROOMS.EXCLUSIVE_ROOMS:
                kwh = room_readings.get(room, 0)
                if kwh <= 0:
                    continue

                charge = round(kwh * floor_1f_unit_price)

                results.append({
                    '樓層': '1F',
                    '房號': room,
                    '類型': '獨立房間',
                    '使用度數': round(kwh, 2),
                    '公用分攤': 0,
                    '總度數': round(kwh, 2),
                    '單價': floor_1f_unit_price,
                    '應繳金額': charge
                })

        # --- 處理 2F~4F (2A~4D) 分攤房間 ---
        for room in ROOMS.SHARING_ROOMS:
            kwh = room_readings.get(room, 0)
            if kwh <= 0:
                continue

            # 判斷樓層
            if room in ['2A', '2B']:
                floor = '2F'
            elif room in ['3A', '3B', '3C', '3D']:
                floor = '3F'
            elif room in ['4A', '4B', '4C', '4D']:
                floor = '4F'
            else:
                floor = None

            shared_kwh = shared_per_room
            total_room_kwh = kwh + shared_kwh
            charge = round(total_room_kwh * merged_unit_price)

            results.append({
                '樓層': floor,
                '房號': room,
                '類型': '分攤房間',
                '使用度數': round(kwh, 2),
                '公用分攤': int(shared_kwh),
                '總度數': round(total_room_kwh, 2),
                '單價': merged_unit_price,
                '應繳金額': charge
            })

        # === Step 6: 計算總計 ===
        total_charge = sum(r['應繳金額'] for r in results)
        total_taipower = sum(bill['amount'] for bill in taipower_bills)

        # === Step 7: 生成樓層摘要 ===
        floor_summaries = []

        # 1F 摘要
        if floor_1f:
            floor_1f_results = [r for r in results if r['房號'] in ['1A', '1B']]
            if floor_1f_results:
                floor_summaries.append({
                    'floor': '1F',
                    'bill_amount': floor_1f['amount'],
                    'bill_kwh': floor_1f['kwh'],
                    'room_kwh': sum(r['使用度數'] for r in floor_1f_results),
                    'unit_price': round(floor_1f['amount'] / floor_1f['kwh'], 2),
                    'total_charge': sum(r['應繳金額'] for r in floor_1f_results)
                })

        # 2F~4F 摘要
        for bill in floors_2f_4f:
            floor_label = bill['floor_label']
            floor_rooms = FLOOR_CONFIG[floor_label]['rooms']
            floor_results = [r for r in results if r['房號'] in floor_rooms]

            if floor_results:
                floor_room_kwh = sum(r['使用度數'] for r in floor_results)
                floor_total_charge = sum(r['應繳金額'] for r in floor_results)

                floor_summaries.append({
                    'floor': floor_label,
                    'bill_amount': bill['amount'],
                    'bill_kwh': bill['kwh'],
                    'room_kwh': floor_room_kwh,
                    'unit_price': merged_unit_price,
                    'total_charge': floor_total_charge
                })

        logger.info(f"✅ 電費計算完成: {len(results)} 間房間")

        return {
            'total_charge': total_charge,
            'taipower_amount': total_taipower,
            'difference': total_charge - total_taipower,
            'details': results,
            'floor_summaries': floor_summaries,
            'merged_unit_price': merged_unit_price,
            'total_public_kwh': public_kwh,
            'shared_per_room': shared_per_room,
            'merged_kwh': merged_kwh,
            'merged_amount': merged_amount
        }

    except Exception as e:
        logger.error(f"❌ 電費計算失敗: {e}")
        st.error(f"❌ 計算失敗: {str(e)}")
        return None


# ============== Tab 1: 計費期間 ==============
def render_period_tab(elec_service: ElectricityService):
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
                ok, msg, period_id = elec_service.add_period(year, month_start, month_end)
                if ok:
                    st.success(msg)
                    st.session_state.current_period_id = period_id
                    st.rerun()
                else:
                    st.error(msg)

    st.divider()

    # 顯示期間列表
    section_header("現有期間", "📋", divider=False)

    periods = elec_service.get_all_periods()
    if not periods:
        empty_state("尚未建立期間", "📅", "請先建立一個計費期間")
        return

    # 選擇期間
    period_options = {
        f"{p['period_year']}/{p['period_month_start']:02d}-{p['period_month_end']:02d} (ID: {p['id']})": p['id']
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

        # 顯示催繳日期設定
        period_info = elec_service.get_period_by_id(period_id)

        st.divider()
        section_header("催繳日期設定", "🔔", divider=False)

        current_remind_date = period_info.get('remind_start_date')

        if current_remind_date:
            st.info(f"✅ 目前催繳日期: {current_remind_date}")
        else:
            st.warning("⚠️ 尚未設定催繳日期")

        col_date, col_btn = st.columns([3, 1])

        with col_date:
            new_remind_date = st.date_input(
                "設定催繳開始日",
                value=datetime.strptime(current_remind_date, "%Y-%m-%d").date() if current_remind_date else date.today(),
                key="remind_date_input"
            )

        with col_btn:
            st.write("")
            st.write("")
            if st.button("💾 儲存日期", type="primary"):
                ok, msg = elec_service.update_period_remind_date(
                    period_id,
                    new_remind_date.strftime("%Y-%m-%d")
                )
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

        st.divider()

        col_del, col_info = st.columns([1, 3])

        with col_del:
            if st.button("🗑️ 刪除期間", type="secondary"):
                if st.session_state.get('confirm_delete_period'):
                    ok, msg = elec_service.delete_period(period_id)
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
def render_calculation_tab(elec_service: ElectricityService, notify_service: NotificationService):
    """計算電費"""
    if 'current_period_id' not in st.session_state:
        info_card("請先選擇期間", "請前往「計費期間」Tab 選擇一個期間", "⚠️", "warning")
        return

    period_id = st.session_state.current_period_id
    st.info(f"📅 當前期間 ID: {period_id}")

    # 檢查是否已有儲存記錄
    existing_records = elec_service.get_payment_record(period_id)
    if existing_records is not None and not existing_records.empty:
        st.success(f"✅ 此期間已有 {len(existing_records)} 筆儲存記錄，可前往「📜 繳費記錄」Tab 查看")

    st.divider()

    # === 步驟 1: 台電帳單 ===
    section_header("步驟 1: 輸入台電帳單", "📄")
    st.caption("💡 提示：1F 獨立計算 | 2F~4F 合併計算公用電並分攤給 2A~4D")

    # 使用 2x2 排列
    row1_col1, row1_col2 = st.columns(2)
    row2_col1, row2_col2 = st.columns(2)

    cols_map = {
        '1F': row1_col1,
        '2F': row1_col2,
        '3F': row2_col1,
        '4F': row2_col2
    }

    floor_data = {}

    for floor_key, config in FLOOR_CONFIG.items():
        with cols_map[floor_key]:
            st.markdown(f"**{config['label']}**")

            if config['is_independent']:
                st.caption(f"🔒 獨立：{', '.join(config['rooms'])}")
            else:
                st.caption(f"🔗 分攤：{', '.join(config['rooms'])}")

            amount = st.number_input(
                "金額 (元)",
                min_value=0,
                value=0,
                step=100,
                key=f"{floor_key}_amt",
                label_visibility="visible"
            )

            kwh = st.number_input(
                "度數",
                min_value=0.0,
                value=0.0,
                step=10.0,
                format="%.2f",
                key=f"{floor_key}_kwh",
                label_visibility="visible"
            )

            floor_data[floor_key] = {
                'amount': amount,
                'kwh': kwh
            }

    # 儲存台電單
    if 'taipower_bills' not in st.session_state:
        st.session_state.taipower_bills = {}

    if st.button("💾 儲存台電單", type="primary"):
        bills = [
            {
                'floor_label': floor_key,
                'amount': data['amount'],
                'kwh': data['kwh']
            }
            for floor_key, data in floor_data.items()
            if data['amount'] > 0 or data['kwh'] > 0
        ]

        if not bills:
            st.error("❌ 請至少輸入一個樓層的台電單")
        else:
            st.session_state.taipower_bills[period_id] = bills
            st.success(f"✅ 已儲存 {len(bills)} 個台電單")
            logger.info(f"Saved {len(bills)} taipower bills for period {period_id}")

    # 顯示已儲存的摘要
    if period_id in st.session_state.get('taipower_bills', {}):
        bills = st.session_state.taipower_bills[period_id]

        # 分離顯示
        floor_1f_bill = next((b for b in bills if b['floor_label'] == '1F'), None)
        floors_2f_4f_bills = [b for b in bills if b['floor_label'] != '1F']

        st.divider()
        st.write("**已儲存摘要:**")

        # 1F 獨立顯示
        if floor_1f_bill:
            col_1f = st.columns(1)[0]
            with col_1f:
                st.metric(
                    label="1F (獨立)",
                    value=f"${floor_1f_bill['amount']:,}",
                    delta=f"{floor_1f_bill['kwh']:.0f} 度"
                )

        # 2F~4F 合併顯示
        if floors_2f_4f_bills:
            merged_amt = sum(b['amount'] for b in floors_2f_4f_bills)
            merged_kwh = sum(b['kwh'] for b in floors_2f_4f_bills)

            summary_cols = st.columns(len(floors_2f_4f_bills) + 1)

            for idx, bill in enumerate(floors_2f_4f_bills):
                with summary_cols[idx]:
                    st.metric(
                        label=f"{bill['floor_label']}",
                        value=f"${bill['amount']:,}",
                        delta=f"{bill['kwh']:.0f} 度"
                    )

            with summary_cols[-1]:
                st.metric(
                    label="**2-4F 合計**",
                    value=f"${merged_amt:,}",
                    delta=f"{merged_kwh:.0f} 度"
                )

    st.divider()

    # === 步驟 2: 房間讀數 ===
    section_header("步驟 2: 輸入房間讀數", "🔢")
    st.caption("💡 提示：首次輸入時上期可編輯，之後自動帶入上次讀數並鎖定。")

    room_readings = {}
    raw_readings = {}

    # 按樓層分組顯示
    for floor_key, config in FLOOR_CONFIG.items():
        st.markdown(f"### {config['label']}")

        floor_rooms = config['rooms']
        cols = st.columns(len(floor_rooms))

        for col, room in zip(cols, floor_rooms):
            with col:
                st.markdown(f"**{room}**")

                # 取得上次讀數
                last_reading = elec_service.get_latest_meter_reading(room, period_id)
                is_first_time = (last_reading is None or last_reading == 0)

                if is_first_time:
                    previous = st.number_input(
                        "上期 📊",
                        min_value=0.0,
                        value=0.0,
                        step=1.0,
                        key=f"prev_{room}",
                        help="首次輸入，請輸入起始讀數",
                        disabled=False
                    )
                else:
                    previous_value = float(last_reading)
                    st.number_input(
                        "上期 📊",
                        min_value=0.0,
                        value=previous_value,
                        step=1.0,
                        key=f"prev_{room}",
                        help="自動帶入上次讀數（不可修改）",
                        disabled=True
                    )
                    previous = previous_value

                current = st.number_input(
                    "本期 📈",
                    min_value=previous,
                    value=previous,
                    step=1.0,
                    key=f"curr_{room}",
                    help="本次抄表的讀數"
                )

                usage = current - previous

                if usage > 0:
                    st.success(f"⚡ 用電 {usage:.1f} 度")
                elif usage == 0 and current > 0:
                    st.info("📊 讀數無變化")
                else:
                    st.caption("⚪ 等待輸入")

                room_readings[room] = usage
                raw_readings[room] = {
                    'previous': previous,
                    'current': current
                }

        st.divider()

    # 儲存讀數（僅基本資訊）
    if st.button("💾 儲存讀數", type="primary"):
        if 'room_readings' not in st.session_state:
            st.session_state.room_readings = {}
        if 'raw_readings' not in st.session_state:
            st.session_state.raw_readings = {}

        st.session_state.room_readings[period_id] = room_readings
        st.session_state.raw_readings[period_id] = raw_readings

        st.success(f"✅ 已儲存讀數到記憶體（請繼續計算）")
        logger.info(f"Saved readings to session for period {period_id}")

    st.divider()

    # === 步驟 3: 計算 ===
    section_header("步驟 3: 計算電費", "🧮")

    # 計算按鈕
    if st.button("🚀 開始計算", type="primary"):
        bills = st.session_state.get('taipower_bills', {}).get(period_id)
        readings = st.session_state.get('room_readings', {}).get(period_id)
        raw = st.session_state.get('raw_readings', {}).get(period_id)

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

        # ✅ v4.2 關鍵修正：計算完成後立即儲存到資料庫
        enriched_details = []
        save_count = 0

        with st.spinner("💾 正在儲存計費資訊到資料庫..."):
            for detail in result['details']:
                room = detail['房號']
                detail['previous_reading'] = raw[room]['previous']
                detail['current_reading'] = raw[room]['current']
                enriched_details.append(detail)

                # 立即儲存完整計費資訊
                ok, msg = elec_service.save_reading(
                    period_id=period_id,
                    room=room,
                    previous=raw[room]['previous'],
                    current=raw[room]['current'],
                    kwh_used=detail['使用度數'],
                    unit_price=detail['單價'],
                    public_share_kwh=detail['公用分攤'],
                    amount_due=detail['應繳金額'],
                    room_type=detail['類型']
                )

                if ok:
                    save_count += 1

        # 儲存到 session_state（用於顯示）
        st.session_state[f'calc_result_{period_id}'] = result
        st.session_state[f'calc_details_{period_id}'] = enriched_details

        logger.info(f"Calculated and saved {save_count} records for period {period_id}")
        st.success(f"✅ 計算完成！已自動儲存 {save_count} 筆計費記錄到資料庫")
        st.rerun()

    # 顯示計算結果（從 session_state 讀取）
    result = st.session_state.get(f'calc_result_{period_id}')
    enriched_details = st.session_state.get(f'calc_details_{period_id}')

    if result and enriched_details:
        # 顯示關鍵資訊
        st.markdown("### 📊 計算摘要")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("2-4F 合計", f"{result['merged_kwh']:.0f} 度")
        with col2:
            st.metric("總公用電", f"{result['total_public_kwh']:.0f} 度")
        with col3:
            st.metric("每間分攤", f"{result['shared_per_room']} 度")
        with col4:
            st.metric("2-4F 單價", f"${result['merged_unit_price']:.2f}/度")

        st.divider()

        # 顯示樓層摘要
        st.markdown("### 📊 各樓層摘要")
        for floor_summary in result['floor_summaries']:
            with st.expander(
                f"**{floor_summary['floor']}** - 台電: ${floor_summary['bill_amount']:,} | 收費: ${floor_summary['total_charge']:,}",
                expanded=True
            ):
                col1, col2 = st.columns(2)

                with col1:
                    st.metric("台電度數", f"{floor_summary['bill_kwh']:.0f} 度")

                with col2:
                    st.metric("房間用電", f"{floor_summary['room_kwh']:.0f} 度")

        st.divider()

        # 顯示總計
        st.markdown(f"""
### 💰 總計
- **台電總金額**: ${result['taipower_amount']:,} 元
- **收費總金額**: ${result['total_charge']:,} 元
- **差異**: ${result['difference']:+,.0f} 元
        """)

        st.divider()

        # 顯示明細
        st.write("**各房間明細**")
        details_df = pd.DataFrame(enriched_details)

        column_order = ['樓層', '房號', '類型', 'previous_reading', 'current_reading',
                       '使用度數', '公用分攤', '總度數', '單價', '應繳金額']
        details_df = details_df[column_order]

        # 格式化
        details_df['公用分攤'] = details_df['公用分攤'].astype(int)

        details_df.columns = ['樓層', '房號', '類型', '上期讀數', '本期讀數',
                             '使用度數', '公用分攤', '總度數', '單價', '應繳金額']

        data_table(details_df, key="calc_details")

        st.divider()

        # ✅ v4.3 新增：通知設定區
        section_header("通知設定", "🔔", divider=False)

        st.markdown("### 📱 LINE 電費通知")

        notify_mode = st.radio(
            "通知模式",
            options=["不發送", "手動發送", "自動發送"],
            horizontal=True,
            key="notify_mode"
        )

        if notify_mode == "不發送":
            st.info("⚪ 不會發送任何通知")

        elif notify_mode == "手動發送":
            st.warning("⚠️ 需要手動點擊「發送通知」按鈕")

            if st.button("📤 立即發送電費通知", type="primary"):
                with st.spinner("正在發送通知..."):
                    tenant_service = TenantService()
                    success_count = 0
                    fail_count = 0

                    for detail in enriched_details:
                        room = detail['房號']
                        amount = detail['應繳金額']
                        kwh = detail['總度數']

                        # 發送通知
                        ok, msg = notify_service.send_electricity_bill_notification(
                            room_number=room,
                            period_id=period_id,
                            amount=amount,
                            kwh=kwh
                        )

                        if ok:
                            success_count += 1
                        else:
                            fail_count += 1
                            logger.error(f"發送失敗: {room} - {msg}")

                    if success_count > 0:
                        st.success(f"✅ 成功發送 {success_count} 則通知")

                    if fail_count > 0:
                        st.error(f"❌ 失敗 {fail_count} 則（可能是租客未綁定 LINE）")

        elif notify_mode == "自動發送":
            period_info = elec_service.get_period_by_id(period_id)
            remind_date = period_info.get('remind_start_date')

            if not remind_date:
                st.error("❌ 請先在「計費期間」Tab 設定催繳日期")
            else:
                remind_datetime = datetime.strptime(remind_date, "%Y-%m-%d")
                today = datetime.now()

                if today >= remind_datetime:
                    st.success(f"✅ 催繳日期已到（{remind_date}），系統將自動發送通知")
                else:
                    days_left = (remind_datetime - today).days
                    st.info(f"⏳ 催繳日期: {remind_date}（還有 {days_left} 天）")

        st.divider()

        # 下載按鈕
        csv = details_df.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            "📥 下載 CSV 備份",
            csv,
            f"electricity_{period_id}.csv",
            "text/csv"
        )

        st.info("💡 計費記錄已自動儲存，可前往「📜 繳費記錄」Tab 查看")


# ============== Tab 3: 繳費記錄 ==============
def render_records_tab(elec_service: ElectricityService):
    """繳費記錄"""
    section_header("繳費記錄", "📜")

    if 'current_period_id' not in st.session_state:
        info_card("請先選擇期間", "請前往「計費期間」Tab 選擇一個期間", "⚠️", "warning")
        return

    period_id = st.session_state.current_period_id

    # 顯示當前期間資訊
    st.info(f"📅 當前查詢期間 ID: {period_id}")

    # 查詢記錄
    with st.spinner("正在從資料庫查詢記錄..."):
        df = elec_service.get_payment_record(period_id)
        logger.info(f"Query result for period {period_id}: {len(df) if df is not None else 0} records")

    if df is None or df.empty:
        empty_state(
            "尚無記錄",
            "📭",
            f"請先在「計算電費」Tab 完成計算（會自動儲存）"
        )
        return

    # 顯示記錄數量
    st.success(f"✅ 已找到 {len(df)} 筆電費記錄")

    # 顯示統計摘要
    summary = elec_service.get_payment_summary(period_id)
    if summary:
        col1, col2, col3 = st.columns(3)

        with col1:
            metric_card("應收總額", f"${summary.get('total_due', 0):,}", "", "💰", "normal")

        with col2:
            metric_card("已收金額", f"${summary.get('total_paid', 0):,}", "", "✅", "success")

        with col3:
            metric_card("未收金額", f"${summary.get('total_balance', 0):,}", "", "⚠️", "warning")

    st.divider()

    st.write(f"**共 {len(df)} 筆記錄**")
    data_table(df, key="payment_records")

    st.divider()

    # 下載按鈕
    csv = df.to_csv(index=False, encoding='utf-8-sig')
    st.download_button(
        "📥 下載繳費記錄 CSV",
        csv,
        f"payment_records_{period_id}.csv",
        "text/csv",
        help="下載此期間的完整繳費記錄"
    )


# ============== 主函數 ==============
def render():
    """主渲染函數"""
    st.title("⚡ 電費管理")

    # ✅ 初始化 Services
    elec_service = ElectricityService()
    notify_service = NotificationService()

    tab1, tab2, tab3 = st.tabs(["📅 計費期間", "🧮 計算電費", "📜 繳費記錄"])

    with tab1:
        render_period_tab(elec_service)

    with tab2:
        render_calculation_tab(elec_service, notify_service)

    with tab3:
        render_records_tab(elec_service)


# ✅ 主入口
def show():
    """Streamlit 頁面入口"""
    render()


if __name__ == "__main__":
    show()
