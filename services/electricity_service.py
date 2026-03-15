"""
電費管理服務 - v5.6
✅ 保留既有電費功能與快取策略
✅ [NEW v5.6] 所有 DB 操作移至 repository/electricity_repository.py
✅ Service 層只保留驗證、格式轉換、快取與業務協調
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

from repository.electricity_repository import ElectricityRepository
from services.base_db import BaseDBService
from services.cache_utils import cache_data, clear_cached_functions, get_cache_scope
from services.logger import logger


@cache_data(ttl=300)
def _cached_get_taipower_bills(
    period_id: int,
    user_id: str,
    dev_mode: bool,
) -> List[Dict]:
    return ElectricityService()._get_taipower_bills_uncached(period_id)


@cache_data(ttl=300)
def _cached_get_deposit_ledger(
    room_number: str,
    user_id: str,
    dev_mode: bool,
) -> pd.DataFrame:
    return ElectricityService()._get_deposit_ledger_uncached(room_number)


@cache_data(ttl=300)
def _cached_get_all_rooms_deposit_summary(
    user_id: str,
    dev_mode: bool,
) -> pd.DataFrame:
    return ElectricityService()._get_all_rooms_deposit_summary_uncached()


@cache_data(ttl=600)
def _cached_get_all_periods(user_id: str, dev_mode: bool) -> List[Dict]:
    return ElectricityService()._get_all_periods_uncached()


@cache_data(ttl=300)
def _cached_get_all_readings(
    period_id: int,
    user_id: str,
    dev_mode: bool,
) -> List[Dict]:
    return ElectricityService()._get_all_readings_uncached(period_id)


@cache_data(ttl=300)
def _cached_get_payment_record(
    period_id: int,
    user_id: str,
    dev_mode: bool,
) -> Optional[pd.DataFrame]:
    return ElectricityService()._get_payment_record_uncached(period_id)


def clear_electricity_cache() -> None:
    clear_cached_functions(
        _cached_get_taipower_bills,
        _cached_get_deposit_ledger,
        _cached_get_all_rooms_deposit_summary,
        _cached_get_all_periods,
        _cached_get_all_readings,
        _cached_get_payment_record,
    )


class ElectricityService(BaseDBService):
    def __init__(self):
        super().__init__()
        self.repository = ElectricityRepository()
        self._init_deposit_ledger_table()
        self._init_taipower_bills_table()

    # ==================== 內部建表 ====================

    def _init_deposit_ledger_table(self) -> None:
        ok, msg = self.repository.init_deposit_ledger_table()
        if ok:
            logger.info("✅ electricity_deposit_ledger 資料表檢查完成")
        else:
            logger.error(f"❌ 建表失敗: {msg}")

    def _init_taipower_bills_table(self) -> None:
        ok, msg = self.repository.init_taipower_bills_table()
        if ok:
            logger.info("✅ electricity_taipower_bills 資料表檢查完成")
        else:
            logger.error(f"❌ 建立 taipower_bills 表失敗: {msg}")

    # ==================== 台電帳單 CRUD ====================

    def save_taipower_bills(
        self,
        period_id: int,
        bills: List[Dict],
    ) -> Tuple[bool, str]:
        ok, result = self.repository.save_taipower_bills(period_id, bills)
        if ok:
            clear_electricity_cache()
            logger.info(f"✅ 台電帳單已儲存: period={period_id}, {result} 筆")
            return True, f"✅ 已儲存 {result} 個台電單"
        logger.error(f"❌ 儲存台電帳單失敗: {result}")
        return False, f"❌ {str(result)[:100]}"

    def _get_taipower_bills_uncached(self, period_id: int) -> List[Dict]:
        ok, data = self.repository.get_taipower_bills(period_id)
        if not ok:
            logger.error(f"❌ 讀取台電帳單失敗: {data}")
            return []

        result = [
            {
                "floor_label": row["floor_label"],
                "amount": int(row["amount"]),
                "kwh": float(row["kwh"]),
            }
            for row in data
        ]
        logger.info(f"✅ 載入台電帳單: period={period_id}, {len(result)} 筆")
        return result

    def get_taipower_bills(self, period_id: int) -> List[Dict]:
        user_id, dev_mode = get_cache_scope(self)
        return _cached_get_taipower_bills(period_id, user_id, dev_mode)

    def delete_taipower_bills(self, period_id: int) -> Tuple[bool, str]:
        ok, deleted = self.repository.delete_taipower_bills(period_id)
        if ok:
            clear_electricity_cache()
            logger.info(f"✅ 刪除台電帳單: period={period_id}, {deleted} 筆")
            return True, f"✅ 已刪除 {deleted} 筆"
        logger.error(f"❌ 刪除台電帳單失敗: {deleted}")
        return False, f"❌ {str(deleted)[:100]}"

    # ==================== 預收電費帳戶 ====================

    def add_deposit(
        self,
        room_number: str,
        date_str: str,
        amount: float,
        description: str = "",
    ) -> Tuple[bool, str, Optional[int]]:
        try:
            if amount <= 0:
                return False, "❌ 金額必須大於 0", None
            datetime.strptime(date_str, "%Y-%m-%d")

            ok, result = self.repository.add_deposit_entry(
                room_number,
                date_str,
                amount,
                description,
            )
            if ok:
                clear_electricity_cache()
                logger.info(f"✅ 預收電費: {room_number} +${amount:,.0f} ({date_str})")
                return True, f"✅ 已新增預收 ${amount:,.0f} 元", int(result)
            logger.error(f"❌ 新增失敗: {result}")
            return False, f"❌ {str(result)[:100]}", None

        except ValueError:
            return False, "❌ 日期格式錯誤，應為 YYYY-MM-DD", None

    def deduct_electricity(
        self,
        room_number: str,
        date_str: str,
        amount: float,
        description: str = "",
        period_id: Optional[int] = None,
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

            ok, result = self.repository.add_deduction_entry(
                room_number,
                date_str,
                amount,
                description,
                period_id,
            )
            if ok:
                clear_electricity_cache()
                logger.info(
                    f"✅ 扣電費: {room_number} -${amount:,.0f} "
                    f"({date_str}) period={period_id}"
                )
                return True, f"✅ 已扣除 ${amount:,.0f} 元", int(result)
            logger.error(f"❌ 扣除失敗: {result}")
            return False, f"❌ {str(result)[:100]}", None

        except ValueError:
            return False, "❌ 日期格式錯誤，應為 YYYY-MM-DD", None

    def get_deposit_balance(self, room_number: str) -> float:
        ok, result = self.repository.get_deposit_balance(room_number)
        if ok:
            return float(result)
        logger.error(f"❌ 查詢餘款失敗: {result}")
        return 0.0

    def _get_deposit_ledger_uncached(self, room_number: str) -> pd.DataFrame:
        ok, rows = self.repository.get_deposit_ledger(room_number)
        if not ok:
            logger.error(f"❌ 查詢流水帳失敗: {rows}")
            return pd.DataFrame()
        if not rows:
            return pd.DataFrame(
                columns=["id", "日期", "類型", "說明", "預收電費", "扣電費", "餘款", "period_id"]
            )
        return pd.DataFrame(rows)

    def get_deposit_ledger(self, room_number: str) -> pd.DataFrame:
        user_id, dev_mode = get_cache_scope(self)
        return _cached_get_deposit_ledger(room_number, user_id, dev_mode)

    def delete_deposit_entry(self, entry_id: int) -> Tuple[bool, str]:
        ok, entry = self.repository.get_deposit_entry(entry_id)
        if not ok:
            logger.error(f"❌ 刪除前查詢失敗: {entry}")
            return False, f"❌ {str(entry)[:100]}"
        if not entry:
            return False, f"❌ 找不到 ID {entry_id} 的記錄"

        ok, deleted = self.repository.delete_deposit_entry(entry_id)
        if ok:
            clear_electricity_cache()
            room = entry["room_number"]
            entry_type = entry["type"]
            credit = float(entry["credit"] or 0)
            debit = float(entry["debit"] or 0)
            logger.info(
                f"✅ 刪除記錄 ID {entry_id}: {room} {entry_type} "
                f"credit={credit} debit={debit}"
            )
            return True, f"✅ 已刪除 ({entry_type} {'+ ' if credit else '- '}${max(credit, debit):,.0f})"

        logger.error(f"❌ 刪除失敗: {deleted}")
        return False, f"❌ {str(deleted)[:100]}"

    def _get_all_rooms_deposit_summary_uncached(self) -> pd.DataFrame:
        ok, rows = self.repository.get_all_rooms_deposit_summary()
        if not ok:
            logger.error(f"❌ 摘要失敗: {rows}")
            return pd.DataFrame()
        if not rows:
            return pd.DataFrame(
                columns=["房號", "租客", "預收總額", "扣除總額", "當前餘款", "最近一筆"]
            )
        return pd.DataFrame(rows)

    def get_all_rooms_deposit_summary(self) -> pd.DataFrame:
        user_id, dev_mode = get_cache_scope(self)
        return _cached_get_all_rooms_deposit_summary(user_id, dev_mode)

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

            ok, exists = self.repository.period_exists(year, month_start, month_end)
            if not ok:
                logger.error(f"❌ 檢查期間失敗: {exists}")
                return False, f"❌ {str(exists)[:100]}", None
            if exists:
                logger.warning(f"⚠️ 期間已存在: {year}/{month_start}-{month_end}")
                return False, f"❌ {year}/{month_start}-{month_end} 已存在", None

            ok, period_id = self.repository.create_period(
                year,
                month_start,
                month_end,
                remind_start_date,
            )
            if ok:
                clear_electricity_cache()
                logger.info(
                    f"✅ 建立期間 ID {period_id}: {year}/{month_start}-{month_end}"
                    + (f" | 催繳日: {remind_start_date}" if remind_start_date else "")
                )
                return True, f"✅ 已建立 {year} 年 {month_start}-{month_end} 月", int(period_id)

            logger.error(f"❌ 建立失敗: {period_id}")
            return False, f"❌ {str(period_id)[:100]}", None

        except Exception as e:
            logger.error(f"❌ 建立失敗: {str(e)}")
            return False, f"❌ {str(e)[:100]}", None

    def _get_all_periods_uncached(self) -> List[Dict]:
        ok, rows = self.repository.get_periods()
        if not ok:
            logger.error(f"❌ 查詢失敗: {rows}")
            return []

        result: List[Dict] = []
        for row in rows:
            result.append(
                {
                    "id": row["id"],
                    "period_year": row["period_year"],
                    "period_month_start": row["period_month_start"],
                    "period_month_end": row["period_month_end"],
                    "remind_start_date": row["remind_start_date"],
                    "created_at": row["created_at"],
                    "display": f"{row['period_year']}/{row['period_month_start']:02d}-{row['period_month_end']:02d}",
                }
            )
        logger.info(f"✅ 查詢到 {len(result)} 個電費期間")
        return result

    def get_all_periods(self) -> List[Dict]:
        user_id, dev_mode = get_cache_scope(self)
        return _cached_get_all_periods(user_id, dev_mode)

    def get_period_by_id(self, period_id: int) -> Optional[Dict]:
        ok, row = self.repository.get_period_by_id(period_id)
        if not ok:
            logger.error(f"❌ 查詢失敗: {row}")
            return None
        if not row:
            logger.warning(f"⚠️ 期間 ID {period_id} 不存在")
            return None
        return {
            "id": row["id"],
            "period_year": row["period_year"],
            "period_month_start": row["period_month_start"],
            "period_month_end": row["period_month_end"],
            "remind_start_date": row["remind_start_date"],
            "created_at": row["created_at"],
            "display": f"{row['period_year']}/{row['period_month_start']:02d}-{row['period_month_end']:02d}",
        }

    def delete_period(self, period_id: int) -> Tuple[bool, str]:
        period = self.get_period_by_id(period_id)
        if not period:
            return False, f"❌ 期間 ID {period_id} 不存在"

        ok, record_count = self.repository.count_period_readings(period_id)
        if not ok:
            logger.error(f"❌ 查詢關聯記錄失敗: {record_count}")
            return False, f"❌ {str(record_count)[:100]}"
        if record_count > 0:
            logger.warning(f"⚠️ 期間 {period_id} 有 {record_count} 筆關聯記錄（仍強制刪除）")

        ok, deleted = self.repository.delete_period(period_id)
        if ok and deleted > 0:
            clear_electricity_cache()
            logger.info(f"✅ 刪除期間 ID: {period_id}")
            return True, "✅ 已刪除期間"
        if ok:
            return False, f"❌ 期間 ID {period_id} 不存在"
        logger.error(f"❌ 刪除失敗: {deleted}")
        return False, f"❌ {str(deleted)[:100]}"

    def update_period_remind_date(
        self,
        period_id: int,
        remind_date: str,
    ) -> Tuple[bool, str]:
        try:
            datetime.strptime(remind_date, "%Y-%m-%d")
        except ValueError:
            return False, "❌ 日期格式錯誤，應為 YYYY-MM-DD"

        ok, updated = self.repository.update_period_remind_date(period_id, remind_date)
        if ok and updated > 0:
            clear_electricity_cache()
            logger.info(f"✅ 設定催繳日期: {remind_date} (期間 {period_id})")
            return True, f"✅ 已設定催繳日期: {remind_date}"
        if ok:
            return False, f"❌ 未找到期間 ID {period_id}"
        logger.error(f"❌ 更新失敗: {updated}")
        return False, f"❌ {str(updated)[:100]}"

    # ==================== 電表讀數 ====================

    def get_latest_meter_reading(
        self,
        room: str,
        period_id: int,
    ) -> Optional[float]:
        ok, result = self.repository.get_latest_meter_reading(room, period_id)
        if not ok:
            logger.error(f"❌ 查詢失敗: {result}")
            return None
        if result is not None:
            logger.debug(f"🔍 {room} 上期讀數: {result}")
        else:
            logger.debug(f"📭 {room} 無上期讀數")
        return result

    def _get_all_readings_uncached(self, period_id: int) -> List[Dict]:
        ok, rows = self.repository.get_readings_by_period(period_id)
        if not ok:
            logger.error(f"❌ 查詢失敗: {rows}")
            return []
        return rows

    def get_all_readings(self, period_id: int) -> List[Dict]:
        user_id, dev_mode = get_cache_scope(self)
        return _cached_get_all_readings(period_id, user_id, dev_mode)

    def save_reading(
        self,
        period_id: int,
        room: str,
        previous: float,
        current: float,
        kwh_used: float,
        unit_price: float = 0.0,
        public_share_kwh: int = 0,
        amount_due: int = 0,
        room_type: str = "unknown",
    ) -> Tuple[bool, str]:
        if current < previous:
            logger.warning(f"⚠️ {room}: 本期讀數 ({current}) < 上期讀數 ({previous})")
            return False, f"❌ {room}: 本期讀數不能小於上期讀數"

        if abs((current - previous) - kwh_used) > 0.01:
            logger.warning(f"⚠️ {room}: 使用度數計算不符")
            return False, f"❌ {room}: 使用度數計算錯誤"

        total_kwh = kwh_used + public_share_kwh
        ok, result = self.repository.upsert_reading(
            period_id,
            room,
            previous,
            current,
            kwh_used,
            unit_price,
            public_share_kwh,
            total_kwh,
            amount_due,
            room_type,
        )
        if ok:
            clear_electricity_cache()
            logger.info(
                f"✅ {room} ({room_type}): {kwh_used}度 "
                f"+ {public_share_kwh}分擔 = {total_kwh}度 → ${amount_due}"
            )
            return True, f"✅ 已儲存 {room}"

        logger.error(f"❌ 儲存失敗: {result}")
        return False, f"❌ {str(result)[:100]}"

    # ==================== 繳費狀態更新 ====================

    def mark_paid(
        self,
        period_id: int,
        room_number: str,
        paid_amount: int,
        payment_date: str,
    ) -> Tuple[bool, str]:
        ok, updated = self.repository.mark_paid(period_id, room_number, paid_amount, payment_date)
        if ok and updated > 0:
            clear_electricity_cache()
            logger.info(f"✅ 電費已繳: {room_number} - ${paid_amount:,} (period {period_id})")
            return True, f"✅ {room_number} 已標記為已繳"
        if ok:
            return False, f"❌ 找不到 {room_number} 的電費記錄（period_id={period_id}）"
        logger.error(f"❌ 標記電費失敗: {updated}")
        return False, f"❌ {str(updated)[:100]}"

    def mark_unpaid(
        self,
        period_id: int,
        room_number: str,
    ) -> Tuple[bool, str]:
        ok, updated = self.repository.mark_unpaid(period_id, room_number)
        if ok and updated > 0:
            clear_electricity_cache()
            logger.info(f"✅ 電費取消已繳: {room_number} (period {period_id})")
            return True, f"✅ {room_number} 已取消已繳狀態"
        if ok:
            return False, f"❌ 找不到 {room_number} 的電費記錄"
        logger.error(f"❌ 取消標記失敗: {updated}")
        return False, f"❌ {str(updated)[:100]}"

    # ==================== 計費記錄查詢 ====================

    def _get_payment_record_uncached(self, period_id: int) -> Optional[pd.DataFrame]:
        ok, rows = self.repository.get_payment_record(period_id)
        if not ok:
            logger.error(f"❌ 查詢失敗: {rows}")
            return None
        if not rows:
            logger.info(f"📭 期間 {period_id} 無計費記錄")
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        logger.info(f"✅ 查詢到 {len(df)} 筆電費記錄")
        return df

    def get_payment_record(self, period_id: int) -> Optional[pd.DataFrame]:
        user_id, dev_mode = get_cache_scope(self)
        return _cached_get_payment_record(period_id, user_id, dev_mode)

    def get_period_records(self, period_id: int) -> pd.DataFrame:
        df = self.get_payment_record(period_id)
        if df is None:
            return pd.DataFrame()
        return df

    def get_payment_summary(self, period_id: int) -> Optional[Dict]:
        ok, summary = self.repository.get_payment_summary(period_id)
        if ok:
            if summary is None:
                logger.info(f"📭 期間 {period_id} 無統計數據")
                return None
            logger.info(
                f"📊 繳費率: {summary['payment_rate']:.1f}% "
                f"({summary['paid_count']}/{summary['total_count']})"
            )
            return summary
        logger.error(f"❌ 統計失敗: {summary}")
        return None

    # ==================== 廢棄方法（保留向後相容）====================

    def save_records(self, period_id: int, calc_results: List[Dict]) -> Tuple[bool, str]:
        """⚠️ 已廢棄：請使用 save_reading"""
        logger.warning("⚠️ save_records 已廢棄，請使用 save_reading")
        return False, "❌ 此功能已停用"

    def update_payment(
        self,
        period_id: int,
        room_number: str,
        new_status: str,
        paid_amount: int,
        payment_date: str,
    ) -> Tuple[bool, str]:
        """⚠️ 已廢棄，自動轉導到 mark_paid / mark_unpaid"""
        logger.warning("⚠️ update_payment 已廢棄，請改用 mark_paid / mark_unpaid")
        if new_status == "paid":
            return self.mark_paid(period_id, room_number, paid_amount, payment_date)
        if new_status == "unpaid":
            return self.mark_unpaid(period_id, room_number)
        return False, f"❌ 未知狀態: {new_status}"

    def batch_update_payments(self, updates: List[Dict]) -> Tuple[int, int]:
        """⚠️ 已廢棄"""
        logger.warning("⚠️ batch_update_payments 已廢棄")
        return 0, len(updates)
