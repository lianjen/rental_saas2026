"""
payment_reminder_service.py - v1.0.0
租金催繳服務
負責逾期租金偵測與待通知查詢
"""

from typing import Dict, List

from services.base_db import BaseDBService
from services.logger import logger, log_db_operation


class PaymentReminderService(BaseDBService):
    """租金催繳服務"""

    def get_overdue_payments(self) -> List[Dict]:
        """
        查詢逾期租金（自動過濾當前用戶）
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                user_id_check = ""
                params: List = []

                if not self.is_dev_mode():
                    user_id = self._get_current_user_id()
                    if user_id:
                        user_id_check = "AND user_id = %s"
                        params.append(user_id)

                cursor.execute(
                    f"""
                    SELECT
                        id,
                        room_number,
                        tenant_name,
                        payment_year,
                        payment_month,
                        amount,
                        paid_amount,
                        payment_method,
                        due_date,
                        status,
                        (CURRENT_DATE - due_date) AS days_overdue
                    FROM payment_schedule
                    WHERE status = 'unpaid'
                      AND due_date <= CURRENT_DATE
                      {user_id_check}
                    ORDER BY due_date
                    """,
                    params,
                )

                columns = [desc[0] for desc in cursor.description]
                data = cursor.fetchall()

                log_db_operation("SELECT", "payment_schedule (overdue)", True, len(data))

                if data:
                    logger.warning(f"{len(data)} 筆逾期帳單")
                else:
                    logger.info("目前無逾期帳單")

                return [dict(zip(columns, row)) for row in data]

        except Exception as e:
            log_db_operation("SELECT", "payment_schedule (overdue)", False, error=str(e))
            logger.error(f"查詢逾期租金失敗: {str(e)}")
            return []

    def get_pending_notifications(self) -> List[Dict]:
        """
        查詢待通知的租金項目（未繳 + 逾期），供 views.notifications 使用
        notification_type 說明：
          - overdue  : status='overdue' 或 due_date < 今天
          - due      : 今天到期
          - reminder : 未來到期（尚未逾期）
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                conditions = ["status IN ('unpaid', 'overdue')"]
                params: List = []

                if not self.is_dev_mode():
                    user_id = self._get_current_user_id()
                    if user_id:
                        conditions.append("user_id = %s")
                        params.append(user_id)

                where_clause = " AND ".join(conditions)

                cursor.execute(
                    f"""
                    SELECT
                        id,
                        room_number,
                        tenant_name,
                        payment_year,
                        payment_month,
                        amount,
                        due_date,
                        status,
                        CASE
                            WHEN status = 'overdue' OR (due_date IS NOT NULL AND due_date < CURRENT_DATE)
                                THEN 'overdue'
                            WHEN due_date = CURRENT_DATE
                                THEN 'due'
                            ELSE 'reminder'
                        END AS notification_type
                    FROM payment_schedule
                    WHERE {where_clause}
                    ORDER BY due_date NULLS LAST, room_number
                    """,
                    params,
                )

                columns = [d[0] for d in cursor.description]
                rows = cursor.fetchall()
                log_db_operation("SELECT", "payment_schedule (pending_notifications)", True, len(rows))
                logger.info(f"✅ 查詢待通知租金: {len(rows)} 筆")
                return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            log_db_operation("SELECT", "payment_schedule (pending_notifications)", False, error=str(e))
            logger.error(f"查詢待通知項目失敗: {e}")
            return []
