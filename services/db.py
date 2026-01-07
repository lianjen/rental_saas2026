"""
租屋管理系統 - 資料庫層 (生產級版本 v2.1 - 完整電費功能)
"""
import streamlit as st
import psycopg2
from psycopg2 import pool, sql
import pandas as pd
import contextlib
import logging
from datetime import datetime, date
from typing import Optional, Tuple, List, Dict
import time

# ============== 統一常數導入 ==============
try:
    from config.constants import (
        ROOMS, PAYMENT, EXPENSE, ELECTRICITY, SYSTEM, UI
    )
    CONSTANTS_LOADED = True
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.error(f"⚠️ 無法導入 config.constants: {e}")
    logger.warning("⚠️ 將使用備用常數")
    CONSTANTS_LOADED = False

# ============== 日誌設定 ==============
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============== 備用常數 (如果 import 失敗) ==============
class BackupConstants:
    """備用常數 - 當 config.constants 無法導入時使用"""
    ALL_ROOMS = ["1A", "1B", "2A", "2B", "3A", "3B", "3C", "3D", "4A", "4B", "4C", "4D"]
    SHARING_ROOMS = ["2A", "2B", "3A", "3B", "3C", "3D", "4A", "4B", "4C", "4D"]
    EXCLUSIVE_ROOMS = ["1A", "1B"]
    PAYMENT_METHODS = ["月繳", "半年繳", "年繳"]
    EXPENSE_CATEGORIES = ["維修", "雜項", "貸款", "水電費", "網路費"]
    PAYMENT_STATUS = ["未繳", "已繳"]
    WATER_FEE = 100

# ============== 常數驗證函數 ==============
def validate_constants():
    """驗證常數的完整性"""
    try:
        if not CONSTANTS_LOADED:
            logger.warning("⚠️ 使用備用常數配置")
            return BackupConstants()
        
        # 驗證房號
        assert len(ROOMS.ALL_ROOMS) > 0, "房號列表不能為空"
        assert len(ROOMS.SHARING_ROOMS) > 0, "分攤房間列表不能為空"
        assert len(ROOMS.EXCLUSIVE_ROOMS) > 0, "獨享房間列表不能為空"
        
        # 驗證子集關係
        for room in ROOMS.EXCLUSIVE_ROOMS:
            assert room in ROOMS.ALL_ROOMS, f"獨享房間 {room} 不在總列表中"
        for room in ROOMS.SHARING_ROOMS:
            assert room in ROOMS.ALL_ROOMS, f"分攤房間 {room} 不在總列表中"
        
        # 驗證繳款方式
        assert len(PAYMENT.METHODS) > 0, "繳款方式不能為空"
        assert len(PAYMENT.STATUSES) > 0, "繳款狀態不能為空"
        
        # 驗證支出分類
        assert len(EXPENSE.CATEGORIES) > 0, "支出分類不能為空"
        
        logger.info("✅ 常數驗證通過")
        return ROOMS, PAYMENT, EXPENSE, ELECTRICITY
    except AssertionError as e:
        logger.error(f"❌ 常數驗證失敗: {e}")
        return BackupConstants()
    except Exception as e:
        logger.error(f"❌ 常數驗證異常: {e}")
        return BackupConstants()

# ============== 資料庫連線池 ==============
class DatabaseConnectionPool:
    """Connection Pool 單例模式 - 管理資料庫連線池"""
    _instance = None
    _pool = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def initialize(self, config: dict):
        """
        初始化連線池
        Args:
            config: Supabase 連線配置 (host, port, database, user, password)
        """
        if self._pool is not None:
            logger.warning("⚠️ 連線池已初始化,跳過重複初始化")
            return
        
        try:
            minconn = SYSTEM.CONNECTION_POOL_MIN if CONSTANTS_LOADED else 2
            maxconn = SYSTEM.CONNECTION_POOL_MAX if CONSTANTS_LOADED else 10
            
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=minconn,
                maxconn=maxconn,
                host=config.get('host'),
                port=config.get('port', 5432),
                database=config.get('database'),
                user=config.get('user'),
                password=config.get('password'),
                connect_timeout=10
            )
            logger.info(f"✅ Connection Pool 已初始化 (min={minconn}, max={maxconn})")
        except Exception as e:
            logger.error(f"❌ Connection Pool 初始化失敗: {e}")
            raise
    
    def get_connection(self):
        """取得連線"""
        if self._pool is None:
            raise RuntimeError("❌ Connection pool 未初始化")
        return self._pool.getconn()
    
    def return_connection(self, conn):
        """歸還連線"""
        if self._pool and conn:
            self._pool.putconn(conn)
    
    def close_all(self):
        """關閉所有連線"""
        if self._pool:
            self._pool.closeall()
            self._pool = None
            logger.info("✅ 所有連線已關閉")

# ============== 主要資料庫類別 ==============
class SupabaseDB:
    """資料庫操作層 - 生產級版本 v2.1"""
    
    def __init__(self):
        """初始化資料庫連線"""
        self.pool = DatabaseConnectionPool()
        self.validated_constants = validate_constants()
        
        try:
            self.pool.initialize(st.secrets.get("supabase", {}))
            logger.info("✅ 資料庫初始化成功")
        except Exception as e:
            logger.error(f"❌ 資料庫初始化失敗: {e}")
            st.error("⚠️ 資料庫連線失敗,請檢查環境設定")
    
    @contextlib.contextmanager
    def _get_connection(self):
        """
        Context Manager 管理連線生命週期
        Yields:
            psycopg2 連線物件
        """
        conn = None
        try:
            conn = self.pool.get_connection()
            yield conn
            conn.commit()
            logger.debug("✅ Transaction 已提交")
        except psycopg2.IntegrityError as e:
            if conn:
                conn.rollback()
            logger.error(f"❌ 資料一致性錯誤: {e}")
            raise
        except psycopg2.OperationalError as e:
            if conn:
                conn.rollback()
            logger.error(f"❌ 操作錯誤 (可能需重試): {e}")
            raise
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"❌ Transaction 失敗: {e}")
            raise
        finally:
            if conn:
                self.pool.return_connection(conn)
    
    def _retry_on_failure(self, func, max_retries: int = 3):
        """
        失敗重試機制
        Args:
            func: 要執行的函數
            max_retries: 最大重試次數 (預設3)
        Returns:
            函數執行結果
        """
        retry_delay = SYSTEM.RETRY_DELAY if CONSTANTS_LOADED else 1
        for attempt in range(max_retries):
            try:
                return func()
            except psycopg2.OperationalError as e:
                if attempt == max_retries - 1:
                    logger.error(f"❌ 重試 {max_retries} 次後失敗: {e}")
                    raise
                wait_time = retry_delay * (attempt + 1)
                logger.warning(
                    f"⚠️ 重試 {attempt + 1}/{max_retries} "
                    f"({wait_time}s後): {str(e)[:100]}"
                )
                time.sleep(wait_time)
    
    def health_check(self) -> bool:
        """
        檢查資料庫連線狀態
        Returns:
            連線是否正常
        """
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT 1")
                result = cur.fetchone()
                logger.info("✅ 資料庫連線正常")
                return result is not None
        except Exception as e:
            logger.error(f"❌ 資料庫連線失敗: {e}")
            return False
    
    # ============== 房客管理 ==============
    
    def get_tenants(self, active_only: bool = True) -> pd.DataFrame:
        """
        取得房客列表
        Args:
            active_only: 只取得在住房客
        Returns:
            房客資訊 DataFrame
        """
        def query():
            with self._get_connection() as conn:
                cur = conn.cursor()
                # ✅ 修正：改用 boolean true/false
                condition = "WHERE is_active = true" if active_only else ""
                cur.execute(f"""
                    SELECT id, room_number, tenant_name, phone, deposit,
                           base_rent, lease_start, lease_end, payment_method,
                           has_water_fee, annual_discount_months, discount_notes,
                           last_ac_cleaning_date, is_active, created_at
                    FROM tenants
                    {condition}
                    ORDER BY room_number
                """)
                columns = [desc[0] for desc in cur.description]
                data = cur.fetchall()
                
                if not data:
                    logger.info("ℹ️ 無房客資料")
                    return pd.DataFrame(columns=columns)
                
                logger.info(f"✅ 取得 {len(data)} 筆房客資料")
                return pd.DataFrame(data, columns=columns)
        
        return self._retry_on_failure(query)
    
    def add_tenant(
        self, room: str, name: str, phone: str, deposit: float,
        base_rent: float, start: date, end: date, payment_method: str,
        has_water_fee: bool = False, annual_discount_months: int = 0,
        discount_notes: str = ''
    ) -> Tuple[bool, str]:
        """新增房客 (含驗證)"""
        try:
            # 驗證房號
            all_rooms = ROOMS.ALL_ROOMS if CONSTANTS_LOADED else BackupConstants.ALL_ROOMS
            if room not in all_rooms:
                return False, f"❌ 無效房號: {room}"
            
            # 驗證繳款方式
            methods = PAYMENT.METHODS if CONSTANTS_LOADED else BackupConstants.PAYMENT_METHODS
            if payment_method not in methods:
                return False, f"❌ 無效繳款方式: {payment_method}"
            
            with self._get_connection() as conn:
                cur = conn.cursor()
                
                # ✅ 修正：改用 boolean true
                cur.execute(
                    "SELECT COUNT(*) FROM tenants WHERE room_number = %s AND is_active = true",
                    (room,)
                )
                if cur.fetchone()[0] > 0:
                    return False, f"⚠️ 房號 {room} 已有房客入住"
                
                cur.execute("""
                    INSERT INTO tenants
                    (room_number, tenant_name, phone, deposit, base_rent,
                     lease_start, lease_end, payment_method, has_water_fee,
                     annual_discount_months, discount_notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (room, name, phone, deposit, base_rent, start, end,
                      payment_method, has_water_fee, annual_discount_months, discount_notes))
                
                logger.info(f"✅ 新增房客: {name} ({room})")
                return True, f"✅ 成功新增房客: {name}"
        except Exception as e:
            logger.error(f"❌ 新增房客失敗: {e}")
            return False, f"❌ 新增失敗: {str(e)[:100]}"
    
    def update_tenant(
        self, tenant_id: int, room: str, name: str, phone: str,
        deposit: float, base_rent: float, start: date, end: date,
        payment_method: str, has_water_fee: bool = False,
        annual_discount_months: int = 0, discount_notes: str = ''
    ) -> Tuple[bool, str]:
        """更新房客資訊 (含驗證)"""
        try:
            # 驗證房號和繳款方式
            all_rooms = ROOMS.ALL_ROOMS if CONSTANTS_LOADED else BackupConstants.ALL_ROOMS
            methods = PAYMENT.METHODS if CONSTANTS_LOADED else BackupConstants.PAYMENT_METHODS
            
            if room not in all_rooms:
                return False, f"❌ 無效房號: {room}"
            if payment_method not in methods:
                return False, f"❌ 無效繳款方式: {payment_method}"
            
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE tenants
                    SET room_number = %s, tenant_name = %s, phone = %s,
                        deposit = %s, base_rent = %s, lease_start = %s,
                        lease_end = %s, payment_method = %s, has_water_fee = %s,
                        annual_discount_months = %s, discount_notes = %s
                    WHERE id = %s
                """, (room, name, phone, deposit, base_rent, start, end,
                      payment_method, has_water_fee, annual_discount_months,
                      discount_notes, tenant_id))
                
                logger.info(f"✅ 更新房客: {name} (ID: {tenant_id})")
                return True, f"✅ 成功更新房客: {name}"
        except Exception as e:
            logger.error(f"❌ 更新房客失敗: {e}")
            return False, f"❌ 更新失敗: {str(e)[:100]}"
    
    def delete_tenant(self, tenant_id: int) -> Tuple[bool, str]:
        """軟刪除房客"""
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                # ✅ 修正：改用 boolean false
                cur.execute("UPDATE tenants SET is_active = false WHERE id = %s", (tenant_id,))
                logger.info(f"✅ 刪除房客 ID: {tenant_id}")
                return True, "✅ 已刪除房客"
        except Exception as e:
            logger.error(f"❌ 刪除房客失敗: {e}")
            return False, f"❌ 刪除失敗: {str(e)[:100]}"
    
    # ============== 繳費管理 ==============
    
    def get_payment_schedule(
        self, year: Optional[int] = None, month: Optional[int] = None,
        room: Optional[str] = None, status: Optional[str] = None
    ) -> pd.DataFrame:
        """取得繳費排程 (支援多重篩選)"""
        def query():
            with self._get_connection() as conn:
                cur = conn.cursor()
                conditions = ["1=1"]
                params = []
                
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
                    SELECT id, room_number, tenant_name, payment_year, payment_month,
                           amount, paid_amount, payment_method, due_date, status,
                           created_at, updated_at
                    FROM payment_schedule
                    WHERE {' AND '.join(conditions)}
                    ORDER BY payment_year DESC, payment_month DESC, room_number
                """
                
                cur.execute(query_sql, params)
                columns = [desc[0] for desc in cur.description]
                data = cur.fetchall()
                return pd.DataFrame(data, columns=columns)
        
        return self._retry_on_failure(query)
    
    def add_payment_schedule(
        self, room: str, tenant_name: str, year: int, month: int,
        amount: float, payment_method: str,
        due_date: Optional[date] = None
    ) -> Tuple[bool, str]:
        """新增繳費排程 (防重複)"""
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                
                # 檢查是否重複
                cur.execute("""
                    SELECT COUNT(*) FROM payment_schedule
                    WHERE room_number = %s AND payment_year = %s AND payment_month = %s
                """, (room, year, month))
                
                if cur.fetchone()[0] > 0:
                    return False, f"⚠️ {year}/{month} {room} 的應收單已存在"
                
                cur.execute("""
                    INSERT INTO payment_schedule
                    (room_number, tenant_name, payment_year, payment_month,
                     amount, paid_amount, payment_method, due_date, status)
                    VALUES (%s, %s, %s, %s, %s, 0, %s, %s, %s)
                """, (room, tenant_name, year, month, amount, payment_method, due_date, '未繳'))
                
                logger.info(f"✅ 新增繳費排程: {room} {year}/{month}")
                return True, "✅ 成功新增"
        except Exception as e:
            logger.error(f"❌ 新增繳費排程失敗: {e}")
            return False, f"❌ 新增失敗: {str(e)[:100]}"
    
    def mark_payment_done(
        self, payment_id: int, paid_amount: Optional[float] = None
    ) -> bool:
        """標記繳費完成"""
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                if paid_amount:
                    cur.execute("""
                        UPDATE payment_schedule
                        SET status = %s, paid_amount = %s, updated_at = NOW()
                        WHERE id = %s
                    """, ('已繳', paid_amount, payment_id))
                else:
                    cur.execute("""
                        UPDATE payment_schedule
                        SET status = %s, paid_amount = amount, updated_at = NOW()
                        WHERE id = %s
                    """, ('已繳', payment_id))
                
                logger.info(f"✅ 標記繳費完成: ID {payment_id}")
                return True
        except Exception as e:
            logger.error(f"❌ 標記繳費失敗: {e}")
            return False
    
    def get_overdue_payments(self) -> pd.DataFrame:
        """取得逾期未繳"""
        def query():
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT room_number, tenant_name, payment_year, payment_month,
                           amount, due_date
                    FROM payment_schedule
                    WHERE status = %s AND due_date < CURRENT_DATE
                    ORDER BY due_date
                """, ('未繳',))
                columns = [desc[0] for desc in cur.description]
                data = cur.fetchall()
                return pd.DataFrame(data, columns=columns)
        
        return self._retry_on_failure(query)
    
    # ============== 備忘錄管理 ==============
    
    def add_memo(self, text: str, priority: str = 'normal') -> bool:
        """新增備忘錄"""
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO memos (memo_text, priority) VALUES (%s, %s)",
                    (text, priority)
                )
                logger.info(f"✅ 新增備忘錄 (優先度: {priority})")
                return True
        except Exception as e:
            logger.error(f"❌ 新增備忘錄失敗: {e}")
            return False
    
    def get_memos(self, include_completed: bool = False) -> List[Dict]:
        """取得備忘錄"""
        def query():
            with self._get_connection() as conn:
                cur = conn.cursor()
                # ✅ 修正：改用 boolean false
                condition = "" if include_completed else "WHERE is_completed = false"
                cur.execute(f"""
                    SELECT id, memo_text, priority, is_completed, created_at
                    FROM memos
                    {condition}
                    ORDER BY is_completed, priority DESC, created_at DESC
                """)
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        
        return self._retry_on_failure(query)
    
    # ============== 支出管理 ==============
    
    def add_expense(
        self, expense_date: date, category: str,
        amount: float, description: str
    ) -> Tuple[bool, str]:
        """新增支出 (含驗證)"""
        try:
            # 驗證分類
            categories = EXPENSE.CATEGORIES if CONSTANTS_LOADED else BackupConstants.EXPENSE_CATEGORIES
            if category not in categories:
                return False, f"❌ 無效分類: {category}"
            
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO expenses (expense_date, category, amount, description)
                    VALUES (%s, %s, %s, %s)
                """, (expense_date, category, amount, description))
                
                logger.info(f"✅ 新增支出: {category} NT${amount}")
                return True, "✅ 成功新增"
        except Exception as e:
            logger.error(f"❌ 新增支出失敗: {e}")
            return False, f"❌ 新增失敗: {str(e)[:100]}"
    
    def get_expenses(self, limit: int = 50) -> pd.DataFrame:
        """取得支出列表"""
        def query():
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT id, expense_date, category, amount, description, created_at
                    FROM expenses
                    ORDER BY expense_date DESC
                    LIMIT %s
                """, (limit,))
                columns = [desc[0] for desc in cur.description]
                data = cur.fetchall()
                return pd.DataFrame(data, columns=columns)
        
        return self._retry_on_failure(query)
    
    # ============== 電費管理 (完整版) ==============
    
    def add_electricity_period(self, year: int, month_start: int, month_end: int):
        """新增計費期間（electricity.py 使用此方法名）"""
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO electricity_periods (period_year, period_month_start, period_month_end)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """, (year, month_start, month_end))
                period_id = cur.fetchone()[0]
                logger.info(f"✅ 新增計費期間: {year}年 {month_start}-{month_end}月")
                return True, f"計費期間已建立: {year}年 {month_start}-{month_end}月", period_id
        except Exception as e:
            logger.error(f"❌ 新增計費期間失敗: {e}")
            return False, str(e), None
    
    def get_all_periods(self):
        """取得所有計費期間（electricity.py 使用此方法名）"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, period_year, period_month_start, period_month_end, created_at
                FROM electricity_periods
                ORDER BY period_year DESC, period_month_start DESC
            """)
            rows = cursor.fetchall()
            return [
                {
                    'id': row[0],
                    'period_year': row[1],
                    'period_month_start': row[2],
                    'period_month_end': row[3],
                    'created_at': row[4]
                }
                for row in rows
            ]
    
    def delete_electricity_period(self, period_id: int):
        """刪除計費期間"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM electricity_periods WHERE id = %s", (period_id,))
            logger.info(f"✅ 刪除計費期間 ID: {period_id}")
            return True, "計費期間已刪除"
    
    def save_electricity_record(self, period_id: int, calc_results: list):
        """儲存電費計算記錄"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                for result in calc_results:
                    cursor.execute("""
                        INSERT INTO electricity_records 
                        (period_id, room_number, room_type, usage_kwh, public_share_kwh, 
                         total_kwh, amount_due, payment_status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, '未繳')
                        ON CONFLICT (period_id, room_number) 
                        DO UPDATE SET 
                            room_type = EXCLUDED.room_type,
                            usage_kwh = EXCLUDED.usage_kwh,
                            public_share_kwh = EXCLUDED.public_share_kwh,
                            total_kwh = EXCLUDED.total_kwh,
                            amount_due = EXCLUDED.amount_due
                    """, (
                        period_id,
                        result['房號'],
                        result['類型'],
                        result['使用度數'],
                        result['公用分攤'],
                        result['總度數'],
                        result['應繳金額']
                    ))
                logger.info(f"✅ 儲存電費記錄: {len(calc_results)} 筆")
                return True, "電費記錄已儲存"
            except Exception as e:
                logger.error(f"❌ 儲存電費記錄失敗: {e}")
                return False, str(e)
    
    def get_electricity_payment_record(self, period_id: int):
        """取得繳費記錄"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT room_number, amount_due, paid_amount, payment_status, 
                       payment_date, notes, updated_at
                FROM electricity_records
                WHERE period_id = %s
                ORDER BY room_number
            """, (period_id,))
            rows = cursor.fetchall()
            
            if not rows:
                return pd.DataFrame()
            
            return pd.DataFrame([
                {
                    '房號': row[0],
                    '應繳金額': row[1],
                    '已繳金額': row[2] or 0,
                    '繳費狀態': row[3],
                    '繳款日期': row[4].strftime('%Y-%m-%d') if row[4] else '-',
                    '備註': row[5] or '-',
                    '更新時間': row[6].strftime('%Y-%m-%d %H:%M') if row[6] else '-'
                }
                for row in rows
            ])
    
    def update_electricity_payment(self, period_id: int, room_number: str, 
                                   payment_status: str, paid_amount: int = 0,
                                   payment_date: str = None, notes: str = ""):
        """更新繳費狀態"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    UPDATE electricity_records
                    SET payment_status = %s,
                        paid_amount = %s,
                        payment_date = %s,
                        notes = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE period_id = %s AND room_number = %s
                """, (payment_status, paid_amount, payment_date, notes, period_id, room_number))
                logger.info(f"✅ 更新繳費狀態: {room_number} -> {payment_status}")
                return True, "繳費狀態已更新"
            except Exception as e:
                logger.error(f"❌ 更新繳費狀態失敗: {e}")
                return False, str(e)
    
    def get_electricity_payment_summary(self, period_id: int):
        """取得繳費統計"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    SUM(amount_due) as total_due,
                    SUM(paid_amount) as total_paid,
                    COUNT(*) FILTER (WHERE payment_status = '已繳') as paid_rooms,
                    COUNT(*) FILTER (WHERE payment_status = '未繳') as unpaid_rooms,
                    COUNT(*) as total_rooms
                FROM electricity_records
                WHERE period_id = %s
            """, (period_id,))
            row = cursor.fetchone()
            
            total_due = row[0] or 0
            total_paid = row[1] or 0
            paid_rooms = row[2] or 0
            unpaid_rooms = row[3] or 0
            total_rooms = row[4] or 0
            
            return {
                'total_due': total_due,
                'total_paid': total_paid,
                'total_balance': total_due - total_paid,
                'paid_rooms': paid_rooms,
                'unpaid_rooms': unpaid_rooms,
                'total_rooms': total_rooms,
                'collection_rate': (total_paid / total_due * 100) if total_due > 0 else 0
            }
    
    def calculate_electricity_cost(
        self, kwh: float, is_summer: bool = False
    ) -> float:
        """
        計算電費 (使用統一常數)
        Args:
            kwh: 用電度數
            is_summer: 是否為夏月
        Returns:
            電費金額
        """
        try:
            if CONSTANTS_LOADED and ELECTRICITY:
                return ELECTRICITY.calculate_progressive_fee(kwh, is_summer)
            else:
                logger.warning("⚠️ 使用備用電費計算")
                # 備用計算
                return round(kwh * 4.5, 2)  # 簡易計算
        except Exception as e:
            logger.error(f"❌ 電費計算失敗: {e}")
            return 0.0

# ============== 初始化單例 ==============

@st.cache_resource
def get_db() -> SupabaseDB:
    """
    取得資料庫實例 (Singleton)
    使用 Streamlit cache 確保整個 session 只有一個實例
    Returns:
        SupabaseDB 實例
    """
    logger.info("✅ 初始化 SupabaseDB 單例")
    return SupabaseDB()

# ============== 測試與驗證 ==============

if __name__ == "__main__":
    # 簡易測試
    print("🧪 開始測試 services/db.py...")
    
    # 測試常數驗證
    print("\n1️⃣ 測試常數驗證:")
    try:
        validate_constants()
        print("✅ 常數驗證成功")
    except Exception as e:
        print(f"❌ 常數驗證失敗: {e}")
    
    # 測試連線池
    print("\n2️⃣ 測試連線池初始化:")
    try:
        pool = DatabaseConnectionPool()
        print("✅ 連線池實例化成功")
    except Exception as e:
        print(f"❌ 連線池初始化失敗: {e}")
    
    print("\n✅ 測試完成!")
