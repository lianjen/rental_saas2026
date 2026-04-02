"""
基礎數據庫服務 - v5.0
✅ 單例連接池管理（Streamlit / 非 Streamlit 通用）
✅ 統一的錯誤處理和重試機制
✅ Streamlit 資源快取整合（若可用）
✅ 認證整合：自動注入 user_id
✅ Session 管理
✅ RLS Policy 支援
"""

import os
import time
import contextlib
from typing import Generator, Tuple, Callable, Any, Optional

import psycopg2
from psycopg2 import pool

# ========= 可選的 Streamlit 依賴 =========
try:
    import streamlit as st  # type: ignore
    HAS_STREAMLIT = True
except ImportError:
    st = None  # type: ignore
    HAS_STREAMLIT = False

# ========= 日誌 =========
try:
    from services.logger import logger, log_db_operation
except ImportError:
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    def log_db_operation(op, table, success, count: int = 0, error: str | None = None):
        if success:
            logger.info(f"✅ {op} {table}: {count} rows")
        else:
            logger.error(f"❌ {op} {table}: {error}")


# ============== 連接池管理 ==============
class DatabaseConnectionPool:
    """單例連接池 - 避免在 Streamlit rerun / 多處重複建立"""

    _instance: "DatabaseConnectionPool | None" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self._pool: pool.ThreadedConnectionPool | None = None
        self._initialized: bool = False

    def initialize(self, config: dict):
        """初始化連接池 - 只執行一次"""
        if self._initialized and self._pool is not None:
            logger.debug("連接池已存在，跳過初始化")
            return

        try:
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=config.get("min_connections", 2),
                maxconn=config.get("max_connections", 10),
                host=config.get("host"),
                port=config.get("port", 5432),
                database=config.get("database"),
                user=config.get("user"),
                password=config.get("password"),
                connect_timeout=10,
            )
            self._initialized = True
            logger.info("✅ 連接池初始化成功")

        except Exception as e:
            logger.error(f"❌ 連接池初始化失敗: {e}")
            raise

    def get_connection(self):
        """獲取連接"""
        if self._pool is None or not self._initialized:
            raise RuntimeError("連接池未初始化")
        return self._pool.getconn()

    def return_connection(self, conn):
        """歸還連接"""
        if self._pool and conn:
            self._pool.putconn(conn)

    def is_initialized(self) -> bool:
        """檢查是否已初始化"""
        return self._initialized and self._pool is not None

    def close_all(self):
        """關閉所有連接"""
        if self._pool:
            self._pool.closeall()
            self._pool = None
            self._initialized = False
            logger.info("✅ 連接池已關閉")


def _load_db_config() -> dict:
    """
    載入 DB 設定：
    - 若在 Streamlit 環境：使用 st.secrets['supabase']
    - 否則：使用環境變數 SUPABASE_*
    """
    if HAS_STREAMLIT and hasattr(st, "secrets"):
        try:
            supa = st.secrets.get("supabase", {})  # type: ignore[attr-defined]
            if supa:
                return {
                    "host": supa.get("host"),
                    "port": supa.get("port", 5432),
                    "database": supa.get("database"),
                    "user": supa.get("user"),
                    "password": supa.get("password"),
                    "min_connections": 2,
                    "max_connections": 10,
                }
        except Exception:
            logger.debug("st.secrets unavailable, fallback to environment variables")

    # 非 Streamlit 環境：讀取環境變數
    return {
        "host": os.getenv("SUPABASE_HOST"),
        "port": int(os.getenv("SUPABASE_PORT", "5432")),
        "database": os.getenv("SUPABASE_DB"),
        "user": os.getenv("SUPABASE_USER"),
        "password": os.getenv("SUPABASE_PASSWORD"),
        "min_connections": int(os.getenv("DB_MIN_CONNECTIONS", "2")),
        "max_connections": int(os.getenv("DB_MAX_CONNECTIONS", "10")),
    }


# ============== 連接池入口 ==============
# Streamlit 環境：使用 cache_resource；非 Streamlit：使用全域單例
_pool_instance = DatabaseConnectionPool()

if HAS_STREAMLIT and hasattr(st, "cache_resource"):

    @st.cache_resource  # type: ignore[attr-defined]
    def get_connection_pool() -> DatabaseConnectionPool:
        """Streamlit 資源快取 - 確保整個 session 只創建一次"""
        if not _pool_instance.is_initialized():
            config = _load_db_config()
            _pool_instance.initialize(config)
        return _pool_instance

else:

    def get_connection_pool() -> DatabaseConnectionPool:
        """非 Streamlit 環境使用的連接池取得方法"""
        if not _pool_instance.is_initialized():
            config = _load_db_config()
            _pool_instance.initialize(config)
        return _pool_instance


# ============== 基礎服務類 ==============
class BaseDBService:
    """基礎數據庫服務 - 所有服務的父類（整合認證）"""

    def __init__(self):
        """初始化服務 - 使用共用連接池"""
        self.pool = get_connection_pool()

    @contextlib.contextmanager
    def get_connection(self) -> Generator:
        """
        Context Manager - 自動處理事務與認證

        ✅ 新增功能：自動注入 user_id 到 PostgreSQL Session

        使用方式:
        ```python
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT ...")
        ```
        """
        conn = None
        try:
            conn = self.pool.get_connection()

            # ✅ 自動注入 user_id 到 PostgreSQL Session
            # 這讓 RLS Policy 可以使用 auth.uid() 進行過濾
            user_id = self._get_current_user_id()
            if user_id:
                with conn.cursor() as cur:
                    try:
                        # 設置 PostgreSQL Session 變數
                        # RLS Policy 會使用 current_setting('request.jwt.claim.sub')
                        cur.execute(
                            "SELECT set_config('request.jwt.claim.sub', %s, false)",
                            (user_id,)
                        )
                        logger.debug(f"✅ 已設置 Session user_id: {user_id}")
                    except Exception as e:
                        logger.warning(f"⚠️ 設置 Session user_id 失敗: {e}")

            yield conn
            conn.commit()
            logger.debug("✅ 事務提交成功")

        except psycopg2.IntegrityError as e:
            if conn:
                conn.rollback()
            logger.error(f"❌ 數據完整性錯誤: {e}")
            raise

        except psycopg2.OperationalError as e:
            if conn:
                conn.rollback()
            logger.error(f"❌ 數據庫操作錯誤: {e}")
            raise

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"❌ 未知錯誤: {e}")
            raise

        finally:
            if conn:
                self.pool.return_connection(conn)

    def retry_on_failure(
        self,
        func: Callable[[], Any],
        max_retries: int = 3,
        delay: int = 1,
    ):
        """
        重試機制 - 處理臨時性網路錯誤

        Args:
            func: 要執行的函數
            max_retries: 最大重試次數
            delay: 重試延遲（秒）

        Returns:
            func 的返回值
        """
        for attempt in range(max_retries):
            try:
                return func()

            except psycopg2.OperationalError as e:
                if attempt == max_retries - 1:
                    logger.error(f"❌ 重試 {max_retries} 次後仍失敗: {e}")
                    raise

                wait_time = delay * (attempt + 1)
                logger.warning(
                    f"⚠️ 第 {attempt + 1}/{max_retries} 次嘗試失敗，"
                    f"等待 {wait_time}s 後重試..."
                )
                time.sleep(wait_time)

    def health_check(self) -> bool:
        """健康檢查"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()

            logger.info("✅ 數據庫連接正常")
            return result is not None

        except Exception as e:
            logger.error(f"❌ 健康檢查失敗: {e}")
            return False

    def execute_query(
        self,
        query: str,
        params: Tuple | None = None,
        fetch_one: bool = False,
        fetch_all: bool = True,
    ):
        """
        通用查詢執行器

        Args:
            query: SQL 查詢
            params: 參數
            fetch_one: 是否只取一筆
            fetch_all: 是否取全部

        Returns:
            查詢結果
        """

        def _execute():
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)

                if fetch_one:
                    return cursor.fetchone()
                elif fetch_all:
                    return cursor.fetchall()
                else:
                    return cursor.rowcount

        return self.retry_on_failure(_execute)

    def batch_insert(
        self,
        table: str,
        columns: list[str],
        values_list: list[Tuple],
    ) -> Tuple[int, int]:
        """
        批次插入

        Args:
            table: 表名
            columns: 欄位列表
            values_list: 值列表（每個元素是一個 tuple）

        Returns:
            (success_count, fail_count)
        """
        success_count = 0
        fail_count = 0

        placeholders = ", ".join(["%s"] * len(columns))
        query = f"""
            INSERT INTO {table} ({', '.join(columns)})
            VALUES ({placeholders})
        """

        with self.get_connection() as conn:
            cursor = conn.cursor()

            for values in values_list:
                try:
                    cursor.execute(query, values)
                    success_count += 1
                except Exception as e:
                    logger.error(f"❌ 批次插入失敗: {e}")
                    fail_count += 1

        log_db_operation("BATCH_INSERT", table, True, success_count)
        return success_count, fail_count

    # ==================== 認證相關方法 ====================

    def _get_current_user_id(self) -> Optional[str]:
        """
        獲取當前登入用戶的 ID

        優先級：
        1. 從 SessionManager 獲取（推薦）
        2. 從 st.session_state 直接獲取
        3. 開發模式：返回預設 user_id

        Returns:
            user_id or None
        """
        try:
            # 方法 1：使用 SessionManager（推薦）
            if HAS_STREAMLIT:
                try:
                    from utils.session_manager import session_manager
                    user_id = session_manager.get_user_id()
                    if user_id:
                        return user_id
                except ImportError:
                    logger.debug("SessionManager 未載入，嘗試其他方法")

                # 方法 2：直接從 st.session_state 獲取
                if hasattr(st, 'session_state'):
                    user_data = st.session_state.get('auth_user')  # type: ignore
                    if user_data and isinstance(user_data, dict):
                        return user_data.get('id')

            # 方法 3：開發模式（如果設定）
            if self.is_dev_mode():
                dev_user_id = self._get_dev_user_id()
                if dev_user_id:
                    logger.debug(f"✅ 使用開發模式 user_id: {dev_user_id}")
                    return dev_user_id

            return None

        except Exception as e:
            logger.debug(f"無法獲取 user_id: {e}")
            return None

    def get_user_id_or_raise(self) -> str:
        """
        獲取當前用戶 ID，如果未登入則拋出異常

        Returns:
            user_id

        Raises:
            ValueError: 用戶未登入
        """
        user_id = self._get_current_user_id()

        if not user_id:
            raise ValueError("用戶未登入，無法執行此操作")

        return user_id

    def is_authenticated(self) -> bool:
        """
        檢查用戶是否已登入

        Returns:
            bool: True=已登入, False=未登入
        """
        return self._get_current_user_id() is not None

    # ==================== 開發模式 ====================

    def is_dev_mode(self) -> bool:
        """
        檢查是否為開發模式（繞過認證）

        開發模式設定方式：
        - Streamlit: .streamlit/secrets.toml 設定 dev_mode = true
        - 環境變數: DEV_MODE=true

        Returns:
            bool: True=開發模式, False=生產模式
        """
        try:
            # Streamlit 環境
            if HAS_STREAMLIT and hasattr(st, 'secrets'):
                return st.secrets.get('dev_mode', False)  # type: ignore

            # 環境變數
            return os.getenv('DEV_MODE', 'false').lower() == 'true'

        except Exception:
            return False

    def _get_dev_user_id(self) -> Optional[str]:
        """
        取得開發模式的預設 user_id

        設定方式：
        - Streamlit: .streamlit/secrets.toml 設定 dev_user_id = "xxx"
        - 環境變數: DEV_USER_ID=xxx

        Returns:
            dev_user_id or None
        """
        try:
            # Streamlit 環境
            if HAS_STREAMLIT and hasattr(st, 'secrets'):
                return st.secrets.get('dev_user_id')  # type: ignore

            # 環境變數
            return os.getenv('DEV_USER_ID')

        except Exception:
            return None

    # ==================== RLS 支援方法 ====================

    def bypass_rls_query(
        self,
        query: str,
        params: Tuple | None = None,
    ):
        """
        繞過 RLS 的查詢（使用 Service Role 權限）

        ⚠️  警告：僅在必要時使用，如：
        - 管理後台查詢所有用戶資料
        - 系統級統計報表
        - 資料遷移腳本

        Args:
            query: SQL 查詢
            params: 參數

        Returns:
            查詢結果
        """
        logger.warning("⚠️  使用 bypass_rls_query - 繞過 RLS 保護")

        def _execute():
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # 臨時提升權限（如果可用）
                try:
                    cursor.execute("SET LOCAL row_security = off")
                except Exception:
                    pass  # 如果無權限，忽略

                cursor.execute(query, params)
                return cursor.fetchall()

        return self.retry_on_failure(_execute)

    def set_rls_user(self, user_id: str):
        """
        手動設置 RLS 使用的 user_id（進階用法）

        Args:
            user_id: 要設置的 user_id
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT set_config('request.jwt.claim.sub', %s, false)",
                (user_id,)
            )
            logger.info(f"✅ 手動設置 RLS user_id: {user_id}")


# ============== 工具函數 ==============

def close_all_connections():
    """關閉所有連接池（應用結束時調用）"""
    _pool_instance.close_all()


# ============== 測試 ==============
if __name__ == "__main__":
    try:
        print("=== 測試 BaseDBService v5.0 ===\n")

        service = BaseDBService()
        print("✅ BaseDBService 初始化成功\n")

        # 測試 1：健康檢查
        print("1. 健康檢查:")
        is_healthy = service.health_check()
        print(f"   結果: {'✅ 正常' if is_healthy else '❌ 異常'}\n")

        # 測試 2：認證狀態
        print("2. 認證狀態:")
        print(f"   已登入: {service.is_authenticated()}")
        print(f"   開發模式: {service.is_dev_mode()}")
        user_id = service._get_current_user_id()
        print(f"   User ID: {user_id or '無'}\n")

        # 測試 3：簡單查詢
        print("3. 查詢測試:")
        with service.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT current_database(), current_user")
            result = cursor.fetchone()
            print(f"   資料庫: {result[0]}")
            print(f"   用戶: {result[1]}\n")

        print("✅ 所有測試完成")

    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        import traceback
        traceback.print_exc()
