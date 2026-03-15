"""
Session state keys - v1.0.0
Centralize shared Streamlit session_state keys and dynamic key builders.

Keep the existing key formats for backward compatibility. This module only
standardizes how keys are referenced and generated.
"""

from __future__ import annotations

from enum import StrEnum


class SessionKeys(StrEnum):
    """Central session_state key registry."""

    # Auth/session
    ACCESS_TOKEN = "access_token"
    REFRESH_TOKEN = "refresh_token"
    EXPIRES_AT = "expires_at"
    USER_DATA = "user_data"
    USER_ID = "user_id"
    USER_EMAIL = "user_email"
    USER_NAME = "user_name"
    USER_ROLE = "user_role"
    IS_AUTHENTICATED = "is_authenticated"
    AUTHENTICATED_LEGACY = "authenticated"
    LOGIN_TIME = "login_time"
    LAST_ACTIVITY = "last_activity"

    # App/navigation
    CURRENT_MENU = "current_menu"
    SIDEBAR_RADIO = "_sidebar_radio"
    AUTH_MODE = "auth_mode"
    COOKIE_CONTROLLER = "__cookie_ctrl"

    # CTA/navigation state
    DASHBOARD_FOCUS_SECTION = "dashboard_focus_section"
    RENT_DEFAULT_TAB = "rent_default_tab"
    RENT_DEFAULT_STATUS_FILTER = "rent_default_status_filter"
    ELECTRICITY_DEFAULT_TAB = "electricity_default_tab"
    CURRENT_PERIOD_ID = "current_period_id"

    # Electricity state
    CONFIRM_DELETE_PERIOD = "confirm_delete_period"
    TAIPOWER_BILLS = "taipower_bills"
    ROOM_READINGS = "room_readings"
    RAW_READINGS = "raw_readings"

    # View/UI filters
    PENDING_EXPENSE_NO_DESC = "pending_expense_no_desc"
    LINE_FILTER = "line_filter"
    TRACKING_RENT_FILTER = "rent_filter"
    TRACKING_ELEC_FILTER = "elec_filter"
    RENT_BATCH_MODE = "batch_mode"
    RENT_SELECTED_ROOMS_FOR_BATCH = "selected_rooms_for_batch"

    # Refresh guard
    FAILED_REFRESH_TOKEN_HASH = "_failed_refresh_token_hash"
    FAILED_REFRESH_SOURCE = "_failed_refresh_source"
    FAILED_REFRESH_AT = "_failed_refresh_at"

    # Pending/confirm flow helpers
    CONFIRM_DELETE_GENERIC = "confirm_delete"
    CONFIRM_DELETE_EXPENSE = "confirm_delete_expense"
    CONFIRM_DELETE_RENT = "confirm_delete_rent"
    CONFIRM_DELETE_ELEC = "confirm_delete_elec"

    @staticmethod
    def confirm_delete(record_id: str | int) -> str:
        return f"confirm_delete_{record_id}"

    @staticmethod
    def custom(key: str) -> str:
        return f"custom_{key}"

    @staticmethod
    def taipower_db_loaded(period_id: int) -> str:
        return f"tp_{period_id}_db_loaded"

    @staticmethod
    def taipower_amount(period_id: int, floor_key: str) -> str:
        return f"tp_{period_id}_{floor_key}_amt"

    @staticmethod
    def taipower_kwh(period_id: int, floor_key: str) -> str:
        return f"tp_{period_id}_{floor_key}_kwh"

    @staticmethod
    def calc_result(period_id: int) -> str:
        return f"calc_result_{period_id}"

    @staticmethod
    def calc_details(period_id: int) -> str:
        return f"calc_details_{period_id}"
