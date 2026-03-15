"""
electricity_repository.py - v1.0.0
電費相關資料存取層
遵循專案慣例：所有方法回傳 (ok: bool, data_or_msg)
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from psycopg2.extras import RealDictCursor

from services.base_db import BaseDBService
from services.logger import logger, log_db_operation


class ElectricityRepository(BaseDBService):
    """電費資料存取層（Repository Pattern）"""

    def _fetchall(
        self,
        query: str,
        params: tuple = (),
        *,
        table: str,
        operation: str = "SELECT",
    ) -> Tuple[bool, List[Dict] | str]:
        try:
            with self.get_connection() as conn:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute(query, params)
                rows = [dict(row) for row in cur.fetchall()]
                log_db_operation(operation, table, True, len(rows))
                return True, rows
        except Exception as e:
            log_db_operation(operation, table, False, error=str(e))
            logger.error(f"❌ {table} 查詢失敗: {str(e)}")
            return False, str(e)

    def _fetchone(
        self,
        query: str,
        params: tuple = (),
        *,
        table: str,
        operation: str = "SELECT",
        use_dict_cursor: bool = True,
    ) -> Tuple[bool, Dict | tuple | None | str]:
        try:
            with self.get_connection() as conn:
                if use_dict_cursor:
                    cur = conn.cursor(cursor_factory=RealDictCursor)
                else:
                    cur = conn.cursor()
                cur.execute(query, params)
                row = cur.fetchone()
                result = dict(row) if use_dict_cursor and row is not None else row
                log_db_operation(operation, table, True, 1 if row else 0)
                return True, result
        except Exception as e:
            log_db_operation(operation, table, False, error=str(e))
            logger.error(f"❌ {table} 單筆查詢失敗: {str(e)}")
            return False, str(e)

    def _execute(
        self,
        query: str,
        params: tuple = (),
        *,
        table: str,
        operation: str,
    ) -> Tuple[bool, int | str]:
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(query, params)
                affected = cur.rowcount
                log_db_operation(operation, table, True, affected)
                return True, affected
        except Exception as e:
            log_db_operation(operation, table, False, error=str(e))
            logger.error(f"❌ {table} 寫入失敗: {str(e)}")
            return False, str(e)

    def init_deposit_ledger_table(self) -> Tuple[bool, str]:
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS electricity_deposit_ledger (
                        id          SERIAL PRIMARY KEY,
                        room_number TEXT        NOT NULL,
                        date        TEXT        NOT NULL,
                        type        TEXT        NOT NULL
                                    CHECK (type IN ('預收電費', '扣電費')),
                        description TEXT,
                        credit      NUMERIC(10,2) NOT NULL DEFAULT 0,
                        debit       NUMERIC(10,2) NOT NULL DEFAULT 0,
                        period_id   INTEGER
                                    REFERENCES electricity_periods(id)
                                    ON DELETE SET NULL,
                        created_at  TIMESTAMP DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_edl_room
                    ON electricity_deposit_ledger(room_number)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_edl_room_date
                    ON electricity_deposit_ledger(room_number, date, id)
                    """
                )
                log_db_operation("CREATE TABLE", "electricity_deposit_ledger", True, 3)
                return True, "ok"
        except Exception as e:
            log_db_operation("CREATE TABLE", "electricity_deposit_ledger", False, error=str(e))
            logger.error(f"❌ 建立 electricity_deposit_ledger 失敗: {str(e)}")
            return False, str(e)

    def init_taipower_bills_table(self) -> Tuple[bool, str]:
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS electricity_taipower_bills (
                        id          SERIAL PRIMARY KEY,
                        period_id   INTEGER NOT NULL
                                    REFERENCES electricity_periods(id)
                                    ON DELETE CASCADE,
                        floor_label TEXT    NOT NULL,
                        amount      INTEGER NOT NULL DEFAULT 0,
                        kwh         NUMERIC(10,2) NOT NULL DEFAULT 0,
                        updated_at  TIMESTAMP DEFAULT NOW(),
                        UNIQUE (period_id, floor_label)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_etb_period
                    ON electricity_taipower_bills(period_id)
                    """
                )
                log_db_operation("CREATE TABLE", "electricity_taipower_bills", True, 2)
                return True, "ok"
        except Exception as e:
            log_db_operation("CREATE TABLE", "electricity_taipower_bills", False, error=str(e))
            logger.error(f"❌ 建立 electricity_taipower_bills 失敗: {str(e)}")
            return False, str(e)

    def save_taipower_bills(self, period_id: int, bills: List[Dict]) -> Tuple[bool, int | str]:
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                for bill in bills:
                    cur.execute(
                        """
                        INSERT INTO electricity_taipower_bills
                            (period_id, floor_label, amount, kwh, updated_at)
                        VALUES (%s, %s, %s, %s, NOW())
                        ON CONFLICT (period_id, floor_label) DO UPDATE SET
                            amount     = EXCLUDED.amount,
                            kwh        = EXCLUDED.kwh,
                            updated_at = NOW()
                        """,
                        (
                            period_id,
                            bill["floor_label"],
                            int(bill["amount"]),
                            float(bill["kwh"]),
                        ),
                    )
                log_db_operation("UPSERT", "electricity_taipower_bills", True, len(bills))
                return True, len(bills)
        except Exception as e:
            log_db_operation("UPSERT", "electricity_taipower_bills", False, error=str(e))
            logger.error(f"❌ 儲存台電帳單失敗: {str(e)}")
            return False, str(e)

    def get_taipower_bills(self, period_id: int) -> Tuple[bool, List[Dict] | str]:
        return self._fetchall(
            """
            SELECT floor_label, amount, kwh
            FROM electricity_taipower_bills
            WHERE period_id = %s
            ORDER BY floor_label
            """,
            (period_id,),
            table="electricity_taipower_bills",
        )

    def delete_taipower_bills(self, period_id: int) -> Tuple[bool, int | str]:
        return self._execute(
            "DELETE FROM electricity_taipower_bills WHERE period_id = %s",
            (period_id,),
            table="electricity_taipower_bills",
            operation="DELETE",
        )

    def add_deposit_entry(
        self,
        room_number: str,
        date_str: str,
        amount: float,
        description: str = "",
    ) -> Tuple[bool, int | str]:
        result = self._fetchone(
            """
            INSERT INTO electricity_deposit_ledger
                (room_number, date, type, description, credit, debit)
            VALUES (%s, %s, '預收電費', %s, %s, 0)
            RETURNING id
            """,
            (room_number, date_str, description, amount),
            table="electricity_deposit_ledger",
            operation="INSERT",
            use_dict_cursor=False,
        )
        if not result[0]:
            return False, result[1]
        row = result[1]
        return True, row[0] if row else 0

    def add_deduction_entry(
        self,
        room_number: str,
        date_str: str,
        amount: float,
        description: str = "",
        period_id: Optional[int] = None,
    ) -> Tuple[bool, int | str]:
        result = self._fetchone(
            """
            INSERT INTO electricity_deposit_ledger
                (room_number, date, type, description, credit, debit, period_id)
            VALUES (%s, %s, '扣電費', %s, 0, %s, %s)
            RETURNING id
            """,
            (room_number, date_str, description, amount, period_id),
            table="electricity_deposit_ledger",
            operation="INSERT",
            use_dict_cursor=False,
        )
        if not result[0]:
            return False, result[1]
        row = result[1]
        return True, row[0] if row else 0

    def get_deposit_balance(self, room_number: str) -> Tuple[bool, float | str]:
        result = self._fetchone(
            """
            SELECT COALESCE(SUM(credit - debit), 0)
            FROM electricity_deposit_ledger
            WHERE room_number = %s
            """,
            (room_number,),
            table="electricity_deposit_ledger",
            use_dict_cursor=False,
        )
        if not result[0]:
            return False, result[1]
        row = result[1]
        return True, float(row[0] if row else 0.0)

    def get_deposit_ledger(self, room_number: str) -> Tuple[bool, List[Dict] | str]:
        return self._fetchall(
            """
            SELECT
                id,
                date                                                    AS 日期,
                type                                                    AS 類型,
                COALESCE(description, '')                               AS 說明,
                CASE WHEN credit > 0 THEN credit ELSE NULL END          AS 預收電費,
                CASE WHEN debit  > 0 THEN debit  ELSE NULL END          AS 扣電費,
                SUM(credit - debit) OVER (
                    PARTITION BY room_number
                    ORDER BY date, id
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                )                                                       AS 餘款,
                period_id
            FROM electricity_deposit_ledger
            WHERE room_number = %s
            ORDER BY date, id
            """,
            (room_number,),
            table="electricity_deposit_ledger",
        )

    def get_deposit_entry(self, entry_id: int) -> Tuple[bool, Optional[Dict] | str]:
        return self._fetchone(
            """
            SELECT room_number, type, credit, debit
            FROM electricity_deposit_ledger
            WHERE id = %s
            """,
            (entry_id,),
            table="electricity_deposit_ledger",
        )

    def delete_deposit_entry(self, entry_id: int) -> Tuple[bool, int | str]:
        return self._execute(
            "DELETE FROM electricity_deposit_ledger WHERE id = %s",
            (entry_id,),
            table="electricity_deposit_ledger",
            operation="DELETE",
        )

    def get_all_rooms_deposit_summary(self) -> Tuple[bool, List[Dict] | str]:
        return self._fetchall(
            """
            SELECT
                l.room_number                   AS 房號,
                COALESCE(t.name, '')            AS 租客,
                SUM(l.credit)                   AS 預收總額,
                SUM(l.debit)                    AS 扣除總額,
                SUM(l.credit - l.debit)         AS 當前餘款,
                MAX(l.date)                     AS 最近一筆
            FROM electricity_deposit_ledger l
            LEFT JOIN tenants t ON l.room_number = t.room_number
            GROUP BY l.room_number, t.name
            ORDER BY l.room_number
            """,
            table="electricity_deposit_ledger",
        )

    def period_exists(
        self,
        year: int,
        month_start: int,
        month_end: int,
    ) -> Tuple[bool, bool | str]:
        result = self._fetchone(
            """
            SELECT COUNT(*)
            FROM electricity_periods
            WHERE period_year = %s
              AND period_month_start = %s
              AND period_month_end = %s
            """,
            (year, month_start, month_end),
            table="electricity_periods",
            use_dict_cursor=False,
        )
        if not result[0]:
            return False, result[1]
        row = result[1]
        return True, bool(row and row[0] > 0)

    def create_period(
        self,
        year: int,
        month_start: int,
        month_end: int,
        remind_start_date: Optional[str],
    ) -> Tuple[bool, int | str]:
        result = self._fetchone(
            """
            INSERT INTO electricity_periods
                (period_year, period_month_start, period_month_end, remind_start_date)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (year, month_start, month_end, remind_start_date),
            table="electricity_periods",
            operation="INSERT",
            use_dict_cursor=False,
        )
        if not result[0]:
            return False, result[1]
        row = result[1]
        return True, row[0] if row else 0

    def get_periods(self) -> Tuple[bool, List[Dict] | str]:
        return self._fetchall(
            """
            SELECT
                id,
                period_year,
                period_month_start,
                period_month_end,
                remind_start_date,
                created_at
            FROM electricity_periods
            ORDER BY period_year DESC, period_month_start DESC
            """,
            table="electricity_periods",
        )

    def get_period_by_id(self, period_id: int) -> Tuple[bool, Optional[Dict] | str]:
        return self._fetchone(
            """
            SELECT
                id,
                period_year,
                period_month_start,
                period_month_end,
                remind_start_date,
                created_at
            FROM electricity_periods
            WHERE id = %s
            """,
            (period_id,),
            table="electricity_periods",
        )

    def count_period_readings(self, period_id: int) -> Tuple[bool, int | str]:
        result = self._fetchone(
            "SELECT COUNT(*) FROM electricity_readings WHERE period_id = %s",
            (period_id,),
            table="electricity_readings",
            use_dict_cursor=False,
        )
        if not result[0]:
            return False, result[1]
        row = result[1]
        return True, int(row[0] if row else 0)

    def delete_period(self, period_id: int) -> Tuple[bool, int | str]:
        return self._execute(
            "DELETE FROM electricity_periods WHERE id = %s",
            (period_id,),
            table="electricity_periods",
            operation="DELETE",
        )

    def update_period_remind_date(
        self,
        period_id: int,
        remind_date: str,
    ) -> Tuple[bool, int | str]:
        return self._execute(
            """
            UPDATE electricity_periods
            SET remind_start_date = %s
            WHERE id = %s
            """,
            (remind_date, period_id),
            table="electricity_periods",
            operation="UPDATE",
        )

    def get_latest_meter_reading(
        self,
        room_number: str,
        period_id: int,
    ) -> Tuple[bool, Optional[float] | str]:
        result = self._fetchone(
            """
            SELECT current_reading
            FROM electricity_readings
            WHERE room_number = %s AND period_id < %s
            ORDER BY period_id DESC
            LIMIT 1
            """,
            (room_number, period_id),
            table="electricity_readings",
            use_dict_cursor=False,
        )
        if not result[0]:
            return False, result[1]
        row = result[1]
        return True, float(row[0]) if row else None

    def get_readings_by_period(self, period_id: int) -> Tuple[bool, List[Dict] | str]:
        return self._fetchall(
            """
            SELECT
                room_number,
                previous_reading,
                current_reading,
                kwh_used,
                COALESCE(payment_status, 'unpaid') AS payment_status,
                COALESCE(paid_amount, 0)           AS paid_amount,
                paid_at,
                created_at
            FROM electricity_readings
            WHERE period_id = %s
            ORDER BY room_number
            """,
            (period_id,),
            table="electricity_readings",
        )

    def upsert_reading(
        self,
        period_id: int,
        room_number: str,
        previous: float,
        current: float,
        kwh_used: float,
        unit_price: float,
        public_share_kwh: float,
        total_kwh: float,
        amount_due: int,
        room_type: str,
    ) -> Tuple[bool, int | str]:
        return self._execute(
            """
            INSERT INTO electricity_readings
                (period_id, room_number, previous_reading, current_reading,
                 kwh_used, unit_price, public_share_kwh, total_kwh,
                 amount_due, room_type,
                 payment_status, paid_amount, paid_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    'unpaid', 0, NULL)
            ON CONFLICT (period_id, room_number) DO UPDATE SET
                previous_reading = EXCLUDED.previous_reading,
                current_reading  = EXCLUDED.current_reading,
                kwh_used         = EXCLUDED.kwh_used,
                unit_price       = EXCLUDED.unit_price,
                public_share_kwh = EXCLUDED.public_share_kwh,
                total_kwh        = EXCLUDED.total_kwh,
                amount_due       = EXCLUDED.amount_due,
                room_type        = EXCLUDED.room_type,
                updated_at       = NOW()
            """,
            (
                period_id,
                room_number,
                previous,
                current,
                kwh_used,
                unit_price,
                public_share_kwh,
                total_kwh,
                amount_due,
                room_type,
            ),
            table="electricity_readings",
            operation="INSERT",
        )

    def mark_paid(
        self,
        period_id: int,
        room_number: str,
        paid_amount: int,
        payment_date: str,
    ) -> Tuple[bool, int | str]:
        return self._execute(
            """
            UPDATE electricity_readings
            SET
                payment_status = 'paid',
                paid_amount    = %s,
                paid_at        = %s,
                updated_at     = NOW()
            WHERE period_id = %s AND room_number = %s
            """,
            (paid_amount, payment_date, period_id, room_number),
            table="electricity_readings (mark_paid)",
            operation="UPDATE",
        )

    def mark_unpaid(self, period_id: int, room_number: str) -> Tuple[bool, int | str]:
        return self._execute(
            """
            UPDATE electricity_readings
            SET
                payment_status = 'unpaid',
                paid_amount    = 0,
                paid_at        = NULL,
                updated_at     = NOW()
            WHERE period_id = %s AND room_number = %s
            """,
            (period_id, room_number),
            table="electricity_readings (mark_unpaid)",
            operation="UPDATE",
        )

    def get_payment_record(self, period_id: int) -> Tuple[bool, List[Dict] | str]:
        return self._fetchall(
            """
            SELECT
                er.id,
                er.room_number                                              AS 房號,
                t.name                                                      AS 租客姓名,
                er.previous_reading                                         AS 上期讀數,
                er.current_reading                                          AS 本期讀數,
                er.kwh_used                                                 AS 使用度數,
                COALESCE(er.public_share_kwh, 0)                            AS 公用分擔,
                COALESCE(er.total_kwh, er.kwh_used)                         AS 總度數,
                COALESCE(er.unit_price, 0)                                  AS 單價,
                COALESCE(er.room_type, 'unknown')                           AS 類型,
                COALESCE(er.amount_due, 0)                                  AS 應繳金額,
                COALESCE(er.paid_amount, 0)                                 AS 已繳金額,
                CASE
                    WHEN COALESCE(er.payment_status, 'unpaid') = 'paid'
                    THEN '✅ 已繳'
                    ELSE '⏳ 未繳'
                END                                                         AS 繳費狀態,
                er.paid_at                                                  AS 繳費日期,
                ep.period_year,
                ep.period_month_start,
                ep.period_month_end
            FROM electricity_readings er
            LEFT JOIN electricity_periods ep ON er.period_id = ep.id
            LEFT JOIN tenants t ON er.room_number = t.room_number
            WHERE er.period_id = %s
            ORDER BY er.room_number
            """,
            (period_id,),
            table="electricity_readings",
        )

    def get_payment_summary(self, period_id: int) -> Tuple[bool, Optional[Dict] | str]:
        result = self._fetchone(
            """
            SELECT
                COUNT(*)                                                        AS total_count,
                SUM(COALESCE(amount_due, 0))                                    AS total_due,
                SUM(COALESCE(paid_amount, 0))                                   AS total_paid,
                COUNT(
                    CASE WHEN COALESCE(payment_status, 'unpaid') = 'paid'
                         THEN 1 END
                )                                                               AS paid_count,
                SUM(
                    CASE WHEN COALESCE(payment_status, 'unpaid') = 'unpaid'
                         THEN COALESCE(amount_due, 0) ELSE 0 END
                )                                                               AS total_balance,
                SUM(kwh_used)                                                   AS total_kwh_used
            FROM electricity_readings
            WHERE period_id = %s
            """,
            (period_id,),
            table="electricity_readings (summary)",
        )
        if not result[0]:
            return False, result[1]

        row = result[1]
        if not row or row["total_count"] == 0:
            return True, None

        total_count = int(row["total_count"])
        paid_count = int(row["paid_count"] or 0)
        payment_rate = paid_count / total_count * 100 if total_count > 0 else 0

        return True, {
            "total_count": total_count,
            "paid_count": paid_count,
            "unpaid_count": total_count - paid_count,
            "total_due": int(row["total_due"] or 0),
            "total_paid": int(row["total_paid"] or 0),
            "total_balance": int(row["total_balance"] or 0),
            "total_kwh_used": float(row["total_kwh_used"] or 0),
            "payment_rate": round(payment_rate, 1),
        }
