"""
payment_schedule_service.py - v1.0.0
租金排程服務
負責租金排程查詢、建立與批次產生
"""

import calendar
from datetime import date
from typing import Dict, List, Optional, Tuple

import pandas as pd

from services.base_db import BaseDBService
from services.logger import logger, log_db_operation


class PaymentScheduleService(BaseDBService):
    """租金排程服務"""

    def get_payment_schedule(
        self,
        year: Optional[int] = None,
        month: Optional[int] = None,
        room: Optional[str] = None,
        status: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        查詢租金排程（自動過濾當前用戶，回傳 DataFrame）
        """

        def query():
            with self.get_connection() as conn:
                cursor = conn.cursor()

                conditions = ["1=1"]
                params: List = []

                if not self.is_dev_mode():
                    user_id = self._get_current_user_id()
                    if user_id:
                        conditions.append("user_id = %s")
                        params.append(user_id)
                    else:
                        logger.warning("⚠️ 未登入，返回空結果")
                        return pd.DataFrame()

                if year:
                    conditions.append("payment_year = %s")
                    params.append(year)
                if month:
                    conditions.append("payment_month = %s")
                    params.append(month)
                if room:
                    conditions.append("room_number = %s")
                    params.append(room)
                if status:
                    conditions.append("status = %s")
                    params.append(status)

                query_sql = f"""
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
                        created_at,
                        updated_at
                    FROM payment_schedule
                    WHERE {' AND '.join(conditions)}
                    ORDER BY payment_year DESC, payment_month DESC, room_number
                """

                cursor.execute(query_sql, params)
                columns = [desc[0] for desc in cursor.description]
                data = cursor.fetchall()

                log_db_operation("SELECT", "payment_schedule", True, len(data))
                logger.info(f"查詢租金排程 {len(data)} 筆")
                return pd.DataFrame(data, columns=columns)

        return self.retry_on_failure(query)

    def get_payment_by_id(self, payment_id: int) -> Optional[Dict]:
        """
        根據 ID 查詢單筆租金記錄（自動驗證權限）
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                user_id_check = ""
                params = [payment_id]

                if not self.is_dev_mode():
                    user_id = self._get_current_user_id()
                    if user_id:
                        user_id_check = "AND user_id = %s"
                        params.append(user_id)
                    else:
                        logger.warning("⚠️ 未登入，無法查詢")
                        return None

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
                        status
                    FROM payment_schedule
                    WHERE id = %s {user_id_check}
                    """,
                    params,
                )

                row = cursor.fetchone()

                if not row:
                    logger.warning(f"找不到租金記錄 ID: {payment_id} 或無權限")
                    return None

                columns = [desc[0] for desc in cursor.description]
                log_db_operation("SELECT", "payment_schedule", True, 1)
                return dict(zip(columns, row))

        except Exception as e:
            log_db_operation("SELECT", "payment_schedule", False, error=str(e))
            logger.error(f"查詢失敗: {str(e)}")
            return None

    def add_payment_schedule(
        self,
        room: str,
        tenant_name: str,
        year: int,
        month: int,
        amount: float,
        payment_method: str,
        due_date: Optional[date] = None,
    ) -> Tuple[bool, str]:
        """新增租金排程（自動注入 user_id）"""
        try:
            user_id = self._get_current_user_id()

            if not user_id and not self.is_dev_mode():
                return False, "請先登入"

            with self.get_connection() as conn:
                cursor = conn.cursor()

                check_conditions = [
                    "room_number = %s", "payment_year = %s", "payment_month = %s"
                ]
                check_params = [room, year, month]

                if not self.is_dev_mode() and user_id:
                    check_conditions.append("user_id = %s")
                    check_params.append(user_id)

                cursor.execute(
                    f"""
                    SELECT COUNT(*) FROM payment_schedule
                    WHERE {' AND '.join(check_conditions)}
                    """,
                    check_params,
                )

                if cursor.fetchone()[0] > 0:
                    logger.warning(f"{room} {year}/{month} 已有記錄")
                    return False, f"{year}/{month} {room} 已存在"

                cursor.execute(
                    """
                    INSERT INTO payment_schedule
                    (user_id, room_number, tenant_name, payment_year, payment_month, amount,
                     paid_amount, payment_method, due_date, status)
                    VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s, 'unpaid')
                    """,
                    (user_id, room, tenant_name, year, month, amount, payment_method, due_date),
                )

                log_db_operation("INSERT", "payment_schedule", True, 1)
                logger.info(f"新增帳單: {room} {year}/{month} 金額 {amount:,.0f}")
                return True, "新增成功"

        except Exception as e:
            log_db_operation("INSERT", "payment_schedule", False, error=str(e))
            logger.error(f"新增租金排程失敗: {str(e)}")
            return False, f"新增失敗: {str(e)[:100]}"

    def create_monthly_schedule(
        self,
        room_number: str,
        year: int,
        month: int,
    ) -> Tuple[bool, str]:
        """
        高階 API：依房號 + 年月，自動從 tenants 取資料建立租金排程
        ✅ [FIX] 欄位改為 rent（原 rent_amount），移除不存在的 payment_method
        ✅ [NEW] due_date 從 tenants.rent_due_day 讀取，預設 1 號，移除 hardcode
        """
        try:
            user_id = self._get_current_user_id()

            if not user_id and not self.is_dev_mode():
                return False, "請先登入"

            with self.get_connection() as conn:
                cursor = conn.cursor()

                tenant_conditions = [
                    "room_number = %s", "status = 'active'"
                ]
                tenant_params = [room_number]

                if not self.is_dev_mode() and user_id:
                    tenant_conditions.append("user_id = %s")
                    tenant_params.append(user_id)

                cursor.execute(
                    f"""
                    SELECT name, rent, COALESCE(rent_due_day, 1) AS rent_due_day
                    FROM tenants
                    WHERE {' AND '.join(tenant_conditions)}
                    """,
                    tenant_params,
                )
                tenant = cursor.fetchone()

                if not tenant:
                    logger.warning(f"房間 {room_number} 無有效房客，略過")
                    return False, f"房間 {room_number} 無有效房客"

                tenant_name, rent_amount, rent_due_day = tenant

                check_conditions = [
                    "room_number = %s", "payment_year = %s", "payment_month = %s"
                ]
                check_params = [room_number, year, month]

                if not self.is_dev_mode() and user_id:
                    check_conditions.append("user_id = %s")
                    check_params.append(user_id)

                cursor.execute(
                    f"""
                    SELECT COUNT(*) FROM payment_schedule
                    WHERE {' AND '.join(check_conditions)}
                    """,
                    check_params,
                )
                if cursor.fetchone()[0] > 0:
                    logger.info(f"{room_number} {year}/{month} 已存在，略過")
                    return True, f"{room_number} {year}/{month} 已存在"

                try:
                    due_day = int(rent_due_day)
                    last_day = calendar.monthrange(year, month)[1]
                    due_day = min(due_day, last_day)
                    due = date(year, month, due_day)
                except Exception:
                    due = None

                cursor.execute(
                    """
                    INSERT INTO payment_schedule
                    (user_id, room_number, tenant_name, payment_year, payment_month, amount,
                     paid_amount, payment_method, due_date, status)
                    VALUES (%s, %s, %s, %s, %s, %s, 0, NULL, %s, 'unpaid')
                    """,
                    (user_id, room_number, tenant_name, year, month, rent_amount, due),
                )

                log_db_operation("INSERT", "payment_schedule (create_monthly)", True, 1)
                logger.info(
                    f"建立排程: {room_number} {year}/{month} "
                    f"金額 {rent_amount:,.0f} 到期日 {due}"
                )
                return True, "新增成功"

        except Exception as e:
            log_db_operation("INSERT", "payment_schedule (create_monthly)", False, error=str(e))
            logger.error(f"建立月租排程失敗: {str(e)}")
            return False, f"建立排程失敗: {str(e)[:100]}"

    def batch_create_payment_schedule(
        self,
        schedules: List[Dict],
    ) -> Tuple[int, int, int]:
        """
        批次建立租金排程（自動注入 user_id）

        Returns:
            (success_count, skip_count, fail_count)
        """
        success_count = 0
        skip_count = 0
        fail_count = 0

        try:
            user_id = self._get_current_user_id()

            if not user_id and not self.is_dev_mode():
                logger.error("未登入，無法批次建立")
                return 0, 0, len(schedules)

            with self.get_connection() as conn:
                cursor = conn.cursor()

                for schedule in schedules:
                    try:
                        check_conditions = [
                            "room_number = %s",
                            "payment_year = %s",
                            "payment_month = %s",
                        ]
                        check_params = [
                            schedule["room_number"],
                            schedule["payment_year"],
                            schedule["payment_month"],
                        ]

                        if not self.is_dev_mode() and user_id:
                            check_conditions.append("user_id = %s")
                            check_params.append(user_id)

                        cursor.execute(
                            f"""
                            SELECT COUNT(*) FROM payment_schedule
                            WHERE {' AND '.join(check_conditions)}
                            """,
                            check_params,
                        )

                        if cursor.fetchone()[0] > 0:
                            logger.debug(
                                f"跳過既有記錄: {schedule['room_number']} "
                                f"{schedule['payment_year']}/{schedule['payment_month']}"
                            )
                            skip_count += 1
                            continue

                        cursor.execute(
                            """
                            INSERT INTO payment_schedule
                            (user_id, room_number, tenant_name, payment_year, payment_month,
                             amount, paid_amount, payment_method, due_date, status)
                            VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s, 'unpaid')
                            """,
                            (
                                user_id,
                                schedule["room_number"],
                                schedule["tenant_name"],
                                schedule["payment_year"],
                                schedule["payment_month"],
                                schedule["amount"],
                                schedule.get("payment_method"),
                                schedule["due_date"],
                            ),
                        )

                        success_count += 1

                    except Exception as e:
                        logger.error(f"{schedule.get('room_number', '?')} 建立失敗: {e}")
                        fail_count += 1

                log_db_operation("INSERT", "payment_schedule (batch)", True, success_count)
                logger.info(
                    f"批量新增租金排程: 成功 {success_count} 筆, 跳過 {skip_count} 筆, 失敗 {fail_count} 筆"
                )
                return success_count, skip_count, fail_count

        except Exception as e:
            log_db_operation("INSERT", "payment_schedule (batch)", False, error=str(e))
            logger.error(f"批量新增租金排程失敗: {str(e)}")
            return 0, 0, len(schedules)

    def check_payment_exists(self, room: str, year: int, month: int) -> bool:
        """檢查指定房號在某年/月是否已存在租金記錄"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                conditions = [
                    "room_number = %s", "payment_year = %s", "payment_month = %s"
                ]
                params = [room, year, month]

                if not self.is_dev_mode():
                    user_id = self._get_current_user_id()
                    if user_id:
                        conditions.append("user_id = %s")
                        params.append(user_id)

                where_clause = " AND ".join(conditions)

                cursor.execute(
                    f"SELECT COUNT(*) FROM payment_schedule WHERE {where_clause}",
                    params,
                )

                exists = cursor.fetchone()[0] > 0
                logger.debug(f"檢查 {room} {year}/{month} 是否存在: {'是' if exists else '否'}")
                return exists

        except Exception as e:
            logger.error(f"檢查租金記錄是否存在失敗: {str(e)}")
            return False
