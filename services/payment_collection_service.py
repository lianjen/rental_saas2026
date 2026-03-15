"""
payment_collection_service.py - v1.0.0
租金收款服務
負責收款查詢、收款確認、報表與歷史資料
"""

from typing import Dict, List, Optional, Tuple

from services.base_db import BaseDBService
from services.logger import logger, log_db_operation


class PaymentCollectionService(BaseDBService):
    """租金收款服務"""

    def _get_payment_by_id_for_update(self, payment_id: int) -> Optional[Dict]:
        """供收款更新流程使用的單筆帳單查詢。"""
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

    def get_all_payments(self) -> List[Dict]:
        """取得所有租金記錄（自動過濾當前用戶）"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                user_id_check = ""
                params: List = []

                if not self.is_dev_mode():
                    user_id = self._get_current_user_id()
                    if user_id:
                        user_id_check = "WHERE user_id = %s"
                        params.append(user_id)

                cursor.execute(
                    f"""
                    SELECT
                        id, room_number, tenant_name,
                        payment_year, payment_month,
                        amount, paid_amount, payment_method,
                        due_date, status
                    FROM payment_schedule
                    {user_id_check}
                    ORDER BY payment_year DESC, payment_month DESC, room_number
                    """,
                    params,
                )
                columns = [d[0] for d in cursor.description]
                rows = cursor.fetchall()
                log_db_operation("SELECT", "payment_schedule (all)", True, len(rows))
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            log_db_operation("SELECT", "payment_schedule (all)", False, error=str(e))
            logger.error(f"取得所有租金記錄失敗: {e}")
            return []

    def get_unpaid_payments(self) -> List[Dict]:
        """取得所有未繳租金（自動過濾當前用戶）"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                conditions = ["status = 'unpaid'"]
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
                        id, room_number, tenant_name,
                        payment_year, payment_month,
                        amount, paid_amount, payment_method,
                        due_date, status
                    FROM payment_schedule
                    WHERE {where_clause}
                    ORDER BY due_date, room_number
                    """,
                    params,
                )
                columns = [d[0] for d in cursor.description]
                rows = cursor.fetchall()
                log_db_operation("SELECT", "payment_schedule (unpaid)", True, len(rows))
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            log_db_operation("SELECT", "payment_schedule (unpaid)", False, error=str(e))
            logger.error(f"取得未繳租金失敗: {e}")
            return []

    def get_paid_payments(self) -> List[Dict]:
        """取得所有已繳租金（自動過濾當前用戶）"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                conditions = ["status = 'paid'"]
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
                        id, room_number, tenant_name,
                        payment_year, payment_month,
                        amount, paid_amount, payment_method,
                        due_date, status
                    FROM payment_schedule
                    WHERE {where_clause}
                    ORDER BY payment_year DESC, payment_month DESC, room_number
                    """,
                    params,
                )
                columns = [d[0] for d in cursor.description]
                rows = cursor.fetchall()
                log_db_operation("SELECT", "payment_schedule (paid)", True, len(rows))
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            log_db_operation("SELECT", "payment_schedule (paid)", False, error=str(e))
            logger.error(f"取得已繳租金失敗: {e}")
            return []

    def get_payments_by_period(self, year: int, month: int) -> List[Dict]:
        """依年/月取得所有房間的租金記錄（本月摘要 tab 使用）"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                conditions = ["payment_year = %s", "payment_month = %s"]
                params = [year, month]

                if not self.is_dev_mode():
                    user_id = self._get_current_user_id()
                    if user_id:
                        conditions.append("user_id = %s")
                        params.append(user_id)

                where_clause = " AND ".join(conditions)

                cursor.execute(
                    f"""
                    SELECT
                        id, room_number, tenant_name,
                        payment_year, payment_month,
                        amount, paid_amount, payment_method,
                        due_date, status
                    FROM payment_schedule
                    WHERE {where_clause}
                    ORDER BY room_number
                    """,
                    params,
                )
                columns = [d[0] for d in cursor.description]
                rows = cursor.fetchall()
                log_db_operation("SELECT", "payment_schedule (by_period)", True, len(rows))
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            log_db_operation("SELECT", "payment_schedule (by_period)", False, error=str(e))
            logger.error(f"取得指定月份租金失敗: {e}")
            return []

    def get_room_payments(self, room_number: str, year: int, month: int) -> List[Dict]:
        """取得單一房號在某年/月的租金記錄"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                conditions = [
                    "room_number = %s",
                    "payment_year = %s",
                    "payment_month = %s",
                ]
                params = [room_number, year, month]

                if not self.is_dev_mode():
                    user_id = self._get_current_user_id()
                    if user_id:
                        conditions.append("user_id = %s")
                        params.append(user_id)

                where_clause = " AND ".join(conditions)

                cursor.execute(
                    f"""
                    SELECT
                        id, room_number, tenant_name,
                        payment_year, payment_month,
                        amount, paid_amount, payment_method,
                        due_date, status
                    FROM payment_schedule
                    WHERE {where_clause}
                    ORDER BY due_date
                    """,
                    params,
                )
                columns = [d[0] for d in cursor.description]
                rows = cursor.fetchall()
                log_db_operation("SELECT", "payment_schedule (room_period)", True, len(rows))
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            log_db_operation("SELECT", "payment_schedule (room_period)", False, error=str(e))
            logger.error(f"取得房間租金失敗: {e}")
            return []

    def get_monthly_summary(self, year: int, month: int) -> Dict:
        """本月摘要用的統計資料"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                conditions = ["payment_year = %s", "payment_month = %s"]
                params = [year, month]

                if not self.is_dev_mode():
                    user_id = self._get_current_user_id()
                    if user_id:
                        conditions.append("user_id = %s")
                        params.append(user_id)

                where_clause = " AND ".join(conditions)

                cursor.execute(
                    f"""
                    SELECT
                        COALESCE(SUM(amount), 0) AS total_expected,
                        COALESCE(
                            SUM(CASE WHEN status = 'paid' THEN paid_amount ELSE 0 END), 0
                        ) AS total_received,
                        COALESCE(
                            SUM(CASE WHEN status = 'unpaid' THEN 1 ELSE 0 END), 0
                        ) AS unpaid_count,
                        COALESCE(
                            SUM(CASE WHEN status = 'overdue' THEN 1 ELSE 0 END), 0
                        ) AS overdue_count
                    FROM payment_schedule
                    WHERE {where_clause}
                    """,
                    params,
                )
                row = cursor.fetchone()
                total_expected, total_received, unpaid_count, overdue_count = row

                total_expected = float(total_expected or 0)
                total_received = float(total_received or 0)
                collection_rate = (
                    total_received / total_expected if total_expected > 0 else 0.0
                )

                log_db_operation("SELECT", "payment_schedule (monthly_summary)", True, 1)
                return {
                    "total_expected": total_expected,
                    "total_received": total_received,
                    "unpaid_count": int(unpaid_count or 0),
                    "overdue_count": int(overdue_count or 0),
                    "collection_rate": collection_rate,
                }

        except Exception as e:
            log_db_operation("SELECT", "payment_schedule (monthly_summary)", False, error=str(e))
            logger.error(f"本月摘要查詢失敗: {e}")
            return {
                "total_expected": 0.0,
                "total_received": 0.0,
                "unpaid_count": 0,
                "overdue_count": 0,
                "collection_rate": 0.0,
            }

    def mark_payment_done(
        self,
        payment_id: int,
        paid_amount: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """將單筆租金標記為已繳款（自動驗證權限）"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                payment = self._get_payment_by_id_for_update(payment_id)
                if not payment:
                    return False, f"租金記錄 ID {payment_id} 不存在或無權限"

                original_amount = payment["amount"]
                room = payment["room_number"]
                actual_paid = paid_amount if paid_amount is not None else original_amount

                user_id_check = ""
                user_id = None

                if not self.is_dev_mode():
                    user_id = self._get_current_user_id()
                    if user_id:
                        user_id_check = "AND user_id = %s"

                if paid_amount is not None:
                    params = [paid_amount, payment_id]
                    if user_id_check and user_id:
                        params.append(user_id)
                    cursor.execute(
                        f"""
                        UPDATE payment_schedule
                        SET status = 'paid', paid_amount = %s, updated_at = NOW()
                        WHERE id = %s {user_id_check}
                        """,
                        params,
                    )
                else:
                    params = [payment_id]
                    if user_id_check and user_id:
                        params.append(user_id)
                    cursor.execute(
                        f"""
                        UPDATE payment_schedule
                        SET status = 'paid', paid_amount = amount, updated_at = NOW()
                        WHERE id = %s {user_id_check}
                        """,
                        params,
                    )

                if cursor.rowcount == 0:
                    return False, f"租金記錄 ID {payment_id} 不存在或無權限"

                log_db_operation("UPDATE", "payment_schedule", True, 1)
                logger.info(f"標記已繳: ID {payment_id} 房間 {room} 金額 {actual_paid:,.0f}")
                return True, "標記成功"

        except Exception as e:
            log_db_operation("UPDATE", "payment_schedule", False, error=str(e))
            logger.error(f"更新繳款狀態失敗: {str(e)}")
            return False, f"更新失敗: {str(e)[:100]}"

    def batch_mark_paid(self, payment_ids: List[int]) -> Dict[str, int]:
        """批次標記為已繳款（自動驗證權限）"""
        success_count = 0
        fail_count = 0

        try:
            user_id_check = ""

            if not self.is_dev_mode():
                user_id = self._get_current_user_id()
                if user_id:
                    user_id_check = f"AND user_id = '{user_id}'"

            with self.get_connection() as conn:
                cursor = conn.cursor()

                for payment_id in payment_ids:
                    try:
                        cursor.execute(
                            f"""
                            UPDATE payment_schedule
                            SET status = 'paid', paid_amount = amount, updated_at = NOW()
                            WHERE id = %s {user_id_check}
                            """,
                            (payment_id,),
                        )

                        if cursor.rowcount > 0:
                            success_count += 1
                        else:
                            fail_count += 1
                            logger.warning(f"ID {payment_id} 不存在或無權限")

                    except Exception as e:
                        logger.error(f"ID {payment_id} 標記失敗: {e}")
                        fail_count += 1

                log_db_operation("UPDATE", "payment_schedule (batch)", True, success_count)
                logger.info(f"批量標記已繳: 成功 {success_count} 筆, 失敗 {fail_count} 筆")
                return {"success": success_count, "failed": fail_count}

        except Exception as e:
            log_db_operation("UPDATE", "payment_schedule (batch)", False, error=str(e))
            logger.error(f"批量標記已繳失敗: {str(e)}")
            return {"success": 0, "failed": len(payment_ids)}

    def update_payment_amount(self, payment_id: int, new_amount: float) -> Tuple[bool, str]:
        """更新租金金額（僅限未繳款記錄，自動驗證權限）"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                user_id_check = ""
                params = [new_amount, payment_id]

                if not self.is_dev_mode():
                    user_id = self._get_current_user_id()
                    if user_id:
                        user_id_check = "AND user_id = %s"
                        params.append(user_id)

                cursor.execute(
                    f"""
                    UPDATE payment_schedule
                    SET amount = %s, updated_at = NOW()
                    WHERE id = %s AND status = 'unpaid' {user_id_check}
                    """,
                    params,
                )

                if cursor.rowcount == 0:
                    return False, "記錄不存在、已繳款或無權限"

                log_db_operation("UPDATE", "payment_schedule", True, 1)
                logger.info(f"更新金額: ID {payment_id} 新金額 {new_amount:,.0f}")
                return True, "更新成功"

        except Exception as e:
            log_db_operation("UPDATE", "payment_schedule", False, error=str(e))
            logger.error(f"更新租金金額失敗: {str(e)}")
            return False, f"更新失敗: {str(e)[:100]}"

    def delete_payment_schedule(self, payment_id: int) -> Tuple[bool, str]:
        """刪除租金排程（自動驗證權限）"""
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

                cursor.execute(
                    f"""
                    SELECT room_number, payment_year, payment_month
                    FROM payment_schedule
                    WHERE id = %s {user_id_check}
                    """,
                    params,
                )

                row = cursor.fetchone()
                if not row:
                    return False, f"租金記錄 ID {payment_id} 不存在或無權限"

                room, year, month = row

                cursor.execute(
                    f"DELETE FROM payment_schedule WHERE id = %s {user_id_check}",
                    params,
                )

                log_db_operation("DELETE", "payment_schedule", True, 1)
                logger.info(f"刪除帳單: ID {payment_id} 房間 {room} {year}/{month}")
                return True, "刪除成功"

        except Exception as e:
            log_db_operation("DELETE", "payment_schedule", False, error=str(e))
            logger.error(f"刪除租金排程失敗: {str(e)}")
            return False, f"刪除失敗: {str(e)[:100]}"

    def get_payment_statistics(
        self,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> Dict:
        """取得租金統計數據（自動過濾當前用戶）"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                conditions = ["1=1"]
                params: List = []

                if not self.is_dev_mode():
                    user_id = self._get_current_user_id()
                    if user_id:
                        conditions.append("user_id = %s")
                        params.append(user_id)

                if year:
                    conditions.append("payment_year = %s")
                    params.append(year)
                if month:
                    conditions.append("payment_month = %s")
                    params.append(month)

                where_clause = " AND ".join(conditions)

                cursor.execute(
                    f"""
                    SELECT
                        COUNT(*) AS total_count,
                        SUM(amount) AS total_amount,
                        SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END) AS paid_count,
                        SUM(CASE WHEN status = 'paid' THEN paid_amount ELSE 0 END) AS paid_amount,
                        SUM(CASE WHEN status = 'unpaid' THEN 1 ELSE 0 END) AS unpaid_count,
                        SUM(CASE WHEN status = 'unpaid' THEN amount ELSE 0 END) AS unpaid_amount
                    FROM payment_schedule
                    WHERE {where_clause}
                    """,
                    params,
                )

                row = cursor.fetchone()

                if not row or row[0] == 0:
                    logger.info("目前無租金統計數據")
                    return {
                        "total_amount": 0.0,
                        "paid_amount": 0.0,
                        "unpaid_amount": 0.0,
                        "total_count": 0,
                        "paid_count": 0,
                        "unpaid_count": 0,
                        "payment_rate": 0.0,
                    }

                (
                    total_count,
                    total_amount,
                    paid_count,
                    paid_amount,
                    unpaid_count,
                    unpaid_amount,
                ) = row

                payment_rate = paid_count / total_count * 100 if total_count > 0 else 0

                log_db_operation("SELECT", "payment_schedule (statistics)", True, 1)
                logger.info(f"統計: 繳款率 {payment_rate:.1f}% ({paid_count}/{total_count})")
                return {
                    "total_amount": float(total_amount or 0),
                    "paid_amount": float(paid_amount or 0),
                    "unpaid_amount": float(unpaid_amount or 0),
                    "total_count": int(total_count),
                    "paid_count": int(paid_count),
                    "unpaid_count": int(unpaid_count),
                    "payment_rate": round(payment_rate, 1),
                }

        except Exception as e:
            log_db_operation("SELECT", "payment_schedule (statistics)", False, error=str(e))
            logger.error(f"統計失敗: {str(e)}")
            return {
                "total_amount": 0.0,
                "paid_amount": 0.0,
                "unpaid_amount": 0.0,
                "total_count": 0,
                "paid_count": 0,
                "unpaid_count": 0,
                "payment_rate": 0.0,
            }

    def get_payment_trends(self, year: int) -> List[Dict]:
        """取得租金收款趨勢（按月彙總）"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                user_id_check = ""
                params = [year]

                if not self.is_dev_mode():
                    user_id = self._get_current_user_id()
                    if user_id:
                        user_id_check = "AND user_id = %s"
                        params.append(user_id)

                cursor.execute(
                    f"""
                    SELECT
                        payment_month,
                        SUM(amount) AS total_amount,
                        SUM(CASE WHEN status = 'paid' THEN paid_amount ELSE 0 END) AS paid_amount,
                        COUNT(*) AS total_count,
                        SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END) AS paid_count
                    FROM payment_schedule
                    WHERE payment_year = %s {user_id_check}
                    GROUP BY payment_month
                    ORDER BY payment_month
                    """,
                    params,
                )

                trends: List[Dict] = []
                for row in cursor.fetchall():
                    month, total_amt, paid_amt, total_cnt, paid_cnt = row
                    payment_rate = paid_cnt / total_cnt * 100 if total_cnt > 0 else 0
                    trends.append(
                        {
                            "month": int(month),
                            "total_amount": float(total_amt or 0),
                            "paid_amount": float(paid_amt or 0),
                            "total_count": int(total_cnt),
                            "paid_count": int(paid_cnt),
                            "payment_rate": round(payment_rate, 1),
                        }
                    )

                log_db_operation("SELECT", "payment_schedule (trends)", True, len(trends))
                logger.info(f"{year} 年趨勢查詢完成，{len(trends)} 個月")
                return trends

        except Exception as e:
            log_db_operation("SELECT", "payment_schedule (trends)", False, error=str(e))
            logger.error(f"租金趨勢查詢失敗: {str(e)}")
            return []

    def get_room_payment_history(
        self,
        room_number: str,
        limit: int = 12,
    ) -> List[Dict]:
        """查詢特定房間的繳款歷史"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                conditions = ["room_number = %s"]
                params = [room_number]

                if not self.is_dev_mode():
                    user_id = self._get_current_user_id()
                    if user_id:
                        conditions.append("user_id = %s")
                        params.append(user_id)

                params.append(limit)
                where_clause = " AND ".join(conditions)

                cursor.execute(
                    f"""
                    SELECT
                        payment_year, payment_month,
                        amount, paid_amount, status,
                        due_date, updated_at
                    FROM payment_schedule
                    WHERE {where_clause}
                    ORDER BY payment_year DESC, payment_month DESC
                    LIMIT %s
                    """,
                    params,
                )

                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()

                log_db_operation("SELECT", "payment_schedule (history)", True, len(rows))
                return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            log_db_operation("SELECT", "payment_schedule (history)", False, error=str(e))
            logger.error(f"房間歷史查詢失敗: {str(e)}")
            return []

    def get_tenant_history(
        self,
        room_number: str,
        limit: int = 12,
    ) -> List[Dict]:
        """房客繳款歷史（別名，供 views.rent.render_tenant_history_report 使用）"""
        return self.get_room_payment_history(room_number, limit=limit)
