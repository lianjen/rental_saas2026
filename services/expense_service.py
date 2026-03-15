"""
支出管理服務 - v4.3
✅ [FIX v4.2] add_expense 補入 user_id 參數與 INSERT 欄位
✅ [NEW v4.3] 高頻唯讀查詢加上 cache_data，寫入後自動清 cache
✅ 其餘功能與 v4.1 完全相同
"""

import pandas as pd
from datetime import date
from typing import Tuple, Dict, List, Optional
from services.base_db import BaseDBService
from services.cache_utils import cache_data, clear_cached_functions, get_cache_scope
from services.logger import logger, log_db_operation


@cache_data(ttl=300)
def _cached_get_expenses(
    year: Optional[int],
    month: Optional[int],
    categories: Optional[tuple[str, ...]],
    limit: int,
    user_id: str,
    dev_mode: bool,
) -> List[Dict]:
    category_list = list(categories) if categories else None
    return ExpenseService()._get_expenses_uncached(year, month, category_list, limit)


@cache_data(ttl=300)
def _cached_get_expense_statistics(
    year: Optional[int],
    month: Optional[int],
    user_id: str,
    dev_mode: bool,
) -> Dict:
    return ExpenseService()._get_expense_statistics_uncached(year, month)


def clear_expense_cache() -> None:
    clear_cached_functions(
        _cached_get_expenses,
        _cached_get_expense_statistics,
    )

try:
    from config.constants import EXPENSE
    CONSTANTS_LOADED = True
except ImportError:
    logger.warning("無法載入 config.constants，使用備用常量")
    CONSTANTS_LOADED = False

    class BackupConstants:
        class EXPENSE:
            CATEGORIES = ["維修", "清潔", "水電", "其他"]


class ExpenseService(BaseDBService):

    def __init__(self):
        super().__init__()
        self.categories = EXPENSE.CATEGORIES if CONSTANTS_LOADED else BackupConstants.EXPENSE.CATEGORIES

    # ==================== 新增 ====================

    def add_expense(
        self,
        user_id: str,           # ✅ [FIX v4.2] 補上 user_id
        expense_date: date,
        category: str,
        amount: float,
        description: str,
    ) -> Tuple[bool, str]:
        """
        新增支出

        Args:
            user_id:      登入用戶 UUID（對應 expenses.user_id NOT NULL）
            expense_date: 支出日期
            category:     類別
            amount:       金額
            description:  描述
        """
        try:
            if not user_id:
                logger.error("❌ user_id 為空，拒絕寫入")
                return False, "user_id 不可為空"

            if category not in self.categories:
                logger.warning(f"❌ 類別無效: {category}")
                return False, f"無效類別: {category}"

            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO expenses
                        (user_id, expense_date, category, amount, description)
                    VALUES
                        (%s, %s, %s, %s, %s)
                    """,
                    (user_id, expense_date, category, amount, description),  # ✅ FIX v4.2
                )

                clear_expense_cache()
                log_db_operation("INSERT", "expenses", True, 1)
                logger.info(f"✅ 新增支出: {category} NT${amount:,.0f} (user={user_id})")
                return True, "新增成功"

        except Exception as e:
            log_db_operation("INSERT", "expenses", False, error=str(e))
            logger.error(f"❌ 新增失敗: {str(e)}")
            return False, f"新增失敗: {str(e)[:100]}"

    # ==================== 查詢列表 ====================

    def _get_expenses_uncached(
        self,
        year: Optional[int] = None,
        month: Optional[int] = None,
        categories: Optional[List[str]] = None,
        limit: int = 50,
    ) -> List[Dict]:
        def query():
            with self.get_connection() as conn:
                cursor = conn.cursor()

                conditions = ["1=1"]
                params: List = []

                if year:
                    conditions.append("EXTRACT(YEAR FROM expense_date) = %s")
                    params.append(year)
                if month:
                    conditions.append("EXTRACT(MONTH FROM expense_date) = %s")
                    params.append(month)
                if categories:
                    conditions.append("category = ANY(%s)")
                    params.append(categories)

                where_clause = " AND ".join(conditions)

                cursor.execute(
                    f"""
                    SELECT id, expense_date, category, amount, description, created_at
                    FROM expenses
                    WHERE {where_clause}
                    ORDER BY expense_date DESC
                    LIMIT %s
                    """,
                    (*params, limit),
                )

                columns = [desc[0] for desc in cursor.description]
                rows    = cursor.fetchall()

                log_db_operation("SELECT", "expenses", True, len(rows))
                logger.info(f"✅ 取得支出記錄: {len(rows)} 筆")
                return [dict(zip(columns, row)) for row in rows]

        return self.retry_on_failure(query)

    # ==================== 統計 ====================

    def _get_expense_statistics_uncached(
        self, year: Optional[int] = None, month: Optional[int] = None
    ) -> Dict:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                conditions = ["1=1"]
                params: List = []

                if year:
                    conditions.append("EXTRACT(YEAR FROM expense_date) = %s")
                    params.append(year)
                if month:
                    conditions.append("EXTRACT(MONTH FROM expense_date) = %s")
                    params.append(month)

                cursor.execute(
                    f"""
                    SELECT COUNT(*), SUM(amount), category, SUM(amount)
                    FROM expenses
                    WHERE {" AND ".join(conditions)}
                    GROUP BY category
                    ORDER BY 4 DESC
                    """,
                    params,
                )

                rows         = cursor.fetchall()
                total_count  = sum(r[0] for r in rows)
                total_amount = sum(r[1] for r in rows)
                by_category  = {r[2]: float(r[3]) for r in rows}

                log_db_operation("SELECT", "expenses (statistics)", True, total_count)
                logger.info(f"✅ 統計: 總計 NT${total_amount:,.0f}, {total_count} 筆")

                return {
                    "total_count":  total_count,
                    "total_amount": float(total_amount or 0),
                    "by_category":  by_category,
                }

        except Exception as e:
            log_db_operation("SELECT", "expenses (statistics)", False, error=str(e))
            logger.error(f"❌ 統計失敗: {str(e)}")
            return {"total_count": 0, "total_amount": 0, "by_category": {}}

    # ==================== 更新 ====================

    def get_expenses(
        self,
        year: Optional[int] = None,
        month: Optional[int] = None,
        categories: Optional[List[str]] = None,
        limit: int = 50,
    ) -> List[Dict]:
        user_id, dev_mode = get_cache_scope(self)
        categories_key = tuple(categories) if categories else None
        return _cached_get_expenses(year, month, categories_key, limit, user_id, dev_mode)

    def get_expense_statistics(
        self, year: Optional[int] = None, month: Optional[int] = None
    ) -> Dict:
        user_id, dev_mode = get_cache_scope(self)
        return _cached_get_expense_statistics(year, month, user_id, dev_mode)

    def update_expense(
        self,
        expense_id: int,
        expense_date: date,
        category: str,
        amount: float,
        description: str,
    ) -> Tuple[bool, str]:
        try:
            if category not in self.categories:
                return False, f"無效類別: {category}"

            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE expenses
                    SET expense_date = %s, category = %s, amount = %s, description = %s
                    WHERE id = %s
                    """,
                    (expense_date, category, amount, description, expense_id),
                )

                clear_expense_cache()
                log_db_operation("UPDATE", "expenses", True, 1)
                logger.info(f"✅ 更新支出 ID: {expense_id}")
                return True, "更新成功"

        except Exception as e:
            log_db_operation("UPDATE", "expenses", False, error=str(e))
            logger.error(f"❌ 更新失敗: {str(e)}")
            return False, f"更新失敗: {str(e)[:100]}"

    # ==================== 刪除 ====================

    def delete_expense(self, expense_id: int) -> Tuple[bool, str]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM expenses WHERE id = %s", (expense_id,))

                clear_expense_cache()
                log_db_operation("DELETE", "expenses", True, 1)
                logger.info(f"✅ 刪除支出 ID: {expense_id}")
                return True, "刪除成功"

        except Exception as e:
            log_db_operation("DELETE", "expenses", False, error=str(e))
            logger.error(f"❌ 刪除失敗: {str(e)}")
            return False, f"刪除失敗: {str(e)[:100]}"

    # ==================== 類別查詢（舊介面保留）====================

    def get_expense_by_category(self, category: str, limit: int = 50) -> pd.DataFrame:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, expense_date, category, amount, description, created_at
                    FROM expenses
                    WHERE category = %s
                    ORDER BY expense_date DESC
                    LIMIT %s
                    """,
                    (category, limit),
                )
                columns = [desc[0] for desc in cursor.description]
                data    = cursor.fetchall()

                log_db_operation("SELECT", "expenses (by category)", True, len(data))
                return pd.DataFrame(data, columns=columns)

        except Exception as e:
            logger.error(f"❌ 查詢失敗: {str(e)}")
            return pd.DataFrame()
