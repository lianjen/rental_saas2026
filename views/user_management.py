"""
用戶管理頁面 - v1.0
✅ Admin 專屬功能
✅ 列表所有用戶、設定角色、邀請新用戶、停用用戶
✅ 使用 AuthService + BaseDBService
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import logging

from services.auth_service import AuthService
from services.base_db import BaseDBService

try:
    from utils.session_manager import session_manager
except ImportError:
    session_manager = None

logger = logging.getLogger(__name__)


# ==================== 輔助函數 ====================

def _get_current_user_id() -> str | None:
    for key in ("user_id", "uid", "auth_user_id"):
        uid = st.session_state.get(key)
        if uid:
            return uid
    return None


def _fetch_users() -> list[dict]:
    """從 DB 讀取用戶列表（試多個常見 Table 名稱）"""
    db = BaseDBService()
    tables_to_try = ["user_profiles", "app_users", "profiles"]

    for table in tables_to_try:
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT *
                    FROM {table}
                    ORDER BY created_at DESC
                    LIMIT 200
                """)
                cols = [d[0] for d in cursor.description]
                rows = cursor.fetchall()
                logger.info(f"✅ 從 {table} 取得 {len(rows)} 個用戶")
                return [dict(zip(cols, r)) for r in rows]
        except Exception as e:
            logger.debug(f"{table} 不存在或查詢失敗: {e}")
            continue

    logger.warning("無法從 DB 取得用戶列表")
    return []


def _update_user_role(user_id: str, new_role: str) -> tuple[bool, str]:
    db = BaseDBService()
    tables_to_try = ["user_profiles", "app_users", "profiles"]
    for table in tables_to_try:
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"UPDATE {table} SET role = %s WHERE id = %s",
                    (new_role, user_id),
                )
                logger.info(f"✅ 更新用戶 {user_id} 角色 → {new_role}")
                return True, f"角色已更新為 {new_role}"
        except Exception as e:
            logger.debug(f"{table} 更新失敗: {e}")
            continue
    return False, "更新失敗：找不到 user_profiles / app_users / profiles 表"


def _disable_user(user_id: str, disabled: bool) -> tuple[bool, str]:
    db = BaseDBService()
    tables_to_try = ["user_profiles", "app_users", "profiles"]
    for table in tables_to_try:
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"UPDATE {table} SET is_active = %s WHERE id = %s",
                    (not disabled, user_id),
                )
                action = "停用" if disabled else "啟用"
                logger.info(f"✅ {action}用戶 {user_id}")
                return True, f"用戶已{action}"
        except Exception as e:
            logger.debug(f"{table} 更新失敗: {e}")
            continue
    return False, "更新失敗"


# ==================== Tab 1: 用戶列表 ====================

def render_list_tab():
    st.subheader("📋 用戶列表")

    if st.button("🔄 重新整載", key="refresh_users"):
        st.cache_data.clear()
        st.rerun()

    users = _fetch_users()

    if not users:
        st.warning("⚠️ 無法讀取用戶資料，請確認 DB 中存在 user_profiles 表")
        with st.expander("🛠️ 建表 SQL 參考"):
            st.code("""
CREATE TABLE IF NOT EXISTS user_profiles (
    id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email       TEXT NOT NULL,
    name        TEXT,
    role        TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin','user')),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
            """, language="sql")
        return

    df = pd.DataFrame(users)

    # 概覽指標
    total      = len(df)
    admin_cnt  = len(df[df.get("role", pd.Series()).eq("admin")]) if "role" in df.columns else "-"
    active_cnt = len(df[df.get("is_active", pd.Series()).eq(True)]) if "is_active" in df.columns else "-"

    c1, c2, c3 = st.columns(3)
    with c1: st.metric("總用戶數",  total)
    with c2: st.metric("管理員數",  admin_cnt)
    with c3: st.metric("啟用中用戶", active_cnt)

    st.divider()

    # 搜尋過濾
    col_search, col_role_filter = st.columns([3, 1])
    with col_search:
        search = st.text_input("🔍 搜尋用戶（Email / 名稱）", key="user_search")
    with col_role_filter:
        role_filter = st.selectbox("角色過濾", ["全部", "admin", "user"], key="role_filter")

    filtered_df = df.copy()
    if search:
        mask = pd.Series([False] * len(filtered_df))
        for col in ["email", "name"]:
            if col in filtered_df.columns:
                mask |= filtered_df[col].astype(str).str.contains(search, case=False, na=False)
        filtered_df = filtered_df[mask]

    if role_filter != "全部" and "role" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["role"] == role_filter]

    # 顯示欄位選擇
    all_cols      = list(filtered_df.columns)
    priority_cols = [c for c in ["id", "email", "name", "role", "is_active", "created_at"] if c in all_cols]
    other_cols    = [c for c in all_cols if c not in priority_cols]
    show_cols     = priority_cols + other_cols

    st.write(f"共 **{len(filtered_df)}** 位用戶")
    st.dataframe(
        filtered_df[show_cols],
        use_container_width=True,
        hide_index=True,
        key="user_table",
    )


# ==================== Tab 2: 編輯用戶 ====================

def render_edit_tab():
    st.subheader("✏️ 編輯用戶角色 / 狀態")

    users = _fetch_users()
    if not users:
        st.warning("無用戶資料可編輯")
        return

    df = pd.DataFrame(users)
    current_uid = _get_current_user_id()

    # 選擇用戶
    id_col    = "id"    if "id"    in df.columns else df.columns[0]
    email_col = "email" if "email" in df.columns else id_col

    options = {}
    for _, row in df.iterrows():
        label = f"{row.get(email_col, row[id_col])} ({row.get('role', '?')})"
        options[label] = row[id_col]

    selected_label = st.selectbox(
        "選擇要編輯的用戶",
        ["-- 請選擇 --"] + list(options.keys()),
        key="edit_user_select",
    )

    if selected_label == "-- 請選擇 --":
        return

    selected_uid = options[selected_label]
    row = df[df[id_col] == selected_uid].iloc[0]

    # 安全防護：管理員不能編輯自己的角色
    is_self = str(selected_uid) == str(current_uid)
    if is_self:
        st.info("🔒 無法編輯自己的帳號，請求其他管理員操作")

    col1, col2 = st.columns(2)

    with col1:
        with st.form("edit_role_form"):
            st.write("🏷️ **角色設定**")
            current_role = row.get("role", "user")
            new_role = st.selectbox(
                "角色",
                ["user", "admin"],
                index=0 if current_role == "user" else 1,
                disabled=is_self,
                key="new_role",
            )
            if st.form_submit_button("💾 儲存角色", disabled=is_self):
                ok, msg = _update_user_role(selected_uid, new_role)
                if ok:
                    st.success(f"✅ {msg}")
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")

    with col2:
        with st.form("edit_status_form"):
            st.write("🔘 **帳號狀態**")
            current_active = row.get("is_active", True)
            new_disabled = st.toggle(
                "停用此帳號",
                value=(not current_active),
                disabled=is_self,
                key="new_disabled",
            )
            if st.form_submit_button("💾 儲存狀態", disabled=is_self):
                ok, msg = _disable_user(selected_uid, new_disabled)
                if ok:
                    st.success(f"✅ {msg}")
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")

    # 用戶詳情
    st.divider()
    st.write("📄 **用戶詳情**")
    detail_items = {
        "🔑 ID":        str(row.get("id", "-")),
        "📧 Email":    str(row.get("email", "-")),
        "👤 名稱":      str(row.get("name", "-")),
        "🏷️ 角色":      str(row.get("role", "-")),
        "🟢 狀態":      "啟用" if row.get("is_active", True) else "停用",
        "📅 建立時間":  str(row.get("created_at", "-")),
    }
    for k, v in detail_items.items():
        st.caption(f"{k}:  `{v}`")


# ==================== Tab 3: 邀請新用戶 ====================

def render_invite_tab():
    st.subheader("✉️ 邀請新用戶")
    st.info("💡 發送邀請信件至指定 Email，對方可透過連結設定密碼後登入")

    with st.form("invite_user_form"):
        invite_email = st.text_input("📧 Email", placeholder="example@gmail.com", key="invite_email")
        invite_role  = st.selectbox("🏷️ 角色", ["user", "admin"], key="invite_role")
        invite_name  = st.text_input("👤 姓名（可選）", key="invite_name")
        submit = st.form_submit_button("📨 發送邀請", type="primary", use_container_width=True)

        if submit:
            if not invite_email or "@" not in invite_email:
                st.error("⚠️ 請輸入有效的 Email")
            else:
                with st.spinner("發送中..."):
                    try:
                        auth_service = AuthService()

                        # 嘗試呼叫 invite_user / create_user
                        ok, msg = False, "未知錯誤"

                        if hasattr(auth_service, "invite_user"):
                            ok, msg = auth_service.invite_user(
                                email=invite_email,
                                role=invite_role,
                                name=invite_name or None,
                            )
                        elif hasattr(auth_service, "create_user"):
                            ok, msg = auth_service.create_user(
                                email=invite_email,
                                role=invite_role,
                            )
                        else:
                            st.error("❌ AuthService 不支援 invite_user / create_user。請在 auth_service.py 新增該方法")
                            st.stop()

                        if ok:
                            st.success(f"✅ {msg}")
                            st.balloons()
                            logger.info(f"邀請用戶成功: {invite_email} ({invite_role})")
                        else:
                            st.error(f"❌ {msg}")

                    except Exception as e:
                        logger.error(f"邀請用戶失敗: {e}")
                        st.error(f"❌ 發送失敗: {e}")


# ==================== Tab 4: 權限說明 ====================

def render_roles_tab():
    st.subheader("📚 角色與權限說明")

    data = [
        {"功能": "📊 儀表板",     "user 用戶": "✅", "admin 管理員": "✅"},
        {"功能": "👥 房客管理",   "user 用戶": "✅", "admin 管理員": "✅"},
        {"功能": "💰 租金管理",   "user 用戶": "✅", "admin 管理員": "✅"},
        {"功能": "📋 繳費追蹤",   "user 用戶": "✅", "admin 管理員": "✅"},
        {"功能": "⚡ 電費管理",   "user 用戶": "✅", "admin 管理員": "✅"},
        {"功能": "💸 支出記錄",   "user 用戶": "✅", "admin 管理員": "✅"},
        {"功能": "📱 LINE 綁定",  "user 用戶": "✅", "admin 管理員": "✅"},
        {"功能": "📬 通知管理",   "user 用戶": "✅", "admin 管理員": "✅"},
        {"功能": "⚙️ 系統設定",   "user 用戶": "❌", "admin 管理員": "✅"},
        {"功能": "👨‍💼 用戶管理", "user 用戶": "❌", "admin 管理員": "✅"},
    ]
    st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True, key="roles_table")

    st.divider()
    st.caption("💡 角色儲存於 user_profiles.role，可在 [編輯用戶] Tab 修改")


# ==================== 主入口 ====================

def render():
    st.title("👨‍💼 用戶管理")

    # 雙重安全檢查
    user_role = None
    if session_manager:
        user_role = session_manager.get_user_role()
    else:
        user_role = st.session_state.get("user_role", "user")

    if user_role != "admin":
        st.error("🔒 此頁面僅限管理員使用")
        st.info("💡 請聯絡管理員開通權限")
        return

    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 用戶列表",
        "✏️ 編輯用戶",
        "✉️ 邀請新用戶",
        "📚 角色權限",
    ])
    with tab1: render_list_tab()
    with tab2: render_edit_tab()
    with tab3: render_invite_tab()
    with tab4: render_roles_tab()


def show():
    render()


if __name__ == "__main__":
    show()
