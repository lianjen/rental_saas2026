import logging
import os
from datetime import datetime
from typing import Optional


def _get_log_level() -> int:
    """從環境變數讀取 LOG_LEVEL，預設 INFO。"""
    level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    return getattr(logging, level_str, logging.INFO)


# 設定基本 logging 格式（只會在第一次 import 時執行）
logging.basicConfig(
    level=_get_log_level(),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

# 專用的 app logger
logger = logging.getLogger("rental_app")
logger.setLevel(_get_log_level())


def log_db_operation(
    operation: str,
    table: str,
    success: bool,
    rows: Optional[int] = None,
    error: Optional[str] = None,
) -> None:
    """統一的資料庫操作日誌格式。

    Args:
        operation: 操作類型，例如 "SELECT", "INSERT", "UPDATE", "DELETE"
        table: 資料表名稱
        success: 是否成功
        rows: 影響列數（可選）
        error: 錯誤訊息（失敗時可選）
    """
    status = "SUCCESS" if success else "FAILED"
    base_msg = f"[DB] {operation} {table} - {status}"

    if rows is not None:
        base_msg += f" (rows={rows})"

    if error and not success:
        base_msg += f" | error={error}"

    if success:
        logger.info(base_msg)
    else:
        logger.error(base_msg)


# 簡單的自我測試（本機直接執行 logger.py 時用，部署時不會跑到）
if __name__ == "__main__":
    logger.info("Logger module test started")
    log_db_operation("SELECT", "tenants", True, rows=10)
    log_db_operation("INSERT", "tenants", False, error="Sample error")
    logger.info("Logger module test finished")
