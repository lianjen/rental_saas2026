"""
通知管理頁面
"""
import streamlit as st
import pandas as pd
from datetime import datetime
import requests
import logging


logger = logging.getLogger(__name__)


# ============== Tab 1: 系統設定 ==============


def render_settings_tab(db):
    """系統設定頁面"""
    st.subheader("⚙️ 系統設定")
    
    st.info("ℹ️ 請設定 LINE User ID，系統會在每日自動發送租金提醒。")
    st.divider()
    
    # 取得當前設定
    current_settings = get_all_settings(db)
    
    # === LINE 設定 ===
    with st.expander("📱 LINE 通知設定", expanded=True):
        st.write("**步驟 1：設定 LINE Channel Access Token**")
        st.caption("從 LINE Developers Console → Messaging API → Channel Access Token 取得")
        
        line_token = st.text_input(
            "LINE Channel Access Token",
            value=current_settings.get("line_channel_access_token", ""),
            type="password",
            key="line_token"
        )
        
        st.write("**步驟 2：設定房東 LINE User ID**")
        st.caption("加 LINE Bot 為好友後，發送訊息給 Bot，從 Webhook Log 取得")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            line_user_id = st.text_input(
                "房東 LINE User ID",
                value=current_settings.get("landlord_line_user_id", ""),
                placeholder="U1234567890abcdef...",
                key="line_user_id"
            )
        
        with col2:
            st.write("")
            st.write("")
            if st.button("💾 儲存設定", use_container_width=True):
                try:
                    save_setting(db, "line_channel_access_token", line_token)
                    save_setting(db, "landlord_line_user_id", line_user_id)
                    st.success("✅ LINE 設定已儲存")
                    st.rerun()
                except Exception as e:
                    st.error(f"儲存失敗: {e}")
        
        st.divider()
        if st.button("📤 發送測試訊息", disabled=not (line_token and line_user_id)):
            with st.spinner("發送中..."):
                success, msg = send_test_line_message(line_token, line_user_id)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
    
    # === 通知時間設定 ===
    with st.expander("⏰ 通知時間設定", expanded=False):
        cola, colb = st.columns(2)
        
        with cola:
            morning_time = st.time_input(
                "早上通知時間",
                value=datetime.strptime(current_settings.get("notification_time_morning", "09:00"), "%H:%M").time(),
                key="morning_time"
            )
        
        with colb:
            evening_time = st.time_input(
                "晚上通知時間",
                value=datetime.strptime(current_settings.get("notification_time_evening", "21:00"), "%H:%M").time(),
                key="evening_time"
            )
        
        st.caption("⚠️ 修改後需要更新 Supabase Cron Job 設定")
        
        if st.button("💾 儲存時間設定"):
            try:
                save_setting(db, "notification_time_morning", morning_time.strftime("%H:%M"))
                save_setting(db, "notification_time_evening", evening_time.strftime("%H:%M"))
                st.success("✅ 通知時間已儲存")
            except Exception as e:
                st.error(f"儲存失敗: {e}")
    
    # === 提前提醒天數 ===
    with st.expander("📅 提前提醒設定", expanded=False):
        reminder_days = st.number_input(
            "提前幾天發送催繳提醒",
            min_value=1,
            max_value=7,
            value=int(current_settings.get("reminder_days_before", "3")),
            key="reminder_days"
        )
        
        if st.button("💾 儲存提醒設定"):
            try:
                save_setting(db, "reminder_days_before", str(reminder_days))
                st.success("✅ 提醒設定已儲存")
            except Exception as e:
                st.error(f"儲存失敗: {e}")
    
    # === 啟用/停用通知 ===
    st.divider()
    
    col_enable, col_info = st.columns([1, 3])
    
    with col_enable:
        notification_enabled = st.checkbox(
            "啟用自動通知",
            value=current_settings.get("enable_tenant_notification", "true") == "true",
            key="notification_enabled"
        )
        
        if st.button("💾 儲存", key="save_enabled"):
            try:
                save_setting(db, "enable_tenant_notification", "true" if notification_enabled else "false")
                st.success("✅ 設定已更新")
            except Exception as e:
                st.error(f"儲存失敗: {e}")
    
    with col_info:
        if notification_enabled:
            st.success("🟢 自動通知已啟用")
        else:
            st.warning("🔴 自動通知已停用")


# ============== Tab 2: 手動觸發 ==============


def render_manual_tab(db):
    """手動觸發通知"""
    st.subheader("🚀 手動觸發通知")
    
    st.info("ℹ️ 可以手動觸發 Edge Function，立即發送通知（不需等到排程時間）。")
    st.divider()
    
    # 檢查設定
    settings = get_all_settings(db)
    has_line = settings.get("landlord_line_user_id") and settings.get("line_channel_access_token")
    
    if not has_line:
        st.warning("⚠️ 請先到「系統設定」Tab 設定 LINE Token 和 User ID")
        return
    
    # 顯示當前待通知項目
    st.subheader("📋 當前待通知項目")
    
    try:
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT 
                    room_number,
                    tenant_name,
                    payment_year,
                    payment_month,
                    amount,
                    due_date,
                    notification_type,
                    days_until_due
                FROM vw_payments_need_notification
                ORDER BY due_date
            """)
            
            columns = [desc[0] for desc in cur.description]
            data = cur.fetchall()
            df = pd.DataFrame(data, columns=columns)
        
        if df.empty:
            st.info("🎉 目前沒有需要通知的項目")
        else:
            col1, col2, col3 = st.columns(3)
            
            reminder_count = len(df[df['notification_type'] == 'reminder'])
            due_count = len(df[df['notification_type'] == 'due'])
            overdue_count = len(df[df['notification_type'] == 'overdue'])
            
            with col1:
                st.metric("📅 提前提醒", f"{reminder_count} 筆")
            with col2:
                st.metric("⏰ 今日到期", f"{due_count} 筆")
            with col3:
                st.metric("🚨 已逾期", f"{overdue_count} 筆")
            
            st.divider()
            st.dataframe(df, use_container_width=True, hide_index=True)
    
    except Exception as e:
        st.error(f"查詢失敗: {e}")
    
    st.divider()
    
    # 觸發按鈕
    st.subheader("⚡ 立即發送通知")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("☀️ 觸發早上通知", type="primary", use_container_width=True):
            st.info("💡 請到 Supabase Dashboard → Edge Functions → daily-payment-check → Invoke 手動觸發")
    
    with col2:
        if st.button("🌙 觸發晚上通知", type="primary", use_container_width=True):
            st.info("💡 請到 Supabase Dashboard → Edge Functions → daily-payment-check → Invoke 手動觸發")
    
    st.divider()
    
    # 最近記錄
    st.subheader("📜 最近觸發記錄")
    
    try:
        recent_logs = get_recent_notifications(db, limit=10)
        
        if not recent_logs.empty:
            display_df = recent_logs.copy()
            display_df["created_at"] = pd.to_datetime(display_df["created_at"]).dt.strftime("%Y-%m-%d %H:%M")
            display_df["status"] = display_df["status"].apply(
                lambda x: "✅ 已發送" if x == "sent" else "❌ 失敗" if x == "failed" else "⏳ 待發送"
            )
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.info("📭 尚無記錄")
    
    except Exception as e:
        st.error(f"載入失敗: {e}")


# ============== Tab 3: 通知記錄 ==============


def render_logs_tab(db):
    """通知記錄查看"""
    st.subheader("📜 通知記錄")
    
    # 篩選條件
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        filter_status = st.selectbox(
            "狀態",
            [None, "sent", "failed", "pending"],
            format_func=lambda x: "全部" if x is None else "✅ 已發送" if x == "sent" else "❌ 失敗" if x == "failed" else "⏳ 待發送",
            key="log_status"
        )
    
    with col2:
        filter_type = st.selectbox(
            "接收者類型",
            [None, "landlord", "tenant"],
            format_func=lambda x: "全部" if x is None else "🏠 房東" if x == "landlord" else "👤 房客",
            key="log_recipient"
        )
    
    with col3:
        days_back = st.number_input("查詢天數", min_value=1, max_value=90, value=7, key="log_days")
    
    with col4:
        limit = st.number_input("顯示筆數", min_value=10, max_value=500, value=100, key="log_limit")
    
    st.divider()
    
    # 查詢記錄
    try:
        df = get_notification_logs(db, days_back, filter_type, filter_status, limit)
        
        if df.empty:
            st.info("📭 查無記錄")
            return
        
        # 統計卡片
        cols1, cols2, cols3, cols4 = st.columns(4)
        
        with cols1:
            st.metric("📊 總記錄數", str(len(df)))
        
        with cols2:
            success_count = len(df[df["status"] == "sent"])
            st.metric("✅ 已發送", str(success_count))
        
        with cols3:
            failed_count = len(df[df["status"] == "failed"])
            st.metric("❌ 失敗", str(failed_count))
        
        with cols4:
            if len(df) > 0:
                success_rate = (success_count / len(df) * 100)
                st.metric("📈 成功率", f"{success_rate:.1f}%")
        
        st.divider()
        
        # 顯示記錄表格
        st.write(f"**共 {len(df)} 筆記錄**")
        
        display_df = df.copy()
        display_df["created_at"] = pd.to_datetime(display_df["created_at"]).dt.strftime("%Y-%m-%d %H:%M")
        display_df["status"] = display_df["status"].apply(
            lambda x: "✅ 已發送" if x == "sent" else "❌ 失敗" if x == "failed" else "⏳ 待發送"
        )
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        # 失敗記錄詳情
        st.divider()
        failed_df = df[df["status"] == "failed"]
        
        if not failed_df.empty:
            st.write(f"**❌ 失敗記錄詳情（{len(failed_df)} 筆）**")
            
            for idx, row in failed_df.iterrows():
                with st.expander(f"ID: {row['id']} - {row['notification_type']}"):
                    st.write(f"**接收者：** {row['recipient_type']} - {row['recipient_id']}")
                    if row.get('error_message'):
                        st.error(f"**錯誤：** {row['error_message']}")
    
    except Exception as e:
        st.error(f"查詢失敗: {e}")


# ============== 輔助函數 ==============


def get_all_settings(db) -> dict:
    """取得所有系統設定"""
    try:
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT setting_key, setting_value FROM notification_settings")
            settings = {}
            for row in cur.fetchall():
                settings[row[0]] = row[1]
            return settings
    except Exception as e:
        logger.error(f"取得設定失敗: {e}")
        return {}


def save_setting(db, key: str, value: str):
    """儲存單一設定"""
    try:
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO notification_settings (setting_key, setting_value, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (setting_key) 
                DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = NOW()
            """, (key, value))
            conn.commit()
    except Exception as e:
        logger.error(f"儲存設定失敗: {e}")
        raise


def send_test_line_message(access_token: str, user_id: str) -> tuple:
    """發送測試 LINE 訊息"""
    try:
        test_message = f"""🧪 測試訊息

這是一則測試通知，用於確認 LINE Bot 設定正確。

發送時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

如果您看到這則訊息，代表設定成功！✅"""
        
        response = requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}"
            },
            json={
                "to": user_id,
                "messages": [{"type": "text", "text": test_message}]
            },
            timeout=10
        )
        
        if response.status_code == 200:
            return True, "✅ 測試訊息已發送！請檢查 LINE 是否收到。"
        else:
            return False, f"❌ 發送失敗 (HTTP {response.status_code}): {response.text}"
    
    except Exception as e:
        return False, f"❌ 發送失敗: {str(e)}"


def get_recent_notifications(db, limit: int = 10) -> pd.DataFrame:
    """取得最近的通知記錄"""
    try:
        with db.get_connection() as conn:
            cur = conn.cursor()
            query = """
                SELECT 
                    id,
                    recipient_type,
                    notification_type,
                    status,
                    created_at
                FROM notification_logs
                ORDER BY created_at DESC
                LIMIT %s
            """
            cur.execute(query, (limit,))
            
            columns = [desc[0] for desc in cur.description]
            data = cur.fetchall()
            
            return pd.DataFrame(data, columns=columns)
    except Exception as e:
        logger.error(f"查詢最近通知失敗: {e}")
        return pd.DataFrame()


def get_notification_logs(db, days: int, recipient_type: str = None, status: str = None, limit: int = 100) -> pd.DataFrame:
    """查詢通知記錄"""
    try:
        with db.get_connection() as conn:
            cur = conn.cursor()
            
            conditions = ["created_at > NOW() - INTERVAL '%s days'"]
            params = [days]
            
            if recipient_type:
                conditions.append("recipient_type = %s")
                params.append(recipient_type)
            
            if status:
                conditions.append("status = %s")
                params.append(status)
            
            where_clause = " AND ".join(conditions)
            params.append(limit)
            
            query = f"""
                SELECT 
                    id,
                    recipient_type,
                    recipient_id,
                    notification_type,
                    title,
                    message,
                    status,
                    error_message,
                    created_at
                FROM notification_logs
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT %s
            """
            
            cur.execute(query, tuple(params))
            
            columns = [desc[0] for desc in cur.description]
            data = cur.fetchall()
            
            return pd.DataFrame(data, columns=columns)
    except Exception as e:
        logger.error(f"查詢通知記錄失敗: {e}")
        return pd.DataFrame()


# ============== 主函數 ==============


def render(db):
    """通知管理主頁面（供 main.py 呼叫）"""
    st.title("📬 通知管理")
    
    tab1, tab2, tab3 = st.tabs(["⚙️ 系統設定", "🚀 手動觸發", "📜 通知記錄"])
    
    with tab1:
        render_settings_tab(db)
    
    with tab2:
        render_manual_tab(db)
    
    with tab3:
        render_logs_tab(db)
