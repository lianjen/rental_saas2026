"""
電費管理 - v4.8
✅ v4.7 所有功能保留
✅ [NEW v4.8] 新增「📊 用電統計」 Tab
      - 雙軸指標圖：黄色長條 = 總度數，綠色折線 = 總金額（仿台電 App）
      - 年度筛選：可切換年層查看
      - 4 大指標：累計期數、總度數、總金額、平均每期
      - 房間用電趨勢表（可展開）
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
import logging

try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

from services.electricity_service import ElectricityService
from services.notification_service import NotificationService
from services.tenant_service import TenantService

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
        st.dataframe(df, use_container_width=True, key=key)

    def info_card(title, content, icon="", type="info"):
        st.info(f"{icon} {title}: {content}")

try:
    from config.constants import ROOMS
except ImportError:
    class ROOMS:
        ALL_ROOMS       = ["1A", "1B", "2A", "2B", "3A", "3B", "3C", "3D", "4A", "4B", "4C", "4D"]
        SHARING_ROOMS   = ["2A", "2B", "3A", "3B", "3C", "3D", "4A", "4B", "4C", "4D"]
        EXCLUSIVE_ROOMS = ["1A", "1B"]

logger = logging.getLogger(__name__)

_1F_ROOMS = ["1A", "1B"]


# ============================================================
# 樓層配置
# ============================================================
FLOOR_CONFIG = {
    "1F": {"label": "1F 台電單", "rooms": ["1A", "1B"],               "is_independent": True},
    "2F": {"label": "2F 台電單", "rooms": ["2A", "2B"],               "is_independent": False},
    "3F": {"label": "3F 台電單", "rooms": ["3A", "3B", "3C", "3D"],   "is_independent": False},
    "4F": {"label": "4F 台電單", "rooms": ["4A", "4B", "4C", "4D"],   "is_independent": False},
}


# ============================================================
# 計算邏輯
# ============================================================
def calculate_electricity_charges(
    taipower_bills: List[Dict],
    room_readings: Dict[str, float],
) -> Optional[Dict]:
    """v4.8 電費計算核心（邏輯不變）"""
    try:
        floor_1f      = next((b for b in taipower_bills if b["floor_label"] == "1F"), None)
        floors_2f_4f  = [b for b in taipower_bills if b["floor_label"] != "1F"]

        if floors_2f_4f:
            merged_amount     = sum(b["amount"] for b in floors_2f_4f)
            merged_kwh        = sum(b["kwh"]    for b in floors_2f_4f)
            merged_unit_price = round(merged_amount / merged_kwh, 2) if merged_kwh > 0 else 0
        else:
            merged_amount = merged_kwh = merged_unit_price = 0

        sharing_rooms_usage = sum(room_readings.get(r, 0) for r in ROOMS.SHARING_ROOMS)
        public_kwh          = max(0, merged_kwh - sharing_rooms_usage)
        sharing_rooms_with_reading = [r for r in ROOMS.SHARING_ROOMS if room_readings.get(r, 0) > 0]
        sharing_count   = len(sharing_rooms_with_reading)
        shared_per_room = int(round(public_kwh / sharing_count)) if sharing_count > 0 else 0

        results = []
        if floor_1f and floor_1f["kwh"] > 0:
            unit_1f = round(floor_1f["amount"] / floor_1f["kwh"], 2)
            for room in ROOMS.EXCLUSIVE_ROOMS:
                kwh = room_readings.get(room, 0)
                if kwh <= 0:
                    continue
                results.append({
                    "樓層": "1F", "房號": room, "類型": "獨立房間",
                    "使用度數": round(kwh, 2), "公用分攤": 0,
                    "總度數": round(kwh, 2), "單價": unit_1f,
                    "應繳金額": round(kwh * unit_1f),
                })

        floor_map = {r: "2F" for r in ["2A", "2B"]}
        floor_map.update({r: "3F" for r in ["3A", "3B", "3C", "3D"]})
        floor_map.update({r: "4F" for r in ["4A", "4B", "4C", "4D"]})
        for room in ROOMS.SHARING_ROOMS:
            kwh = room_readings.get(room, 0)
            if kwh <= 0:
                continue
            total_room_kwh = kwh + shared_per_room
            results.append({
                "樓層": floor_map.get(room), "房號": room, "類型": "分攤房間",
                "使用度數": round(kwh, 2), "公用分攤": int(shared_per_room),
                "總度數": round(total_room_kwh, 2), "單價": merged_unit_price,
                "應繳金額": round(total_room_kwh * merged_unit_price),
            })

        total_charge   = sum(r["應繳金額"] for r in results)
        total_taipower = sum(b["amount"]  for b in taipower_bills)

        floor_summaries = []
        if floor_1f:
            f1_results = [r for r in results if r["房號"] in ["1A", "1B"]]
            if f1_results:
                floor_summaries.append({
                    "floor": "1F", "bill_amount": floor_1f["amount"],
                    "bill_kwh": floor_1f["kwh"],
                    "room_kwh": sum(r["使用度數"] for r in f1_results),
                    "unit_price": round(floor_1f["amount"] / floor_1f["kwh"], 2),
                    "total_charge": sum(r["應繳金額"] for r in f1_results),
                })
        for bill in floors_2f_4f:
            fl   = bill["floor_label"]
            fl_r = [r for r in results if r["房號"] in FLOOR_CONFIG[fl]["rooms"]]
            if fl_r:
                floor_summaries.append({
                    "floor": fl, "bill_amount": bill["amount"], "bill_kwh": bill["kwh"],
                    "room_kwh": sum(r["使用度數"] for r in fl_r),
                    "unit_price": merged_unit_price,
                    "total_charge": sum(r["應繳金額"] for r in fl_r),
                })

        logger.info(f"✅ 電費計算完成: {len(results)} 間房間")
        return {
            "total_charge":      total_charge,
            "taipower_amount":   total_taipower,
            "difference":        total_charge - total_taipower,
            "details":           results,
            "floor_summaries":   floor_summaries,
            "merged_unit_price": merged_unit_price,
            "total_public_kwh":  public_kwh,
            "shared_per_room":   shared_per_room,
            "merged_kwh":        merged_kwh,
            "merged_amount":     merged_amount,
        }
    except Exception as e:
        logger.error(f"❌ 電費計算失敗: {e}")
        st.error(f"❌ 計算失敗: {str(e)}")
        return None


# ============================================================
# Tab 1: 計費期間
# ============================================================
def render_period_tab(elec_service: ElectricityService):
    section_header("計費期間管理", "📅")

    col1, col2, col3 = st.columns(3)
    with col1:
        year = st.number_input("年份", min_value=2020, max_value=2030,
                               value=date.today().year, key="period_year")
    with col2:
        month_start = st.selectbox("開始月", range(1, 13),
                                    index=date.today().month - 1, key="period_start")
    with col3:
        month_end = st.selectbox("結束月", range(1, 13),
                                  index=date.today().month % 12, key="period_end")

    col_date, col_btn = st.columns([3, 1])
    with col_date:
        remind_on_create = st.date_input("催繳開始日（可留空，稍後再設）",
                                          value=None, key="remind_on_create")
    with col_btn:
        st.write("")
        st.write("")
        if st.button("➕ 建立", type="primary"):
            if month_end <= month_start:
                st.error("❌ 結束月必須大於開始月")
            else:
                remind_str = remind_on_create.strftime("%Y-%m-%d") if remind_on_create else None
                ok, msg, period_id = elec_service.add_period(year, month_start, month_end, remind_str)
                if ok:
                    st.success(msg)
                    st.session_state.current_period_id = period_id
                    st.rerun()
                else:
                    st.error(msg)

    st.divider()
    section_header("現有期間", "📋", divider=False)
    periods = elec_service.get_all_periods()
    if not periods:
        empty_state("尚未建立期間", "📅", "請先建立一個計費期間")
        return

    period_options = {
        f"{p['period_year']}/{p['period_month_start']:02d}-{p['period_month_end']:02d} (ID: {p['id']})": p["id"]
        for p in periods
    }
    selected = st.selectbox("選擇計費期間", list(period_options.keys()), key="selected_period")
    if not selected:
        return

    period_id = period_options[selected]
    st.session_state.current_period_id = period_id
    period_info = elec_service.get_period_by_id(period_id)

    st.divider()
    section_header("催繳日期設定", "🔔", divider=False)
    current_remind_date = period_info.get("remind_start_date")
    if current_remind_date:
        st.info(f"✅ 目前催繳日期: {current_remind_date}")
    else:
        st.warning("⚠️ 尚未設定催繳日期")

    col_d, col_b = st.columns([3, 1])
    with col_d:
        new_remind_date = st.date_input(
            "設定催繳開始日",
            value=(datetime.strptime(current_remind_date, "%Y-%m-%d").date()
                   if current_remind_date else date.today()),
            key="remind_date_input",
        )
    with col_b:
        st.write("")
        st.write("")
        if st.button("💾 儲存日期", type="primary"):
            ok, msg = elec_service.update_period_remind_date(
                period_id, new_remind_date.strftime("%Y-%m-%d"))
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    st.divider()
    col_del, col_info = st.columns([1, 3])
    with col_del:
        if st.button("🗑️ 刪除期間", type="secondary"):
            if st.session_state.get("confirm_delete_period"):
                ok, msg = elec_service.delete_period(period_id)
                if ok:
                    st.success(msg)
                    st.session_state.pop("current_period_id", None)
                    st.session_state.pop("confirm_delete_period", None)
                    st.rerun()
                else:
                    st.error(msg)
            else:
                st.session_state.confirm_delete_period = True
                st.warning("⚠️ 再按一次確認刪除")
    with col_info:
        st.info(f"✅ 當前選中: ID {period_id}")


# ============================================================
# Tab 2: 計算電費
# ============================================================
def render_calculation_tab(elec_service: ElectricityService,
                           notify_service: NotificationService):
    if "current_period_id" not in st.session_state:
        info_card("請先選擇期間", "請前往「計費期間」Tab 選擇一個期間", "⚠️", "warning")
        return

    period_id = st.session_state.current_period_id
    st.info(f"📅 當前期間 ID: {period_id}")
    existing = elec_service.get_payment_record(period_id)
    if existing is not None and not existing.empty:
        st.success(f"✅ 此期間已有 {len(existing)} 筆儲存記錄，可前往「📜 繳費記錄」Tab 查看")

    st.divider()
    section_header("步驟 1: 輸入台電帳單", "📄")
    st.caption("💡 1F 獨立計算 | 2F~4F 合併計算公用電並分攤給 2A~4D")

    r1c1, r1c2 = st.columns(2)
    r2c1, r2c2 = st.columns(2)
    cols_map = {"1F": r1c1, "2F": r1c2, "3F": r2c1, "4F": r2c2}
    floor_data = {}
    for floor_key, config in FLOOR_CONFIG.items():
        with cols_map[floor_key]:
            st.markdown(f"**{config['label']}**")
            badge = "🔒 獨立" if config["is_independent"] else "🔗 分攤"
            st.caption(f"{badge}: {', '.join(config['rooms'])}")
            amount = st.number_input("金額 (元)", min_value=0, value=0, step=100, key=f"{floor_key}_amt")
            kwh    = st.number_input("度數", min_value=0.0, value=0.0, step=10.0,
                                    format="%.2f", key=f"{floor_key}_kwh")
            floor_data[floor_key] = {"amount": amount, "kwh": kwh}

    if st.button("💾 儲存台電單", type="primary"):
        bills = [{"floor_label": k, "amount": v["amount"], "kwh": v["kwh"]}
                 for k, v in floor_data.items() if v["amount"] > 0 or v["kwh"] > 0]
        if not bills:
            st.error("❌ 請至少輸入一個樓層的台電單")
        else:
            st.session_state.setdefault("taipower_bills", {})[period_id] = bills
            st.success(f"✅ 已儲存 {len(bills)} 個台電單")

    saved_bills = st.session_state.get("taipower_bills", {}).get(period_id)
    if saved_bills:
        bill_1f     = next((b for b in saved_bills if b["floor_label"] == "1F"), None)
        bills_2f_4f = [b for b in saved_bills if b["floor_label"] != "1F"]
        st.divider()
        st.write("**已儲存摘要:**")
        if bill_1f:
            st.metric("1F (獨立)", f"${bill_1f['amount']:,}", f"{bill_1f['kwh']:.0f} 度")
        if bills_2f_4f:
            merged_amt = sum(b["amount"] for b in bills_2f_4f)
            merged_kwh = sum(b["kwh"]    for b in bills_2f_4f)
            scols = st.columns(len(bills_2f_4f) + 1)
            for i, b in enumerate(bills_2f_4f):
                with scols[i]:
                    st.metric(b["floor_label"], f"${b['amount']:,}", f"{b['kwh']:.0f} 度")
            with scols[-1]:
                st.metric("2-4F 合計", f"${merged_amt:,}", f"{merged_kwh:.0f} 度")

    st.divider()
    section_header("步驟 2: 輸入房間讀數", "🔢")
    st.caption("💡 🟢 新期間→上期自動帶入並鎖定  🔵 已儲存→可修改  ⚪ 首次→兩欄皆可輸入")

    existing_readings_list = elec_service.get_all_readings(period_id)
    existing_by_room: Dict[str, Dict] = {r["room_number"]: r for r in existing_readings_list}
    room_readings: Dict[str, float] = {}
    raw_readings:  Dict[str, Dict]  = {}

    for floor_key, config in FLOOR_CONFIG.items():
        st.markdown(f"### {config['label']}")
        cols = st.columns(len(config["rooms"]))
        for col, room in zip(cols, config["rooms"]):
            with col:
                st.markdown(f"**{room}**")
                if room in existing_by_room:
                    saved      = existing_by_room[room]
                    previous   = float(saved["previous_reading"])
                    saved_curr = float(saved["current_reading"])
                    st.number_input("上期 📊", value=previous, step=1.0, format="%.2f",
                                    key=f"prev_{room}", disabled=True)
                    current = st.number_input("本期 ✏️", min_value=previous, value=saved_curr,
                                              step=1.0, format="%.2f", key=f"curr_{room}")
                    st.caption("🔵 已儲存，可修改本期")
                else:
                    last_reading = elec_service.get_latest_meter_reading(room, period_id)
                    if last_reading is not None:
                        previous = float(last_reading)
                        st.number_input("上期 📊", value=previous, step=1.0, format="%.2f",
                                        key=f"prev_{room}", disabled=True)
                        current = st.number_input("本期 📈", min_value=previous, value=previous,
                                                  step=1.0, format="%.2f", key=f"curr_{room}")
                        st.caption("🟢 上期已自動帶入")
                    else:
                        previous = st.number_input("上期 📊", min_value=0.0, value=0.0,
                                                    step=1.0, format="%.2f", key=f"prev_{room}")
                        current  = st.number_input("本期 📈", min_value=0.0, value=0.0,
                                                    step=1.0, format="%.2f", key=f"curr_{room}")
                        st.caption("⚪ 首次輸入")

                usage = current - previous
                if usage > 0:
                    st.success(f"⚡ {usage:.1f} 度")
                elif current > 0:
                    st.info("📊 無變化")
                else:
                    st.caption("　等待輸入")
                room_readings[room] = usage
                raw_readings[room]  = {"previous": previous, "current": current}
        st.divider()

    st.session_state.setdefault("room_readings", {})[period_id] = room_readings
    st.session_state.setdefault("raw_readings",  {})[period_id] = raw_readings
    st.divider()

    section_header("步驟 3: 計算電費", "🧮")
    if st.button("🚀 開始計算", type="primary"):
        bills    = st.session_state.get("taipower_bills", {}).get(period_id)
        readings = st.session_state.get("room_readings",  {}).get(period_id)
        raw      = st.session_state.get("raw_readings",   {}).get(period_id)
        if not bills:
            st.error("❌ 請先輸入台電帳單"); return
        if not readings or all(v == 0 for v in readings.values()):
            st.error("❌ 請先輸入房間讀數"); return

        result = calculate_electricity_charges(bills, readings)
        if not result:
            st.error("❌ 計算失敗"); return

        enriched_details = []
        save_count = 0
        with st.spinner("💾 正在儲存..."):
            for detail in result["details"]:
                room = detail["房號"]
                detail["previous_reading"] = raw[room]["previous"]
                detail["current_reading"]  = raw[room]["current"]
                enriched_details.append(detail)
                ok, _ = elec_service.save_reading(
                    period_id=period_id, room=room,
                    previous=raw[room]["previous"], current=raw[room]["current"],
                    kwh_used=detail["使用度數"], unit_price=detail["單價"],
                    public_share_kwh=detail["公用分攤"], amount_due=detail["應繳金額"],
                    room_type=detail["類型"],
                )
                if ok:
                    save_count += 1

        st.session_state[f"calc_result_{period_id}"]  = result
        st.session_state[f"calc_details_{period_id}"] = enriched_details
        st.success(f"✅ 計算完成！已儲存 {save_count} 筆")
        st.rerun()

    result           = st.session_state.get(f"calc_result_{period_id}")
    enriched_details = st.session_state.get(f"calc_details_{period_id}")
    if not (result and enriched_details):
        return

    st.markdown("### 📊 計算摘要")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("2-4F 度數",  f"{result['merged_kwh']:.0f} 度")
    c2.metric("總公用電",   f"{result['total_public_kwh']:.0f} 度")
    c3.metric("每間分攤",   f"{result['shared_per_room']} 度")
    c4.metric("2-4F 單價",  f"${result['merged_unit_price']:.2f}/度")

    st.divider()
    st.markdown("### 📊 各樓層摘要")
    for fs in result["floor_summaries"]:
        with st.expander(f"**{fs['floor']}** - 台電: ${fs['bill_amount']:,} | 收費: ${fs['total_charge']:,}",
                         expanded=True):
            col1, col2 = st.columns(2)
            col1.metric("台電度數", f"{fs['bill_kwh']:.0f} 度")
            col2.metric("房間用電", f"{fs['room_kwh']:.0f} 度")

    st.divider()
    st.markdown(f"""
### 💰 總計
- **台電總金額**: ${result['taipower_amount']:,} 元
- **收費總金額**: ${result['total_charge']:,} 元
- **差異**: ${result['difference']:+,.0f} 元""")

    st.divider()
    st.write("**各房間明細**")
    details_df = pd.DataFrame(enriched_details)
    col_order = ["樓層", "房號", "類型", "previous_reading", "current_reading",
                 "使用度數", "公用分攤", "總度數", "單價", "應繳金額"]
    details_df = details_df[col_order].copy()
    details_df["公用分攤"] = details_df["公用分攤"].astype(int)
    details_df.columns = ["樓層", "房號", "類型", "上期讀數", "本期讀數",
                           "使用度數", "公用分攤", "總度數", "單價", "應繳金額"]
    data_table(details_df, key="calc_details")

    st.divider()
    section_header("通知設定", "🔔", divider=False)
    st.markdown("### 📱 LINE 電費通知")
    notify_mode = st.radio("通知模式",
                            options=["不發送", "手動發送", "自動發送"],
                            horizontal=True, key="notify_mode")
    if notify_mode == "不發送":
        st.info("⚪ 不會發送任何通知")
    elif notify_mode == "手動發送":
        st.warning("⚠️ 需要手動點擊「發送〝")
        if st.button("📤 立即發送電費通知", type="primary"):
            with st.spinner("正在發送通知..."):
                success_count = fail_count = 0
                for detail in enriched_details:
                    ok, msg = notify_service.send_electricity_bill_notification(
                        room_number=detail["房號"], period_id=period_id,
                        amount=detail["應繳金額"], kwh=detail["總度數"])
                    if ok:
                        success_count += 1
                    else:
                        fail_count += 1
                if success_count:
                    st.success(f"✅ 成功發送 {success_count} 則")
                if fail_count:
                    st.error(f"❌ 失敗 {fail_count} 則")
    elif notify_mode == "自動發送":
        period_info = elec_service.get_period_by_id(period_id)
        remind_date = period_info.get("remind_start_date")
        if not remind_date:
            st.error("❌ 請先設定催繳日期")
        else:
            days_left = (datetime.strptime(remind_date, "%Y-%m-%d") - datetime.now()).days
            if days_left <= 0:
                st.success(f"✅ 催繳日期已到（{remind_date}）")
            else:
                st.info(f"⏳ 催繳日期: {remind_date}（還有 {days_left} 天）")

    st.divider()
    csv = details_df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button("📥 下載 CSV 備份", csv, f"electricity_{period_id}.csv", "text/csv")


# ============================================================
# Tab 3: 繳費記錄
# ============================================================
def render_records_tab(elec_service: ElectricityService):
    section_header("繳費記錄", "📜")
    if "current_period_id" not in st.session_state:
        info_card("請先選擇期間", "請前往「計費期間」Tab 選擇一個期間", "⚠️", "warning")
        return

    period_id = st.session_state.current_period_id
    st.info(f"📅 當前查詢期間 ID: {period_id}")

    with st.spinner("正在查詢..."):
        df = elec_service.get_payment_record(period_id)
    if df is None or df.empty:
        empty_state("尚無記錄", "📭", "請先在「計算電費」Tab 完成計算")
        return

    col_toggle, col_hint = st.columns([2, 5])
    with col_toggle:
        hide_1f = st.toggle("🙈 隱藏 1F (1A/1B)", value=False, key="hide_1f_toggle",
                             help="開啟後表格與 CSV 均不含 1A / 1B")
    with col_hint:
        if hide_1f:
            st.warning("⚠️ 目前已隱藏 1F，下方數據與 CSV 均不含 1F")
        else:
            st.caption("💡 開啟左側開關可隱藏 1F 房間")

    display_df = df.copy()
    if hide_1f:
        room_col = "房號" if "房號" in display_df.columns else "room_number"
        display_df = display_df[~display_df[room_col].isin(_1F_ROOMS)].reset_index(drop=True)

    total_rows = len(display_df)
    st.success(f"✅ 顯示 {total_rows} 筆電費記錄" + (" (已隱藏 1F)" if hide_1f else ""))

    due_col  = "應繳金額" if "應繳金額" in display_df.columns else "amount_due"
    paid_col = "已繳金額" if "已繳金額" in display_df.columns else "paid_amount"
    total_due     = int(display_df[due_col].sum())  if due_col  in display_df.columns else 0
    total_paid    = int(display_df[paid_col].sum()) if paid_col in display_df.columns else 0
    total_balance = total_due - total_paid

    c1, c2, c3 = st.columns(3)
    with c1: metric_card("應收總額", f"${total_due:,}",     "", "💰", "normal")
    with c2: metric_card("已收金額", f"${total_paid:,}",    "", "✅", "success")
    with c3: metric_card("未收金額", f"${total_balance:,}", "", "⚠️", "warning")

    st.divider()
    st.write(f"**共 {total_rows} 筆記錄**" + (" ── 已隱藏 1F" if hide_1f else ""))
    data_table(display_df, key="payment_records")

    st.divider()
    csv_suffix   = "_no1F" if hide_1f else ""
    csv_filename = f"payment_records_{period_id}{csv_suffix}.csv"
    csv_bytes    = display_df.to_csv(index=False, encoding="utf-8-sig")
    dl_col, hint_col = st.columns([2, 5])
    with dl_col:
        st.download_button(
            label=f"📥 下載繳費記錄 CSV{'(不含1F)' if hide_1f else ''}",
            data=csv_bytes, file_name=csv_filename, mime="text/csv")
    with hint_col:
        st.caption(f"📄 檔名: {csv_filename}")


# ============================================================
# Tab 4: 用電統計  [NEW v4.8]
# ============================================================
def render_statistics_tab(elec_service: ElectricityService):
    section_header("用電量統計", "📊")
    st.caption("💡 自動從所有已計算期間彙結，可查看全年用電趨勢")

    # ─ 取得所有期間資料 ──────────────────────────────────
    periods = elec_service.get_all_periods()
    if not periods:
        empty_state("尚無期間", "📅", "請先建立期間並完成計算")
        return

    stats_rows = []
    room_trend_rows = []

    for p in sorted(periods, key=lambda x: (x["period_year"], x["period_month_start"])):
        df = elec_service.get_payment_record(p["id"])
        if df is None or df.empty:
            continue

        label = f"{p['period_year']}/{p['period_month_start']:02d}-{p['period_month_end']:02d}"

        # 相容欄位名稱
        kwh_col = "總度數" if "總度數" in df.columns else (
                  "使用度數" if "使用度數" in df.columns else "kwh_used")
        amt_col = "應繳金額" if "應繳金額" in df.columns else "amount_due"
        room_col = "房號"     if "房號"     in df.columns else "room_number"

        stats_rows.append({
            "期間":    label,
            "年份":    p["period_year"],
            "開始月":  p["period_month_start"],
            "總度數": round(df[kwh_col].sum(), 1),
            "總金額": int(df[amt_col].sum()),
            "期間ID":  p["id"],
        })

        # 房間級度數
        for _, row in df.iterrows():
            room_trend_rows.append({
                "期間":  label,
                "年份":  p["period_year"],
                "房號":  row.get(room_col, ""),
                "度數":  round(float(row.get(kwh_col, 0)), 1),
                "金額":  int(row.get(amt_col, 0)),
            })

    if not stats_rows:
        empty_state("尚無計算資料", "📭", "請先在「計算電費」Tab 完成計算")
        return

    stats_df      = pd.DataFrame(stats_rows)
    room_trend_df = pd.DataFrame(room_trend_rows)

    # ─ 年度筛選 ───────────────────────────────────────
    available_years = sorted(stats_df["年份"].unique(), reverse=True)
    year_options    = ["全部"] + [str(y) for y in available_years]

    col_yr, col_hint = st.columns([2, 5])
    with col_yr:
        selected_year = st.selectbox("📆 年度筛選", year_options, key="stat_year_filter")
    with col_hint:
        st.caption("選择年度即可築選該年度所有期間")

    if selected_year != "全部":
        filtered = stats_df[stats_df["年份"] == int(selected_year)].copy()
    else:
        filtered = stats_df.copy()

    if filtered.empty:
        st.warning("⚠️ 該年度尚無數據")
        return

    # ─ 4 大指標 ───────────────────────────────────────
    total_periods = len(filtered)
    total_kwh     = filtered["總度數"].sum()
    total_amt     = filtered["總金額"].sum()
    avg_kwh       = total_kwh / total_periods if total_periods else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1: metric_card("累計期數",   f"{total_periods} 期",       "", "📅", "normal")
    with c2: metric_card("總用電量",   f"{total_kwh:,.0f} 度",     "", "⚡", "normal")
    with c3: metric_card("總收費金額", f"${total_amt:,}",           "", "💰", "success")
    with c4: metric_card("平均每期",   f"{avg_kwh:,.0f} 度",        "", "📊", "normal")

    st.divider()

    # ─ 雙軸指標圖（仿台電 App）────────────────────────
    section_header("用電度數與費用趨勢", "📈", divider=False)

    if HAS_PLOTLY:
        fig = go.Figure()

        # 黄色長條 = 總度數（左軸）
        fig.add_trace(go.Bar(
            x=filtered["期間"],
            y=filtered["總度數"],
            name="總度數 (度)",
            marker_color="#F5C518",
            opacity=0.85,
            yaxis="y1",
            hovertemplate="%{x}<br>總度數: <b>%{y:.0f} 度</b><extra></extra>",
        ))

        # 綠色折線 = 總金額（右軸）
        fig.add_trace(go.Scatter(
            x=filtered["期間"],
            y=filtered["總金額"],
            name="總金額 (元)",
            mode="lines+markers",
            line=dict(color="#2ca02c", width=2.5),
            marker=dict(size=8, color="#2ca02c"),
            yaxis="y2",
            hovertemplate="%{x}<br>總金額: <b>$%{y:,}</b><extra></extra>",
        ))

        fig.update_layout(
            title=dict(text="用電度數 × 費用比較", font=dict(size=16)),
            xaxis=dict(title="期間", tickangle=-30),
            yaxis=dict(
                title="總度數 (度)",
                side="left",
                showgrid=True,
                gridcolor="#eeeeee",
            ),
            yaxis2=dict(
                title="總金額 (元)",
                side="right",
                overlaying="y",
                showgrid=False,
            ),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            plot_bgcolor="white",
            height=420,
            hovermode="x unified",
            margin=dict(l=10, r=10, t=50, b=40),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        # Plotly 未安裝，用 Streamlit 原生圖表降級
        st.bar_chart(filtered.set_index("期間")["總度數"])
        st.line_chart(filtered.set_index("期間")["總金額"])
        st.caption("建議安裝 'plotly' 可獲得雙軸指標圖")

    st.divider()

    # ─ 期間明細表 ─────────────────────────────────────
    section_header("期間明細表", "📝", divider=False)
    display_stats = filtered[["期間", "總度數", "總金額"]].copy()
    display_stats["總金額"] = display_stats["總金額"].apply(lambda x: f"${x:,}")
    data_table(display_stats, key="stats_summary_table")

    st.divider()

    # ─ 房間用電趨勢（可展開）───────────────────────
    with st.expander("🏠 展開各房間用電趨勢", expanded=False):
        if room_trend_df.empty:
            st.info("尚無房間級資料")
        else:
            if selected_year != "全部":
                rt = room_trend_df[room_trend_df["年份"] == int(selected_year)].copy()
            else:
                rt = room_trend_df.copy()

            # pivot: 期間 x 房號 → 度數
            pivot = rt.pivot_table(index="期間", columns="房號",
                                    values="度數", aggfunc="sum").fillna(0)
            pivot = pivot.reindex(filtered["期間"].tolist())  # 保持期間順序

            if HAS_PLOTLY:
                fig2 = go.Figure()
                colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
                          "#9467bd", "#8c564b", "#e377c2", "#7f7f7f",
                          "#bcbd22", "#17becf", "#aec7e8", "#ffbb78"]
                for i, room in enumerate(pivot.columns):
                    fig2.add_trace(go.Bar(
                        name=room,
                        x=pivot.index,
                        y=pivot[room],
                        marker_color=colors[i % len(colors)],
                        hovertemplate=f"{room}<br>%{{x}}<br>度數: <b>%{{y:.0f}} 度</b><extra></extra>",
                    ))
                fig2.update_layout(
                    barmode="group",
                    title="各房間用電度數比較",
                    xaxis=dict(title="期間", tickangle=-30),
                    yaxis=dict(title="度數"),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                    plot_bgcolor="white",
                    height=380,
                    margin=dict(l=10, r=10, t=50, b=40),
                )
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.bar_chart(pivot)

            st.write("**各房間度數明細**")
            data_table(pivot.reset_index().rename(columns={"index": "期間"}), key="room_trend_table")


# ============================================================
# 主渲染
# ============================================================
def render():
    st.title("⚡ 電費管理")

    elec_service   = ElectricityService()
    notify_service = NotificationService()

    tab1, tab2, tab3, tab4 = st.tabs([
        "📅 計費期間",
        "🧮 計算電費",
        "📜 繳費記錄",
        "📊 用電統計",
    ])

    with tab1:
        render_period_tab(elec_service)
    with tab2:
        render_calculation_tab(elec_service, notify_service)
    with tab3:
        render_records_tab(elec_service)
    with tab4:
        render_statistics_tab(elec_service)


def show():
    render()


if __name__ == "__main__":
    show()
