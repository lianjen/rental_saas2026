"""
通知管理頁面
- Streamlit 介面
- LINE/Email 設定與測試
- 手動觸發通知
- 通知記錄查看
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date
import requests
import logging

# 導入組件
try:
    from components.cards import section_header, metric_card, empty_state, data_table, info_card
except ImportError:
    def section_header(title, icon, divider=True):
        st.markdown(f"{icon} {title}")
        if divider:
            st.divider()
    
    def metric_card(label, value, delta, icon, color="normal"):
        st.metric(label, value, delta)
    
    def empty_state(msg, icon, desc):
        st.info(f"{icon} {msg}")
    
    def data_table(df, key="table"):
        st.dataframe(df, use_container_width=True, key=key)
    
    def info_card(title, content, icon, type="info"):
        st.info(f"{icon} {title}\n\n{content}")

logger = logging.getLogger(__name__)


# ============== Tab 1: 系統設定 ==============

def render_settings_tab(db):
    """系統設定頁面"""
    section_header("⚙️ 系統設定", "", divider=False)
    
    info_card(
        "設定說明",
        "請設定 LINE User ID 或 Email，系統會在每日自動發送租金提醒。",
        "ℹ️",
        type="info"
    )
    
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
            help="從 LINE Developers Console 取得",
            key="line_token"
        )
        
        st.write("**步驟 2：設定房東 LINE User ID**")
        st.caption("加 LINE Bot 為好友後，從 Webhook Log 取得 User ID")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            line_user_id = st.text_input(
                "房東 LINE User ID",
                value=current_settings.get("landlord_line_user_id", ""),
                placeholder="U1234567890abcdef...",
                help="從 LINE Webhook 取得",
                key="line_user_id"
            )
        
        with col2:
            st.write("")
            st.write("")
            if st.button("💾 儲存 LINE 設定"):
                save_setting(db, "line_channel_access_token", line_token)
                save_setting(db, "landlord_line_user_id", line_user_id)
                st.success("✅ LINE 設定已儲存")
                st.rerun()
        
        # 測試 LINE 訊息
        st.divider()
        if st.button("📤 發送測試訊息", disabled=not (line_token and line_user_id)):
            with st.spinner("發送中..."):
                success, msg = send_test_line_message(line_token, line_user_id)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
    
    # === Email 設定 ===
    with st.expander("📧 Email 通知設定（選用）", expanded=False):
        st.info("Email 通知功能尚未實作，敬請期待")
        
        landlord_email = st.text_input(
            "房東 Email",
            value=current_settings.get("landlord_email", ""),
            placeholder="landlord@example.com",
            key="landlord_email"
        )
        
        if st.button("💾 儲存 Email 設定"):
            save_setting(db, "landlord_email", landlord_email)
            st.success("✅ Email 設定已儲存")
    
    # === 通知時間設定 ===
    with st.expander("⏰ 通知時間設定", expanded=False):
        cola, colb = st.columns(2)
        
        with cola:
            morning_time = st.time_input(
                "早上通知時間",
                value=datetime.strptime(
                    current_settings.get("notification_time_morning", "09:00"), 
                    "%H:%M"
                ).time(),
                key="morning_time"
            )
        
        with colb:
            evening_time = st.time_input(
                "晚上通知時間",
                value=datetime.strptime(
                    current_settings.get("notification_time_evening", "21:00"), 
                    "%H:%M"
                ).time(),
                key="evening_time"
            )
        
        st.caption("⚠️ 修改後需要更新 Supabase Cron Job 設定")
        
        if st.button("💾 儲存時間設定"):
            save_setting(db, "notification_time_morning", morning_time.strftime("%H:%M"))
            save_setting(db, "notification_time_evening", evening_time.strftime("%H:%M"))
            st.success("✅ 通知時間已儲存")
    
    # === 啟用/停用通知 ===
    st.divider()
    
    col_enable, col_info = st.columns([1, 3])
    
    with col_enable:
        notification_enabled = st.checkbox(
            "啟用自動通知",
            value=current_settings.get("enable_tenant_notification", "true") == "true",
            key="notification_enabled"
        )
        
        if st.button("💾 儲存"):
            save_setting(db, "enable_tenant_notification", "true" if notification_enabled else "false")
            st.success("✅ 設定已更新")
    
    with col_info:
        if notification_enabled:
            st.success("🟢 自動通知已啟用")
        else:
            st.warning("🔴 自動通知已停用")


# ============== Tab 2: 手動觸發 ==============

def render_manual_tab(db):
    """手動觸發通知"""
    section_header("🚀 手動觸發通知", "", divider=False)
    
    info_card(
        "功能說明",
        "可以手動觸發 Edge Function，立即發送通知（不需等到排程時間）。",
        "ℹ️",
        type="info"
    )
    
    st.divider()
    
    # 檢查設定
    settings = get_all_settings(db)
    has_line = settings.get("landlord_line_user_id") and settings.get("line_channel_access_token")
    has_email = settings.get("landlord_email")
    
    if not (has_line or has_email):
        st.warning("⚠️ 請先到「系統設定」Tab 設定 LINE 或 Email")
        return
    
    # 觸發按鈕
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("☀️ 觸發早上通知", type="primary", disabled=not has_line):
            trigger_edge_function(db, "morning")
    
    with col2:
        if st.button("🌙 觸發晚上通知", type="primary", disabled=not has_line):
            trigger_edge_function(db, "evening")
    
    st.divider()
    
    # 顯示最近觸發記錄
    st.write("**最近觸發記錄**")
    
    try:
        recent_logs = get_recent_notifications(db, limit=5)
        
        if not recent_logs.empty:
            display_df = recent_logs.copy()
            display_df["created_at"] = pd.to_datetime(display_df["created_at"]).dt.strftime("%Y-%m-%d %H:%M")
            display_df["status"] = display_df["status"].apply(
                lambda x: "✅" if x == "sent" else "❌" if x == "failed" else "⏳"
            )
            
            show_cols = ["created_at", "notification_type", "status"]
            rename = {
                "created_at": "時間",
                "notification_type": "類型",
                "status": "狀態"
            }
            display_df = display_df.rename(columns=rename)
            data_table(display_df[list(rename.values())], key="recent_triggers")
        else:
            empty_state("尚無記錄", "📭", "")
    
    except Exception as e:
        st.error(f"載入失敗: {e}")


# ============== Tab 3: 通知記錄 ==============

def render_logs_tab(db):
    """通知記錄查看"""
    section_header("📜 通知記錄", "", divider=False)
    
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
            "通知類型",
            [None, "landlord_morning_summary", "landlord_evening_summary", "payment_reminder"],
            format_func=lambda x: "全部" if x is None else x,
            key="log_type"
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
            empty_state("查無記錄", "📭", "")
            return
        
        # 統計卡片
        cols1, cols2, cols3 = st.columns(3)
        
        with cols1:
            metric_card("總記錄數", str(len(df)), None, "📊", color="normal")
        
        with cols2:
            success_count = len(df[df["status"] == "sent"])
            metric_card("已發送", str(success_count), None, "✅", color="success")
        
        with cols3:
            failed_count = len(df[df["status"] == "failed"])
            metric_card("失敗", str(failed_count), None, "❌", color="error")
        
        st.divider()
        
        # 顯示記錄表格
        st.write(f"**共 {len(df)} 筆記錄**")
        
        display_df = df.copy()
        display_df["created_at"] = pd.to_datetime(display_df["created_at"]).dt.strftime("%Y-%m-%d %H:%M")
        display_df["status"] = display_df["status"].apply(
            lambda x: "✅ 已發送" if x == "sent" else "❌ 失敗" if x == "failed" else "⏳ 待發送"
        )
        
        # 選擇顯示欄位
        show_cols = ["id", "created_at", "recipient_type", "notification_type", "status"]
        rename = {
            "id": "ID",
            "created_at": "時間",
            "recipient_type": "接收者",
            "notification_type": "類型",
            "status": "狀態"
        }
        display_df = display_df.rename(columns=rename)
        data_table(display_df[list(rename.values())], key="notification_logs")
        
        # 失敗記錄處理
        st.divider()
        failed_df = df[df["status"] == "failed"]
        
        if not failed_df.empty:
            st.write(f"**失敗記
