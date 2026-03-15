"""
LINE 綁定管理介面 - v3.3 UUID Compatible
✅ 修正：tenant_id 使用 UUID 格式（字串），不再轉換為 int
✅ 綁定狀態總覽（支援新舊欄位命名）
✅ 顯示並區分「已驗證 / 待驗證 / 未綁定」
✅ 批量解除綁定
✅ 單一房客綁定設定（後台以 tenant_id 綁定，視為已驗證）
"""

import logging
from typing import Dict

import pandas as pd
import streamlit as st

from services.tenant_service import TenantService
from services.tenant_contact_service import TenantContactService
from utils.session_keys import SessionKeys

logger = logging.getLogger(__name__)


def render() -> None:
    """主入口（供 main.py 呼叫）"""
    render_line_binding_page()


def show() -> None:
    """Streamlit 頁面入口（兼容舊寫法）"""
    render()


def render_line_binding_page() -> None:
    """LINE 綁定管理主頁面"""

    st.title("📱 LINE 綁定管理")

    tenant_svc = TenantService()
    contact_svc = TenantContactService()

    # === 建立 Tabs ===
    tab1, tab2 = st.tabs(["📊 綁定總覽", "🔗 綁定設定"])

    with tab1:
        render_binding_overview(tenant_svc, contact_svc)

    with tab2:
        render_binding_editor(tenant_svc, contact_svc)


# ==================== 共用：欄位對應工具 ====================

def _resolve_tenant_columns(df: pd.DataFrame) -> Dict[str, str]:
    """
    自動對應租客 DataFrame 的欄位名稱，支援舊欄位 (roomnumber, tenantname) 與新欄位 (room_number, tenant_name)。

    Returns:
        {
            "id": <欄位名>,
            "room": <欄位名>,
            "name": <欄位名>,
            "phone": <欄位名 或 None>,
        }
    """
    cols = {c.lower(): c for c in df.columns}

    id_col = cols.get("id") or cols.get("tenant_id")
    room_col = (
        cols.get("room_number")
        or cols.get("roomnumber")
        or cols.get("房號")
    )
    name_col = (
        cols.get("tenant_name")
        or cols.get("tenantname")
        or cols.get("房客")
        or cols.get("name")
    )
    phone_col = (
        cols.get("phone")
        or cols.get("phone_number")
        or cols.get("phonenumber")
    )

    if not id_col or not room_col or not name_col:
        raise KeyError(
            f"無法解析租客欄位，取得的欄位為: {list(df.columns)} "
            "(需要至少包含 id / room_number / tenant_name 或對應別名)"
        )

    return {
        "id": id_col,
        "room": room_col,
        "name": name_col,
        "phone": phone_col or "",
    }


# ==================== Tab 1: 綁定總覽 ====================

def render_binding_overview(tenant_svc: TenantService, contact_svc: TenantContactService) -> None:
    """綁定狀態總覽"""

    st.subheader("📊 LINE 綁定狀態總覽")

    # === 快速篩選 ===
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("✅ 已驗證綁定", key="filter_bound", use_container_width=True, type="primary"):
            st.session_state[SessionKeys.LINE_FILTER] = "bound"
            st.rerun()

    with col2:
        if st.button("📭 未驗證 / 未綁定", key="filter_unbound", use_container_width=True):
            st.session_state[SessionKeys.LINE_FILTER] = "unbound"
            st.rerun()

    with col3:
        if st.button("🔄 全部", key="filter_all", use_container_width=True):
            st.session_state[SessionKeys.LINE_FILTER] = "all"
            st.rerun()

    if SessionKeys.LINE_FILTER not in st.session_state:
        st.session_state[SessionKeys.LINE_FILTER] = "all"

    current_filter = st.session_state[SessionKeys.LINE_FILTER]

    st.divider()

    # === 載入資料 ===
    try:
        tenants_df = tenant_svc.get_tenants(active_only=True)

        if tenants_df.empty:
            st.warning("⚠️ 目前沒有房客資料")
            return

        try:
            col_map = _resolve_tenant_columns(tenants_df)
        except KeyError as e:
            st.error(f"❌ 欄位解析失敗：{e}")
            logger.error(f"綁定總覽欄位解析失敗: {e}", exc_info=True)
            return

        id_col = col_map["id"]
        room_col = col_map["room"]
        name_col = col_map["name"]
        phone_col = col_map["phone"]

        # 建立綁定狀態表（完整資料集）
        binding_data = []

        for _, tenant in tenants_df.iterrows():
            # ✅ v3.3 修正：tenant_id 使用字串格式（UUID）
            tenant_id = str(tenant[id_col])
            room_number = tenant[room_col]
            tenant_name = tenant[name_col]
            phone = tenant[phone_col] if phone_col and phone_col in tenant else "N/A"

            # 查詢綁定狀態
            contact = contact_svc.get_tenant_contact(tenant_id)

            line_id = contact.get("line_user_id") if contact else None
            is_verified = bool(contact.get("is_verified", False)) if contact else False

            if line_id:
                masked_id = f"{line_id[:8]}...{line_id[-4:]}" if len(line_id) > 12 else line_id
            else:
                masked_id = "-"

            if line_id and is_verified:
                bind_status = "✅ 已綁定"
                verify_status = "✅ 已驗證"
                notify_rent = "✅" if contact.get("notify_rent", False) else "❌"
                notify_elec = "✅" if contact.get("notify_electricity", False) else "❌"
            elif line_id and not is_verified:
                bind_status = "⏳ 待驗證"
                verify_status = "⏳ 待驗證"
                notify_rent = "⏳"  # 尚未正式啟用
                notify_elec = "⏳"
            else:
                bind_status = "📭 未綁定"
                verify_status = "📭 未綁定"
                notify_rent = "-"
                notify_elec = "-"

            binding_data.append(
                {
                    "id": tenant_id,  # ✅ 保持字串格式
                    "房號": room_number,
                    "房客": tenant_name,
                    "電話": phone,
                    "綁定狀態": bind_status,
                    "驗證狀態": verify_status,
                    "LINE ID": masked_id,
                    "租金通知": notify_rent,
                    "電費通知": notify_elec,
                }
            )

        df_all = pd.DataFrame(binding_data)

        # === 統計摘要（用完整 df_all，不受當前篩選影響） ===
        total_tenants = len(df_all)
        bound_count = int((df_all["綁定狀態"] == "✅ 已綁定").sum())
        unbound_count = total_tenants - bound_count
        binding_rate = (bound_count / total_tenants * 100) if total_tenants > 0 else 0.0

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("總房客數", f"{total_tenants} 人")

        with col2:
            st.metric("已驗證綁定", f"{bound_count} 人")

        with col3:
            st.metric("未驗證 / 未綁定", f"{unbound_count} 人")

        with col4:
            st.metric("綁定率", f"{binding_rate:.1f}%")

        st.divider()

        # === 依目前篩選條件建立顯示用 df ===
        df = df_all.copy()

        if current_filter == "bound":
            df = df[df["綁定狀態"] == "✅ 已綁定"]
            st.info(f"📊 顯示：已驗證綁定（共 {len(df)} 筆）")
        elif current_filter == "unbound":
            df = df[df["綁定狀態"] != "✅ 已綁定"]
            st.info(f"📊 顯示：未驗證 / 未綁定（共 {len(df)} 筆）")
        else:
            st.info(f"📊 顯示：全部（共 {len(df)} 筆）")

        if df.empty:
            st.success("✅ 沒有符合條件的記錄")
            return

        # === 顯示表格 ===
        st.markdown("### 📋 詳細列表")

        df_sorted = df.sort_values(["綁定狀態", "房號"], ascending=[True, True])

        display_cols = ["房號", "房客", "電話", "綁定狀態", "驗證狀態", "LINE ID", "租金通知", "電費通知"]

        st.dataframe(
            df_sorted[display_cols],
            use_container_width=True,
            hide_index=True,
        )

        # === 批量解除綁定（只對「有 line_user_id」的做，多數會是 已綁定 or 待驗證） ===
        bound_df = df_all[df_all["LINE ID"] != "-"]

        if not bound_df.empty:
            st.divider()
            st.markdown("### ❌ 批量解除綁定")

            st.warning("⚠️ 解除綁定後，該房客將無法接收 LINE 通知")

            col1, col2 = st.columns([3, 1])

            with col1:
                selected_ids = st.multiselect(
                    "選擇要解除綁定的房客（可多選）",
                    options=bound_df["id"].tolist(),
                    format_func=lambda x: (
                        f"{bound_df[bound_df['id'] == x]['房號'].values[0]} - "
                        f"{bound_df[bound_df['id'] == x]['房客'].values[0]}"
                    ),
                    key="unbind_multiselect",
                )

            with col2:
                st.write("")
                st.write("")
                if st.button(
                    f"❌ 解綁 ({len(selected_ids)})",
                    type="secondary",
                    disabled=len(selected_ids) == 0,
                    use_container_width=True,
                    key="batch_unbind",
                ):
                    with st.spinner("處理中..."):
                        success_count = 0
                        fail_count = 0

                        for tenant_id in selected_ids:
                            # ✅ tenant_id 已經是字串，直接使用
                            ok, msg = contact_svc.unbind_line_user(tenant_id)

                            if ok:
                                success_count += 1
                            else:
                                fail_count += 1
                                logger.error(f"解除綁定失敗: tenant_id={tenant_id}, {msg}")

                        if success_count > 0:
                            st.success(f"✅ 成功解除 {success_count} 筆綁定")

                        if fail_count > 0:
                            st.error(f"❌ 失敗 {fail_count} 筆")

                        st.rerun()

    except Exception as e:
        st.error(f"❌ 載入資料失敗: {str(e)}")
        logger.error(f"綁定總覽錯誤: {str(e)}", exc_info=True)


# ==================== Tab 2: 綁定設定 ====================

def render_binding_editor(tenant_svc: TenantService, contact_svc: TenantContactService) -> None:
    """單一房客綁定設定（後台手動綁定 / 解綁）"""

    st.subheader("🔗 LINE 綁定設定")

    try:
        tenants_df = tenant_svc.get_tenants(active_only=True)

        if tenants_df.empty:
            st.warning("⚠️ 目前沒有房客資料")
            return

        try:
            col_map = _resolve_tenant_columns(tenants_df)
        except KeyError as e:
            st.error(f"❌ 欄位解析失敗：{e}")
            logger.error(f"綁定設定欄位解析失敗: {e}", exc_info=True)
            return

        id_col = col_map["id"]
        room_col = col_map["room"]
        name_col = col_map["name"]

        # 房客選擇
        tenant_options = {
            f"{row[room_col]} - {row[name_col]}": str(row[id_col])  # ✅ 改為字串
            for _, row in tenants_df.iterrows()
        }

        selected = st.selectbox(
            "選擇房客",
            options=list(tenant_options.keys()),
            key="line_bind_tenant_select",
        )

        if not selected:
            return

        tenant_id = tenant_options[selected]  # ✅ 已經是字串

        # 取得目前綁定狀態
        contact_info = contact_svc.get_tenant_contact(tenant_id)

        st.divider()

        # === 顯示目前狀態 ===
        if contact_info and contact_info.get("line_user_id"):
            st.markdown("#### ✅ 目前綁定狀態")

            col1, col2 = st.columns(2)

            with col1:
                st.info(f"**LINE ID:** `{contact_info['line_user_id']}`")

            with col2:
                notify_rent = contact_info.get("notify_rent", True)
                notify_elec = contact_info.get("notify_electricity", True)
                is_verified = bool(contact_info.get("is_verified", False))
                status_text = "✅ 已驗證" if is_verified else "⏳ 待驗證"

                st.info(
                    f"**綁定狀態:** {status_text}\n\n"
                    f"**通知設定:** 租金 {'✅' if notify_rent else '❌'} / 電費 {'✅' if notify_elec else '❌'}"
                )

            # 更新通知設定
            with st.form(key=f"update_notify_form_{tenant_id}"):
                st.markdown("##### 🔔 更新通知設定")

                col1, col2 = st.columns(2)

                with col1:
                    new_notify_rent = st.checkbox(
                        "接收租金通知",
                        value=notify_rent,
                        key=f"update_rent_{tenant_id}",
                    )

                with col2:
                    new_notify_elec = st.checkbox(
                        "接收電費通知",
                        value=notify_elec,
                        key=f"update_elec_{tenant_id}",
                    )

                update_submitted = st.form_submit_button(
                    "🔄 更新設定",
                    type="primary",
                    use_container_width=True,
                )

                if update_submitted:
                    ok, msg = contact_svc.update_notification_settings(
                        tenant_id,  # ✅ 直接使用字串
                        notify_rent=new_notify_rent,
                        notify_electricity=new_notify_elec,
                    )

                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

            st.divider()

            # 解除綁定
            st.markdown("##### ❌ 解除綁定")
            st.warning("⚠️ 解除綁定後，該房客將無法接收 LINE 通知")

            if st.button(
                "❌ 確認解除綁定",
                key=f"unbind_single_{tenant_id}",
                type="secondary",
            ):
                with st.spinner("處理中..."):
                    ok, msg = contact_svc.unbind_line_user(tenant_id)  # ✅ 直接使用字串

                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

        else:
            st.info("📭 此房客尚未綁定 LINE")

        st.divider()

        # === 新增/更新綁定（後台直接用 LINE User ID 建立綁定，視為已驗證） ===
        with st.form(key=f"bind_form_{tenant_id}"):
            st.markdown("#### 🔗 新增/更新 LINE 綁定")

            line_user_id = st.text_input(
                "LINE User ID",
                placeholder="U1234567890abcdef1234567890abcdef",
                help="從 LINE Bot Webhook 取得的 User ID（通常以 'U' 開頭，長度約 33 字元）",
                key=f"line_id_input_{tenant_id}",
            )

            col1, col2 = st.columns(2)

            with col1:
                bind_notify_rent = st.checkbox(
                    "接收租金通知",
                    value=True,
                    key=f"bind_rent_{tenant_id}",
                )

            with col2:
                bind_notify_elec = st.checkbox(
                    "接收電費通知",
                    value=True,
                    key=f"bind_elec_{tenant_id}",
                )

            st.caption("💡 提示：LINE User ID 可從 LINE Bot Webhook 的 `userId` 欄位取得")

            bind_submitted = st.form_submit_button(
                "✅ 確認綁定",
                type="primary",
                use_container_width=True,
            )

            if bind_submitted:
                if not line_user_id:
                    st.error("❌ 請輸入 LINE User ID")
                elif not line_user_id.startswith("U"):
                    st.error("❌ LINE User ID 格式錯誤（應以 'U' 開頭）")
                else:
                    with st.spinner("綁定中..."):
                        ok, msg = contact_svc.bind_line_user(
                            tenant_id,  # ✅ 直接使用字串
                            line_user_id,
                            notify_rent=bind_notify_rent,
                            notify_electricity=bind_notify_elec,
                        )

                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

    except Exception as e:
        st.error(f"❌ 載入失敗: {str(e)}")
        logger.error(f"綁定設定錯誤: {str(e)}", exc_info=True)


# ============================================
# 本機測試入口
# ============================================
if __name__ == "__main__":
    render_line_binding_page()
