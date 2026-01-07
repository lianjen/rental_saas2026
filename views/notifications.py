"""
通知管理 - Streamlit 頁面
功能:
- 通知設定 (LINE/Email)
- 測試通知發送
- 通知記錄查詢
- 重送失敗通知
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date
import requests
import logging

# 安全 import
try:
    from components.cards import section_header, metric_card, empty_state, data_table, info_card
except ImportError:
    def section_header(title, icon="", divider=True):
        st.markdown(f"### {icon} {title}")
        if divider: st.divider()
    def metric_card(label, value, delta="", icon="", color="normal"):
        st.metric(label, value, delta)
    def empty_state(msg, icon="", desc=""):
        st.info(f"{icon} {msg}")
    def data_table(df, key="table"):
        st.dataframe(df, use_container_width=True, key=key)
    def info_card(title, content, icon="", type="info"):
        st.info(f"{icon} {title}: {content}")

logger = logging.getLogger(__name__)

# ============== Tab 1: 通知設定 ==============

def render_settings_tab(db):
    """通知設定 Tab"""
    section_header("通知設定", "⚙️")
    
    info_card(
        "💡 設定說明",
        "設定房東的 LINE User ID 和 Email,系統將每日自動發送到期/逾期提醒。",
        "💡",
        "info"
    )
    
    st.divider()
    
    # 取得現有設定
    current_settings = get_all_settings(db)
    
    # === LINE 設定 ===
    with st.expander("📱 LINE 通知設定", expanded=True):
        st.write("**步驟 1: 設定 LINE Channel Access Token**")
        st.caption("前往 LINE Developers Console 建立 Messaging API Channel,取得 Channel Access Token")
        
        line_token = st.text_input(
            "LINE Channel Access Token",
            value=current_settings.get('line_channel_access_token', ''),
            type="password",
            help="從 LINE Developers Console 取得",
            key="line_token"
        )
        
        st.write("**步驟 2: 設定房東 LINE User ID**")
        st.caption("將 LINE Bot 加為好友後,發送任意訊息以取得 User ID")
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            line_user_id = st.text_input(
                "房東 LINE User ID",
                value=current_settings.get('landlord_line_user_id', ''),
                placeholder="U1234567890abcdef...",
                help="從 LINE Webhook 取得",
                key="line_user_id"
            )
        
        with col2:
            st.write("")
            st.write("")
            if st.button("💾 儲存 LINE 設定"):
                save_setting(db, 'line_channel_access_token', line_token)
                save_setting(db, 'landlord_line_user_id', line_user_id)
                st.success("✅ 已儲存 LINE 設定")
                st.rerun()
        
        # 測試 LINE 通知
        st.divider()
        if st.button("🧪 測試 LINE 通知", disabled=not (line_token and line_user_id)):
            with st.spinner("發送測試訊息中..."):
                success, msg = send_test_line_message(line_token, line_user_id)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
    
    # === Email 設定 ===
    with st.expander("📧 Email 通知設定", expanded=False):
        st.info("📌 Email 功能開發中,敬請期待！")
        
        landlord_email = st.text_input(
            "房東 Email",
            value=current_settings.get('landlord_email', ''),
            placeholder="landlord@example.com",
            key="landlord_email"
        )
        
        if st.button("💾 儲存 Email 設定"):
            save_setting(db, 'landlord_email', landlord_email)
            st.success("✅ 已儲存 Email 設定")
    
    # === 通知時間設定 ===
    with st.expander("⏰ 通知時間設定", expanded=False):
        col_a, col_b = st.columns(2)
        
        with col_a:
            morning_time = st.time_input(
                "早上通知時間",
                value=datetime.strptime(current_settings.get('notification_time_morning', '09:00'), "%H:%M").time(),
                key="morning_time"
            )
        
        with col_b:
            evening_time = st.time_input(
                "晚上通知時間",
                value=datetime.strptime(current_settings.get('notification_time_evening', '21:00'), "%H:%M").time(),
                key="evening_time"
            )
        
        st.caption("⚠️ 修改時間後需更新 Supabase Cron Job 設定")
        
        if st.button("💾 儲存通知時間"):
            save_setting(db, 'notification_time_morning', morning_time.strftime("%H:%M"))
            save_setting(db, 'notification_time_evening', evening_time.strftime("%H:%M"))
            st.success("✅ 已儲存通知時間")
    
    # === 啟用/停用通知 ===
    st.divider()
    
    col_enable, col_info = st.columns([1, 3])
    
    with col_enable:
        notification_enabled = st.checkbox(
            "啟用自動通知",
            value=current_settings.get('notification_enabled', 'true') == 'true',
            key="notification_enabled"
        )
        
        if st.button("💾 儲存狀態"):
            save_setting(db, 'notification_enabled', 'true' if notification_enabled else 'false')
            st.success("✅ 已更新通知狀態")
    
    with col_info:
        if notification_enabled:
            st.success("✅ 自動通知已啟用")
        else:
            st.warning("⚠️ 自動通知已停用")


# ============== Tab 2: 手動觸發 ==============

def render_manual_tab(db):
    """手動觸發 Tab"""
    section_header("手動觸發通知", "🚀")
    
    info_card(
        "💡 功能說明",
        "手動觸發 Edge Function,測試通知系統是否正常運作。",
        "💡",
        "info"
    )
    
    st.divider()
    
    # 取得 Supabase 設定
    settings = get_all_settings(db)
    
    # 檢查是否設定完整
    has_line = settings.get('landlord_line_user_id') and settings.get('line_channel_access_token')
    has_email = settings.get('landlord_email')
    
    if not (has_line or has_email):
        st.warning("⚠️ 請先在「通知設定」Tab 完成 LINE 或 Email 設定")
        return
    
    # 手動觸發按鈕
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🌅 觸發早上通知", type="primary", disabled=not has_line):
            trigger_edge_function(db, "morning")
    
    with col2:
        if st.button("🌙 觸發晚上通知", type="primary", disabled=not has_line):
            trigger_edge_function(db, "evening")
    
    st.divider()
    
    # 顯示最近一次觸發結果
    st.write("**最近觸發記錄**")
    
    try:
        recent_logs = get_recent_notifications(db, limit=5)
        
        if not recent_logs.empty:
            display_df = recent_logs.copy()
            display_df['時間'] = pd.to_datetime(display_df['created_at']).dt.strftime('%Y-%m-%d %H:%M')
            display_df['狀態'] = display_df['status'].apply(
                lambda x: '✅ 成功' if x == 'SUCCESS' else '❌ 失敗' if x == 'FAILED' else '⏳ 處理中'
            )
            
            show_cols = ['時間', 'channel', 'notification_type', '狀態']
            rename = {
                'channel': '通道',
                'notification_type': '類型'
            }
            
            display_df = display_df.rename(columns=rename)
            data_table(display_df[show_cols], key="recent_triggers")
        else:
            empty_state("尚無觸發記錄", "📭")
    
    except Exception as e:
        st.error(f"❌ 查詢記錄失敗: {e}")


# ============== Tab 3: 通知記錄 ==============

def render_logs_tab(db):
    """通知記錄 Tab"""
    section_header("通知記錄", "📜")
    
    # 篩選條件
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        filter_channel = st.selectbox(
            "通道",
            [None, "LINE", "EMAIL"],
            format_func=lambda x: "全部" if x is None else x,
            key="log_channel"
        )
    
    with col2:
        filter_status = st.selectbox(
            "狀態",
            [None, "SUCCESS", "FAILED", "PENDING"],
            format_func=lambda x: "全部" if x is None else x,
            key="log_status"
        )
    
    with col3:
        days_back = st.number_input(
            "查詢天數",
            min_value=1,
            max_value=90,
            value=7,
            key="log_days"
        )
    
    with col4:
        limit = st.number_input(
            "顯示筆數",
            min_value=10,
            max_value=500,
            value=100,
            key="log_limit"
        )
    
    st.divider()
    
    # 查詢
    try:
        df = get_notification_logs(db, days_back, filter_channel, filter_status, limit)
        
        if df.empty:
            empty_state("沒有符合條件的記錄", "📭")
            return
        
        # 統計
        col_s1, col_s2, col_s3 = st.columns(3)
        
        with col_s1:
            metric_card("總筆數", str(len(df)), icon="📋")
        
        with col_s2:
            success_count = len(df[df['status'] == 'SUCCESS'])
            metric_card("成功", str(success_count), icon="✅", color="success")
        
        with col_s3:
            failed_count = len(df[df['status'] == 'FAILED'])
            metric_card("失敗", str(failed_count), icon="❌", color="error")
        
        st.divider()
        
        # 顯示表格
        st.write(f"共 {len(df)} 筆記錄")
        
        display_df = df.copy()
        display_df['時間'] = pd.to_datetime(display_df['created_at']).dt.strftime('%Y-%m-%d %H:%M')
        display_df['狀態'] = display_df['status'].apply(
            lambda x: '✅ 成功' if x == 'SUCCESS' else '❌ 失敗' if x == 'FAILED' else '⏳ 處理中'
        )
        
        # 選擇要顯示的欄位
        show_cols = ['id', '時間', 'channel', 'notification_type', 'recipient', '狀態']
        rename = {
            'channel': '通道',
            'notification_type': '類型',
            'recipient': '收件人'
        }
        
        display_df = display_df.rename(columns=rename)
        
        data_table(display_df[show_cols], key="notification_logs")
        
        # 重送失敗通知
        st.divider()
        
        failed_df = df[df['status'] == 'FAILED']
        
        if not failed_df.empty:
            st.write("**重送失敗通知**")
            
            failed_ids = st.multiselect(
                "選擇要重送的通知",
                failed_df['id'].tolist(),
                format_func=lambda x: f"ID {x} - {failed_df[failed_df['id']==x]['notification_type'].values[0]}",
                key="retry_ids"
            )
            
            if st.button("🔄 重送", disabled=len(failed_ids) == 0):
                st.info("💡 重送功能開發中")
    
    except Exception as e:
        st.error(f"❌ 查詢失敗: {e}")


# ============== 輔助函數 ==============

def get_all_settings(db) -> dict:
    """取得所有系統設定"""
    try:
        with db._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT setting_key, setting_value FROM system_settings")
            
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
        with db._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE system_settings
                SET setting_value = %s, updated_at = NOW()
                WHERE setting_key = %s
            """, (value, key))
    except Exception as e:
        logger.error(f"儲存設定失敗: {e}")
        raise


def send_test_line_message(access_token: str, user_id: str) -> tuple:
    """發送測試 LINE 訊息"""
    try:
        response = requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}"
            },
            json={
                "to": user_id,
                "messages": [
                    {
                        "type": "text",
                        "text": f"[測試訊息 {datetime.now().strftime('%H:%M:%S')}]\n\n✅ 租屋系統通知功能運作正常！"
                    }
                ]
            },
            timeout=10
        )
        
        if response.status_code == 200:
            return (True, "✅ 測試訊息發送成功！請檢查 LINE")
        else:
            return (False, f"❌ 發送失敗: HTTP {response.status_code}\n{response.text}")
    
    except Exception as e:
        return (False, f"❌ 發送失敗: {str(e)}")


def trigger_edge_function(db, trigger_type: str):
    """手動觸發 Edge Function"""
    st.info("💡 手動觸發功能需要 Supabase Function URL,請參考部署文檔設定")
    # TODO: 實作手動觸發邏輯


def get_recent_notifications(db, limit: int = 10) -> pd.DataFrame:
    """取得最近通知記錄"""
    try:
        with db._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, channel, notification_type, status, created_at
                FROM notifications_log
                ORDER BY created_at DESC
                LIMIT %s
            """, (limit,))
            
            columns = [desc[0] for desc in cur.description]
            data = cur.fetchall()
            
            return pd.DataFrame(data, columns=columns)
    except Exception as e:
        logger.error(f"查詢記錄失敗: {e}")
        return pd.DataFrame()


def get_notification_logs(db, days: int, channel: str = None, 
                         status: str = None, limit: int = 100) -> pd.DataFrame:
    """取得通知記錄"""
    try:
        with db._get_connection() as conn:
            cur = conn.cursor()
            
            conditions = [f"created_at >= NOW() - INTERVAL '{days} days'"]
            params = []
            
            if channel:
                conditions.append("channel = %s")
                params.append(channel)
            
            if status:
                conditions.append("status = %s")
                params.append(status)
            
            where_clause = " AND ".join(conditions)
            params.append(limit)
            
            cur.execute(f"""
                SELECT id, channel, notification_type, recipient, 
                       status, error_message, created_at
                FROM notifications_log
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT %s
            """, params)
            
            columns = [desc[0] for desc in cur.description]
            data = cur.fetchall()
            
            return pd.DataFrame(data, columns=columns)
    except Exception as e:
        logger.error(f"查詢記錄失敗: {e}")
        return pd.DataFrame()


# ============== 主函數 ==============

def render(db):
    """主渲染函數"""
    st.title("📬 通知管理")
    
    tab1, tab2, tab3 = st.tabs(["⚙️ 通知設定", "🚀 手動觸發", "📜 通知記錄"])
    
    with tab1:
        render_settings_tab(db)
    
    with tab2:
        render_manual_tab(db)
    
    with tab3:
        render_logs_tab(db)
