"""
電費管理 - v6.0
✅ 保留原有功能
✅ 修正 NotificationService.send_electricity_bill_notification() 參數不一致問題
✅ 強化日期 / 數值轉換穩定性
✅ 強化 session state 管理
✅ 強化通知發送防呆與 logging
"""

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

try:
    import plotly.graph_objects as go

    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

from services.electricity_service import ElectricityService
from services.notification_service import NotificationService

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
        st.dataframe(df, width="stretch", key=key)

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

_1F_ROOMS = ["1A", "1B"]

# 台電風格色票
_COLOR_BAR = "#FFD600"
_COLOR_LINE = "#00C853"
_COLOR_LATEST = "#FF6D00"
_ROOM_COLORS = [
    "#1565C0", "#42A5F5", "#C62828", "#EF9A9A",
    "#2E7D32", "#66BB6A", "#00838F", "#80DEEA",
    "#E65100", "#FFB74D", "#4527A0", "#B39DDB",
]

# ============================================================
# 樓層配置
# ============================================================
FLOOR_CONFIG = {
    "1F": {"label": "1F 台電單", "rooms": ["1A", "1B"], "is_independent": True},
    "2F": {"label": "2F 台電單", "rooms": ["2A", "2B"], "is_independent": False},
    "3F": {"label": "3F 台電單", "rooms": ["3A", "3B", "3C", "3D"], "is_independent": False},
    "4F": {"label": "4F 台電單", "rooms": ["4A", "4B", "4C", "4D"], "is_independent": False},
}

# ============================================================
# Session Keys
# ============================================================
KEY_TAIPOWER_BILLS = "taipower_bills"
KEY_ROOM_READINGS = "room_readings"
KEY_RAW_READINGS = "raw_readings"
KEY_CURRENT_PERIOD_ID = "current_period_id"
KEY_CONFIRM_DELETE_PERIOD = "confirm_delete_period"
KEY_NOTIFY_MODE = "notify_mode"

# ============================================================
# 共用小工具
# ============================================================
def _get_room_options() -> List[str]:
    return getattr(
        ROOMS,
        "ALL_ROOMS",
        ["1A", "1B", "2A", "2B", "3A", "3B", "3C", "3D", "4A", "4B", "4C", "4D"],
    )


def _safe_int(v) -> int:
    try:
        if pd.isna(v):
            return 0
        return int(float(v))
    except Exception:
        return 0


def _safe_float(v, default: float = 0.0) -> float:
    try:
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def _to_int_safe(value, default=0) -> int:
    try:
        if pd.isna(value):
            return default
        return int(round(float(value)))
    except Exception:
        return default


def _format_amount_cell(value) -> str:
    try:
        if pd.isna(value):
            return ""
        return f"{float(value):,.0f}"
    except Exception:
        return ""


def _get_selected_period_default_index(
    period_options: Dict[str, Optional[int]],
    default_period_id: Optional[int],
) -> int:
    if default_period_id is None:
        return 0
    values = list(period_options.values())
    return values.index(default_period_id) if default_period_id in values else 0


def _session_get_nested(key: str, subkey: Any, default=None):
    return st.session_state.get(key, {}).get(subkey, default)


def _session_set_nested(key: str, subkey: Any, value: Any) -> None:
    st.session_state.setdefault(key, {})[subkey] = value


def _calc_result_key(period_id: int) -> str:
    return f"calc_result_{period_id}"


def _calc_details_key(period_id: int) -> str:
    return f"calc_details_{period_id}"


def _to_date_safe(v) -> Optional[date]:
    """
    相容 str / datetime.date / datetime / None
    """
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return datetime.strptime(str(v), "%Y-%m-%d").date()
    except Exception:
        return None


def _normalize_period_label(period: Dict) -> str:
    return f"{period['period_year']}/{period['period_month_start']:02d}-{period['period_month_end']:02d}"


def _get_amount_col(df: pd.DataFrame) -> str:
    return "應繳金額" if "應繳金額" in df.columns else "amount_due"


def _get_paid_col(df: pd.DataFrame) -> str:
    return "已繳金額" if "已繳金額" in df.columns else "paid_amount"


def _get_room_col(df: pd.DataFrame) -> str:
    return "房號" if "房號" in df.columns else "room_number"


def _get_kwh_col(df: pd.DataFrame) -> str:
    if "總度數" in df.columns:
        return "總度數"
    if "使用度數" in df.columns:
        return "使用度數"
    return "kwh_used"


def _coerce_notify_payload(detail: Dict, period_id: int) -> Dict[str, Any]:
    return {
        "room_number": str(detail.get("房號", "")).strip(),
        "period_id": _to_int_safe(period_id, 0),
        "amount": _safe_float(detail.get("應繳金額", 0), 0.0),
        "kwh": _safe_float(detail.get("總度數", 0), 0.0),
    }


def _send_electricity_notification_safe(
    notify_service: NotificationService,
    detail: Dict[str, Any],
    period_id: int,
) -> Tuple[bool, str]:
    """
    包裝通知發送，避免 NotificationService 介面變動導致整頁炸掉。
    會依序嘗試多種常見簽名。
    """
    payload = _coerce_notify_payload(detail, period_id)
    room_number = payload["room_number"]
    amount = payload["amount"]
    kwh = payload["kwh"]
    period_id_int = payload["period_id"]

    method = getattr(notify_service, "send_electricity_bill_notification", None)
    if not callable(method):
        logger.error("[Electricity] NotificationService 缺少 send_electricity_bill_notification")
        return False, "通知服務未提供 send_electricity_bill_notification"

    candidate_calls = [
        {"room_number": room_number, "period_id": period_id_int, "amount": amount, "kwh": kwh},
        {"room": room_number, "period_id": period_id_int, "amount": amount, "kwh": kwh},
        {"room_number": room_number, "amount": amount, "kwh": kwh},
        {"room": room_number, "amount": amount, "kwh": kwh},
        {"room_number": room_number, "amount_due": amount, "kwh_used": kwh, "period_id": period_id_int},
        {"room": room_number, "amount_due": amount, "kwh_used": kwh, "period_id": period_id_int},
    ]

    last_error = None
    for kwargs in candidate_calls:
        try:
            logger.info("[Electricity] 嘗試發送電費通知 room=%s kwargs=%s", room_number, list(kwargs.keys()))
            result = method(**kwargs)

            if isinstance(result, tuple) and len(result) >= 2:
                ok = bool(result[0])
                msg = str(result[1])
                return ok, msg

            if isinstance(result, bool):
                return result, "通知已發送" if result else "通知發送失敗"

            return True, "通知已送出"

        except TypeError as e:
            last_error = e
            continue
        except Exception as e:
            logger.exception("[Electricity] 發送通知失敗 room=%s", room_number)
            return False, f"{room_number} 發送失敗: {e}"

    logger.exception("[Electricity] 通知方法簽名不相容 room=%s err=%s", room_number, last_error)
    return False, f"{room_number} 通知方法參數不相容: {last_error}"


# ============================================================
# 計算邏輯
# ============================================================
def calculate_electricity_charges(
    taipower_bills: List[Dict],
    room_readings: Dict[str, float],
) -> Optional[Dict]:
    try:
        floor_1f = next((b for b in taipower_bills if b["floor_label"] == "1F"), None)
        floors_2f_4f = [b for b in taipower_bills if b["floor_label"] != "1F"]

        if floors_2f_4f:
            merged_amount = sum(_safe_float(b["amount"]) for b in floors_2f_4f)
            merged_kwh = sum(_safe_float(b["kwh"]) for b in floors_2f_4f)
            merged_unit_price = round(merged_amount / merged_kwh, 2) if merged_kwh > 0 else 0
        else:
            merged_amount = merged_kwh = merged_unit_price = 0

        sharing_rooms_usage = sum(_safe_float(room_readings.get(r, 0)) for r in ROOMS.SHARING_ROOMS)
        public_kwh = max(0, merged_kwh - sharing_rooms_usage)
        sharing_rooms_with_reading = [r for r in ROOMS.SHARING_ROOMS if _safe_float(room_readings.get(r, 0)) > 0]
        sharing_count = len(sharing_rooms_with_reading)
        shared_per_room = int(round(public_kwh / sharing_count)) if sharing_count > 0 else 0

        results = []
        if floor_1f and _safe_float(floor_1f["kwh"]) > 0:
            unit_1f = round(_safe_float(floor_1f["amount"]) / _safe_float(floor_1f["kwh"]), 2)
            for room in ROOMS.EXCLUSIVE_ROOMS:
                kwh = _safe_float(room_readings.get(room, 0))
                if kwh <= 0:
                    continue
                results.append({
                    "樓層": "1F",
                    "房號": room,
                    "類型": "獨立房間",
                    "使用度數": round(kwh, 2),
                    "公用分攤": 0,
                    "總度數": round(kwh, 2),
                    "單價": unit_1f,
                    "應繳金額": round(kwh * unit_1f),
                })

        floor_map = {r: "2F" for r in ["2A", "2B"]}
        floor_map.update({r: "3F" for r in ["3A", "3B", "3C", "3D"]})
        floor_map.update({r: "4F" for r in ["4A", "4B", "4C", "4D"]})

        for room in ROOMS.SHARING_ROOMS:
            kwh = _safe_float(room_readings.get(room, 0))
            if kwh <= 0:
                continue
            total_room_kwh = kwh + shared_per_room
            results.append({
                "樓層": floor_map.get(room),
                "房號": room,
                "類型": "分攤房間",
                "使用度數": round(kwh, 2),
                "公用分攤": int(shared_per_room),
                "總度數": round(total_room_kwh, 2),
                "單價": merged_unit_price,
                "應繳金額": round(total_room_kwh * merged_unit_price),
            })

        total_charge = sum(_safe_float(r["應繳金額"]) for r in results)
        total_taipower = sum(_safe_float(b["amount"]) for b in taipower_bills)

        floor_summaries = []
        if floor_1f:
            f1_results = [r for r in results if r["房號"] in ["1A", "1B"]]
            if f1_results:
                floor_summaries.append({
                    "floor": "1F",
                    "bill_amount": _safe_float(floor_1f["amount"]),
                    "bill_kwh": _safe_float(floor_1f["kwh"]),
                    "room_kwh": sum(_safe_float(r["使用度數"]) for r in f1_results),
                    "unit_price": round(_safe_float(floor_1f["amount"]) / _safe_float(floor_1f["kwh"]), 2)
                    if _safe_float(floor_1f["kwh"]) > 0 else 0,
                    "total_charge": sum(_safe_float(r["應繳金額"]) for r in f1_results),
                })

        for bill in floors_2f_4f:
            fl = bill["floor_label"]
            fl_r = [r for r in results if r["房號"] in FLOOR_CONFIG[fl]["rooms"]]
            if fl_r:
                floor_summaries.append({
                    "floor": fl,
                    "bill_amount": _safe_float(bill["amount"]),
                    "bill_kwh": _safe_float(bill["kwh"]),
                    "room_kwh": sum(_safe_float(r["使用度數"]) for r in fl_r),
                    "unit_price": merged_unit_price,
                    "total_charge": sum(_safe_float(r["應繳金額"]) for r in fl_r),
                })

        logger.info("✅ 電費計算完成: %s 間房間", len(results))
        return {
            "total_charge": total_charge,
            "taipower_amount": total_taipower,
            "difference": total_charge - total_taipower,
            "details": results,
            "floor_summaries": floor_summaries,
            "merged_unit_price": merged_unit_price,
            "total_public_kwh": public_kwh,
            "shared_per_room": shared_per_room,
            "merged_kwh": merged_kwh,
            "merged_amount": merged_amount,
        }

    except Exception as e:
        logger.exception("❌ 電費計算失敗")
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
            "年份",
            min_value=2020,
            max_value=2030,
            value=date.today().year,
            key="period_year",
        )
    with col2:
        month_start = st.selectbox(
            "開始月",
            range(1, 13),
            index=date.today().month - 1,
            key="period_start",
        )
    with col3:
        month_end = st.selectbox(
            "結束月",
            range(1, 13),
            index=date.today().month % 12,
            key="period_end",
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
                remind_str = remind_on_create.strftime("%Y-%m-%d") if remind_on_create else None
                ok, msg, period_id = elec_service.add_period(year, month_start, month_end, remind_str)
                if ok:
                    st.success(msg)
                    st.session_state[KEY_CURRENT_PERIOD_ID] = period_id
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
    st.session_state[KEY_CURRENT_PERIOD_ID] = period_id
    period_info = elec_service.get_period_by_id(period_id)

    st.divider()
    section_header("催繳日期設定", "🔔", divider=False)
    current_remind_date = period_info.get("remind_start_date") if period_info else None

    if current_remind_date:
        st.info(f"✅ 目前催繳日期: {current_remind_date}")
    else:
        st.warning("⚠️ 尚未設定催繳日期")

    col_d, col_b = st.columns([3, 1])
    with col_d:
        remind_default = _to_date_safe(current_remind_date) or date.today()
        new_remind_date = st.date_input(
            "設定催繳開始日",
            value=remind_default,
            key="remind_date_input",
        )
    with col_b:
        st.write("")
        st.write("")
        if st.button("💾 儲存日期", type="primary"):
            ok, msg = elec_service.update_period_remind_date(
                period_id,
                new_remind_date.strftime("%Y-%m-%d"),
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
            if st.session_state.get(KEY_CONFIRM_DELETE_PERIOD):
                ok, msg = elec_service.delete_period(period_id)
                if ok:
                    st.success(msg)
                    st.session_state.pop(KEY_CURRENT_PERIOD_ID, None)
                    st.session_state.pop(KEY_CONFIRM_DELETE_PERIOD, None)
                    st.rerun()
                else:
                    st.error(msg)
            else:
                st.session_state[KEY_CONFIRM_DELETE_PERIOD] = True
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
    if KEY_CURRENT_PERIOD_ID not in st.session_state:
        info_card("請先選擇期間", "請前往「計費期間」Tab 選擇一個期間", "⚠️", "warning")
        return

    period_id = st.session_state[KEY_CURRENT_PERIOD_ID]
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

            amount = st.number_input(
                "金額 (元)",
                min_value=0,
                value=0,
                step=100,
                key=f"{floor_key}_amt",
            )
            kwh = st.number_input(
                "度數",
                min_value=0.0,
                value=0.0,
                step=10.0,
                format="%.2f",
                key=f"{floor_key}_kwh",
            )
            floor_data[floor_key] = {"amount": amount, "kwh": kwh}

    if st.button("💾 儲存台電單", type="primary"):
        bills = [
            {"floor_label": k, "amount": v["amount"], "kwh": v["kwh"]}
            for k, v in floor_data.items()
            if _safe_float(v["amount"]) > 0 or _safe_float(v["kwh"]) > 0
        ]
        if not bills:
            st.error("❌ 請至少輸入一個樓層的台電單")
        else:
            _session_set_nested(KEY_TAIPOWER_BILLS, period_id, bills)
            st.success(f"✅ 已儲存 {len(bills)} 個台電單")

    saved_bills = _session_get_nested(KEY_TAIPOWER_BILLS, period_id)
    if saved_bills:
        bill_1f = next((b for b in saved_bills if b["floor_label"] == "1F"), None)
        bills_2f_4f = [b for b in saved_bills if b["floor_label"] != "1F"]

        st.divider()
        st.write("**已儲存摘要:**")

        if bill_1f:
            st.metric("1F (獨立)", f"${_safe_int(bill_1f['amount']):,}", f"{_safe_float(bill_1f['kwh']):.0f} 度")

        if bills_2f_4f:
            merged_amt = sum(_safe_float(b["amount"]) for b in bills_2f_4f)
            merged_kwh = sum(_safe_float(b["kwh"]) for b in bills_2f_4f)
            scols = st.columns(len(bills_2f_4f) + 1)

            for i, b in enumerate(bills_2f_4f):
                with scols[i]:
                    st.metric(b["floor_label"], f"${_safe_int(b['amount']):,}", f"{_safe_float(b['kwh']):.0f} 度")

            with scols[-1]:
                st.metric("2-4F 合計", f"${_safe_int(merged_amt):,}", f"{merged_kwh:.0f} 度")

    st.divider()
    section_header("步驟 2: 輸入房間讀數", "🔢")
    st.caption("💡 🟢 新期間→上期自動帶入並鎖定  🔵 已儲存→可修改  ⚪ 首次→兩欄皆可輸入")

    existing_readings_list = elec_service.get_all_readings(period_id)
    existing_by_room: Dict[str, Dict] = {r["room_number"]: r for r in existing_readings_list}
    room_readings: Dict[str, float] = {}
    raw_readings: Dict[str, Dict] = {}

    for floor_key, config in FLOOR_CONFIG.items():
        st.markdown(f"### {config['label']}")
        cols = st.columns(len(config["rooms"]))

        for col, room in zip(cols, config["rooms"]):
            with col:
                st.markdown(f"**{room}**")

                if room in existing_by_room:
                    saved = existing_by_room[room]
                    previous = _safe_float(saved["previous_reading"])
                    saved_curr = _safe_float(saved["current_reading"])

                    st.number_input(
                        "上期 📊",
                        value=previous,
                        step=1.0,
                        format="%.2f",
                        key=f"prev_{room}",
                        disabled=True,
                    )
                    current = st.number_input(
                        "本期 ✏️",
                        min_value=previous,
                        value=saved_curr,
                        step=1.0,
                        format="%.2f",
                        key=f"curr_{room}",
                    )
                    st.caption("🔵 已儲存，可修改本期")
                else:
                    last_reading = elec_service.get_latest_meter_reading(room, period_id)
                    if last_reading is not None:
                        previous = _safe_float(last_reading)
                        st.number_input(
                            "上期 📊",
                            value=previous,
                            step=1.0,
                            format="%.2f",
                            key=f"prev_{room}",
                            disabled=True,
                        )
                        current = st.number_input(
                            "本期 📈",
                            min_value=previous,
                            value=previous,
                            step=1.0,
                            format="%.2f",
                            key=f"curr_{room}",
                        )
                        st.caption("🟢 上期已自動帶入")
                    else:
                        previous = st.number_input(
                            "上期 📊",
                            min_value=0.0,
                            value=0.0,
                            step=1.0,
                            format="%.2f",
                            key=f"prev_{room}",
                        )
                        current = st.number_input(
                            "本期 📈",
                            min_value=0.0,
                            value=0.0,
                            step=1.0,
                            format="%.2f",
                            key=f"curr_{room}",
                        )
                        st.caption("⚪ 首次輸入")

                usage = current - previous
                if usage > 0:
                    st.success(f"⚡ {usage:.1f} 度")
                elif current > 0:
                    st.info("📊 無變化")
                else:
                    st.caption("　等待輸入")

                room_readings[room] = usage
                raw_readings[room] = {"previous": previous, "current": current}

        st.divider()

    _session_set_nested(KEY_ROOM_READINGS, period_id, room_readings)
    _session_set_nested(KEY_RAW_READINGS, period_id, raw_readings)

    st.divider()
    section_header("步驟 3: 計算電費", "🧮")
    if st.button("🚀 開始計算", type="primary"):
        bills = _session_get_nested(KEY_TAIPOWER_BILLS, period_id)
        readings = _session_get_nested(KEY_ROOM_READINGS, period_id)
        raw = _session_get_nested(KEY_RAW_READINGS, period_id)

        if not bills:
            st.error("❌ 請先輸入台電帳單")
            return
        if not readings or all(_safe_float(v) == 0 for v in readings.values()):
            st.error("❌ 請先輸入房間讀數")
            return

        result = calculate_electricity_charges(bills, readings)
        if not result:
            st.error("❌ 計算失敗")
            return

        enriched_details = []
        save_count = 0

        with st.spinner("💾 正在儲存..."):
            for detail in result["details"]:
                room = detail["房號"]
                detail["previous_reading"] = raw[room]["previous"]
                detail["current_reading"] = raw[room]["current"]
                enriched_details.append(detail)

                ok, save_msg = elec_service.save_reading(
                    period_id=period_id,
                    room=room,
                    previous=raw[room]["previous"],
                    current=raw[room]["current"],
                    kwh_used=detail["使用度數"],
                    unit_price=detail["單價"],
                    public_share_kwh=detail["公用分攤"],
                    amount_due=detail["應繳金額"],
                    room_type=detail["類型"],
                )
                if ok:
                    save_count += 1
                else:
                    logger.warning("[Electricity] save_reading failed room=%s msg=%s", room, save_msg)

        st.session_state[_calc_result_key(period_id)] = result
        st.session_state[_calc_details_key(period_id)] = enriched_details
        st.success(f"✅ 計算完成！已儲存 {save_count} 筆")
        st.rerun()

    result = st.session_state.get(_calc_result_key(period_id))
    enriched_details = st.session_state.get(_calc_details_key(period_id))
    if not (result and enriched_details):
        return

    st.markdown("### 📊 計算摘要")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("2-4F 度數", f"{_safe_float(result['merged_kwh']):.0f} 度")
    c2.metric("總公用電", f"{_safe_float(result['total_public_kwh']):.0f} 度")
    c3.metric("每間分攤", f"{_safe_int(result['shared_per_room'])} 度")
    c4.metric("2-4F 單價", f"${_safe_float(result['merged_unit_price']):.2f}/度")

    st.divider()
    st.markdown("### 📊 各樓層摘要")
    for fs in result["floor_summaries"]:
        with st.expander(
            f"**{fs['floor']}** - 台電: ${_safe_int(fs['bill_amount']):,} | 收費: ${_safe_int(fs['total_charge']):,}",
            expanded=True,
        ):
            col1, col2 = st.columns(2)
            col1.metric("台電度數", f"{_safe_float(fs['bill_kwh']):.0f} 度")
            col2.metric("房間用電", f"{_safe_float(fs['room_kwh']):.0f} 度")

    st.divider()
    st.markdown(
        f"""
### 💰 總計
- **台電總金額**: ${_safe_int(result['taipower_amount']):,} 元
- **收費總金額**: ${_safe_int(result['total_charge']):,} 元
- **差異**: ${_safe_float(result['difference']):+,.0f} 元
"""
    )

    st.divider()
    st.write("**各房間明細**")
    details_df = pd.DataFrame(enriched_details)

    col_order = [
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
        key=KEY_NOTIFY_MODE,
    )

    if notify_mode == "不發送":
        st.info("⚪ 不會發送任何通知")

    elif notify_mode == "手動發送":
        st.warning("⚠️ 需要手動點擊「發送」")
        if st.button("📤 立即發送電費通知", type="primary"):
            with st.spinner("正在發送通知..."):
                success_count = 0
                fail_count = 0
                fail_msgs = []

                for detail in enriched_details:
                    ok, msg = _send_electricity_notification_safe(
                        notify_service=notify_service,
                        detail=detail,
                        period_id=period_id,
                    )
                    if ok:
                        success_count += 1
                    else:
                        fail_count += 1
                        fail_msgs.append(msg)

                if success_count:
                    st.success(f"✅ 成功發送 {success_count} 則")
                if fail_count:
                    st.error(f"❌ 失敗 {fail_count} 則")
                    with st.expander("查看失敗明細", expanded=False):
                        for m in fail_msgs:
                            st.write(f"- {m}")

    elif notify_mode == "自動發送":
        period_info = elec_service.get_period_by_id(period_id)
        remind_date_raw = period_info.get("remind_start_date") if period_info else None

        if not remind_date_raw:
            st.error("❌ 請先設定催繳日期")
        else:
            remind_date_obj = _to_date_safe(remind_date_raw)
            if remind_date_obj:
                days_left = (remind_date_obj - date.today()).days
                if days_left <= 0:
                    st.success(f"✅ 催繳日期已到（{remind_date_obj}）")
                else:
                    st.info(f"⏳ 催繳日期: {remind_date_obj}（還有 {days_left} 天）")
            else:
                st.warning("⚠️ 催繳日期格式無法解析，請重新設定")

    st.divider()
    csv = details_df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button("📥 下載 CSV 備份", csv, f"electricity_{period_id}.csv", "text/csv")


# ============================================================
# Tab 3: 繳費記錄
# ============================================================
def render_records_tab(elec_service: ElectricityService):
    section_header("繳費記錄", "📜")

    if KEY_CURRENT_PERIOD_ID not in st.session_state:
        info_card("請先選擇期間", "請前往「計費期間」Tab 選擇一個期間", "⚠️", "warning")
        return

    period_id = st.session_state[KEY_CURRENT_PERIOD_ID]
    st.info(f"📅 當前查詢期間 ID: {period_id}")

    with st.spinner("正在查詢..."):
        df = elec_service.get_payment_record(period_id)

    if df is None or df.empty:
        empty_state("尚無記錄", "📭", "請先在「計算電費」Tab 完成計算")
        return

    col_toggle, col_hint = st.columns([2, 5])
    with col_toggle:
        hide_1f = st.toggle(
            "🙈 隱藏 1F (1A/1B)",
            value=False,
            key="hide_1f_toggle",
            help="開啟後表格與 CSV 均不含 1A / 1B",
        )
    with col_hint:
        if hide_1f:
            st.warning("⚠️ 目前已隱藏 1F，下方數據與 CSV 均不含 1F")
        else:
            st.caption("💡 開啟左側開關可隱藏 1F 房間")

    display_df = df.copy()
    if hide_1f:
        room_col = _get_room_col(display_df)
        display_df = display_df[~display_df[room_col].isin(_1F_ROOMS)].reset_index(drop=True)

    total_rows = len(display_df)
    st.success(f"✅ 顯示 {total_rows} 筆電費記錄" + (" (已隱藏 1F)" if hide_1f else ""))

    due_col = _get_amount_col(display_df)
    paid_col = _get_paid_col(display_df)
    total_due = int(display_df[due_col].sum()) if due_col in display_df.columns else 0
    total_paid = int(display_df[paid_col].sum()) if paid_col in display_df.columns else 0
    total_balance = total_due - total_paid

    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("應收總額", f"${total_due:,}", "", "💰", "normal")
    with c2:
        metric_card("已收金額", f"${total_paid:,}", "", "✅", "success")
    with c3:
        metric_card("未收金額", f"${total_balance:,}", "", "⚠️", "warning")

    st.divider()
    st.write(f"**共 {total_rows} 筆記錄**" + (" ── 已隱藏 1F" if hide_1f else ""))
    data_table(display_df, key="payment_records")

    st.divider()
    csv_suffix = "_no1F" if hide_1f else ""
    csv_filename = f"payment_records_{period_id}{csv_suffix}.csv"
    csv_bytes = display_df.to_csv(index=False, encoding="utf-8-sig")

    dl_col, hint_col = st.columns([2, 5])
    with dl_col:
        st.download_button(
            label=f"📥 下載繳費記錄 CSV{'(不含1F)' if hide_1f else ''}",
            data=csv_bytes,
            file_name=csv_filename,
            mime="text/csv",
        )
    with hint_col:
        st.caption(f"📄 檔名: {csv_filename}")


# ============================================================
# Tab 4: 用電統計
# ============================================================
def render_statistics_tab(elec_service: ElectricityService):
    section_header("用電量統計", "📊")
    st.caption("💡 自動從所有已計算期間彙整，可查看全年用電趨勢")

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

        label = _normalize_period_label(p)
        kwh_col = _get_kwh_col(df)
        amt_col = _get_amount_col(df)
        room_col = _get_room_col(df)

        stats_rows.append({
            "期間": label,
            "年份": p["period_year"],
            "開始月": p["period_month_start"],
            "總度數": round(float(df[kwh_col].sum()), 1),
            "總金額": int(df[amt_col].sum()),
            "期間ID": p["id"],
        })

        for _, row in df.iterrows():
            room_trend_rows.append({
                "期間": label,
                "年份": p["period_year"],
                "房號": row.get(room_col, ""),
                "度數": round(float(row.get(kwh_col, 0)), 1),
                "金額": int(row.get(amt_col, 0)),
            })

    if not stats_rows:
        empty_state("尚無計算資料", "📭", "請先在「計算電費」Tab 完成計算")
        return

    stats_df = pd.DataFrame(stats_rows)
    room_trend_df = pd.DataFrame(room_trend_rows)

    available_years = sorted(stats_df["年份"].unique(), reverse=True)
    year_options = ["全部"] + [str(y) for y in available_years]

    col_yr, col_hint = st.columns([2, 5])
    with col_yr:
        selected_year = st.selectbox("📆 年度篩選", year_options, key="stat_year_filter")
    with col_hint:
        st.caption("選擇年度即可篩選該年度所有期間")

    if selected_year == "全部":
        filtered = stats_df.copy()
    else:
        filtered = stats_df[stats_df["年份"] == int(selected_year)].copy()

    if filtered.empty:
        st.warning("⚠️ 該年度尚無數據")
        return

    total_periods = len(filtered)
    total_kwh = filtered["總度數"].sum()
    total_amt = filtered["總金額"].sum()
    avg_kwh = total_kwh / total_periods if total_periods else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("累計期數", f"{total_periods} 期", "", "📅", "normal")
    with c2:
        metric_card("總用電量", f"{total_kwh:,.0f} 度", "", "⚡", "normal")
    with c3:
        metric_card("總收費金額", f"${total_amt:,}", "", "💰", "success")
    with c4:
        metric_card("平均每期", f"{avg_kwh:,.0f} 度", "", "📊", "normal")

    st.divider()
    section_header("用電度數與帳單金額趨勢", "📈", divider=False)

    if HAS_PLOTLY:
        periods_list = filtered["期間"].tolist()
        usages = filtered["總度數"].tolist()
        amounts = filtered["總金額"].tolist()

        fig = go.Figure()

        fig.add_trace(go.Bar(
            x=periods_list,
            y=usages,
            name="用電度數（度）",
            yaxis="y2",
            marker=dict(
                color=_COLOR_BAR,
                line=dict(color="#F9A825", width=1),
                cornerradius=4,
            ),
            opacity=0.85,
            hovertemplate="<b>%{x}</b><br>用電度數：<b>%{y:,.0f} 度</b><extra></extra>",
        ))

        fig.add_trace(go.Scatter(
            x=periods_list,
            y=amounts,
            name="帳單金額（元）",
            yaxis="y",
            mode="lines+markers",
            line=dict(color=_COLOR_LINE, width=2.5),
            marker=dict(
                color=_COLOR_LINE,
                size=9,
                line=dict(color="white", width=2),
            ),
            hovertemplate="<b>%{x}</b><br>帳單金額：<b>$%{y:,}</b><extra></extra>",
        ))

        if usages:
            fig.add_annotation(
                x=periods_list[-1],
                y=usages[-1],
                yref="y2",
                text=f"<b>{usages[-1]:,.0f}度</b>",
                showarrow=False,
                bgcolor=_COLOR_LATEST,
                font=dict(color="white", size=13),
                borderpad=6,
                xanchor="center",
                yanchor="bottom",
                yshift=12,
            )

        fig.update_layout(
            height=420,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            hovermode="x unified",
            legend=dict(
                orientation="h",
                x=0.5,
                xanchor="center",
                y=1.06,
                yanchor="bottom",
                font=dict(size=13),
            ),
            margin=dict(l=60, r=60, t=50, b=50),
            xaxis=dict(
                title="期間",
                type="category",
                tickangle=-30,
                gridcolor="rgba(200,200,200,0.3)",
            ),
            yaxis=dict(
                title="帳單金額（元）",
                gridcolor="rgba(200,200,200,0.3)",
                zeroline=False,
                tickformat=",",
            ),
            yaxis2=dict(
                title="用電度數（度）",
                overlaying="y",
                side="right",
                gridcolor="rgba(0,0,0,0)",
                zeroline=False,
                tickformat=",",
            ),
            bargap=0.35,
        )
        st.plotly_chart(fig, width="stretch")

    else:
        col_b, col_l = st.columns(2)
        with col_b:
            st.write("**用電度數**")
            st.bar_chart(filtered.set_index("期間")["總度數"])
        with col_l:
            st.write("**帳單金額**")
            st.line_chart(filtered.set_index("期間")["總金額"])
        st.warning("⚠️ 安裝 plotly 可獲得仿台電 App 雙軸圖：`pip install plotly`")

    st.divider()
    section_header("期間明細表", "📝", divider=False)

    display_stats = filtered[["期間", "總度數", "總金額"]].copy()
    display_stats["總金額"] = display_stats["總金額"].apply(lambda x: f"${x:,}")
    data_table(display_stats, key="stats_summary_table")

    st.divider()
    with st.expander("🏠 展開各房間用電趨勢", expanded=False):
        if room_trend_df.empty:
            st.info("尚無房間級資料")
            return

        if selected_year == "全部":
            rt = room_trend_df.copy()
        else:
            rt = room_trend_df[room_trend_df["年份"] == int(selected_year)].copy()

        if HAS_PLOTLY:
            rooms = sorted(rt["房號"].unique().tolist())
            periods_order = filtered["期間"].tolist()

            fig2 = go.Figure()
            for i, room in enumerate(rooms):
                rdf = rt[rt["房號"] == room].sort_values("期間")
                fig2.add_trace(go.Bar(
                    name=str(room),
                    x=rdf["期間"].tolist(),
                    y=rdf["度數"].tolist(),
                    marker_color=_ROOM_COLORS[i % len(_ROOM_COLORS)],
                    opacity=0.88,
                    hovertemplate=(
                        f"<b>{room}</b><br>"
                        "期間：%{x}<br>"
                        "用電：<b>%{y:,.0f} 度</b><extra></extra>"
                    ),
                ))

            fig2.update_layout(
                height=380,
                barmode="group",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                hovermode="x unified",
                legend=dict(
                    orientation="h",
                    x=0.5,
                    xanchor="center",
                    y=-0.22,
                    yanchor="top",
                    font=dict(size=11),
                ),
                margin=dict(l=50, r=20, t=20, b=60),
                xaxis=dict(
                    title="期間",
                    type="category",
                    tickangle=-30,
                    categoryorder="array",
                    categoryarray=periods_order,
                    gridcolor="rgba(200,200,200,0.3)",
                ),
                yaxis=dict(
                    title="用電度數（度）",
                    gridcolor="rgba(200,200,200,0.3)",
                    zeroline=False,
                ),
                bargap=0.15,
                bargroupgap=0.05,
            )
            st.plotly_chart(fig2, width="stretch")

        else:
            pivot = rt.pivot_table(
                index="期間",
                columns="房號",
                values="度數",
                aggfunc="sum",
            ).fillna(0).reindex(filtered["期間"].tolist())
            st.bar_chart(pivot)

        st.write("**各房間度數明細**")
        pivot2 = rt.pivot_table(
            index="期間",
            columns="房號",
            values="度數",
            aggfunc="sum",
        ).fillna(0).reindex(filtered["期間"].tolist()).reset_index()
        data_table(pivot2, key="room_trend_table")


# ============================================================
# Tab 5: 電費預收帳
# ============================================================
def render_deposit_tab(elec_service: ElectricityService):
    section_header("電費預收帳", "💰")
    st.caption("💡 管理各房間的預收電費、扣款、餘額與流水帳")

    room_options = _get_room_options()

    st.markdown("### 🏠 全房間餘額總覽")
    summary_df = elec_service.get_all_rooms_deposit_summary()

    if summary_df is None or summary_df.empty:
        empty_state("尚無預收資料", "📭", "請先新增一筆預收電費")
    else:
        display_summary = summary_df.copy()

        for col in ["預收總額", "扣除總額", "當前餘款"]:
            if col in display_summary.columns:
                display_summary[col] = display_summary[col].apply(_safe_int)

        def _flag_balance(v):
            if v < 0:
                return "🔴 不足"
            if v <= 500:
                return "🟠 偏低"
            return "🟢 正常"

        display_summary["狀態"] = display_summary["當前餘款"].apply(_flag_balance)

        c1, c2, c3 = st.columns(3)
        with c1:
            metric_card("預收總額", f"${display_summary['預收總額'].sum():,}", "", "💵", "normal")
        with c2:
            metric_card("累計扣除", f"${display_summary['扣除總額'].sum():,}", "", "⚡", "warning")
        with c3:
            metric_card("總餘款", f"${display_summary['當前餘款'].sum():,}", "", "🏦", "success")

        display_summary = display_summary[
            ["狀態", "房號", "租客", "預收總額", "扣除總額", "當前餘款", "最近一筆"]
        ].sort_values(by=["當前餘款", "房號"], ascending=[True, True]).reset_index(drop=True)

        data_table(display_summary, key="deposit_summary_table")

    st.divider()

    section_header("房間流水帳", "📒", divider=False)

    selected_room = st.selectbox(
        "選擇房號",
        options=room_options,
        index=room_options.index("2A") if "2A" in room_options else 0,
        key="deposit_selected_room",
    )

    current_balance = elec_service.get_deposit_balance(selected_room)

    c1, c2 = st.columns([1, 3])
    with c1:
        metric_card("目前餘款", f"${_safe_int(current_balance):,}", "", "💰", "normal")
    with c2:
        if current_balance < 0:
            st.error("⚠️ 目前餘款為負，代表已先扣後補")
        elif current_balance <= 500:
            st.warning("⚠️ 餘款偏低，建議補收預付款")
        else:
            st.success("✅ 餘款充足")

    ledger_df = elec_service.get_deposit_ledger(selected_room)

    if ledger_df is None or ledger_df.empty:
        st.info(f"{selected_room} 目前尚無流水帳")
    else:
        ledger_display = ledger_df.copy()

        if "period_id" in ledger_display.columns:
            ledger_display = ledger_display.rename(columns={"period_id": "期間ID"})

        for col in ["預收電費", "扣電費", "餘款"]:
            if col in ledger_display.columns:
                ledger_display[col] = ledger_display[col].apply(_format_amount_cell)

        ordered_cols = ["id", "日期", "類型", "說明", "預收電費", "扣電費", "餘款", "期間ID"]
        ordered_cols = [c for c in ordered_cols if c in ledger_display.columns]
        ledger_display = ledger_display[ordered_cols]

        data_table(ledger_display, key="deposit_ledger_table")

        st.divider()
        st.markdown("### 🗑️ 刪除錯誤記錄")

        delete_options = {
            f"ID {int(row['id'])} | {row['日期']} | {row['類型']} | {row['說明'] or '-'}": int(row["id"])
            for _, row in ledger_df.iterrows()
        }

        col_sel, col_del = st.columns([4, 1])
        with col_sel:
            selected_delete_label = st.selectbox(
                "選擇要刪除的流水記錄",
                options=list(delete_options.keys()),
                key="deposit_delete_select",
            )
        with col_del:
            st.write("")
            st.write("")
            if st.button("刪除記錄", type="secondary", key="deposit_delete_btn"):
                entry_id = delete_options[selected_delete_label]
                ok, msg = elec_service.delete_deposit_entry(entry_id)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    st.divider()

    form_tab1, form_tab2 = st.tabs(["➕ 新增預收", "⚡ 扣電費"])

    with form_tab1:
        with st.form("add_deposit_form", clear_on_submit=True):
            st.markdown("### ➕ 新增預收電費")

            d1, d2, d3 = st.columns(3)
            with d1:
                deposit_room = st.selectbox("房號", room_options, key="deposit_form_room")
            with d2:
                deposit_date = st.date_input("日期", value=date.today(), key="deposit_form_date")
            with d3:
                deposit_amount = st.number_input(
                    "預收金額",
                    min_value=0,
                    value=1000,
                    step=500,
                    key="deposit_form_amount",
                )

            deposit_desc = st.text_input(
                "說明",
                value="預收電費",
                key="deposit_form_desc",
                placeholder="例如：3B 先收 3-4 月電費預付款",
            )

            submitted = st.form_submit_button("💾 新增預收", type="primary")
            if submitted:
                ok, msg, _ = elec_service.add_deposit(
                    room_number=deposit_room,
                    date_str=deposit_date.strftime("%Y-%m-%d"),
                    amount=float(deposit_amount),
                    description=deposit_desc.strip(),
                )
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    with form_tab2:
        periods = elec_service.get_all_periods()
        period_options = {"不關聯期間": None}
        for p in periods:
            label = f"{p['period_year']}/{p['period_month_start']:02d}-{p['period_month_end']:02d} (ID:{p['id']})"
            period_options[label] = p["id"]

        default_period = st.session_state.get(KEY_CURRENT_PERIOD_ID)
        default_index = _get_selected_period_default_index(period_options, default_period)

        with st.form("deduct_deposit_form", clear_on_submit=True):
            st.markdown("### ⚡ 從預收帳扣電費")

            x1, x2, x3 = st.columns(3)
            with x1:
                deduct_room = st.selectbox("房號", room_options, key="deduct_form_room")
            with x2:
                deduct_date = st.date_input("日期", value=date.today(), key="deduct_form_date")
            with x3:
                deduct_amount = st.number_input(
                    "扣款金額",
                    min_value=0,
                    value=0,
                    step=100,
                    key="deduct_form_amount",
                )

            y1, y2 = st.columns([3, 2])
            with y1:
                deduct_desc = st.text_input(
                    "說明",
                    value="電費扣款",
                    key="deduct_form_desc",
                    placeholder="例如：5-6 月電費",
                )
            with y2:
                selected_period_label = st.selectbox(
                    "關聯期間",
                    options=list(period_options.keys()),
                    index=default_index,
                    key="deduct_form_period",
                )

            selected_period_id = period_options[selected_period_label]
            submitted = st.form_submit_button("💸 執行扣款", type="primary")

            if submitted:
                ok, msg, _ = elec_service.deduct_electricity(
                    room_number=deduct_room,
                    date_str=deduct_date.strftime("%Y-%m-%d"),
                    amount=float(deduct_amount),
                    description=deduct_desc.strip(),
                    period_id=selected_period_id,
                )
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)


# ============================================================
# 主渲染
# ============================================================
def render():
    st.title("⚡ 電費管理")

    elec_service = ElectricityService()
    notify_service = NotificationService()

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📅 計費期間",
        "🧮 計算電費",
        "📜 繳費記錄",
        "📊 用電統計",
        "💰 電費預收帳",
    ])

    with tab1:
        render_period_tab(elec_service)
    with tab2:
        render_calculation_tab(elec_service, notify_service)
    with tab3:
        render_records_tab(elec_service)
    with tab4:
        render_statistics_tab(elec_service)
    with tab5:
        render_deposit_tab(elec_service)


def show():
    render()


if __name__ == "__main__":
    show()
