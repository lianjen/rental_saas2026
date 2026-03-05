"""
房客管理 - v5.5 (Payment Cycle + 年繳折扣)
✅ 整合認證系統 / 登入保護
✅ 整合 Pydantic 驗證層
✅ 完全移除 db 依賴
✅ 使用 TenantService v5.4
✅ 完整表單驗證 / 租約衝突檢查
✅ [NEW] 繳費週期：月繳 / 半年繳 / 年繳
✅ [NEW] 年繳折扣月數（年繳才顯示）
✅ [NEW] 即時預覽折扣後月租
✅ [FIX] 統一欄位：rent / deposit / lease_start / lease_end
✅ [FIX] st.number_input 型別一致（min_value 改為 0.0）
✅ [FIX] use_container_width → width="stretch"
✅ [FIX] \\n 跳脫修正 (format_validation_error 及 error 訊息)
✅ [FIX] 移除 rent_due_day 不存在欄位存取
✅ [FIX] 活蹍 → 活躍（typo 修正）
"""

import streamlit as st
import pandas as pd
from datetime import date
from typing import Optional, Tuple
import logging
from pydantic import ValidationError

try:
    from utils.session_manager import session_manager
    HAS_SESSION_MANAGER = True
except ImportError:
    HAS_SESSION_MANAGER = False
    import warnings
    warnings.warn("⚠️ session_manager 未載入，認證功能將受限")

from schemas.tenant import TenantCreate, TenantUpdate
from services.tenant_service import TenantService
from config.constants import ROOMS, PAYMENT
from utils.rent_pricing import calc_effective_monthly_rent

try:
    from components.cards import section_header, empty_state, data_table
except ImportError:
    def section_header(title, icon="", divider=True):
        st.markdown(f"### {icon} {title}")
        if divider:
            st.divider()

    def empty_state(msg, icon="", desc=""):
        st.info(f"{icon} {msg}")
        if desc:
            st.caption(desc)

    def data_table(df, key="table"):
        st.dataframe(df, width="stretch", key=key, hide_index=True)

logger = logging.getLogger(__name__)


# ── DB 欄位 → 顯示名稱（唯一真相來源）────────────────────────────
COLUMN_DISPLAY_MAP = {
    "room_number":            "房號",
    "name":                   "姓名",
    "phone":                  "電話",
    "payment_cycle":          "繳費週期",
    "annual_discount_months": "折扣月數",
    "base_rent":              "原月租",
    "rent":                   "月租(折扣後)",
    "deposit":                "押金",
    "lease_start":            "入住日期",
    "lease_end":              "退租日期",
    "status":                 "狀態",
    "email":                  "Email",
    "id_number":              "身分證字號",
    "notes":                  "備註",
}


# ── 認證 ──────────────────────────────────────────────────────────
def check_authentication() -> bool:
    if not HAS_SESSION_MANAGER:
        return st.secrets.get("dev_mode", False)
    return session_manager.is_authenticated()


def render_login_required():
    st.warning("🔒 此頁面需要登入才能使用")
    st.info("👉 請先前往「登入」頁面完成登入")
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("🔑 前往登入", width="stretch", type="primary"):
            st.switch_page("pages/login.py")


# ── 輔助函數 ──────────────────────────────────────────────────────
def format_validation_error(error: ValidationError) -> str:
    """格式化 Pydantic 驗證錯誤訊息"""
    field_names = {
        "name":                     "姓名",
        "room_number":              "房號",
        "phone":                    "電話",
        "email":                    "Email",
        "id_number":                "身分證字號",
        "base_rent":                "原月租",
        "payment_cycle":            "繳費週期",
        "annual_discount_months":   "折扣月數",
        "rent":                     "月租(折扣後)",
        "deposit":                  "押金",
        "lease_start":              "入住日期",
        "lease_end":                "退租日期",
        "status":                   "狀態",
        "notes":                    "備註",
    }
    errors = []
    for err in error.errors():
        field = err["loc"][0] if err["loc"] else "unknown"
        field_cn = field_names.get(str(field), str(field))
        errors.append(f"{field_cn}: {err['msg']}")
    # ✅ FIX: "\n" 才是真正換行，"\\n" 是字面文字
    return "\n".join(errors)


def check_room_conflict(
    tenant_service: TenantService,
    room: str,
    start: date,
    end: date,
    exclude_tenant_id: Optional[str] = None,
) -> Tuple[bool, str]:
    try:
        if exclude_tenant_id:
            existing = tenant_service.get_tenant_by_room(room)
            if existing and existing["id"] != exclude_tenant_id:
                return True, f"房間 {room} 已有其他租客 {existing['name']}"
        else:
            if not tenant_service.check_room_availability(room):
                existing = tenant_service.get_tenant_by_room(room)
                if existing:
                    return True, f"房間 {room} 已有租客 {existing['name']}"
        return False, ""
    except Exception as e:
        logger.error(f"檢查房號衝突失敗: {e}", exc_info=True)
        return False, ""


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int = 0) -> int:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_date(value) -> Optional[date]:
    if value is None or str(value) in ("None", "NaT", "nan", ""):
        return None
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None


def _payment_cycle_index(current: Optional[str]) -> int:
    """取得 PAYMENT.METHODS 的 index，找不到回傳 0（月繳）"""
    try:
        return PAYMENT.METHODS.index(current or "月繳")
    except ValueError:
        return 0


# ── Tab 1：新增房客 ───────────────────────────────────────────────
def render_add_tab(tenant_service: TenantService):
    section_header("新增房客", "➕")

    with st.form("add_tenant_form"):
        col1, col2 = st.columns(2)

        with col1:
            room = st.selectbox("房號 *", ROOMS.ALL_ROOMS, key="add_room")
            name = st.text_input("姓名 *", placeholder="例如: 王小明", key="add_name")
            phone = st.text_input("電話", placeholder="例如: 0912-345-678", key="add_phone")
            email = st.text_input("Email", placeholder="例如: tenant@example.com", key="add_email")

            # ✅ NEW: 繳費週期
            payment_cycle = st.selectbox(
                "繳費週期 *",
                PAYMENT.METHODS,
                index=0,
                key="add_payment_cycle",
            )

        with col2:
            # ✅ NEW: 原月租（base_rent）
            base_rent_input = st.number_input(
                "原月租 *", min_value=0.0, value=6000.0, step=500.0, key="add_base_rent"
            )

            # ✅ NEW: 年繳才顯示折扣月數
            annual_discount_months = 0
            if payment_cycle == "年繳":
                annual_discount_months = st.number_input(
                    "年繳折扣（月）",
                    min_value=0, max_value=12, value=1, step=1,
                    help="折幾個月：原月租 6000 折 1 個月 → 月租(折扣後) = 5500",
                    key="add_annual_discount_months",
                )

            # ✅ NEW: 即時預覽折扣後月租
            effective_rent = calc_effective_monthly_rent(
                base_rent=float(base_rent_input),
                payment_cycle=payment_cycle,
                annual_discount_months=int(annual_discount_months),
            )
            st.caption(f"💡 月租（折扣後）= **NT$ {effective_rent:,.0f}**")

            deposit_input = st.number_input(
                "押金 *", min_value=0.0, value=12000.0, step=1000.0, key="add_deposit"
            )
            lease_start_input = st.date_input("入住日期 *", value=date.today(), key="add_start")
            lease_end_input = st.date_input(
                "退租日期",
                value=date.today().replace(year=date.today().year + 1),
                key="add_end",
            )

        st.divider()
        col3, col4 = st.columns(2)
        with col3:
            st.number_input(
                "每月繳租日（顯示用）",
                min_value=1, max_value=31, value=5,
                help="每月的第幾天繳租金（目前僅供顯示）",
                key="add_due_day",
            )
        with col4:
            id_number = st.text_input(
                "身分證字號", placeholder="例如: A123456789", key="add_id_number"
            )

        notes = st.text_area("備註", placeholder="例如: 優良房客、特殊需求等", key="add_notes")

        submitted = st.form_submit_button("✅ 新增房客", type="primary", width="stretch")

        if submitted:
            try:
                # ✅ FIX: 送 base_rent / payment_cycle / annual_discount_months
                tenant_data = TenantCreate(
                    name=name,
                    room_number=room,
                    phone=phone if phone else None,
                    email=email if email else None,
                    id_number=id_number if id_number else None,
                    base_rent=float(base_rent_input),
                    payment_cycle=payment_cycle,
                    annual_discount_months=int(annual_discount_months),
                    deposit=float(deposit_input),
                    lease_start=lease_start_input,
                    lease_end=lease_end_input if lease_end_input else None,
                    notes=notes if notes else None,
                )

                conflict, conflict_msg = check_room_conflict(
                    tenant_service, room,
                    lease_start_input, lease_end_input or date(2099, 12, 31),
                )
                if conflict:
                    st.error(f"❌ {conflict_msg}")
                    return

                success, message = tenant_service.add_tenant(tenant_data=tenant_data)
                if success:
                    st.success(f"✅ {message}")
                    st.balloons()
                    st.rerun()
                else:
                    st.error(f"❌ {message}")

            except ValidationError as e:
                # ✅ FIX: "\n" 而非 "\\n"
                st.error(f"❌ 資料驗證失敗:\n{format_validation_error(e)}")
            except Exception as e:
                st.error(f"❌ 新增失敗: {str(e)}")
                logger.error(f"新增房客失敗: {str(e)}", exc_info=True)


# ── Tab 2：房客列表 ───────────────────────────────────────────────
def render_list_tab(tenant_service: TenantService):
    section_header("所有房客", "👥")

    try:
        tenants = tenant_service.get_all_tenants()
        if not tenants:
            empty_state("目前沒有房客資料", "👥", "點擊「新增房客」開始管理")
            return

        df = pd.DataFrame(tenants)

        col1, col2, col3 = st.columns(3)
        with col1:
            filter_room = st.multiselect("篩選房號", ROOMS.ALL_ROOMS, key="filter_room")
        with col2:
            filter_status = st.multiselect(
                "篩選狀態", ["active", "inactive"], default=["active"], key="filter_status"
            )
        with col3:
            search_name = st.text_input("搜尋姓名", placeholder="輸入姓名關鍵字", key="search_name")

        filtered_df = df.copy()
        if filter_room:
            filtered_df = filtered_df[filtered_df["room_number"].isin(filter_room)]
        if filter_status:
            filtered_df = filtered_df[filtered_df["status"].isin(filter_status)]
        if search_name:
            filtered_df = filtered_df[
                filtered_df["name"].str.contains(search_name, case=False, na=False)
            ]

        st.write(f"**共 {len(filtered_df)} 筆資料**")
        st.divider()

        if not filtered_df.empty:
            display_cols = [
                "room_number", "name", "phone",
                "payment_cycle", "base_rent", "rent",
                "lease_start", "lease_end", "status",
            ]
            available_cols = [c for c in display_cols if c in filtered_df.columns]
            display_df = filtered_df[available_cols].copy()
            display_df.columns = [COLUMN_DISPLAY_MAP.get(c, c) for c in available_cols]

            for d_col in ["入住日期", "退租日期"]:
                if d_col in display_df.columns:
                    display_df[d_col] = pd.to_datetime(
                        display_df[d_col], errors="coerce"
                    ).dt.strftime("%Y-%m-%d")

            if "狀態" in display_df.columns:
                # ✅ FIX: 活蹍 → 活躍
                display_df["狀態"] = display_df["狀態"].replace(
                    {"active": "✅ 活躍", "inactive": "❌ 已退租"}
                )

            for m_col in ["原月租", "月租(折扣後)"]:
                if m_col in display_df.columns:
                    display_df[m_col] = display_df[m_col].apply(
                        lambda x: f"NT$ {float(x):,.0f}" if pd.notna(x) else "-"
                    )

            data_table(display_df, key="tenant_list")
        else:
            st.info("💭 沒有符合條件的資料")

    except Exception as e:
        st.error(f"❌ 載入房客列表失敗: {str(e)}")
        logger.error(f"載入房客列表失敗: {str(e)}", exc_info=True)


# ── Tab 3：編輯房客 ───────────────────────────────────────────────
def render_edit_tab(tenant_service: TenantService):
    section_header("編輯房客", "✏️")

    try:
        tenants = tenant_service.get_all_tenants()
        if not tenants:
            empty_state("沒有可編輯的房客", "👥")
            return

        df = pd.DataFrame(tenants)
        tenant_options = {
            f"{row['room_number']} - {row['name']} ({row['status']})": row["id"]
            for _, row in df.iterrows()
        }

        selected = st.selectbox("選擇要編輯的房客", list(tenant_options.keys()), key="edit_select")
        if not selected:
            return

        tenant_id = tenant_options[selected]
        td = df[df["id"] == tenant_id].iloc[0]

        st.divider()

        with st.form(key=f"edit_tenant_form_{tenant_id}"):
            col1, col2 = st.columns(2)

            with col1:
                room = st.selectbox(
                    "房號 *", ROOMS.ALL_ROOMS,
                    index=ROOMS.ALL_ROOMS.index(td["room_number"])
                    if td["room_number"] in ROOMS.ALL_ROOMS else 0,
                    key=f"edit_room_{tenant_id}",
                )
                name = st.text_input("姓名 *", value=td["name"], key=f"edit_name_{tenant_id}")
                phone = st.text_input("電話", value=td.get("phone") or "", key=f"edit_phone_{tenant_id}")
                email = st.text_input("Email", value=td.get("email") or "", key=f"edit_email_{tenant_id}")

                # ✅ NEW: 繳費週期（帶入既有值）
                payment_cycle = st.selectbox(
                    "繳費週期 *",
                    PAYMENT.METHODS,
                    index=_payment_cycle_index(td.get("payment_cycle")),
                    key=f"edit_payment_cycle_{tenant_id}",
                )

            with col2:
                # ✅ NEW: 原月租（base_rent，舊資料 fallback 到 rent）
                base_rent_default = _safe_float(
                    td.get("base_rent") or td.get("rent"), 6000.0
                )
                base_rent_input = st.number_input(
                    "原月租 *",
                    min_value=0.0,
                    value=base_rent_default,
                    step=500.0,
                    key=f"edit_base_rent_{tenant_id}",
                )

                # ✅ NEW: 年繳才顯示折扣月數
                annual_discount_months = 0
                if payment_cycle == "年繳":
                    annual_discount_months = st.number_input(
                        "年繳折扣（月）",
                        min_value=0, max_value=12,
                        value=_safe_int(td.get("annual_discount_months"), 1),
                        step=1,
                        help="折幾個月：原月租 6000 折 1 個月 → 月租(折扣後) = 5500",
                        key=f"edit_annual_discount_months_{tenant_id}",
                    )

                # ✅ NEW: 即時預覽折扣後月租
                effective_rent = calc_effective_monthly_rent(
                    base_rent=float(base_rent_input),
                    payment_cycle=payment_cycle,
                    annual_discount_months=int(annual_discount_months),
                )
                st.caption(f"💡 月租（折扣後）= **NT$ {effective_rent:,.0f}**")

                deposit_input = st.number_input(
                    "押金 *", min_value=0.0,
                    value=_safe_float(td.get("deposit"), 12000.0),
                    step=1000.0, key=f"edit_deposit_{tenant_id}",
                )
                lease_start_input = st.date_input(
                    "入住日期 *",
                    value=_safe_date(td.get("lease_start")) or date.today(),
                    key=f"edit_start_{tenant_id}",
                )
                lease_end_input = st.date_input(
                    "退租日期",
                    value=_safe_date(td.get("lease_end")),
                    key=f"edit_end_{tenant_id}",
                )

            st.divider()
            col3, col4 = st.columns(2)
            with col3:
                st.number_input(
                    "每月繳租日（顯示用）",
                    min_value=1, max_value=31, value=5,
                    help="目前僅供顯示，不寫入 DB",
                    key=f"edit_due_day_{tenant_id}",
                )
            with col4:
                id_number = st.text_input(
                    "身分證字號",
                    value=td.get("id_number") or "",
                    key=f"edit_id_number_{tenant_id}",
                )
                status = st.selectbox(
                    "狀態",
                    ["active", "inactive"],
                    index=0 if td.get("status") == "active" else 1,
                    # ✅ FIX: 活蹍 → 活躍
                    format_func=lambda x: "✅ 活躍" if x == "active" else "❌ 已退租",
                    key=f"edit_status_{tenant_id}",
                )

            notes = st.text_area(
                "備註", value=td.get("notes") or "", key=f"edit_notes_{tenant_id}"
            )
            st.divider()

            col_update, col_delete = st.columns([3, 1])
            with col_update:
                update_btn = st.form_submit_button("💾 儲存變更", type="primary", width="stretch")
            with col_delete:
                delete_btn = st.form_submit_button("🗑️ 刪除", type="secondary", width="stretch")

            if update_btn:
                try:
                    # ✅ FIX: 送 base_rent / payment_cycle / annual_discount_months
                    update_data = TenantUpdate(
                        name=name,
                        room_number=room,
                        phone=phone if phone else None,
                        email=email if email else None,
                        id_number=id_number if id_number else None,
                        base_rent=float(base_rent_input),
                        payment_cycle=payment_cycle,
                        annual_discount_months=int(annual_discount_months),
                        deposit=float(deposit_input),
                        lease_start=lease_start_input,
                        lease_end=lease_end_input if lease_end_input else None,
                        status=status,
                        notes=notes if notes else None,
                    )

                    conflict, conflict_msg = check_room_conflict(
                        tenant_service, room,
                        lease_start_input,
                        lease_end_input or date(2099, 12, 31),
                        tenant_id,
                    )
                    if conflict:
                        st.error(f"❌ {conflict_msg}")
                        return

                    success, message = tenant_service.update_tenant(
                        tenant_id=tenant_id, tenant_data=update_data
                    )
                    if success:
                        st.success(f"✅ {message}")
                        st.rerun()
                    else:
                        st.error(f"❌ {message}")

                except ValidationError as e:
                    # ✅ FIX: "\n" 而非 "\\n"
                    st.error(f"❌ 資料驗證失敗:\n{format_validation_error(e)}")
                except Exception as e:
                    st.error(f"❌ 更新失敗: {str(e)}")
                    logger.error(f"更新房客失敗: {str(e)}", exc_info=True)

            if delete_btn:
                confirm_key = f"confirm_delete_{tenant_id}"
                if not st.session_state.get(confirm_key):
                    st.session_state[confirm_key] = True
                    st.warning("⚠️ 再次點擊「刪除」確認刪除房客")
                    st.rerun()
                else:
                    try:
                        success, message = tenant_service.delete_tenant(tenant_id)
                        if success:
                            st.success(f"✅ {message}")
                            if confirm_key in st.session_state:
                                del st.session_state[confirm_key]
                            st.rerun()
                        else:
                            st.error(f"❌ {message}")
                    except Exception as e:
                        st.error(f"❌ 刪除失敗: {str(e)}")
                        logger.error(f"刪除房客失敗: {str(e)}", exc_info=True)

    except Exception as e:
        st.error(f"❌ 載入編輯頁面失敗: {str(e)}")
        logger.error(f"載入編輯頁面失敗: {str(e)}", exc_info=True)


# ── Tab 4：統計資訊 ───────────────────────────────────────────────
def render_stats_tab(tenant_service: TenantService):
    section_header("統計資訊", "📊")

    try:
        stats = tenant_service.get_tenant_statistics()

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("總房客數", stats["total_tenants"], f"{stats['occupancy_rate']}% 出租率")
        with col2:
            st.metric("已出租房間", stats["occupied_rooms"], f"共 {stats['total_rooms']} 間")
        with col3:
            st.metric(
                "月租總額(折扣後)",
                f"NT$ {stats['total_rent']:,.0f}",
                f"平均 NT$ {stats['avg_rent']:,.0f}",
            )
        with col4:
            st.metric("押金總額", f"NT$ {stats['total_deposit']:,.0f}")

        st.divider()
        section_header("空房列表", "🏠", divider=False)

        vacant_rooms = tenant_service.get_available_rooms()
        if vacant_rooms:
            st.success(f"✅ 目前有 {len(vacant_rooms)} 間空房")
            cols = st.columns(min(6, len(vacant_rooms)))
            for idx, room in enumerate(vacant_rooms):
                with cols[idx % len(cols)]:
                    st.button(room, key=f"vacant_{room}", width="stretch")
        else:
            st.info("💭 目前沒有空房")

        st.divider()
        section_header("即將到期租約（45天內）", "⏰", divider=False)

        expiring = tenant_service.get_expiring_leases(days=45)
        if expiring:
            st.warning(f"⚠️ 有 {len(expiring)} 筆租約即將到期")
            expiring_df = pd.DataFrame(expiring)
            exp_cols = ["room_number", "name", "phone", "lease_end", "days_remaining"]
            available_exp = [c for c in exp_cols if c in expiring_df.columns]
            disp = expiring_df[available_exp].copy()
            disp.columns = [COLUMN_DISPLAY_MAP.get(c, c) for c in available_exp]
            if "退租日期" in disp.columns:
                disp["退租日期"] = pd.to_datetime(
                    disp["退租日期"], errors="coerce"
                ).dt.strftime("%Y-%m-%d")
            data_table(disp, key="expiring_leases")
        else:
            st.success("✅ 近期沒有租約到期")

    except Exception as e:
        st.error(f"❌ 載入統計資訊失敗: {str(e)}")
        logger.error(f"載入統計資訊失敗: {str(e)}", exc_info=True)


# ── 主函數 ────────────────────────────────────────────────────────
def render():
    if not check_authentication():
        render_login_required()
        return

    st.title("👥 房客管理")

    if HAS_SESSION_MANAGER:
        user_info = session_manager.get_user_info()
        if user_info:
            with st.sidebar:
                st.caption(f"👤 {user_info.get('email', '未知用戶')}")

    try:
        tenant_service = TenantService()
        if not tenant_service.health_check():
            st.error("❌ 資料庫連接失敗，請稍後再試")
            return
    except Exception as e:
        st.error(f"❌ 初始化服務失敗: {str(e)}")
        logger.error(f"初始化 TenantService 失敗: {str(e)}", exc_info=True)
        return

    tab1, tab2, tab3, tab4 = st.tabs(
        ["➕ 新增房客", "📋 房客列表", "✏️ 編輯房客", "📊 統計資訊"]
    )
    with tab1:
        render_add_tab(tenant_service)
    with tab2:
        render_list_tab(tenant_service)
    with tab3:
        render_edit_tab(tenant_service)
    with tab4:
        render_stats_tab(tenant_service)


def show():
    render()


if __name__ == "__main__":
    show()
