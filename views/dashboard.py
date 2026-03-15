"""
儀表板 - 重構版 v3.5 (Dashboard CTA)
特性:
- ✅ 使用 Service 架構
- ✅ 修復 DataFrame 布林判斷錯誤
- ✅ 錯誤邊界處理
- ✅ 效能優化 (快取)
- ✅ 動態房間數
- ✅ 統一日期處理
- ✅ 完全適配 Supabase 欄位結構
- ✅ [FIX] rent_amount → rent, move_out_date → lease_end
- ✅ [FIX v3.3] use_container_width → width="stretch"
- ✅ [NEW v3.4] 房間卡片顯示 payment_cycle badge
- ✅ [FIX v3.4b] 修復 Python 3.13 巢狀 f-string SyntaxError
- ✅ [NEW v3.5] Dashboard KPI 加入行動 CTA 與跨頁導流
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional
import logging

from components.cards import (
    section_header, metric_card, room_status_card,
    empty_state, info_card, status_badge
)
from config.constants import ROOMS, UI

from services.electricity_service import ElectricityService
from services.tenant_service import TenantService
from services.payment_service import PaymentService
from services.base_db import BaseDBService
from services.system_service import SystemService
from utils.navigation_state import (
    DASHBOARD_FOCUS_SECTION_STATE,
    ELECTRICITY_DEFAULT_TAB_STATE,
    ELECTRICITY_TAB_CALCULATION,
    ELECTRICITY_TABS_KEY,
    MENU_DASHBOARD,
        MENU_ELECTRICITY,
        MENU_RENT,
        CURRENT_PERIOD_ID_STATE,
        RENT_DEFAULT_STATUS_FILTER_STATE,
    RENT_DEFAULT_TAB_STATE,
    RENT_ROOM_FILTER_KEY,
    RENT_STATUS_FILTER_KEY,
    RENT_STATUS_OVERDUE,
    RENT_STATUS_UNPAID,
    RENT_TAB_MANAGEMENT,
    RENT_TABS_KEY,
    apply_navigation_state,
    get_pending_electricity_period_summary,
    pop_string_state,
)

logger = logging.getLogger(__name__)


class DashboardService(BaseDBService):
    """儀表板專用 Service"""

    def get_memos(self, include_completed: bool = False) -> List[Dict]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                if include_completed:
                    cursor.execute("""
                        SELECT id, memo_text, priority, is_completed, created_at
                        FROM memos
                        ORDER BY
                            CASE priority
                                WHEN 'urgent' THEN 1
                                WHEN 'high' THEN 2
                                ELSE 3
                            END,
                            created_at DESC
                    """)
                else:
                    cursor.execute("""
                        SELECT id, memo_text, priority, is_completed, created_at
                        FROM memos
                        WHERE is_completed = false
                        ORDER BY
                            CASE priority
                                WHEN 'urgent' THEN 1
                                WHEN 'high' THEN 2
                                ELSE 3
                            END,
                            created_at DESC
                    """)
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            st.error(f"❌ 查詢備忘錄失敗: {str(e)}")
            logger.error(f"查詢備忘錄失敗: {str(e)}", exc_info=True)
            return []

    def add_memo(self, memo_text: str, priority: str = 'normal') -> bool:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO memos (memo_text, priority)
                    VALUES (%s, %s)
                """, (memo_text, priority))
                conn.commit()
                return True
        except Exception as e:
            st.error(f"❌ 新增備忘錄失敗: {str(e)}")
            logger.error(f"新增備忘錄失敗: {str(e)}", exc_info=True)
            return False

    def complete_memo(self, memo_id: int) -> bool:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE memos
                    SET is_completed = true, completed_at = NOW()
                    WHERE id = %s
                """, (memo_id,))
                conn.commit()
                return True
        except Exception as e:
            st.error(f"❌ 完成備忘錄失敗: {str(e)}")
            logger.error(f"完成備忘錄失敗: {str(e)}", exc_info=True)
            return False


def safe_parse_date(date_value) -> Optional[date]:
    if date_value is None:
        return None
    if isinstance(date_value, date):
        return date_value
    if isinstance(date_value, datetime):
        return date_value.date()
    try:
        return datetime.strptime(str(date_value), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def safe_to_dataframe(data) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        return data if not data.empty else pd.DataFrame()
    elif isinstance(data, list):
        return pd.DataFrame(data) if data else pd.DataFrame()
    elif isinstance(data, dict):
        return pd.DataFrame([data]) if data else pd.DataFrame()
    else:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def calculate_metrics(df_tenants: pd.DataFrame, df_overdue: pd.DataFrame) -> Dict:
    total_rooms = len(ROOMS.ALL_ROOMS)
    occupied = len(df_tenants) if isinstance(df_tenants, pd.DataFrame) and not df_tenants.empty else 0
    vacant = total_rooms - occupied
    occupancy_rate = round((occupied / total_rooms) * 100, 1) if total_rooms > 0 else 0

    if isinstance(df_overdue, pd.DataFrame) and not df_overdue.empty and 'amount' in df_overdue.columns:
        overdue_amount = df_overdue['amount'].sum()
        overdue_count = len(df_overdue)
    else:
        overdue_amount = 0
        overdue_count = 0

    return {
        'total_rooms':    total_rooms,
        'occupied':       occupied,
        'vacant':         vacant,
        'occupancy_rate': occupancy_rate,
        'overdue_amount': int(overdue_amount),
        'overdue_count':  overdue_count
    }


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _has_electricity_records(
    elec_service: ElectricityService,
    period_id: int,
) -> bool:
    records = elec_service.get_payment_record(period_id)
    return records is not None and not records.empty


def _build_action_context(
    unpaid_payments: List[Dict],
    overdue_payments: List[Dict],
    pending_electricity: Dict[str, Optional[int]],
    memos: List[Dict],
    settings: Dict[str, str],
) -> Dict[str, int | Optional[int]]:
    return {
        "unpaid_count": len(unpaid_payments),
        "overdue_count": len(overdue_payments),
        "overdue_days": _safe_int(settings.get("overdue_days"), 7),
        "pending_electricity_count": _safe_int(pending_electricity.get("pending_count"), 0),
        "pending_period_id": pending_electricity.get("default_period_id"),
        "memo_count": len(memos),
    }


def _navigate_to_rent(status_filter: str) -> None:
    apply_navigation_state(
        MENU_RENT,
        clear_keys=[RENT_TABS_KEY, RENT_STATUS_FILTER_KEY, RENT_ROOM_FILTER_KEY],
        **{
            RENT_DEFAULT_TAB_STATE: RENT_TAB_MANAGEMENT,
            RENT_DEFAULT_STATUS_FILTER_STATE: status_filter,
        },
    )
    st.rerun()


def _navigate_to_electricity(default_period_id: Optional[int]) -> None:
    apply_navigation_state(
        MENU_ELECTRICITY,
        clear_keys=[ELECTRICITY_TABS_KEY],
        **{
            ELECTRICITY_DEFAULT_TAB_STATE: ELECTRICITY_TAB_CALCULATION,
            CURRENT_PERIOD_ID_STATE: default_period_id,
        },
    )
    st.rerun()


def _focus_memos() -> None:
    apply_navigation_state(
        MENU_DASHBOARD,
        **{DASHBOARD_FOCUS_SECTION_STATE: "memos"},
    )
    st.rerun()


def get_expiring_leases(df_tenants: pd.DataFrame, days: int = 45) -> List[Dict]:
    if not isinstance(df_tenants, pd.DataFrame) or df_tenants.empty:
        return []
    expiring = []
    today = date.today()
    warning_date = today + timedelta(days=days)
    for _, tenant in df_tenants.iterrows():
        lease_end = safe_parse_date(tenant.get('lease_end'))
        if lease_end and today <= lease_end <= warning_date:
            days_left = (lease_end - today).days
            expiring.append({
                'room':      tenant['room_number'],
                'tenant':    tenant['name'],
                'lease_end': lease_end,
                'days_left': days_left
            })
    return sorted(expiring, key=lambda x: x['days_left'])


def render_kpi_section(metrics: Dict):
    section_header("📊 關鍵指標", divider=True)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        metric_card("佔用率", f"{metrics['occupancy_rate']}%",
                    f"{metrics['occupied']}/{metrics['total_rooms']} 房", "🏠",
                    "success" if metrics['occupancy_rate'] >= 80 else "warning")
    with col2:
        metric_card("空房數", str(metrics['vacant']), "可出租", "🔓",
                    "normal" if metrics['vacant'] > 0 else "success")
    with col3:
        color = "error" if metrics['overdue_count'] > 0 else "success"
        metric_card("逾期未繳", str(metrics['overdue_count']),
                    f"金額: ${metrics['overdue_amount']:,}", "⚠️", color)
    with col4:
        metric_card("總房間數", str(metrics['total_rooms']), "管理中", "🏢", "normal")


def _render_action_card(
    title: str,
    value: str,
    delta: str,
    icon: str,
    color: str,
    button_label: str,
    button_key: str,
    callback,
):
    metric_card(title, value, delta, icon, color)
    if st.button(button_label, key=button_key, type="primary", width="stretch"):
        callback()


def render_action_cta_section(action_context: Dict[str, int | Optional[int]]):
    section_header("🎯 快速行動", divider=True)

    overdue_days = _safe_int(action_context.get("overdue_days"), 7)
    pending_period_id = action_context.get("pending_period_id")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        _render_action_card(
            title="未繳租金筆數",
            value=str(_safe_int(action_context.get("unpaid_count"))),
            delta=f"逾期 {_safe_int(action_context.get('overdue_count'))} 筆",
            icon="💰",
            color="warning",
            button_label="立即催繳",
            button_key="cta_unpaid_rent",
            callback=lambda: _navigate_to_rent(RENT_STATUS_UNPAID),
        )
    with col2:
        _render_action_card(
            title=f"逾期超過 {overdue_days} 天",
            value=str(_safe_int(action_context.get("overdue_count"))),
            delta="快速查看逾期清單",
            icon="🚨",
            color="error",
            button_label="查看清單",
            button_key="cta_overdue_rent",
            callback=lambda: _navigate_to_rent(RENT_STATUS_OVERDUE),
        )
    with col3:
        _render_action_card(
            title="待計算電費",
            value=str(_safe_int(action_context.get("pending_electricity_count"))),
            delta="導向最新未完成期間",
            icon="⚡",
            color="warning",
            button_label="前往計算",
            button_key="cta_electricity_calc",
            callback=lambda: _navigate_to_electricity(
                pending_period_id if isinstance(pending_period_id, int) else None
            ),
        )
    with col4:
        _render_action_card(
            title="待確認備忘錄",
            value=str(_safe_int(action_context.get("memo_count"))),
            delta="可直接新增或完成",
            icon="📝",
            color="normal",
            button_label="查看備忘",
            button_key="cta_memos",
            callback=_focus_memos,
        )


def render_lease_alerts(expiring_leases: List[Dict]):
    """渲染租約警示。注意: 不能在 f-string 裡再嵌 f-string，Python 3.13 不允許。"""
    section_header("⏰ 租約到期警示", divider=True)

    if not expiring_leases:
        info_card("✅ 無即將到期租約", "45 天內沒有租約到期，一切正常！", "✅", "success")
        return

    urgent  = [l for l in expiring_leases if l['days_left'] <= 14]
    warning = [l for l in expiring_leases if 14 < l['days_left'] <= 30]
    notice  = [l for l in expiring_leases if l['days_left'] > 30]

    if urgent:
        st.error(f"🚨 緊急: {len(urgent)} 個租約 14 天內到期")
        for lease in urgent:
            days_text = str(lease['days_left']) + " 天"
            badge_html = status_badge(days_text, 'error')
            st.markdown(
                f"**{lease['room']}** - {lease['tenant']} | "
                f"到期日: {lease['lease_end']} | {badge_html}",
                unsafe_allow_html=True
            )

    if warning:
        st.warning(f"⚠️ 注意: {len(warning)} 個租約 30 天內到期")
        for lease in warning:
            days_text = str(lease['days_left']) + " 天"
            badge_html = status_badge(days_text, 'warning')
            st.markdown(
                f"**{lease['room']}** - {lease['tenant']} | "
                f"到期日: {lease['lease_end']} | {badge_html}",
                unsafe_allow_html=True
            )

    if notice:
        st.info(f"ℹ️ 提醒: {len(notice)} 個租約 45 天內到期")
        with st.expander("查看詳情"):
            for lease in notice:
                days_text = str(lease['days_left']) + " 天"
                badge_html = status_badge(days_text, 'info')
                st.markdown(
                    f"**{lease['room']}** - {lease['tenant']} | "
                    f"到期日: {lease['lease_end']} | {badge_html}",
                    unsafe_allow_html=True
                )


def render_room_status(df_tenants: pd.DataFrame):
    """渲染房間狀態 - 加入 payment_cycle badge"""
    section_header("🏠 房間狀態一覽", divider=True)

    room_status = {}
    today = date.today()
    warning_date = today + timedelta(days=45)

    if isinstance(df_tenants, pd.DataFrame) and not df_tenants.empty:
        for _, tenant in df_tenants.iterrows():
            room = tenant['room_number']
            lease_end = safe_parse_date(tenant.get('lease_end'))
            status = 'warning' if (lease_end and lease_end <= warning_date) else 'occupied'
            room_status[room] = {
                'tenant':        tenant['name'],
                'status':        status,
                'rent':          tenant.get('rent', 0),
                'payment_cycle': tenant.get('payment_cycle') or '月繳',
            }

    rows = [ROOMS.ALL_ROOMS[i:i+3] for i in range(0, len(ROOMS.ALL_ROOMS), 3)]
    for row_rooms in rows:
        cols = st.columns(3)
        for col, room in zip(cols, row_rooms):
            with col:
                room_info = room_status.get(room)
                if room_info:
                    room_status_card(
                        room,
                        room_info['tenant'],
                        room_info['status'],
                        room_info['rent'],
                        room_info['payment_cycle'],
                    )
                else:
                    room_status_card(room, None, 'vacant')


def render_memo_section(
    dashboard_service: DashboardService,
    memos: Optional[List[Dict]] = None,
    highlight: bool = False,
):
    section_header("📝 待辦事項", divider=True)
    if highlight:
        info_card(
            "已聚焦待確認備忘錄",
            "這裡顯示目前尚未完成的備忘事項，可直接新增或標記完成。",
            "🎯",
            "info",
        )

    if memos is None:
        memos = dashboard_service.get_memos(include_completed=False)

    col1, col2 = st.columns([3, 1])
    with col1:
        new_memo = st.text_input(
            "新增待辦",
            placeholder="例如: 清洗冷氣 4A、檢查熱水器...",
            key="new_memo_input"
        )
    with col2:
        priority = st.selectbox(
            "優先級",
            ["normal", "high", "urgent"],
            format_func=lambda x: {"normal": "普通", "high": "重要", "urgent": "緊急"}[x],
            key="memo_priority"
        )

    if st.button("➕ 新增", key="add_memo_btn", width="stretch"):
        if new_memo.strip():
            if dashboard_service.add_memo(new_memo, priority):
                st.success("✅ 已新增待辦事項")
                st.rerun()
            else:
                st.error("❌ 新增失敗")
        else:
            st.warning("⚠️ 請輸入待辦內容")

    st.divider()

    if not memos:
        empty_state("目前沒有待辦事項", "✨", "一切都處理完畢了！")
    else:
        for memo in memos:
            col1, col2, col3 = st.columns([1, 6, 1])
            with col1:
                priority_emoji = {'urgent': '🔴', 'high': '🟡', 'normal': '⚪'}
                st.write(priority_emoji.get(memo['priority'], '⚪'))
            with col2:
                st.write(memo['memo_text'])
                st.caption(f"建立於: {memo['created_at']}")
            with col3:
                if st.button("✅", key=f"complete_{memo['id']}"):
                    if dashboard_service.complete_memo(memo['id']):
                        st.success("✅ 已完成")
                        st.rerun()


def render():
    st.title(f"{UI.PAGE_ICON} 儀表板")

    tenant_service    = TenantService()
    payment_service   = PaymentService()
    dashboard_service = DashboardService()
    electricity_service = ElectricityService()
    system_service = SystemService()

    with st.spinner("載入資料中..."):
        try:
            tenants    = tenant_service.get_all_tenants()
            overdue    = payment_service.get_overdue_payments()
            unpaid     = payment_service.get_unpaid_payments()
            memos      = dashboard_service.get_memos(include_completed=False)
            settings   = system_service.get_all_settings()
            periods    = electricity_service.get_all_periods()
            pending_electricity = get_pending_electricity_period_summary(
                periods,
                lambda period_id: _has_electricity_records(electricity_service, period_id),
            )
            df_tenants = safe_to_dataframe(tenants)
            df_overdue = safe_to_dataframe(overdue)
            logger.info(
                f"✅ 資料載入成功: 房客 {len(df_tenants)}，逾期 {len(df_overdue)}，"
                f"未繳 {len(unpaid)}，備忘 {len(memos)}"
            )
        except Exception as e:
            st.error(f"❌ 資料載入失敗: {str(e)}")
            logger.error(f"資料載入失敗: {str(e)}", exc_info=True)
            return

    try:
        metrics = calculate_metrics(df_tenants, df_overdue)
    except Exception as e:
        st.error(f"❌ 指標計算失敗: {str(e)}")
        logger.error(f"指標計算失敗: {str(e)}", exc_info=True)
        return

    action_context = _build_action_context(
        unpaid_payments=unpaid,
        overdue_payments=overdue,
        pending_electricity=pending_electricity,
        memos=memos,
        settings=settings,
    )
    focus_section = pop_string_state(DASHBOARD_FOCUS_SECTION_STATE, "")

    try:
        render_kpi_section(metrics)
        st.divider()
        render_action_cta_section(action_context)
        if focus_section == "memos":
            st.divider()
            render_memo_section(dashboard_service, memos=memos, highlight=True)
        expiring_leases = get_expiring_leases(df_tenants)
        st.divider()
        render_lease_alerts(expiring_leases)
        st.divider()
        render_room_status(df_tenants)
        if focus_section != "memos":
            st.divider()
            render_memo_section(dashboard_service, memos=memos)
    except Exception as e:
        st.error(f"❌ 渲染失敗: {str(e)}")
        logger.error(f"渲染失敗: {str(e)}", exc_info=True)


def show():
    render()


if __name__ == "__main__":
    show()
