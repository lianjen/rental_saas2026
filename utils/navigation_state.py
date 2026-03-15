"""
Navigation state helpers - v1.0.0
Shared session_state keys for dashboard CTA page jumps.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Optional, Sequence

try:
    import streamlit as st  # type: ignore
except ImportError:
    st = None  # type: ignore


MENU_DASHBOARD = "📊 儀表板"
MENU_RENT = "💰 租金管理"
MENU_ELECTRICITY = "⚡ 電費管理"

DASHBOARD_FOCUS_SECTION_STATE = "dashboard_focus_section"
RENT_DEFAULT_TAB_STATE = "rent_default_tab"
RENT_DEFAULT_STATUS_FILTER_STATE = "rent_default_status_filter"
ELECTRICITY_DEFAULT_TAB_STATE = "electricity_default_tab"

RENT_TAB_BATCH = "📅 批量建立排程"
RENT_TAB_SUMMARY = "📊 本月摘要"
RENT_TAB_MANAGEMENT = "💳 收款管理"
RENT_TAB_REPORTS = "📚 報表分析"
RENT_TABS_KEY = "rent_main_tabs"
RENT_STATUS_FILTER_KEY = "rent_management_status_filter"
RENT_ROOM_FILTER_KEY = "management_room_filter"
RENT_STATUS_ALL = "全部"
RENT_STATUS_UNPAID = "未繳"
RENT_STATUS_PAID = "已繳"
RENT_STATUS_OVERDUE = "逾期"

ELECTRICITY_TAB_PERIOD = "📅 計費期間"
ELECTRICITY_TAB_CALCULATION = "🧮 計算電費"
ELECTRICITY_TAB_RECORDS = "📜 繳費記錄"
ELECTRICITY_TAB_STATISTICS = "📊 用電統計"
ELECTRICITY_TAB_DEPOSIT = "💰 電費預收帳"
ELECTRICITY_TABS_KEY = "electricity_main_tabs"


def build_navigation_state(menu: str, **updates: Any) -> Dict[str, Any]:
    """Return the session_state updates for a CTA navigation event."""
    state = {"current_menu": menu}
    for key, value in updates.items():
        if value is not None:
            state[key] = value
    return state


def apply_navigation_state(
    menu: str,
    *,
    clear_keys: Optional[Sequence[str]] = None,
    **updates: Any,
) -> Dict[str, Any]:
    """Write CTA navigation targets into Streamlit session_state."""
    state = build_navigation_state(menu, **updates)
    if st is not None:
        for key in clear_keys or ():
            st.session_state.pop(key, None)
        for key, value in state.items():
            st.session_state[key] = value
    return state


def pop_string_state(key: str, default: str) -> str:
    """Pop a string from session_state once so defaults do not keep overriding UI."""
    if st is None:
        return default
    value = st.session_state.pop(key, default)
    return value if isinstance(value, str) else default


def resolve_default_label(
    options: Sequence[str],
    requested: Optional[str],
    fallback: Optional[str] = None,
) -> str:
    """Resolve a safe default label from a requested value and available options."""
    if requested in options:
        return str(requested)
    if fallback in options:
        return str(fallback)
    return options[0] if options else ""


def get_pending_electricity_period_summary(
    periods: Sequence[Mapping[str, Any]],
    has_records: Callable[[int], bool],
) -> Dict[str, Optional[int]]:
    """Compute how many periods still need calculation and which period to focus."""
    ordered_periods = sorted(
        periods,
        key=lambda period: (
            int(period.get("period_year") or 0),
            int(period.get("period_month_end") or period.get("period_month_start") or 0),
            int(period.get("id") or 0),
        ),
    )

    if not ordered_periods:
        return {"pending_count": 0, "default_period_id": None}

    pending_ids = []
    for period in ordered_periods:
        period_id = period.get("id")
        if isinstance(period_id, int) and not has_records(period_id):
            pending_ids.append(period_id)

    if pending_ids:
        return {
            "pending_count": len(pending_ids),
            "default_period_id": pending_ids[-1],
        }

    latest_period_id = ordered_periods[-1].get("id")
    return {
        "pending_count": 0,
        "default_period_id": latest_period_id if isinstance(latest_period_id, int) else None,
    }
