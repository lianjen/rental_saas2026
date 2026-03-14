"""
電費管理服務 - v5.4
✅ v5.0 所有功能保留
✅ [NEW v5.4] electricity_taipower_bills 台電帳單持久化
    - _init_taipower_bills_table: 自動建表
    - save_taipower_bills:   UPSERT 一整期的 4 筆帳單
    - get_taipower_bills:    讀取指定 period_id 的帳單 → List[Dict]
    - delete_taipower_bills: 刪除整期帳單（重新輸入時使用）
"""

import pandas as pd
from typing import Optional, Tuple, List, Dict
from datetime import datetime, date

from services.base_db import BaseDBService
from services.logger import logger, log_db_operation


class ElectricityService(BaseDBService):

    def __init__(self):
        super().__init__()
        self._init_deposit_ledger_table()
        self._init_taipower_bills_table()

    # ==================== 內部建表 ====================

    def _init_deposit_ledger_table(self) -> None:
        """首次實例化時自動建立 electricity_deposit_ledger 資料表"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
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
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_edl_room
                    ON electricity_deposit_ledger(room_number)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_edl_room_date
                    ON electricity_deposit_ledger(room_number, date, id)
                """)
                conn.commit()
                logger.info("✅ electricity_deposit_ledger 資料表檢查完成")
        except Exception as e:
            logger.error(f"❌ 建表失敗: {str(e)}")

    def _init_taipower_bills_table(self) -> None:
        """自動建立 electricity_taipower_bills 台電帳單資料表"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
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
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_etb_period
                    ON electricity_taipower_bills(period_id)
                """)
                conn.commit()
                logger.info("✅ electricity_taipower_bills 資料表檢查完成")
        except Exception as e:
            logger.error(f"❌ 建立 taipower_bills 表失敗: {str(e)}")

    # ==================== 台電帳單 CRUD ====================

    def save_taipower_bills(
        self,
        period_id: int,
        bills: List[Dict],
    ) -> Tuple[bool, str]:
        """
        UPSERT 一整期台電帳單
        bills 格式: [{"floor_label": "1F", "amount": 1200, "kwh": 85.0}, ...]
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                for b in bills:
                    cursor.execute(
                        """
                        INSERT INTO electricity_taipower_bills
                            (period_id, floor_label, amount, kwh, updated_at)
                        VALUES (%s, %s, %s, %s, NOW())
                        ON CONFLICT (period_id, floor_label) DO UPDATE SET
                            amount     = EXCLUDED.amount,
                            kwh        = EXCLUDED.kwh,
                            updated_at = NOW()
                        """,
                        (period_id, b["floor_label"], int(b["amount"]), float(b["kwh"])),
                    )
                conn.commit()
                log_db_operation("UPSERT", "electricity_taipower_bills", True, len(bills))
                logger.info(f"✅ 台電帳單已儲存: period={period_id}, {len(bills)} 筆")
                return True, f"✅ 已儲存 {len(bills)} 個台電單"
        except Exception as e:
            log_db_operation("UPSERT", "electricity_taipower_bills", False, error=str(e))
            logger.error(f"❌ 儲存台電帳單失敗: {str(e)}")
            return False, f"❌ {str(e)[:100]}"

    def get_taipower_bills(self, period_id: int) -> List[Dict]:
        """
        讀取指定期間的台電帳單
        返回: [{"floor_label": "1F", "amount": 1200, "kwh": 85.0}, ...]
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT floor_label, amount, kwh
                    FROM electricity_taipower_bills
                    WHERE period_id = %s
                    ORDER BY floor_label
                    """,
                    (period_id,),
                )
                rows = cursor.fetchall()
                result = [
                    {"floor_label": row[0], "amount": int(row[1]), "kwh": float(row[2])}
                    for row in rows
                ]
                log_db_operation("SELECT", "electricity_taipower_bills", True, len(result))
                logger.info(f"✅ 載入台電帳單: period={period_id}, {len(result)} 筆")
                return result
        except Exception as e:
            log_db_operation("SELECT", "electricity_taipower_bills", False, error=str(e))
            logger.error(f"❌ 讀取台電帳單失敗: {str(e)}")
            return []

    def delete_taipower_bills(self, period_id: int) -> Tuple[bool, str]:
        """刪除整期台電帳單（重新輸入時使用）"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM electricity_taipower_bills WHERE period_id = %s",
                    (period_id,),
                )
                deleted = cursor.rowcount
                conn.commit()
                log_db_operation("DELETE", "electricity_taipower_bills", True, deleted)
                logger.info(f"✅ 刪除台電帳單: period={period_id}, {deleted} 筆")
                return True, f"✅ 已刪除 {deleted} 筆"
        except Exception as e:
            log_db_operation("DELETE", "electricity_taipower_bills", False, error=str(e))
            logger.error(f"❌ 刪除台電帳單失敗: {str(e)}")
            return False, f"❌ {str(e)[:100]}"

    # ==================== 預收電費帳戶 ====================

    def add_deposit(
        self,
        room_number: str,
        date_str:    str,
        amount:      float,
        description: str = "",
    ) -> Tuple[bool, str, Optional[int]]:
        try:
            if amount <= 0:
                return False, "❌ 金額必須大於 0", None
            datetime.strptime(date_str, "%Y-%m-%d")

            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO electricity_deposit_ledger
                        (room_number, date, type, description, credit, debit)
                    VALUES (%s, %s, '預收電費', %s, %s, 0)
                    RETURNING id
                    """,
                    (room_number, date_str, description, amount),
                )
                entry_id = cursor.fetchone()[0]
                conn.commit()
                log_db_operation("INSERT", "electricity_deposit_ledger", True, 1)
                logger.info(f"✅ 預收電費: {room_number} +${amount:,.0f} ({date_str})")
                return True, f"✅ 已新增預收 ${amount:,.0f} 元", entry_id

        except ValueError:
            return False, "❌ 日期格式錯誤，應為 YYYY-MM-DD", None
        except Exception as e:
            log_db_operation("INSERT", "electricity_deposit_ledger", False, error=str(e))
            logger.error(f"❌ 新增失敗: {str(e)}")
            return False, f"❌ {str(e)[:100]}", None

    def deduct_electricity(
        self,
        room_number: str,
        date_str:    str,
        amount:      float,
        description: str = "",
        period_id:   Optional[int] = None,
    ) -> Tuple[bool, str, Optional[int]]:
        try:
            if amount <= 0:
                return False, "❌ 金額必須大於 0", None
            datetime.strptime(date_str, "%Y-%m-%d")

            balance = self.get_deposit_balance(room_number)
            if balance < amount:
                logger.warning(
                    f"⚠️ {room_number} 餘款不足: 餘 ${balance:,.0f}，要扣 ${amount:,.0f}"
                )

            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO electricity_deposit_ledger
                        (room_number, date, type, description, credit, debit, period_id)
                    VALUES (%s, %s, '扣電費', %s, 0, %s, %s)
                    RETURNING id
                    """,
                    (room_number, date_str, description, amount, period_id),
                )
                entry_id = cursor.fetchone()[0]
                conn.commit()
                log_db_operation("INSERT", "electricity_deposit_ledger", True, 1)
                logger.info(
                    f"✅ 扣電費: {room_number} -${amount:,.0f} "
                    f"({date_str}) period={period_id}"
                )
                return True, f"✅ 已扣除 ${amount:,.0f} 元", entry_id

        except ValueError:
            return False, "❌ 日期格式錯誤，應為 YYYY-MM-DD", None
        except Exception as e:
            log_db_operation("INSERT", "electricity_deposit_ledger", False, error=str(e))
            logger.error(f"❌ 扣除失敗: {str(e)}")
            return False, f"❌ {str(e)[:100]}", None

    def get_deposit_balance(self, room_number: str) -> float:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(credit - debit), 0)
                    FROM electricity_deposit_ledger
                    WHERE room_number = %s
                    """,
                    (room_number,),
                )
                return float(cursor.fetchone()[0])
        except Exception as e:
            logger.error(f"❌ 查詢餘款失敗: {str(e)}")
            return 0.0

    def get_deposit_ledger(self, room_number: str) -> pd.DataFrame:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
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
                )
                columns = [desc[0] for desc in cursor.description]
                rows    = cursor.fetchall()
                if not rows:
                    return pd.DataFrame(
                        columns=["id", "日期", "類型", "說明",
                                  "預收電費", "扣電費", "餘款", "period_id"]
                    )
                df = pd.DataFrame(rows, columns=columns)
                log_db_operation("SELECT", "electricity_deposit_ledger", True, len(df))
                return df

        except Exception as e:
            log_db_operation("SELECT", "electricity_deposit_ledger", False, error=str(e))
            logger.error(f"❌ 查詢流水帳失敗: {str(e)}")
            return pd.DataFrame()

    def delete_deposit_entry(self, entry_id: int) -> Tuple[bool, str]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT room_number, type, credit, debit "
                    "FROM electricity_deposit_ledger WHERE id = %s",
                    (entry_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return False, f"❌ 找不到 ID {entry_id} 的記錄"
                room, t, credit, debit = row

                cursor.execute(
                    "DELETE FROM electricity_deposit_ledger WHERE id = %s",
                    (entry_id,),
                )
                conn.commit()
                log_db_operation("DELETE", "electricity_deposit_ledger", True, 1)
                logger.info(
                    f"✅ 刪除記錄 ID {entry_id}: {room} {t} "
                    f"credit={credit} debit={debit}"
                )
                return True, f"✅ 已刪除 ({t} {'+ ' if credit else '- '}${max(credit, debit):,.0f})"

        except Exception as e:
            log_db_operation("DELETE", "electricity_deposit_ledger", False, error=str(e))
            logger.error(f"❌ 刪除失敗: {str(e)}")
            return False, f"❌ {str(e)[:100]}"

    def get_all_rooms_deposit_summary(self) -> pd.DataFrame:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
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
                """)
                columns = [desc[0] for desc in cursor.description]
                rows    = cursor.fetchall()
                if not rows:
                    return pd.DataFrame(
                        columns=["房號", "租客", "預收總額",
                                  "扣除總額", "當前餘款", "最近一筆"]
                    )
                return pd.DataFrame(rows, columns=columns)

        except Exception as e:
            logger.error(f"❌ 摘要失敗: {str(e)}")
            return pd.DataFrame()

    # ==================== 期間管理 ====================

    def add_period(
        self,
        year: int,
        month_start: int,
        month_end: int,
        remind_start_date: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[int]]:
        try:
            if not (1 <= month_start <= 12 and 1 <= month_end <= 12):
                return False, "❌ 月份必須在 1-12 之間", None

            if month_start > month_end:
                return False, "❌ 開始月不能大於結束月", None

            if remind_start_date:
                try:
                    datetime.strptime(remind_start_date, "%Y-%m-%d")
                except ValueError:
                    return False, "❌ remind_start_date 格式錯誤，應為 YYYY-MM-DD", None

            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT COUNT(*) FROM electricity_periods
                    WHERE period_year = %s
                      AND period_month_start = %s
                      AND period_month_end = %s
                    """,
                    (year, month_start, month_end),
                )
                if cursor.fetchone()[0] > 0:
                    logger.warning(f"⚠️ 期間已存在: {year}/{month_start}-{month_end}")
                    return False, f"❌ {year}/{month_start}-{month_end} 已存在", None

                cursor.execute(
                    """
                    INSERT INTO electricity_periods
                        (period_year, period_month_start, period_month_end, remind_start_date)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (year, month_start, month_end, remind_start_date),
                )

                period_id = cursor.fetchone()[0]
                conn.commit()

                log_db_operation("INSERT", "electricity_periods", True, 1)
                logger.info(
                    f"✅ 建立期間 ID {period_id}: {year}/{month_start}-{month_end}"
                    + (f" | 催繳日: {remind_start_date}" if remind_start_date else "")
                )
                return True, f"✅ 已建立 {year} 年 {month_start}-{month_end} 月", period_id

        except Exception as e:
            log_db_operation("INSERT", "electricity_periods", False, error=str(e))
            logger.error(f"❌ 建立失敗: {str(e)}")
            return False, f"❌ {str(e)[:100]}", None

    def get_all_periods(self) -> List[Dict]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
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
                    """
                )
                rows = cursor.fetchall()
                result: List[Dict] = []
                for row in rows:
                    result.append({
                        "id":                 row[0],
                        "period_year":        row[1],
                        "period_month_start": row[2],
                        "period_month_end":   row[3],
                        "remind_start_date":  row[4],
                        "created_at":         row[5],
                        "display":            f"{row[1]}/{row[2]:02d}-{row[3]:02d}",
                    })
                log_db_operation("SELECT", "electricity_periods", True, len(result))
                logger.info(f"✅ 查詢到 {len(result)} 個電費期間")
                return result

        except Exception as e:
            log_db_operation("SELECT", "electricity_periods", False, error=str(e))
            logger.error(f"❌ 查詢失敗: {str(e)}")
            return []

    def get_period_by_id(self, period_id: int) -> Optional[Dict]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
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
                )
                row = cursor.fetchone()
                if not row:
                    logger.warning(f"⚠️ 期間 ID {period_id} 不存在")
                    return None
                return {
                    "id":                 row[0],
                    "period_year":        row[1],
                    "period_month_start": row[2],
                    "period_month_end":   row[3],
                    "remind_start_date":  row[4],
                    "created_at":         row[5],
                    "display":            f"{row[1]}/{row[2]:02d}-{row[3]:02d}",
                }
        except Exception as e:
            logger.error(f"❌ 查詢失敗: {str(e)}")
            return None

    def delete_period(self, period_id: int) -> Tuple[bool, str]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM electricity_periods WHERE id = %s",
                    (period_id,),
                )
                if cursor.fetchone()[0] == 0:
                    return False, f"❌ 期間 ID {period_id} 不存在"

                cursor.execute(
                    "SELECT COUNT(*) FROM electricity_readings WHERE period_id = %s",
                    (period_id,),
                )
                record_count = cursor.fetchone()[0]
                if record_count > 0:
                    logger.warning(
                        f"⚠️ 期間 {period_id} 有 {record_count} 筆關聯記錄（仍強制刪除）"
                    )

                cursor.execute(
                    "DELETE FROM electricity_periods WHERE id = %s", (period_id,)
                )
                conn.commit()
                log_db_operation("DELETE", "electricity_periods", True, 1)
                logger.info(f"✅ 刪除期間 ID: {period_id}")
                return True, "✅ 已刪除期間"

        except Exception as e:
            log_db_operation("DELETE", "electricity_periods", False, error=str(e))
            logger.error(f"❌ 刪除失敗: {str(e)}")
            return False, f"❌ {str(e)[:100]}"

    def update_period_remind_date(
        self,
        period_id: int,
        remind_date: str,
    ) -> Tuple[bool, str]:
        try:
            try:
                datetime.strptime(remind_date, "%Y-%m-%d")
            except ValueError:
                return False, "❌ 日期格式錯誤，應為 YYYY-MM-DD"

            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE electricity_periods
                    SET remind_start_date = %s
                    WHERE id = %s
                    """,
                    (remind_date, period_id),
                )
                if cursor.rowcount == 0:
                    return False, f"❌ 未找到期間 ID {period_id}"
                conn.commit()
                log_db_operation("UPDATE", "electricity_periods", True, 1)
                logger.info(f"✅ 設定催繳日期: {remind_date} (期間 {period_id})")
                return True, f"✅ 已設定催繳日期: {remind_date}"

        except Exception as e:
            log_db_operation("UPDATE", "electricity_periods", False, error=str(e))
            logger.error(f"❌ 更新失敗: {str(e)}")
            return False, f"❌ {str(e)[:100]}"

    # ==================== 電表讀數 ====================

    def get_latest_meter_reading(
        self,
        room: str,
        period_id: int,
    ) -> Optional[float]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT current_reading
                    FROM electricity_readings
                    WHERE room_number = %s AND period_id < %s
                    ORDER BY period_id DESC
                    LIMIT 1
                    """,
                    (room, period_id),
                )
                result = cursor.fetchone()
                if result:
                    logger.debug(f"🔍 {room} 上期讀數: {result[0]}")
                    return float(result[0])
                logger.debug(f"📭 {room} 無上期讀數")
                return None

        except Exception as e:
            logger.error(f"❌ 查詢失敗: {str(e)}")
            return None

    def get_all_readings(self, period_id: int) -> List[Dict]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
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
                )
                columns = [desc[0] for desc in cursor.description]
                rows    = cursor.fetchall()
                log_db_operation("SELECT", "electricity_readings", True, len(rows))
                return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            log_db_operation("SELECT", "electricity_readings", False, error=str(e))
            logger.error(f"❌ 查詢失敗: {str(e)}")
            return []

    def save_reading(
        self,
        period_id:        int,
        room:             str,
        previous:         float,
        current:          float,
        kwh_used:         float,
        unit_price:       float = 0.0,
        public_share_kwh: int   = 0,
        amount_due:       int   = 0,
        room_type:        str   = "unknown",
    ) -> Tuple[bool, str]:
        try:
            if current < previous:
                logger.warning(f"⚠️ {room}: 本期讀數 ({current}) < 上期讀數 ({previous})")
                return False, f"❌ {room}: 本期讀數不能小於上期讀數"

            if abs((current - previous) - kwh_used) > 0.01:
                logger.warning(f"⚠️ {room}: 使用度數計算不符")
                return False, f"❌ {room}: 使用度數計算錯誤"

            total_kwh = kwh_used + public_share_kwh

            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
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
                        period_id, room, previous, current, kwh_used,
                        unit_price, public_share_kwh, total_kwh,
                        amount_due, room_type,
                    ),
                )
                conn.commit()
                log_db_operation("INSERT", "electricity_readings", True, 1)
                logger.info(
                    f"✅ {room} ({room_type}): {kwh_used}度 "
                    f"+ {public_share_kwh}分擔 = {total_kwh}度 → ${amount_due}"
                )
                return True, f"✅ 已儲存 {room}"

        except Exception as e:
            log_db_operation("INSERT", "electricity_readings", False, error=str(e))
            logger.error(f"❌ 儲存失敗: {str(e)}")
            return False, f"❌ {str(e)[:100]}"

    # ==================== 繳費狀態更新 ====================

    def mark_paid(
        self,
        period_id:    int,
        room_number:  str,
        paid_amount:  int,
        payment_date: str,
    ) -> Tuple[bool, str]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
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
                )
                if cursor.rowcount == 0:
                    return False, f"❌ 找不到 {room_number} 的電費記錄（period_id={period_id}）"
                conn.commit()
                log_db_operation("UPDATE", "electricity_readings (mark_paid)", True, 1)
                logger.info(f"✅ 電費已繳: {room_number} - ${paid_amount:,} (period {period_id})")
                return True, f"✅ {room_number} 已標記為已繳"

        except Exception as e:
            log_db_operation("UPDATE", "electricity_readings (mark_paid)", False, error=str(e))
            logger.error(f"❌ 標記電費失敗: {str(e)}")
            return False, f"❌ {str(e)[:100]}"

    def mark_unpaid(
        self,
        period_id:   int,
        room_number: str,
    ) -> Tuple[bool, str]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
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
                )
                if cursor.rowcount == 0:
                    return False, f"❌ 找不到 {room_number} 的電費記錄"
                conn.commit()
                log_db_operation("UPDATE", "electricity_readings (mark_unpaid)", True, 1)
                logger.info(f"✅ 電費取消已繳: {room_number} (period {period_id})")
                return True, f"✅ {room_number} 已取消已繳狀態"

        except Exception as e:
            log_db_operation("UPDATE", "electricity_readings (mark_unpaid)", False, error=str(e))
            logger.error(f"❌ 取消標記失敗: {str(e)}")
            return False, f"❌ {str(e)[:100]}"

    # ==================== 計費記錄查詢 ====================

    def get_payment_record(self, period_id: int) -> Optional[pd.DataFrame]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
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
                )
                columns = [desc[0] for desc in cursor.description]
                rows    = cursor.fetchall()

                if not rows:
                    logger.info(f"📭 期間 {period_id} 無計費記錄")
                    return pd.DataFrame()

                df = pd.DataFrame(rows, columns=columns)
                log_db_operation("SELECT", "electricity_readings", True, len(df))
                logger.info(f"✅ 查詢到 {len(df)} 筆電費記錄")
                return df

        except Exception as e:
            log_db_operation("SELECT", "electricity_readings", False, error=str(e))
            logger.error(f"❌ 查詢失敗: {str(e)}")
            return None

    def get_period_records(self, period_id: int) -> pd.DataFrame:
        df = self.get_payment_record(period_id)
        if df is None:
            return pd.DataFrame()
        return df

    def get_payment_summary(self, period_id: int) -> Optional[Dict]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
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
                )
                row = cursor.fetchone()

                if not row or row[0] == 0:
                    logger.info(f"📭 期間 {period_id} 無統計數據")
                    return None

                total_count  = int(row[0])
                paid_count   = int(row[3] or 0)
                payment_rate = paid_count / total_count * 100 if total_count > 0 else 0

                summary = {
                    "total_count":    total_count,
                    "paid_count":     paid_count,
                    "unpaid_count":   total_count - paid_count,
                    "total_due":      int(row[1] or 0),
                    "total_paid":     int(row[2] or 0),
                    "total_balance":  int(row[4] or 0),
                    "total_kwh_used": float(row[5] or 0),
                    "payment_rate":   round(payment_rate, 1),
                }
                log_db_operation("SELECT", "electricity_readings (summary)", True, 1)
                logger.info(f"📊 繳費率: {payment_rate:.1f}% ({paid_count}/{total_count})")
                return summary

        except Exception as e:
            log_db_operation("SELECT", "electricity_readings (summary)", False, error=str(e))
            logger.error(f"❌ 統計失敗: {str(e)}")
            return None

    # ==================== 廢棄方法（保留向後相容）====================

    def save_records(self, period_id: int, calc_results: List[Dict]) -> Tuple[bool, str]:
        """⚠️ 已廢棄：請使用 save_reading"""
        logger.warning("⚠️ save_records 已廢棄，請使用 save_reading")
        return False, "❌ 此功能已停用"

    def update_payment(
        self,
        period_id:    int,
        room_number:  str,
        new_status:   str,
        paid_amount:  int,
        payment_date: str,
    ) -> Tuple[bool, str]:
        """⚠️ 已廢棄，自動轉導到 mark_paid / mark_unpaid"""
        logger.warning("⚠️ update_payment 已廢棄，請改用 mark_paid / mark_unpaid")
        if new_status == "paid":
            return self.mark_paid(period_id, room_number, paid_amount, payment_date)
        elif new_status == "unpaid":
            return self.mark_unpaid(period_id, room_number)
        return False, f"❌ 未知狀態: {new_status}"

    def batch_update_payments(self, updates: List[Dict]) -> Tuple[int, int]:
        """⚠️ 已廢棄"""
        logger.warning("⚠️ batch_update_payments 已廢棄")
        return 0, len(updates)
