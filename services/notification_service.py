"""
統一通知服務 - v4.7 (transaction isolation 修正版)
✅ v4.6 所有功能保留
✅ [FIX v4.7] send_electricity_bill_notification 拆成三層獨立 connection:
   1. UPDATE electricity_periods (獨立 conn，失敗只 warning 不中斷)
   2. SELECT 待通知名單 (獨立 conn)
   3. 每筆 INSERT notification_logs (獨立 conn)
   → 根治 "current transaction is aborted" 連鎖失敗
"""

import os
import json
import requests
import streamlit as st
from typing import Optional, Dict, Tuple, List
from datetime import datetime

from services.base_db import BaseDBService
from services.logger import logger, log_db_operation


class NotificationService(BaseDBService):
    """統一通知服務 (繼承 BaseDBService)"""

    def __init__(self):
        super().__init__()
        self.line_token = self._load_line_token()

    # ──────────────────────────────────────────
    # Token 載入（三層 fallback）
    # ──────────────────────────────────────────

    def _load_line_token(self) -> Optional[str]:
        """1. env → 2. st.secrets → 3. system_settings DB"""
        token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
        if token:
            logger.info("✅ LINE Token 來源: 環境變數")
            return token

        try:
            token = st.secrets.get("LINE_CHANNEL_ACCESS_TOKEN")
            if token:
                logger.info("✅ LINE Token 來源: st.secrets")
                return token
        except Exception:
            pass

        try:
            token = self.get_setting("line_channel_access_token")
            if token:
                logger.info("✅ LINE Token 來源: system_settings DB")
                return token
        except Exception as e:
            logger.warning(f"⚠️ 讀取 DB LINE Token 失敗: {e}")

        logger.warning("⚠️ 未設定 LINE_CHANNEL_ACCESS_TOKEN，LINE 通知功能將無法使用")
        return None

    def _get_line_token(self) -> Optional[str]:
        """lazy-load: 若 self.line_token 為空，再嘗試 DB"""
        if self.line_token:
            return self.line_token
        try:
            token = self.get_setting("line_channel_access_token")
            if token:
                self.line_token = token
                logger.info("✅ LINE Token lazy-load 成功 (DB)")
                return token
        except Exception:
            pass
        return None

    # ──────────────────────────────────────────
    # 系統設定管理 (欄位: "key" / "value")
    # ──────────────────────────────────────────

    def get_all_settings(self) -> Dict[str, str]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT "key", "value"
                    FROM system_settings
                    ORDER BY "key"
                """)
                rows = cursor.fetchall()
                settings = {row[0]: row[1] for row in rows}
                log_db_operation("SELECT", "system_settings", True, len(settings))
                logger.info(f"✅ 載入系統設定: {len(settings)} 筆")
                return settings
        except Exception as e:
            log_db_operation("SELECT", "system_settings", False, error=str(e))
            logger.error(f"❌ 載入系統設定失敗: {str(e)}")
            return {}

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT "value"
                    FROM system_settings
                    WHERE "key" = %s
                """, (key,))
                result = cursor.fetchone()
                if result:
                    log_db_operation("SELECT", "system_settings", True, 1)
                    return result[0]
                logger.info(f"⚠️ 設定 {key} 不存在，使用預設值: {default}")
                return default
        except Exception as e:
            log_db_operation("SELECT", "system_settings", False, error=str(e))
            logger.error(f"❌ 讀取設定失敗 ({key}): {str(e)}")
            return default

    def save_setting(self, key: str, value: str) -> Tuple[bool, str]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO system_settings ("key", "value", updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT ("key")
                    DO UPDATE SET
                        "value"    = EXCLUDED."value",
                        updated_at = NOW()
                """, (key, value))
                log_db_operation("UPSERT", "system_settings", True, 1)
                logger.info(f"✅ 儲存設定: {key} = {value[:50]}")
                if key == "line_channel_access_token" and value:
                    self.line_token = value
                    logger.info("✅ 同步更新記憶體 LINE Token")
                return True, f"✅ 設定 {key} 已儲存"
        except Exception as e:
            log_db_operation("UPSERT", "system_settings", False, error=str(e))
            logger.error(f"❌ 儲存設定失敗 ({key}): {str(e)}")
            return False, f"❌ 儲存失敗: {str(e)[:100]}"

    def delete_setting(self, key: str) -> Tuple[bool, str]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM system_settings WHERE "key" = %s
                """, (key,))
                log_db_operation("DELETE", "system_settings", True, 1)
                logger.info(f"✅ 刪除設定: {key}")
                return True, f"✅ 設定 {key} 已刪除"
        except Exception as e:
            log_db_operation("DELETE", "system_settings", False, error=str(e))
            logger.error(f"❌ 刪除設定失敗 ({key}): {str(e)}")
            return False, f"❌ 刪除失敗: {str(e)[:100]}"

    # ──────────────────────────────────────────
    # 通知記錄查詢
    # ──────────────────────────────────────────

    def get_recent_notifications(self, limit: int = 10) -> List[Dict]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT
                        id, category, recipient_type, room_number,
                        notification_type, title, channel, status,
                        sent_at, created_at, error_message
                    FROM notification_logs
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                log_db_operation("SELECT", "notification_logs", True, len(rows))
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            log_db_operation("SELECT", "notification_logs", False, error=str(e))
            logger.error(f"❌ 查詢最近通知失敗: {str(e)}")
            return []

    def get_notification_logs(
        self,
        days: int = 7,
        recipient_type: Optional[str] = None,
        status: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                conditions = ["created_at >= NOW() - INTERVAL '%s days'"]
                params = [days]
                if recipient_type:
                    conditions.append("recipient_type = %s")
                    params.append(recipient_type)
                if status:
                    conditions.append("status = %s")
                    params.append(status)
                if category:
                    conditions.append("category = %s")
                    params.append(category)
                params.append(limit)
                query = f"""
                    SELECT
                        id, category, recipient_type, recipient_id, room_number,
                        notification_type, title, message, channel, status,
                        sent_at, created_at, error_message, meta_json
                    FROM notification_logs
                    WHERE {' AND '.join(conditions)}
                    ORDER BY created_at DESC
                    LIMIT %s
                """
                cursor.execute(query, params)
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                log_db_operation("SELECT", "notification_logs", True, len(rows))
                logger.info(f"✅ 查詢通知日誌: {len(rows)} 筆")
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            log_db_operation("SELECT", "notification_logs", False, error=str(e))
            logger.error(f"❌ 查詢通知日誌失敗: {str(e)}")
            return []

    # ──────────────────────────────────────────
    # 核心發送方法
    # ──────────────────────────────────────────

    def send_line_message(self, user_id: str, message: str) -> bool:
        token = self._get_line_token()
        if not token:
            logger.warning("⚠️ 未設定 LINE_CHANNEL_ACCESS_TOKEN")
            return False
        if not user_id:
            logger.warning("⚠️ LINE User ID 為空")
            return False
        try:
            response = requests.post(
                "https://api.line.me/v2/bot/message/push",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                json={"to": user_id, "messages": [{"type": "text", "text": message}]},
                timeout=10,
            )
            if response.status_code == 200:
                logger.info(f"✅ LINE 發送成功: {user_id}")
                return True
            else:
                logger.error(f"❌ LINE 發送失敗: {response.status_code} - {response.text}")
                return False
        except requests.exceptions.Timeout:
            logger.error(f"❌ LINE 發送逾時: {user_id}")
            return False
        except Exception as e:
            logger.error(f"❌ LINE 發送失敗: {e}")
            return False

    # ──────────────────────────────────────────
    # 私有工具：寫入單筆 notification_log（獨立 conn）
    # ──────────────────────────────────────────

    def _write_notification_log(
        self,
        category: str,
        recipient_type: str,
        recipient_id: str,
        room_number: str,
        notification_type: str,
        title: str,
        message: str,
        channel: str,
        status: str,
        error_message: Optional[str],
        meta_json: str,
    ) -> None:
        """每筆 log 用獨立 connection 寫入，確保不受外層 transaction 狀態影響"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO notification_logs
                    (category, recipient_type, recipient_id, room_number,
                     notification_type, title, message, channel, status,
                     sent_at, error_message, meta_json)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),%s,%s::jsonb)
                    """,
                    (category, recipient_type, recipient_id, room_number,
                     notification_type, title, message, channel,
                     status, error_message, meta_json),
                )
        except Exception as e:
            logger.error(f"❌ _write_notification_log 失敗: {e}")

    # ──────────────────────────────────────────
    # 電費通知 (v4.7 三層獨立 connection)
    # ──────────────────────────────────────────

    def send_electricity_bill_notification(
        self,
        period_id: int,
        remind_date: Optional[str] = None
    ) -> Tuple[bool, str, int]:
        # ── 預設催繳日期 ──────────────────────────
        if not remind_date:
            today = datetime.now()
            next_month = today.month + 1 if today.month < 12 else 1
            next_year = today.year if today.month < 12 else today.year + 1
            remind_date = f"{next_year:04d}-{next_month:02d}-01"

        # ── Step 1: UPDATE electricity_periods（獨立 conn，失敗不中斷） ──
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE electricity_periods SET remind_start_date = %s WHERE id = %s",
                    (remind_date, period_id),
                )
            logger.info(f"✅ 已更新催繳日期: period_id={period_id}, date={remind_date}")
        except Exception as e:
            logger.warning(f"⚠️ 更新 remind_start_date 失敗 (不中斷流程): {e}")

        # ── Step 2: SELECT 待通知名單（獨立 conn） ────────────────────
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT
                        er.id, er.room_number, er.amount_due,
                        t.id AS tenant_id, t.name AS tenant_name,
                        tc.line_user_id, tc.notify_electricity,
                        COALESCE(tc.is_verified, false) AS is_verified,
                        ep.period_year, ep.period_month_start, ep.period_month_end
                    FROM electricity_readings er
                    LEFT JOIN electricity_periods ep ON ep.id = er.period_id
                    LEFT JOIN tenants t
                        ON er.room_number = t.room_number AND t.status = 'active'
                    LEFT JOIN tenant_contacts tc ON t.id = tc.tenant_id
                    WHERE er.period_id = %s
                        AND tc.line_user_id IS NOT NULL
                        AND tc.notify_electricity = true
                        AND COALESCE(tc.is_verified, false) = true
                    """,
                    (period_id,),
                )
                records = cursor.fetchall()
        except Exception as e:
            logger.error(f"❌ 查詢待通知名單失敗: {e}")
            return False, f"❌ 查詢待通知名單失敗: {str(e)[:100]}", 0

        if not records:
            logger.info("📭 沒有需要通知的租客（無已驗證綁定）")
            return True, "📭 沒有需要通知的租客（無已驗證綁定）", 0

        logger.info(f"🔍 找到 {len(records)} 筆需要發送電費通知")

        # ── Step 3: 逐筆發送，每筆 log 用獨立 conn ────────────────────
        notified_count = 0
        failed_count = 0

        for record in records:
            (
                er_id, room, amount, tenant_id, tenant_name,
                line_id, _notify_elec, _is_verified,
                year, month_start, month_end,
            ) = record
            period_text = f"{year}/{month_start}-{month_end}"

            msg_body = (
                f"⚡ 電費帳單通知\n\n"
                f"房號：{room}\n租客：{tenant_name}\n"
                f"期間：{period_text}\n金額：NT${amount:,}\n\n"
                f"請於 7 天內完成繳費。\n如有疑問，請聯繫房東。"
            )
            meta_json = json.dumps({
                "period_id": period_id, "electricity_reading_id": er_id,
                "amount": float(amount) if amount else 0,
                "period_text": period_text,
                "tenant_id": tenant_id, "tenant_name": tenant_name,
            }, ensure_ascii=False)

            # 發送 LINE
            ok = self.send_line_message(line_id, msg_body)

            if ok:
                notified_count += 1
                logger.info(f"✅ 發送電費通知: {room} ({tenant_name})")
                # 更新 last_notified_at（獨立 conn，失敗不影響 log）
                try:
                    with self.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE electricity_readings SET last_notified_at = NOW() WHERE id = %s",
                            (er_id,)
                        )
                except Exception as e:
                    logger.warning(f"⚠️ 更新 last_notified_at 失敗: {e}")
                # 寫入成功 log（獨立 conn）
                self._write_notification_log(
                    'electricity', 'tenant', line_id, room,
                    'first_bill', f'{period_text} 電費帳單',
                    msg_body, 'line', 'sent', None, meta_json,
                )
            else:
                failed_count += 1
                logger.warning(f"⚠️ 發送失敗: {room} ({tenant_name})")
                # 寫入失敗 log（獨立 conn）
                self._write_notification_log(
                    'electricity', 'tenant', line_id or 'unknown', room,
                    'first_bill', f'{period_text} 電費帳單',
                    msg_body, 'line', 'failed', 'LINE API 回應失敗', meta_json,
                )

        log_db_operation("NOTIFICATION", "electricity_readings", True, notified_count)
        summary = f"✅ 電費通知完成: 成功 {notified_count} 位"
        if failed_count > 0:
            summary += f", 失敗 {failed_count} 位"
        logger.info(f"{summary}，催繳日期設為 {remind_date}")
        return True, summary, notified_count

    # ──────────────────────────────────────────
    # 租金催繳通知
    # ──────────────────────────────────────────

    def send_rent_reminder(
        self, payment_id: int, reminder_stage: str = "first"
    ) -> Tuple[bool, str]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT
                        ps.room_number, ps.tenant_name, ps.amount,
                        ps.due_date, ps.payment_year, ps.payment_month,
                        t.id AS tenant_id, tc.line_user_id, tc.notify_rent,
                        COALESCE(tc.is_verified, false) AS is_verified
                    FROM payment_schedule ps
                    LEFT JOIN tenants t
                        ON ps.room_number = t.room_number AND t.status = 'active'
                    LEFT JOIN tenant_contacts tc ON t.id = tc.tenant_id
                    WHERE ps.id = %s AND ps.status = 'unpaid'
                    """,
                    (payment_id,),
                )
                result = cursor.fetchone()
                if not result:
                    return False, "❌ 未找到租金記錄或已繳款"

                (room, tenant_name, amount, due_date, year, month,
                 tenant_id, line_id, notify_rent, is_verified) = result

                if not line_id:
                    return False, f"❌ {tenant_name} 未設定 LINE User ID"
                if not is_verified:
                    return False, f"ℹ️ {tenant_name} 尚未完成 LINE 綁定驗證"
                if not notify_rent:
                    return False, f"ℹ️ {tenant_name} 已關閉租金通知"

                overdue_days = (datetime.now().date() - due_date).days
                messages = {
                    "first": (
                        f"💰 租金繳納提醒\n\n親愛的 {tenant_name} 您好，\n\n"
                        f"本月租金即將到期：\n房號：{room}\n期間：{year}/{month}\n"
                        f"金額：NT${amount:,}\n到期日：{due_date}\n\n請準時繳納，謝謝！"
                    ),
                    "second": (
                        f"💰 租金催繳通知\n\n{tenant_name} 您好，\n\n"
                        f"您的租金已逾期：\n房號：{room}\n期間：{year}/{month}\n"
                        f"金額：NT${amount:,}\n逾期天數：{max(0,overdue_days)} 天\n\n"
                        f"麻煩盡快完成繳納，如有困難請聯繫房東。"
                    ),
                    "third": (
                        f"⚠️ 租金逾期警告\n\n{tenant_name} 您好，\n\n"
                        f"您的租金已嚴重逾期：\n房號：{room}\n期間：{year}/{month}\n"
                        f"金額：NT${amount:,}\n逾期天數：{max(0,overdue_days)} 天\n\n"
                        f"請於 2 天內完成繳納，否則將採取進一步措施。"
                    ),
                    "final": (
                        f"🚨 最終通知\n\n{tenant_name}，\n\n"
                        f"您的租金已逾期超過 7 天：\n房號：{room}\n期間：{year}/{month}\n"
                        f"金額：NT${amount:,}\n逾期天數：{max(0,overdue_days)} 天\n\n"
                        f"這是最終通知，房東將直接聯絡您。\n請立即處理。"
                    ),
                }
                message = messages.get(reminder_stage, messages["first"])

            # SELECT 完畢，conn 已關閉，以下用獨立 conn 發送 + log
            ok = self.send_line_message(line_id, message)
            meta_json = json.dumps({
                "payment_id": payment_id, "amount": float(amount),
                "due_date": str(due_date), "year": year, "month": month,
                "tenant_id": tenant_id, "tenant_name": tenant_name,
                "reminder_stage": reminder_stage, "overdue_days": max(0, overdue_days),
            }, ensure_ascii=False)

            self._write_notification_log(
                'rent', 'tenant', line_id, room,
                f'{reminder_stage}_reminder', f'{year}/{month} 租金提醒',
                message, 'line',
                'sent' if ok else 'failed',
                None if ok else 'LINE API 回應失敗',
                meta_json,
            )

            if ok:
                log_db_operation("NOTIFICATION", "payment_schedule", True, 1)
                return True, f"✅ 已發送 {reminder_stage} 階段催繳"
            else:
                log_db_operation("NOTIFICATION", "payment_schedule", False, error="LINE API 失敗")
                return False, "❌ LINE 發送失敗"

        except Exception as e:
            log_db_operation("NOTIFICATION", "payment_schedule", False, error=str(e))
            logger.error(f"❌ 租金催繳失敗: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False, f"❌ 租金催繳失敗: {str(e)[:100]}"

    # ──────────────────────────────────────────
    # 批次租金催繳
    # ──────────────────────────────────────────

    def batch_send_rent_reminders(
        self, payment_ids: List[int], reminder_stage: str = "first"
    ) -> Tuple[int, int, int]:
        success_count = skip_count = fail_count = 0
        for payment_id in payment_ids:
            try:
                ok, msg = self.send_rent_reminder(payment_id, reminder_stage)
                if ok:
                    success_count += 1
                elif any(kw in msg for kw in ["已關閉", "已繳款", "尚未完成 LINE 綁定驗證"]):
                    skip_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                logger.error(f"❌ 批次催繳失敗 ID {payment_id}: {e}")
                fail_count += 1
        logger.info(f"✅ 批次租金催繳: 成功 {success_count}, 跳過 {skip_count}, 失敗 {fail_count}")
        return success_count, skip_count, fail_count

    # ──────────────────────────────────────────
    # 通用通知方法
    # ──────────────────────────────────────────

    def send_custom_notification(
        self, category: str, recipient_type: str, recipient_id: str,
        room_number: str, title: str, message: str,
        channel: str = "line", meta_data: Optional[Dict] = None,
    ) -> Tuple[bool, str]:
        try:
            success = False
            error_msg = None
            if channel == "line":
                success = self.send_line_message(recipient_id, message)
                error_msg = None if success else "LINE API 回應失敗"
            elif channel == "email":
                error_msg = "Email 功能尚未實作"
            elif channel == "sms":
                error_msg = "SMS 功能尚未實作"
            else:
                error_msg = f"不支援的通道: {channel}"

            meta_json = json.dumps(meta_data or {}, ensure_ascii=False)
            self._write_notification_log(
                category, recipient_type, recipient_id, room_number,
                'custom', title, message, channel,
                'sent' if success else 'failed',
                error_msg, meta_json,
            )

            if success:
                log_db_operation("NOTIFICATION", "custom", True, 1)
                return True, "✅ 發送成功"
            else:
                log_db_operation("NOTIFICATION", "custom", False, error=error_msg)
                return False, f"❌ {error_msg or '發送失敗'}"
        except Exception as e:
            log_db_operation("NOTIFICATION", "custom", False, error=str(e))
            logger.error(f"❌ 自定義通知失敗: {str(e)}")
            return False, f"❌ {str(e)[:100]}"

    # ──────────────────────────────────────────
    # 查詢通知歷史（保留舊方法以兼容）
    # ──────────────────────────────────────────

    def get_notification_history(
        self, category: Optional[str] = None, room_number: Optional[str] = None,
        status: Optional[str] = None, limit: int = 100,
    ) -> List[Dict]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                conditions = ["1=1"]
                params = []
                if category:
                    conditions.append("category = %s")
                    params.append(category)
                if room_number:
                    conditions.append("room_number = %s")
                    params.append(room_number)
                if status:
                    conditions.append("status = %s")
                    params.append(status)
                params.append(limit)
                cursor.execute(
                    f"""
                    SELECT
                        id, category, recipient_type, room_number,
                        notification_type, title, channel, status,
                        sent_at, error_message, meta_json
                    FROM notification_logs
                    WHERE {' AND '.join(conditions)}
                    ORDER BY sent_at DESC, created_at DESC
                    LIMIT %s
                    """,
                    params,
                )
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                log_db_operation("SELECT", "notification_logs", True, len(rows))
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            log_db_operation("SELECT", "notification_logs", False, error=str(e))
            logger.error(f"❌ 查詢通知歷史失敗: {str(e)}")
            return []
