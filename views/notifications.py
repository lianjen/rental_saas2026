"""
通知管理頁面 - v3.2
✅ 支援租金 + 電費通知查看
✅ 類別篩選功能
✅ 統計卡片優化
✅ 使用 Service 架構
✅ [FIX v3.1] use_container_width → width (共 6 處)
✅ [FIX v3.2] 修復 get_pending_notifications AttributeError
✅ [FIX v3.2] 修復 meta_json 欄位 Arrow 序列化失敗（混合 dict/str 型別）
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import requests
import logging

from services.notification_service import NotificationService
from services.payment_service import PaymentService

logger = logging.getLogger(__name__)


# ============== Tab 1: 系統設定 ==============

def render_settings_tab(notify_service: NotificationService):
    """系統設定頁面"""
    st.subheader("⚙️ 系統設定")

    st.info("ℹ️ 請設定 LINE User ID，系統會在每日自動發送租金提醒。")
    st.divider()

    current_settings = notify_service.get_all_settings()

    with st.expander("📱 LINE 通知設定", expanded=True):
        st.write("**步驟 1：設定 LINE Channel Access Token**")
        st.caption("從 LINE Developers Console → Messaging API → Channel Access Token 取得")

        line_token = st.text_input(
            "LINE Channel Access Token",
            value=current_settings.get("line_channel_access_token", ""),
            type="password",
            key="line_token",
        )

        st.write("**步驟 2：設定房東 LINE User ID**")
        st.caption("加 LINE Bot 為好友後，發送訊息給 Bot，從 Webhook Log 取得")

        col1, col2 = st.columns([3, 1])
        with col1:
            line_user_id = st.text_input(
                "房東 LINE User ID",
                value=current_settings.get("landlord_line_user_id", ""),
                placeholder="U1234567890abcdef...",
                key="line_user_id",
            )

        with col2:
            st.write("")
            st.write("")
            if st.button(
                "💾 儲存設定",
                width="stretch",
                key="save_line_settings",
            ):
                try:
                    notify_service.save_setting("line_channel_access_token", line_token)
                    notify_service.save_setting("landlord_line_user_id", line_user_id)
                    st.success("✅ LINE 設定已儲存")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 儲存失敗: {e}")
                    logger.exception("儲存 LINE 設定失敗")

        st.divider()
        if st.button("📤 發送測試訊息", disabled=not (line_token and line_user_id)):
            with st.spinner("發送中..."):
                success, msg = send_test_line_message(line_token, line_user_id)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)

    with st.expander("⏰ 通知時間設定", expanded=False):
        cola, colb = st.columns(2)

        with cola:
            morning_time = st.time_input(
                "早上通知時間",
                value=datetime.strptime(
                    current_settings.get("notification_time_morning", "09:00"), "%H:%M"
                ).time(),
                key="morning_time",
            )

        with colb:
            evening_time = st.time_input(
                "晚上通知時間",
                value=datetime.strptime(
                    current_settings.get("notification_time_evening", "21:00"), "%H:%M"
                ).time(),
                key="evening_time",
            )

        st.caption("⚠️ 修改後需要更新 Supabase Cron Job 設定")

        if st.button("💾 儲存時間設定"):
            try:
                notify_service.save_setting(
                    "notification_time_morning", morning_time.strftime("%H:%M")
                )
                notify_service.save_setting(
                    "notification_time_evening", evening_time.strftime("%H:%M")
                )
                st.success("✅ 通知時間已儲存")
            except Exception as e:
                st.error(f"❌ 儲存失敗: {e}")
                logger.exception("儲存通知時間失敗")

    with st.expander("📅 提前提醒設定", expanded=False):
        reminder_days = st.number_input(
            "提前幾天發送催繳提醒",
            min_value=1,
            max_value=7,
            value=int(current_settings.get("reminder_days_before", "3")),
            key="reminder_days",
        )

        if st.button("💾 儲存提醒設定"):
            try:
                notify_service.save_setting("reminder_days_before", str(reminder_days))
                st.success("✅ 提醒設定已儲存")
            except Exception as e:
                st.error(f"❌ 儲存失敗: {e}")
                logger.exception("儲存提醒設定失敗")

    st.divider()

    col_enable, col_info = st.columns([1, 3])

    with col_enable:
        notification_enabled = st.checkbox(
            "啟用自動通知",
            value=current_settings.get("enable_tenant_notification", "true") == "true",
            key="notification_enabled",
        )

        if st.button("💾 儲存", key="save_enabled"):
            try:
                notify_service.save_setting(
                    "enable_tenant_notification",
                    "true" if notification_enabled else "false",
                )
                st.success("✅ 設定已更新")
            except Exception as e:
                st.error(f"❌ 儲存失敗: {e}")
                logger.exception("儲存啟用狀態失敗")

    with col_info:
        if notification_enabled:
            st.success("🟢 自動通知已啟用")
        else:
            st.warning("🔴 自動通知已停用")


# ============== Tab 2: 手動觸發 ==============

def render_manual_tab(
    notify_service: NotificationService, payment_service: PaymentService
):
    """手動觸發通知"""
    st.subheader("🚀 手動觸發通知")

    st.info("ℹ️ 可以手動觸發 Edge Function，立即發送通知（不需等到排程時間）。")
    st.divider()

    settings = notify_service.get_all_settings()
    has_line = settings.get("landlord_line_user_id") and settings.get(
        "line_channel_access_token"
    )

    if not has_line:
        st.warning("⚠️ 請先到「系統設定」Tab 設定 LINE Token 和 User ID")
        return

    st.subheader("📋 當前待通知項目（租金）")

    try:
        pending_notifications = payment_service.get_pending_notifications()

        if not pending_notifications:
            st.info("🎉 目前沒有需要通知的租金項目")
        else:
            df = pd.DataFrame(pending_notifications)

            col1, col2, col3 = st.columns(3)

            reminder_count = (
                len(df[df["notification_type"] == "reminder"])
                if "notification_type" in df.columns
                else 0
            )
            due_count = (
                len(df[df["notification_type"] == "due"])
                if "notification_type" in df.columns
                else 0
            )
            overdue_count = (
                len(df[df["notification_type"] == "overdue"])
                if "notification_type" in df.columns
                else 0
            )

            with col1:
                st.metric("📅 提前提醒", f"{reminder_count} 筆")
            with col2:
                st.metric("⏰ 今日到期", f"{due_count} 筆")
            with col3:
                st.metric("🚨 已逾期", f"{overdue_count} 筆")

            st.divider()
            st.dataframe(
                df,
                width="stretch",
                hide_index=True,
            )

    except Exception as e:
        st.error(f"❌ 查詢失敗: {e}")
        logger.exception("查詢待通知項目失敗")

    st.divider()
    st.subheader("⚡ 立即發送通知")

    col1, col2 = st.columns(2)

    with col1:
        if st.button(
            "💰 觸發租金通知",
            type="primary",
            width="stretch",
        ):
            st.info(
                "💡 請到 Supabase Dashboard → Edge Functions → "
                "daily-payment-check → Invoke 手動觸發"
            )
            st.caption("或使用 supabase functions invoke daily-payment-check 命令")

    with col2:
        if st.button(
            "⚡ 觸發電費通知",
            type="primary",
            width="stretch",
        ):
            st.info(
                "💡 請到 Supabase Dashboard → Edge Functions → "
                "send-electricity-bill → Invoke 手動觸發"
            )
            st.caption("或使用 supabase functions invoke send-electricity-bill 命令")

    st.divider()
    st.subheader("📜 最近觸發記錄")

    try:
        recent_logs = notify_service.get_recent_notifications(limit=10)

        if not recent_logs:
            st.info("📭 尚無記錄")
        else:
            df = pd.DataFrame(recent_logs)
            df["created_at"] = pd.to_datetime(df["created_at"]).dt.strftime(
                "%Y-%m-%d %H:%M"
            )
            df["status"] = df["status"].apply(
                lambda x: "✅ 已發送"
                if x == "sent"
                else "❌ 失敗"
                if x == "failed"
                else "⏳ 待發送"
            )
            df["category"] = df["category"].apply(
                lambda x: "💰 租金"
                if x == "rent"
                else "⚡ 電費"
                if x == "electricity"
                else "📢 系統"
            )

            st.dataframe(
                df,
                width="stretch",
                hide_index=True,
            )

    except Exception as e:
        st.error(f"❌ 載入失敗: {e}")
        logger.exception("載入最近記錄失敗")


# ============== Tab 3: 通知記錄 ==============

def render_logs_tab(notify_service: NotificationService):
    """通知記錄查看"""
    st.subheader("📜 通知記錄")

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        filter_category = st.selectbox(
            "通知類別",
            [None, "rent", "electricity", "system"],
            format_func=lambda x: "全部"
            if x is None
            else "💰 租金"
            if x == "rent"
            else "⚡ 電費"
            if x == "electricity"
            else "📢 系統",
            key="log_category",
        )

    with col2:
        filter_status = st.selectbox(
            "狀態",
            [None, "sent", "failed", "pending"],
            format_func=lambda x: "全部"
            if x is None
            else "✅ 已發送"
            if x == "sent"
            else "❌ 失敗"
            if x == "failed"
            else "⏳ 待發送",
            key="log_status",
        )

    with col3:
        filter_type = st.selectbox(
            "接收者",
            [None, "landlord", "tenant"],
            format_func=lambda x: "全部"
            if x is None
            else "🏠 房東"
            if x == "landlord"
            else "👤 房客",
            key="log_recipient",
        )

    with col4:
        days_back = st.number_input(
            "查詢天數", min_value=1, max_value=90, value=7, key="log_days"
        )

    with col5:
        limit = st.number_input(
            "顯示筆數", min_value=10, max_value=500, value=100, key="log_limit"
        )

    st.divider()

    try:
        logs = notify_service.get_notification_logs(
            days=days_back,
            recipient_type=filter_type,
            status=filter_status,
            category=filter_category,
            limit=limit,
        )

        if not logs:
            st.info("📭 查無記錄")
            return

        df = pd.DataFrame(logs)

        cols1, cols2, cols3, cols4, cols5 = st.columns(5)

        with cols1:
            st.metric("📊 總記錄數", str(len(df)))
        with cols2:
            success_count = (
                len(df[df["status"] == "sent"]) if "status" in df.columns else 0
            )
            st.metric("✅ 已發送", str(success_count))
        with cols3:
            failed_count = (
                len(df[df["status"] == "failed"]) if "status" in df.columns else 0
            )
            st.metric("❌ 失敗", str(failed_count))
        with cols4:
            rent_count = (
                len(df[df["category"] == "rent"]) if "category" in df.columns else 0
            )
            st.metric("💰 租金", str(rent_count))
        with cols5:
            elec_count = (
                len(df[df["category"] == "electricity"])
                if "category" in df.columns
                else 0
            )
            st.metric("⚡ 電費", str(elec_count))

        st.divider()

        if len(df) > 0:
            success_rate = success_count / len(df) * 100
            st.info(
                f"📈 通知成功率：**{success_rate:.1f}%** ({success_count}/{len(df)})"
            )

        st.divider()
        st.write(f"**共 {len(df)} 筆記錄**")

        display_df = df.copy()

        # [FIX v3.2] meta_json 欄位可能混合 dict 和 str，統一轉成字串避免 Arrow 序列化失敗
        if "meta_json" in display_df.columns:
            display_df["meta_json"] = display_df["meta_json"].apply(
                lambda x: str(x) if x is not None else ""
            )

        if "created_at" in display_df.columns:
            display_df["created_at"] = pd.to_datetime(
                display_df["created_at"]
            ).dt.strftime("%Y-%m-%d %H:%M")

        if "status" in display_df.columns:
            display_df["status"] = display_df["status"].apply(
                lambda x: "✅ 已發送"
                if x == "sent"
                else "❌ 失敗"
                if x == "failed"
                else "⏳ 待發送"
            )

        if "category" in display_df.columns:
            display_df["category"] = display_df["category"].apply(
                lambda x: "💰 租金"
                if x == "rent"
                else "⚡ 電費"
                if x == "electricity"
                else "📢 系統"
                if x == "system"
                else "❓ 未知"
            )

        if "recipient_type" in display_df.columns:
            display_df["recipient_type"] = display_df["recipient_type"].apply(
                lambda x: "🏠 房東"
                if x == "landlord"
                else "👤 房客"
                if x == "tenant"
                else "❓ 未知"
            )

        column_order = [
            "created_at", "category", "recipient_type",
            "room_number", "title", "status",
        ]
        available_columns = [c for c in column_order if c in display_df.columns]
        remaining_columns = [c for c in display_df.columns if c not in available_columns]
        display_df = display_df[available_columns + remaining_columns]

        st.dataframe(
            display_df,
            width="stretch",
            hide_index=True,
        )

        st.divider()
        failed_df = (
            df[df["status"] == "failed"] if "status" in df.columns else pd.DataFrame()
        )

        if not failed_df.empty:
            st.write(f"**❌ 失敗記錄詳情（{len(failed_df)} 筆）**")

            for idx, row in failed_df.iterrows():
                category_emoji = (
                    "💰" if row.get("category") == "rent"
                    else "⚡" if row.get("category") == "electricity"
                    else "📢"
                )
                with st.expander(
                    f"{category_emoji} ID: {row['id']} - "
                    f"{row.get('title', row.get('notification_type', 'N/A'))}"
                ):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.write(f"**接收者：** {row.get('recipient_type', 'N/A')}")
                        st.write(f"**房號：** {row.get('room_number', 'N/A')}")
                    with col_b:
                        st.write(f"**類別：** {row.get('category', 'N/A')}")
                        st.write(f"**時間：** {row.get('created_at', 'N/A')}")

                    if row.get("error_message"):
                        st.error(f"**錯誤訊息：** {row['error_message']}")

                    if row.get("message"):
                        with st.expander("查看完整訊息"):
                            st.text(row["message"])

    except Exception as e:
        st.error(f"❌ 查詢失敗: {e}")
        logger.exception("查詢通知記錄時發生錯誤")


# ============== 輔助函數 ==============

def send_test_line_message(access_token: str, user_id: str) -> tuple:
    """發送測試 LINE 訊息"""
    try:
        test_message = (
            f"🧪 測試訊息\n\n"
            f"這是一則測試通知，用於確認 LINE Bot 設定正確。\n\n"
            f"發送時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"如果您看到這則訊息，代表設定成功！✅"
        )

        response = requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
            json={"to": user_id, "messages": [{"type": "text", "text": test_message}]},
            timeout=10,
        )

        if response.status_code == 200:
            return True, "✅ 測試訊息已發送！請檢查 LINE 是否收到。"
        else:
            return False, f"❌ 發送失敗 (HTTP {response.status_code}): {response.text}"

    except Exception as e:
        logger.error(f"發送測試訊息失敗: {e}")
        return False, f"❌ 發送失敗: {str(e)}"


# ============== 主函數 ==============

def render():
    """通知管理主頁面"""
    st.title("📬 通知管理")

    notify_service = NotificationService()
    payment_service = PaymentService()

    tab1, tab2, tab3 = st.tabs(["⚙️ 系統設定", "🚀 手動觸發", "📜 通知記錄"])

    with tab1:
        render_settings_tab(notify_service)
    with tab2:
        render_manual_tab(notify_service, payment_service)
    with tab3:
        render_logs_tab(notify_service)


def show():
    """Streamlit 頁面入口"""
    render()


if __name__ == "__main__":
    show()
