"""
電費管理 - v4.6
✅ v4.5 所有功能保留
✅ [FIX v4.6] 步驟 2 三段式讀數邏輯：
      Case A  本期已有 DB 資料  → 上期鎖定、本期可修改
      Case B  上期有 DB 讀數    → 上期自動帶入並鎖定，只需填本期
      Case C  全新（第一次）    → 上期、本期皆可編輯
✅ [FIX v4.6] is_first_time 不再把「讀數=0」誤判為首次
✅ [FIX v4.6] 視覺提示：顯示讀數來源（上期 ID / 已儲存 / 首次）
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
import logging

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
    """計算電費 - v4.6（邏輯不變）"""
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

        sharing_rooms_with_reading = [
            r for r in ROOMS.SHARING_ROOMS if room_readings.get(r, 0) > 0
        ]
        sharing_count   = len(sharing_rooms_with_reading)
        shared_per_room = int(round(public_kwh / sharing_count)) if sharing_count > 0 else 0

        results = []

        # 1F 獨立房間
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

        # 2F~4F 分攤房間
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

        # 樓層摘要
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
            fl    = bill["floor_label"]
            rooms = FLOOR_CONFIG[fl]["rooms"]
            fl_r  = [r for r in results if r["房號"] in rooms]
            if fl_r:
                floor_summaries.append({
                    "floor": fl, "bill_amount": bill["amount"],
                    "bill_kwh": bill["kwh"],
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
        year = st.number_input(
            "年份", min_value=2020, max_value=2030,
            value=date.today().year, key="period_year",
        )
    with col2:
        month_start = st.selectbox(
            "開始月", range(1, 13),
            index=date.today().month - 1, key="period_start",
        )
    with col3:
        month_end = st.selectbox(
            "結束月", range(1, 13),
            index=date.today().month % 12, key="period_end",
        )

    col_date, col_btn = st.columns([3, 1])
    with col_date:
        remind_on_create = st.date_input(
            "催繳開始日（可留空，稍後再設）",
            value=None,
            key="remind_on_create",
        )
    with col_btn:
        st.write("")
        st.write("")
        if st.button("➕ 建立", type="primary"):
            if month_end <= month_start:
                st.error("❌ 結束月必須大於開始月")
            else:
                remind_str = (
                    remind_on_create.strftime("%Y-%m-%d")
                    if remind_on_create else None
                )
                ok, msg, period_id = elec_service.add_period(
                    year, month_start, month_end, remind_str
                )
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
            value=(
                datetime.strptime(current_remind_date, "%Y-%m-%d").date()
                if current_remind_date
                else date.today()
            ),
            key="remind_date_input",
        )
    with col_b:
        st.write("")
        st.write("")
        if st.button("💾 儲存日期", type="primary"):
            ok, msg = elec_service.update_period_remind_date(
                period_id, new_remind_date.strftime("%Y-%m-%d")
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
def render_calculation_tab(
    elec_service: ElectricityService,
    notify_service: NotificationService,
):
    if "current_period_id" not in st.session_state:
        info_card("請先選擇期間", "請前往「計費期間」Tab 選擇一個期間", "⚠️", "warning")
        return

    period_id = st.session_state.current_period_id
    st.info(f"📅 當前期間 ID: {period_id}")

    existing = elec_service.get_payment_record(period_id)
    if existing is not None and not existing.empty:
        st.success(f"✅ 此期間已有 {len(existing)} 筆儲存記錄，可前往「📜 繳費記錄」Tab 查看")

    st.divider()

    # ── 步驟 1: 台電帳單 ─────────────────────────────────────
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
            kwh    = st.number_input("度數",      min_value=0.0, value=0.0, step=10.0, format="%.2f", key=f"{floor_key}_kwh")
            floor_data[floor_key] = {"amount": amount, "kwh": kwh}

    if st.button("💾 儲存台電單", type="primary"):
        bills = [
            {"floor_label": k, "amount": v["amount"], "kwh": v["kwh"]}
            for k, v in floor_data.items()
            if v["amount"] > 0 or v["kwh"] > 0
        ]
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

    # ── 步驟 2: 房間讀數 ─────────────────────────────────────
    section_header("步驟 2: 輸入房間讀數", "🔢")
    st.caption(
        "💡 規則："
        "🟢 新期間 → 上期自動帶入上次讀數（鎖定），只需填本期  "
        "🔵 本期已儲存 → 可修改本期讀數  "
        "⚪ 首次輸入 → 上期、本期皆可手動輸入"
    )

    # ✅ [v4.6] 一次查出本期已存在 DB 的讀數，key=room_number
    existing_readings_list = elec_service.get_all_readings(period_id)
    existing_by_room: Dict[str, Dict] = {
        r["room_number"]: r for r in existing_readings_list
    }

    room_readings: Dict[str, float] = {}
    raw_readings:  Dict[str, Dict]  = {}

    for floor_key, config in FLOOR_CONFIG.items():
        st.markdown(f"### {config['label']}")
        cols = st.columns(len(config["rooms"]))

        for col, room in zip(cols, config["rooms"]):
            with col:
                st.markdown(f"**{room}**")

                # ── Case A: 本期 DB 已有資料（曾計算過） ────────
                if room in existing_by_room:
                    saved       = existing_by_room[room]
                    previous    = float(saved["previous_reading"])
                    saved_curr  = float(saved["current_reading"])

                    # 上期鎖定顯示
                    st.number_input(
                        "上期 📊",
                        value=previous,
                        step=1.0,
                        format="%.2f",
                        key=f"prev_{room}",
                        disabled=True,
                        help=f"本期已儲存資料，上期讀數鎖定",
                    )
                    # 本期可修改
                    current = st.number_input(
                        "本期 ✏️",
                        min_value=previous,
                        value=saved_curr,
                        step=1.0,
                        format="%.2f",
                        key=f"curr_{room}",
                        help="本期已有儲存值，可直接修改後重新計算",
                    )
                    st.caption("🔵 已儲存，可修改本期")

                else:
                    # ── Case B / C: 查詢上期讀數 ─────────────────
                    # ✅ [v4.6] 只以 None 判斷，不再把 0 誤判為首次
                    last_reading = elec_service.get_latest_meter_reading(room, period_id)

                    if last_reading is not None:
                        # ── Case B: 有上期資料 → 上期鎖定，只填本期 ──
                        previous = float(last_reading)
                        st.number_input(
                            "上期 📊",
                            value=previous,
                            step=1.0,
                            format="%.2f",
                            key=f"prev_{room}",
                            disabled=True,
                            help="自動帶入上期最後讀數（不可修改）",
                        )
                        current = st.number_input(
                            "本期 📈",
                            min_value=previous,
                            value=previous,
                            step=1.0,
                            format="%.2f",
                            key=f"curr_{room}",
                            help="請輸入本次抄表讀數",
                        )
                        st.caption("🟢 上期已自動帶入")

                    else:
                        # ── Case C: 全新第一次，兩欄皆可輸入 ────────
                        previous = st.number_input(
                        "上期 📊",
                            min_value=0.0,
                            value=0.0,
                            step=1.0,
                            format="%.2f",
                            key=f"prev_{room}",
                            help="首次輸入，請填電表起始讀數",
                        )
                        current = st.number_input(
                            "本期 📈",
                            min_value=0.0,
                            value=0.0,
                            step=1.0,
                            format="%.2f",
                            key=f"curr_{room}",
                            help="請輸入本次抄表讀數",
                        )
                        st.caption("⚪ 首次輸入")

                # ── 使用度數 badge ───────────────────────────────
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

    # 儲存讀數到 session_state（供步驟 3 使用）
    st.session_state.setdefault("room_readings", {})[period_id] = room_readings
    st.session_state.setdefault("raw_readings",  {})[period_id] = raw_readings

    st.divider()

    # ── 步驟 3: 計算 ─────────────────────────────────────────
    section_header("步驟 3: 計算電費", "🧮")

    if st.button("🚀 開始計算", type="primary"):
        bills    = st.session_state.get("taipower_bills", {}).get(period_id)
        readings = st.session_state.get("room_readings",  {}).get(period_id)
        raw      = st.session_state.get("raw_readings",   {}).get(period_id)

        if not bills:
            st.error("❌ 請先輸入台電帳單"); return
        if not readings or all(v == 0 for v in readings.values()):
            st.error("❌ 請先輸入房間讀數（本期讀數需大於上期）"); return

        result = calculate_electricity_charges(bills, readings)
        if not result:
            st.error("❌ 計算失敗"); return

        enriched_details = []
        save_count = 0

        with st.spinner("💾 正在儲存計費資訊到資料庫..."):
            for detail in result["details"]:
                room = detail["房號"]
                detail["previous_reading"] = raw[room]["previous"]
                detail["current_reading"]  = raw[room]["current"]
                enriched_details.append(detail)

                ok, _ = elec_service.save_reading(
                    period_id        = period_id,
                    room             = room,
                    previous         = raw[room]["previous"],
                    current          = raw[room]["current"],
                    kwh_used         = detail["使用度數"],
                    unit_price       = detail["單價"],
                    public_share_kwh = detail["公用分攤"],
                    amount_due       = detail["應繳金額"],
                    room_type        = detail["類型"],
                )
                if ok:
                    save_count += 1

        st.session_state[f"calc_result_{period_id}"]  = result
        st.session_state[f"calc_details_{period_id}"] = enriched_details
        logger.info(f"Calculated and saved {save_count} records for period {period_id}")
        st.success(f"✅ 計算完成！已自動儲存 {save_count} 筆計費記錄到資料庫")
        st.rerun()

    # ── 顯示計算結果 ─────────────────────────────────────────
    result           = st.session_state.get(f"calc_result_{period_id}")
    enriched_details = st.session_state.get(f"calc_details_{period_id}")

    if not (result and enriched_details):
        return

    st.markdown("### 📊 計算摘要")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("2-4F 合計",  f"{result['merged_kwh']:.0f} 度")
    c2.metric("總公用電",   f"{result['total_public_kwh']:.0f} 度")
    c3.metric("每間分攤",   f"{result['shared_per_room']} 度")
    c4.metric("2-4F 單價",  f"${result['merged_unit_price']:.2f}/度")

    st.divider()
    st.markdown("### 📊 各樓層摘要")
    for fs in result["floor_summaries"]:
        with st.expander(
            f"**{fs['floor']}** - 台電: ${fs['bill_amount']:,} | 收費: ${fs['total_charge']:,}",
            expanded=True,
        ):
            col1, col2 = st.columns(2)
            col1.metric("台電度數", f"{fs['bill_kwh']:.0f} 度")
            col2.metric("房間用電", f"{fs['room_kwh']:.0f} 度")

    st.divider()
    st.markdown(f"""
### 💰 總計
- **台電總金額**: ${result['taipower_amount']:,} 元
- **收費總金額**: ${result['total_charge']:,} 元
- **差異**: ${result['difference']:+,.0f} 元
    """)

    st.divider()
    st.write("**各房間明細**")
    details_df = pd.DataFrame(enriched_details)
    col_order  = [
        "樓層", "房號", "類型", "previous_reading", "current_reading",
        "使用度數", "公用分攤", "總度數", "單價", "應繳金額",
    ]
    details_df = details_df[col_order].copy()
    details_df["公用分攤"] = details_df["公用分攤"].astype(int)
    details_df.columns = [
        "樓層", "房號", "類型", "上期讀數", "本期讀數",
        "使用度數", "公用分攤", "總度數", "單價", "應繳金額",
    ]
    data_table(details_df, key="calc_details")

    st.divider()
    section_header("通知設定", "🔔", divider=False)
    st.markdown("### 📱 LINE 電費通知")

    notify_mode = st.radio(
        "通知模式",
        options=["不發送", "手動發送", "自動發送"],
        horizontal=True,
        key="notify_mode",
    )

    if notify_mode == "不發送":
        st.info("⚪ 不會發送任何通知")

    elif notify_mode == "手動發送":
        st.warning("⚠️ 需要手動點擊「發送通知」按鈕")
        if st.button("📤 立即發送電費通知", type="primary"):
            with st.spinner("正在發送通知..."):
                success_count = fail_count = 0
                for detail in enriched_details:
                    ok, msg = notify_service.send_electricity_bill_notification(
                        room_number=detail["房號"],
                        period_id=period_id,
                        amount=detail["應繳金額"],
                        kwh=detail["總度數"],
                    )
                    if ok:
                        success_count += 1
                    else:
                        fail_count += 1
                        logger.error(f"發送失敗: {detail['房號']} - {msg}")
                if success_count:
                    st.success(f"✅ 成功發送 {success_count} 則通知")
                if fail_count:
                    st.error(f"❌ 失敗 {fail_count} 則（可能是租客未綁定 LINE）")

    elif notify_mode == "自動發送":
        period_info = elec_service.get_period_by_id(period_id)
        remind_date = period_info.get("remind_start_date")
        if not remind_date:
            st.error("❌ 請先在「計費期間」Tab 設定催繳日期")
        else:
            remind_dt = datetime.strptime(remind_date, "%Y-%m-%d")
            days_left = (remind_dt - datetime.now()).days
            if days_left <= 0:
                st.success(f"✅ 催繳日期已到（{remind_date}），系統將自動發送通知")
            else:
                st.info(f"⏳ 催繳日期: {remind_date}（還有 {days_left} 天）")

    st.divider()
    csv = details_df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button("📥 下載 CSV 備份", csv, f"electricity_{period_id}.csv", "text/csv")
    st.info("💡 計費記錄已自動儲存，可前往「📜 繳費記錄」Tab 查看")


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

    with st.spinner("正在從資料庫查詢記錄..."):
        df = elec_service.get_payment_record(period_id)

    if df is None or df.empty:
        empty_state("尚無記錄", "📭", "請先在「計算電費」Tab 完成計算（會自動儲存）")
        return

    st.success(f"✅ 已找到 {len(df)} 筆電費記錄")

    summary = elec_service.get_payment_summary(period_id)
    if summary:
        c1, c2, c3 = st.columns(3)
        metric_card("應收總額", f"${summary.get('total_due',     0):,}", "", "💰", "normal")
        metric_card("已收金額", f"${summary.get('total_paid',    0):,}", "", "✅", "success")
        metric_card("未收金額", f"${summary.get('total_balance', 0):,}", "", "⚠️", "warning")

    st.divider()
    st.write(f"**共 {len(df)} 筆記錄**")
    data_table(df, key="payment_records")

    st.divider()
    csv = df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        "📥 下載繳費記錄 CSV", csv,
        f"payment_records_{period_id}.csv", "text/csv",
    )


# ============================================================
# 主渲染
# ============================================================
def render():
    st.title("⚡ 電費管理")

    elec_service   = ElectricityService()
    notify_service = NotificationService()

    tab1, tab2, tab3 = st.tabs(["📅 計費期間", "🧮 計算電費", "📜 繳費記錄"])

    with tab1:
        render_period_tab(elec_service)
    with tab2:
        render_calculation_tab(elec_service, notify_service)
    with tab3:
        render_records_tab(elec_service)


def show():
    render()


if __name__ == "__main__":
    show()
