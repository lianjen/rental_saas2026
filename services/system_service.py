"""
系統服務 - v1.1
職責：處理系統參數設定、資料匯出、系統資訊查詢

✅ [FIX] system_settings 舊 schema 相容（自動 migration）
✅ [FIX] check_database_connection 改回傳 dict，對齊 views/settings.py
✅ [FIX] run_system_diagnostics 回傳更完整 detail/message
✅ [HARDEN] 自動補齊缺欄、去重、建立唯一索引
"""

import logging
from typing import Dict, Optional, List, Tuple
from datetime import datetime
from services.base_db import BaseDBService

logger = logging.getLogger(__name__)


DEFAULT_SETTINGS: List[Tuple[str, str, str]] = [
    ("water_fee", "100", "每月水費金額"),
    ("remind_days", "45", "租約到期提醒天數"),
    ("overdue_days", "7", "逾期天數門檻"),
    ("items_per_page", "50", "每頁顯示筆數"),
]


class SystemService(BaseDBService):
    """系統服務類別"""

    def __init__(self):
        super().__init__()
        self._init_settings_table()

    # ============================================================
    # Schema / Migration
    # ============================================================
    def _init_settings_table(self):
        """初始化 system_settings，並自動修補舊 schema"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                self._ensure_system_settings_schema(cursor)
                self._seed_default_settings(cursor)

                logger.info("系統設定表初始化完成")

        except Exception as e:
            logger.error(f"初始化系統設定表失敗: {str(e)}", exc_info=True)

    def _ensure_system_settings_schema(self, cursor):
        """確保 system_settings 表與欄位正確"""
        if not self._table_exists(cursor, "system_settings"):
            self._create_system_settings_table(cursor)
            return

        existing_cols = self._get_table_columns(cursor, "system_settings")

        # 1) key 欄位 migration
        if "key" not in existing_cols:
            legacy_candidates = [
                "setting_key",
                "config_key",
                "name",
                "setting_name",
                "setting",
            ]
            legacy_key = next((c for c in legacy_candidates if c in existing_cols), None)

            if legacy_key:
                logger.warning(
                    f"偵測到舊欄位 `{legacy_key}`，自動 migration 為 `key`"
                )
                cursor.execute(
                    f'ALTER TABLE system_settings RENAME COLUMN "{legacy_key}" TO "key"'
                )
                existing_cols = self._get_table_columns(cursor, "system_settings")
            else:
                raise RuntimeError(
                    "system_settings 表已存在，但找不到可映射為 `key` 的舊欄位，請手動檢查 schema"
                )

        # 2) 補齊缺漏欄位
        self._add_column_if_missing(
            cursor,
            table_name="system_settings",
            column_name="value",
            column_def="TEXT",
        )
        self._add_column_if_missing(
            cursor,
            table_name="system_settings",
            column_name="description",
            column_def="TEXT",
        )
        self._add_column_if_missing(
            cursor,
            table_name="system_settings",
            column_name="updated_at",
            column_def="TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        )
        self._add_column_if_missing(
            cursor,
            table_name="system_settings",
            column_name="updated_by",
            column_def="VARCHAR(100)",
        )

        # 3) 清理資料，避免 NOT NULL / UNIQUE 建立失敗
        cursor.execute("""
            UPDATE system_settings
            SET "value" = ''
            WHERE "value" IS NULL
        """)

        cursor.execute("""
            SELECT COUNT(*)
            FROM system_settings
            WHERE "key" IS NULL OR BTRIM("key") = ''
        """)
        invalid_key_count = cursor.fetchone()[0]
        if invalid_key_count > 0:
            raise RuntimeError(
                f"system_settings 有 {invalid_key_count} 筆空白 key，無法自動建立唯一約束，請先清理資料"
            )

        # 4) 去重（保留 updated_at 較新的那筆）
        cursor.execute("""
            DELETE FROM system_settings t
            USING (
                SELECT ctid
                FROM (
                    SELECT
                        ctid,
                        ROW_NUMBER() OVER (
                            PARTITION BY "key"
                            ORDER BY updated_at DESC NULLS LAST, ctid DESC
                        ) AS rn
                    FROM system_settings
                ) ranked
                WHERE ranked.rn > 1
            ) d
            WHERE t.ctid = d.ctid
        """)

        # 5) 補強欄位約束 / 索引
        cursor.execute("""
            ALTER TABLE system_settings
            ALTER COLUMN "key" SET NOT NULL
        """)
        cursor.execute("""
            ALTER TABLE system_settings
            ALTER COLUMN "value" SET NOT NULL
        """)
        cursor.execute("""
            ALTER TABLE system_settings
            ALTER COLUMN "updated_at" SET DEFAULT CURRENT_TIMESTAMP
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_system_settings_key
            ON system_settings ("key")
        """)

    def _create_system_settings_table(self, cursor):
        """建立 system_settings 表"""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                "key" VARCHAR(100) PRIMARY KEY,
                "value" TEXT NOT NULL,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by VARCHAR(100)
            )
        """)
        logger.info("已建立 system_settings 資料表")

    def _seed_default_settings(self, cursor):
        """插入預設設定（不存在才插入）"""
        for key, value, desc in DEFAULT_SETTINGS:
            cursor.execute("""
                INSERT INTO system_settings ("key", "value", description)
                VALUES (%s, %s, %s)
                ON CONFLICT ("key") DO NOTHING
            """, (key, value, desc))

    def _table_exists(self, cursor, table_name: str) -> bool:
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = %s
            )
        """, (table_name,))
        return cursor.fetchone()[0]

    def _get_table_columns(self, cursor, table_name: str) -> List[str]:
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
            ORDER BY ordinal_position
        """, (table_name,))
        return [row[0] for row in cursor.fetchall()]

    def _add_column_if_missing(
        self,
        cursor,
        table_name: str,
        column_name: str,
        column_def: str,
    ):
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                  AND column_name = %s
            )
        """, (table_name, column_name))
        exists = cursor.fetchone()[0]

        if not exists:
            cursor.execute(
                f'ALTER TABLE {table_name} ADD COLUMN "{column_name}" {column_def}'
            )
            logger.info(f"已補上欄位: {table_name}.{column_name}")

    # ============================================================
    # Settings CRUD
    # ============================================================
    def get_setting(self, key: str) -> Optional[str]:
        """取得單一設定值"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT "value"
                    FROM system_settings
                    WHERE "key" = %s
                """, (key,))
                result = cursor.fetchone()
                return result[0] if result else None

        except Exception as e:
            logger.error(f"取得設定失敗 [{key}]: {str(e)}", exc_info=True)
            return None

    def get_all_settings(self) -> Dict[str, str]:
        """取得所有設定"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT "key", "value"
                    FROM system_settings
                    ORDER BY "key"
                """)
                return {row[0]: row[1] for row in cursor.fetchall()}

        except Exception as e:
            logger.error(f"取得所有設定失敗: {str(e)}", exc_info=True)
            return {}

    def save_setting(self, key: str, value: str, updated_by: str = "system") -> bool:
        """儲存設定（UPSERT）"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO system_settings ("key", "value", updated_at, updated_by)
                    VALUES (%s, %s, NOW(), %s)
                    ON CONFLICT ("key")
                    DO UPDATE SET
                        "value" = EXCLUDED."value",
                        updated_at = NOW(),
                        updated_by = EXCLUDED.updated_by
                """, (key, value, updated_by))

                logger.info(f"設定已儲存: {key} = {value}")
                return True

        except Exception as e:
            logger.error(f"儲存設定失敗 [{key}]: {str(e)}", exc_info=True)
            return False

    def delete_setting(self, key: str) -> bool:
        """刪除設定"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    DELETE FROM system_settings
                    WHERE "key" = %s
                """, (key,))

                logger.info(f"設定已刪除: {key}")
                return True

        except Exception as e:
            logger.error(f"刪除設定失敗 [{key}]: {str(e)}", exc_info=True)
            return False

    # ============================================================
    # Database / Diagnostics
    # ============================================================
    def get_database_stats(self) -> Dict[str, int]:
        """取得資料庫統計資訊"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                stats: Dict[str, int] = {}

                stats["tenants"] = self._safe_count(cursor, "tenants")
                stats["payments"] = self._safe_count(cursor, "payment_schedule")
                stats["expenses"] = self._safe_count(cursor, "expenses")
                stats["electricity_periods"] = self._safe_count(cursor, "electricity_periods")

                return stats

        except Exception as e:
            logger.error(f"取得資料庫統計失敗: {str(e)}", exc_info=True)
            return {}

    def _safe_count(self, cursor, table_name: str) -> int:
        """安全取得資料表筆數"""
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            return int(cursor.fetchone()[0] or 0)
        except Exception as e:
            logger.warning(f"統計資料表失敗 [{table_name}]: {e}")
            return 0

    def check_database_connection(self) -> Dict[str, Optional[str]]:
        """
        檢查資料庫連線

        Returns:
            {
                "connected": bool,
                "version": str | None,
                "error": str | None
            }
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT version()")
                version = cursor.fetchone()[0]
                logger.info(f"資料庫連線正常: {version}")
                return {
                    "connected": True,
                    "version": version,
                    "error": None,
                }

        except Exception as e:
            logger.error(f"資料庫連線失敗: {str(e)}", exc_info=True)
            return {
                "connected": False,
                "version": None,
                "error": str(e),
            }

    def get_database_version(self) -> Optional[str]:
        """取得資料庫版本"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT version()")
                return cursor.fetchone()[0]

        except Exception as e:
            logger.error(f"取得資料庫版本失敗: {str(e)}", exc_info=True)
            return None

    def check_table_exists(self, table_name: str) -> bool:
        """檢查資料表是否存在"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = %s
                    )
                """, (table_name,))

                return cursor.fetchone()[0]

        except Exception as e:
            logger.error(f"檢查資料表失敗 [{table_name}]: {str(e)}", exc_info=True)
            return False

    def run_system_diagnostics(self) -> Dict[str, Dict]:
        """執行系統診斷"""
        results: Dict[str, Dict] = {}

        db_result = self.check_database_connection()
        results["database_connection"] = {
            "status": "success" if db_result["connected"] else "failed",
            "name": "資料庫連線",
            "detail": db_result.get("version") if db_result["connected"] else db_result.get("error"),
            "message": "資料庫連線正常" if db_result["connected"] else db_result.get("error", "連線失敗"),
        }

        required_tables = [
            "tenants",
            "payment_schedule",
            "expenses",
            "electricity_periods",
            "electricity_records",
        ]

        for table in required_tables:
            exists = self.check_table_exists(table)
            results[f"table_{table}"] = {
                "status": "success" if exists else "failed",
                "name": f"{table} 資料表",
                "detail": "存在" if exists else "不存在",
                "message": "資料表存在" if exists else "資料表不存在",
            }

        return results

    # ============================================================
    # Export
    # ============================================================
    def export_system_info(self) -> Dict:
        """匯出系統資訊"""
        return {
            "app_name": "租屋管理系統",
            "version": "v3.0",
            "framework": "Streamlit",
            "database": "PostgreSQL (Supabase)",
            "python_version": "3.9+",
            "export_time": datetime.now().isoformat(),
            "database_version": self.get_database_version(),
            "stats": self.get_database_stats(),
        }


# ============================================
# 本機測試
# ============================================
if __name__ == "__main__":
    service = SystemService()

    print("=== 測試系統服務 ===\n")

    print("1. 所有設定:")
    settings = service.get_all_settings()
    for key, value in settings.items():
        print(f"   {key}: {value}")

    print("\n2. 資料庫統計:")
    stats = service.get_database_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")

    print("\n3. 系統診斷:")
    diagnostics = service.run_system_diagnostics()
    for key, info in diagnostics.items():
        status_icon = "✅" if info["status"] == "success" else "❌"
        print(f"   {status_icon} {info['name']}: {info.get('message', info['status'])}")

    print("\n4. 系統資訊:")
    sys_info = service.export_system_info()
    for key, value in sys_info.items():
        print(f"   {key}: {value}")
