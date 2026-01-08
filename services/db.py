import streamlit as st
import psycopg2
from psycopg2 import pool, sql
from psycopg2.extras import RealDictCursor
import pandas as pd
import contextlib
import logging
from datetime import datetime, date
from typing import Optional, Tuple, List, Dict
import time
from services.logger import logger, log_db_operation

# 載入常數配置
try:
    from config.constants import ROOMS, PAYMENT, EXPENSE, ELECTRICITY, SYSTEM, UI
    CONSTANTS_LOADED = True
except ImportError as e:
    logger.error(f"無法載入 config.constants: {e}")
    logger.warning("使用備用常數")
    CONSTANTS_LOADED = False


class BackupConstants:
    """備用常數（如果 config.constants 載入失敗）"""
    class ROOMS:
        ALL_ROOMS = ['1A', '1B', '2A', '2B', '3A', '3B', '3C', '3D', '4A', '4B', '4C', '4D']
        SHARING_ROOMS = ['2A', '2B', '3A', '3B', '3C', '3D', '4A', '4B', '4C', '4D']
        EXCLUSIVE_ROOMS = ['1A', '1B']
    
    class PAYMENT:
        METHODS = ['月繳', '季繳', '年繳']
        STATUSES = ['unpaid', 'paid', 'overdue']
    
    class EXPENSE:
        CATEGORIES = ['水電', '修繕', '清潔', '其他']
    
    class ELECTRICITY:
        WATER_FEE = 100
    
    class SYSTEM:
        CONNECTION_POOL_MIN = 2
        CONNECTION_POOL_MAX = 10
        RETRY_DELAY = 1


def validate_constants():
    """驗證常數配置"""
    try:
        if not CONSTANTS_LOADED:
            logger.warning("常數配置未載入，使用備用常數")
            return BackupConstants.ROOMS, BackupConstants.PAYMENT, BackupConstants.EXPENSE, BackupConstants.ELECTRICITY
        
        # 驗證房間常數
        assert len(ROOMS.ALL_ROOMS) > 0, "房間列表不能為空"
        assert len(ROOMS.SHARING_ROOMS) > 0, "共用房間列表不能為空"
        assert len(ROOMS.EXCLUSIVE_ROOMS) > 0, "獨立房間列表不能為空"
        
        # 驗證共用房間是否在全部房間中
        for room in ROOMS.EXCLUSIVE_ROOMS:
            assert room in ROOMS.ALL_ROOMS, f"獨立房間 {room} 不在全部房間中"
        
        for room in ROOMS.SHARING_ROOMS:
            assert room in ROOMS.ALL_ROOMS, f"共用房間 {room} 不在全部房間中"
        
        # 驗證付款常數
        assert len(PAYMENT.METHODS) > 0, "付款方式不能為空"
        assert len(PAYMENT.STATUSES) > 0, "付款狀態不能為空"
        
        # 驗證開支常數
        assert len(EXPENSE.CATEGORIES) > 0, "開支類別不能為空"
        
        logger.info("常數驗證成功")
        return ROOMS, PAYMENT, EXPENSE, ELECTRICITY
    
    except AssertionError as e:
        logger.error(f"常數驗證失敗: {e}")
        return BackupConstants.ROOMS, BackupConstants.PAYMENT, BackupConstants.EXPENSE, BackupConstants.ELECTRICITY
    except Exception as e:
        logger.error(f"常數驗證異常: {e}")
        return BackupConstants.ROOMS, BackupConstants.PAYMENT, BackupConstants.EXPENSE, BackupConstants.ELECTRICITY


class DatabaseConnectionPool:
    """資料庫連線池（單例模式）"""
    
    _instance = None
    _pool = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def initialize(self, config: dict):
        """初始化連線池
        
        Args:
            config: {'host': ..., 'port': ..., 'database': ..., 'user': ..., 'password': ...}
        """
        if self._pool is not None:
            logger.warning("連線池已初始化，跳過重複初始化")
            return
        
        try:
            min_conn = SYSTEM.CONNECTION_POOL_MIN if CONSTANTS_LOADED else 2
            max_conn = SYSTEM.CONNECTION_POOL_MAX if CONSTANTS_LOADED else 10
            
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                min_conn, max_conn,
                host=config.get('host'),
                port=config.get('port', 5432),
                database=config.get('database'),
                user=config.get('user'),
                password=config.get('password'),
                connect_timeout=10
            )
            
            logger.info(f"連線池初始化成功 (min={min_conn}, max={max_conn})")
        
        except Exception as e:
            logger.error(f"連線池初始化失敗: {e}")
            raise
    
    def get_connection(self):
        """取得連線"""
        if self._pool is None:
            raise RuntimeError("連線池未初始化")
        
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
            logger.info("連線池已關閉")


class SupabaseDB:
    """Supabase 資料庫操作類 (v2.2) - 已整合日誌"""
    
    def __init__(self):
        self.pool = DatabaseConnectionPool()
        self.validated_constants = validate_constants()
        
        try:
            self.pool.initialize(st.secrets.get("supabase", {}))
            logger.info("SupabaseDB 初始化成功")
        except Exception as e:
            logger.error(f"SupabaseDB 初始化失敗: {e}")
            st.error("資料庫連線失敗，請檢查設定")
    
    @contextlib.contextmanager
    def get_connection(self):
        """Context Manager - 自動管理連線和事務"""
        conn = None
        try:
            conn = self.pool.get_connection()
            yield conn
            conn.commit()
            logger.debug("資料庫事務提交成功")
        
        except psycopg2.IntegrityError as e:
            if conn:
                conn.rollback()
            logger.error(f"資料庫完整性錯誤: {e}")
            raise
        
        except psycopg2.OperationalError as e:
            if conn:
                conn.rollback()
            logger.error(f"資料庫操作錯誤: {e}")
            raise
        
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"資料庫事務失敗: {e}")
            raise
        
        finally:
            if conn:
                self.pool.return_connection(conn)
    
    def retry_on_failure(self, func, max_retries: int = 3):
        """重試機制"""
        retry_delay = SYSTEM.RETRY_DELAY if CONSTANTS_LOADED else 1
        
        for attempt in range(max_retries):
            try:
                return func()
            except psycopg2.OperationalError as e:
                if attempt == max_retries - 1:
                    logger.error(f"重試 {max_retries} 次失敗: {e}")
                    raise
                
                wait_time = retry_delay * (attempt + 1)
                logger.warning(
                    f"資料庫操作失敗 (嘗試 {attempt + 1}/{max_retries})，"
                    f"等待 {wait_time}s 後重試: {str(e)[:100]}"
                )
                time.sleep(wait_time)
    
    def health_check(self) -> bool:
        """健康檢查"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT 1")
                result = cur.fetchone()
                logger.info("資料庫健康檢查通過")
                return result is not None
        except Exception as e:
            logger.error(f"資料庫健康檢查失敗: {e}")
            return False
    
    # ==================== 房客管理 ====================
    
    def get_tenants(self, active_only: bool = True) -> pd.DataFrame:
        """取得所有房客
        
        Args:
            active_only: 只取得活躍房客
        
        Returns:
            房客 DataFrame
        """
        def query():
            with self.get_connection() as conn:
                cur = conn.cursor()
                condition = "WHERE is_active = true" if active_only else ""
                
                cur.execute(f"""
                    SELECT id, room_number, tenant_name, phone, deposit, base_rent,
                           lease_start, lease_end, payment_method, has_water_fee,
                           annual_discount_months, discount_notes, last_acc_cleaning_date,
                           is_active, created_at
                    FROM tenants {condition}
                    ORDER BY room_number
                """)
                
                columns = [desc[0] for desc in cur.description]
                data = cur.fetchall()
                
                if not data:
                    logger.info("沒有房客記錄")
                    return pd.DataFrame(columns=columns)
                
                logger.info(f"取得 {len(data)} 位房客")
                return pd.DataFrame(data, columns=columns)
        
        return self.retry_on_failure(query)
    
    def add_tenant(self, room: str, name: str, phone: str, deposit: float,
                   base_rent: float, start: date, end: date, payment_method: str,
                   has_water_fee: bool = False, annual_discount_months: int = 0,
                   discount_notes: str = "") -> Tuple[bool, str]:
        """新增房客
        
        Args:
            room: 房號
            name: 房客名稱
            phone: 聯絡電話
            ... (其他參數)
        
        Returns:
            (成功, 訊息)
        """
        try:
            # 驗證房號
            all_rooms = ROOMS.ALL_ROOMS if CONSTANTS_LOADED else BackupConstants.ROOMS.ALL_ROOMS
            if room not in all_rooms:
                logger.warning(f"無效房號: {room}")
                return False, f"房號 {room} 無效"
            
            # 驗證付款方式
            methods = PAYMENT.METHODS if CONSTANTS_LOADED else BackupConstants.PAYMENT.METHODS
            if payment_method not in methods:
                logger.warning(f"無效付款方式: {payment_method}")
                return False, f"付款方式 {payment_method} 無效"
            
            with self.get_connection() as conn:
                cur = conn.cursor()
                
                # 檢查房間是否已有活躍房客
                cur.execute("""
                    SELECT COUNT(*) FROM tenants
                    WHERE room_number = %s AND is_active = true
                """, (room,))
                
                if cur.fetchone()[0] > 0:
                    logger.warning(f"房間 {room} 已有房客")
                    return False, f"房間 {room} 已有房客"
                
                # 新增房客
                cur.execute("""
                    INSERT INTO tenants (
                        room_number, tenant_name, phone, deposit, base_rent,
                        lease_start, lease_end, payment_method, has_water_fee,
                        annual_discount_months, discount_notes
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    room, name, phone, deposit, base_rent, start, end,
                    payment_method, has_water_fee, annual_discount_months, discount_notes
                ))
                
                log_db_operation("INSERT", "tenants", True, 1)
                logger.info(f"房客 {name} 新增至房間 {room}")
                return True, f"房客 {name} 新增成功"
        
        except Exception as e:
            log_db_operation("INSERT", "tenants", False, error=str(e))
            logger.error(f"新增房客失敗: {str(e)}")
            return False, f"新增失敗: {str(e)[:100]}"
    
    def update_tenant(self, tenant_id: int, room: str, name: str, phone: str,
                      deposit: float, base_rent: float, start: date, end: date,
                      payment_method: str, has_water_fee: bool = False,
                      annual_discount_months: int = 0, discount_notes: str = "") -> Tuple[bool, str]:
        """更新房客資料"""
        try:
            all_rooms = ROOMS.ALL_ROOMS if CONSTANTS_LOADED else BackupConstants.ROOMS.ALL_ROOMS
            methods = PAYMENT.METHODS if CONSTANTS_LOADED else BackupConstants.PAYMENT.METHODS
            
            if room not in all_rooms:
                return False, f"房號 {room} 無效"
            if payment_method not in methods:
                return False, f"付款方式 {payment_method} 無效"
            
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE tenants SET
                        room_number = %s, tenant_name = %s, phone = %s,
                        deposit = %s, base_rent = %s, lease_start = %s,
                        lease_end = %s, payment_method = %s, has_water_fee = %s,
                        annual_discount_months = %s, discount_notes = %s
                    WHERE id = %s
                """, (
                    room, name, phone, deposit, base_rent, start, end,
                    payment_method, has_water_fee, annual_discount_months, discount_notes, tenant_id
                ))
                
                log_db_operation("UPDATE", "tenants", True, 1)
                logger.info(f"房客 ID {tenant_id} 更新成功")
                return True, f"房客 {
name} 更新成功"
        
        except Exception as e:
            log_db_operation("UPDATE", "tenants", False, error=str(e))
            logger.error(f"更新房客失敗: {str(e)}")
            return False, f"更新失敗: {str(e)[:100]}"
    
    def delete_tenant(self, tenant_id: int) -> Tuple[bool, str]:
        """軟刪除房客（標記為非活躍）"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE tenants SET is_active = false WHERE id = %s
                """, (tenant_id,))
                
                log_db_operation("UPDATE", "tenants", True, 1)
                logger.info(f"房客 ID {tenant_id} 已刪除")
                return True, "房客已刪除"
        
        except Exception as e:
            log_db_operation("UPDATE", "tenants", False, error=str(e))
            logger.error(f"刪除房客失敗: {str(e)}")
            return False, f"刪除失敗: {str(e)[:100]}"
    
    # ==================== 租金管理 ====================
    
    def get_payment_schedule(self, year: Optional[int] = None, month: Optional[int] = None,
                            room: Optional[str] = None, status: Optional[str] = None) -> pd.DataFrame:
        """查詢租金排程
        
        Args:
            year: 年份篩選
            month: 月份篩選
            room: 房號篩選
            status: 狀態篩選
        
        Returns:
            租金排程 DataFrame
        """
        def query():
            with self.get_connection() as conn:
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
                
                log_db_operation("SELECT", "payment_schedule", True, len(data))
                return pd.DataFrame(data, columns=columns)
        
        return self.retry_on_failure(query)
    
    def add_payment_schedule(self, room: str, tenant_name: str, year: int, month: int,
                             amount: float, payment_method: str,
                             due_date: Optional[date] = None) -> Tuple[bool, str]:
        """新增租金排程"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                
                # 檢查是否已存在
                cur.execute("""
                    SELECT COUNT(*) FROM payment_schedule
                    WHERE room_number = %s AND payment_year = %s AND payment_month = %s
                """, (room, year, month))
                
                if cur.fetchone()[0] > 0:
                    logger.warning(f"排程已存在: {room} {year}/{month}")
                    return False, f"{year}/{month} 月份 {room} 房間排程已存在"
                
                # 新增排程
                cur.execute("""
                    INSERT INTO payment_schedule (
                        room_number, tenant_name, payment_year, payment_month,
                        amount, paid_amount, payment_method, due_date, status
                    ) VALUES (%s, %s, %s, %s, %s, 0, %s, %s, 'unpaid')
                """, (room, tenant_name, year, month, amount, payment_method, due_date))
                
                log_db_operation("INSERT", "payment_schedule", True, 1)
                logger.info(f"排程新增: {room} {year}/{month} ${amount}")
                return True, "排程新增成功"
        
        except Exception as e:
            log_db_operation("INSERT", "payment_schedule", False, error=str(e))
            logger.error(f"新增排程失敗: {str(e)}")
            return False, f"新增失敗: {str(e)[:100]}"
    
    def mark_payment_done(self, payment_id: int, paid_amount: Optional[float] = None) -> bool:
        """標記租金已繳"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                
                if paid_amount:
                    cur.execute("""
                        UPDATE payment_schedule
                        SET status = 'paid', paid_amount = %s, updated_at = NOW()
                        WHERE id = %s
                    """, (paid_amount, payment_id))
                else:
                    cur.execute("""
                        UPDATE payment_schedule
                        SET status = 'paid', paid_amount = amount, updated_at = NOW()
                        WHERE id = %s
                    """, (payment_id,))
                
                log_db_operation("UPDATE", "payment_schedule", True, 1)
                logger.info(f"租金 ID {payment_id} 標記為已繳")
                return True
        
        except Exception as e:
            log_db_operation("UPDATE", "payment_schedule", False, error=str(e))
            logger.error(f"標記租金失敗: {str(e)}")
            return False
    
    def get_overdue_payments(self) -> pd.DataFrame:
        """取得逾期租金"""
        def query():
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT room_number, tenant_name, payment_year, payment_month,
                           amount, due_date
                    FROM payment_schedule
                    WHERE status = 'unpaid' AND due_date < CURRENT_DATE
                    ORDER BY due_date
                """)
                
                columns = [desc[0] for desc in cur.description]
                data = cur.fetchall()
                
                log_db_operation("SELECT", "payment_schedule (overdue)", True, len(data))
                logger.warning(f"找到 {len(data)} 筆逾期租金")
                return pd.DataFrame(data, columns=columns)
        
        return self.retry_on_failure(query)
    
    def check_payment_exists(self, room: str, year: int, month: int) -> bool:
        """檢查排程是否存在
        
        Args:
            room: 房號
            year: 年份
            month: 月份
        
        Returns:
            是否存在
        """
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT COUNT(*) FROM payment_schedule
                    WHERE room_number = %s AND payment_year = %s AND payment_month = %s
                """, (room, year, month))
                
                exists = cur.fetchone()[0] > 0
                logger.debug(f"檢查排程: {room} {year}/{month} - {'存在' if exists else '不存在'}")
                return exists
        
        except Exception as e:
            logger.error(f"檢查排程失敗: {str(e)}")
            return False
    
    def batch_create_payment_schedule(self, schedules: list) -> tuple:
        """批量建立租金排程
        
        Args:
            schedules: [
                {
                    'room_number': '1A',
                    'tenant_name': '王小明',
                    'payment_year': 2026,
                    'payment_month': 1,
                    'amount': 5000,
                    'payment_method': '月繳',
                    'due_date': date(2026, 1, 5)
                },
                ...
            ]
        
        Returns:
            (成功筆數, 跳過筆數, 失敗筆數)
        """
        success_count = 0
        skip_count = 0
        fail_count = 0
        
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                
                for schedule in schedules:
                    try:
                        # 檢查是否已存在
                        cur.execute("""
                            SELECT COUNT(*) FROM payment_schedule
                            WHERE room_number = %s AND payment_year = %s AND payment_month = %s
                        """, (
                            schedule['room_number'],
                            schedule['payment_year'],
                            schedule['payment_month']
                        ))
                        
                        if cur.fetchone()[0] > 0:
                            skip_count += 1
                            continue
                        
                        # 新增排程
                        cur.execute("""
                            INSERT INTO payment_schedule (
                                room_number, tenant_name, payment_year, payment_month,
                                amount, paid_amount, payment_method, due_date, status
                            ) VALUES (%s, %s, %s, %s, %s, 0, %s, %s, 'unpaid')
                        """, (
                            schedule['room_number'],
                            schedule['tenant_name'],
                            schedule['payment_year'],
                            schedule['payment_month'],
                            schedule['amount'],
                            schedule['payment_method'],
                            schedule['due_date']
                        ))
                        
                        success_count += 1
                    
                    except Exception as e:
                        logger.error(f"排程新增失敗: {schedule['room_number']} - {e}")
                        fail_count += 1
                
                log_db_operation("INSERT", "payment_schedule (batch)", True, success_count)
                logger.info(f"批量新增完成: 成功 {success_count}，跳過 {skip_count}，失敗 {fail_count}")
                return success_count, skip_count, fail_count
        
        except Exception as e:
            logger.error(f"批量新增租金排程失敗: {str(e)}")
            return 0, 0, len(schedules)
    
    def get_payment_statistics(self, year: int = None, month: int = None) -> dict:
        """取得租金統計"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                
                conditions = ["1=1"]
                params = []
                
                if year:
                    conditions.append("payment_year = %s")
                    params.append(year)
                if month:
                    conditions.append("payment_month = %s")
                    params.append(month)
                
                where_clause = " AND ".join(conditions)
                
                cur.execute(f"""
                    SELECT
                        COUNT(*) as total_count,
                        SUM(amount) as total_amount,
                        SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END) as paid_count,
                        SUM(CASE WHEN status = 'paid' THEN paid_amount ELSE 0 END) as paid_amount,
                        SUM(CASE WHEN status = 'unpaid' THEN 1 ELSE 0 END) as unpaid_count,
                        SUM(CASE WHEN status = 'unpaid' THEN amount ELSE 0 END) as unpaid_amount
                    FROM payment_schedule
                    WHERE {where_clause}
                """, params)
                
                row = cur.fetchone()
                
                if not row or row[0] == 0:
                    logger.debug("沒有租金記錄")
                    return {
                        'total_amount': 0, 'paid_amount': 0, 'unpaid_amount': 0,
                        'total_count': 0, 'paid_count': 0, 'unpaid_count': 0, 'payment_rate': 0
                    }
                
                total_count, total_amount, paid_count, paid_amount, unpaid_count, unpaid_amount = row
                payment_rate = (paid_count / total_count * 100) if total_count > 0 else 0
                
                log_db_operation("SELECT", "payment_schedule (statistics)", True, total_count)
                logger.debug(
                    f"租金統計: 應收 ${total_amount or 0:,.0f}，"
                    f"實收 ${paid_amount or 0:,.0f}，"
                    f"收款率 {payment_rate:.1f}%"
                )
                
                return {
                    'total_amount': float(total_amount or 0),
                    'paid_amount': float(paid_amount or 0),
                    'unpaid_amount': float(unpaid_amount or 0),
                    'total_count': int(total_count),
                    'paid_count': int(paid_count),
                    'unpaid_count': int(unpaid_count),
                    'payment_rate': round(payment_rate, 1)
                }
        
        except Exception as e:
            logger.error(f"取得租金統計失敗: {str(e)}")
            return {}
    
    def get_payment_trends(self, year: int) -> list:
        """取得全年收款趨勢
        
        Args:
            year: 年份
        
        Returns:
            [{'month': 1, 'total_amount': ..., 'paid_amount': ..., 'payment_rate': ...}, ...]
        """
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT
                        payment_month,
                        SUM(amount) as total_amount,
                        SUM(CASE WHEN status = 'paid' THEN paid_amount ELSE 0 END) as paid_amount,
                        COUNT(*) as total_count,
                        SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END) as paid_count
                    FROM payment_schedule
                    WHERE payment_year = %s
                    GROUP BY payment_month
                    ORDER BY payment_month
                """, (year,))
                
                trends = []
                for row in cur.fetchall():
                    month, total_amt, paid_amt, total_cnt, paid_cnt = row
                    payment_rate = (paid_cnt / total_cnt * 100) if total_cnt > 0 else 0
                    
                    trends.append({
                        'month': int(month),
                        'total_amount': float(total_amt or 0),
                        'paid_amount': float(paid_amt
 or 0),
                        'payment_rate': round(payment_rate, 1)
                    })
                
                log_db_operation("SELECT", "payment_schedule (trends)", True, len(trends))
                logger.info(f"取得 {year} 年的 {len(trends)} 個月份趨勢")
                return trends
        
        except Exception as e:
            logger.error(f"取得收款趨勢失敗: {str(e)}")
            return []
    
    def batch_mark_paid(self, payment_ids: list) -> tuple:
        """批量標記為已繳
        
        Args:
            payment_ids: [id1, id2, ...]
        
        Returns:
            (成功筆數, 失敗筆數)
        """
        success_count = 0
        fail_count = 0
        
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                
                for payment_id in payment_ids:
                    try:
                        cur.execute("""
                            UPDATE payment_schedule
                            SET status = 'paid', paid_amount = amount, updated_at = NOW()
                            WHERE id = %s
                        """, (payment_id,))
                        
                        success_count += 1
                    except Exception as e:
                        logger.error(f"標記租金 ID {payment_id} 失敗: {e}")
                        fail_count += 1
                
                log_db_operation("UPDATE", "payment_schedule (batch)", True, success_count)
                logger.info(f"批量標記完成: 成功 {success_count}，失敗 {fail_count}")
                return success_count, fail_count
        
        except Exception as e:
            logger.error(f"批量標記租金失敗: {str(e)}")
            return 0, len(payment_ids)
    
    def delete_payment_schedule(self, payment_id: int) -> tuple:
        """刪除租金排程
        
        Args:
            payment_id: 租金 ID
        
        Returns:
            (成功, 訊息)
        """
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    DELETE FROM payment_schedule WHERE id = %s
                """, (payment_id,))
                
                log_db_operation("DELETE", "payment_schedule", True, 1)
                logger.info(f"租金 ID {payment_id} 已刪除")
                return True, "刪除成功"
        
        except Exception as e:
            log_db_operation("DELETE", "payment_schedule", False, error=str(e))
            logger.error(f"刪除租金失敗: {str(e)}")
            return False, f"刪除失敗: {str(e)}"
    
    # ==================== 備忘錄 ====================
    
    def add_memo(self, text: str, priority: str = "normal") -> bool:
        """新增備忘錄"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO memos (memo_text, priority)
                    VALUES (%s, %s)
                """, (text, priority))
                
                log_db_operation("INSERT", "memos", True, 1)
                logger.info(f"備忘錄新增: {priority} 優先度")
                return True
        
        except Exception as e:
            log_db_operation("INSERT", "memos", False, error=str(e))
            logger.error(f"新增備忘錄失敗: {str(e)}")
            return False
    
    def get_memos(self, include_completed: bool = False) -> List[Dict]:
        """取得備忘錄
        
        Args:
            include_completed: 是否包含已完成的備忘錄
        
        Returns:
            備忘錄列表
        """
        def query():
            with self.get_connection() as conn:
                cur = conn.cursor()
                condition = "" if include_completed else "WHERE is_completed = false"
                
                cur.execute(f"""
                    SELECT id, memo_text, priority, is_completed, created_at
                    FROM memos {condition}
                    ORDER BY is_completed, priority DESC, created_at DESC
                """)
                
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        
        return self.retry_on_failure(query)
    
    # ==================== 開支管理 ====================
    
    def add_expense(self, expense_date: date, category: str, amount: float,
                    description: str = "") -> Tuple[bool, str]:
        """新增開支"""
        try:
            # 驗證類別
            categories = EXPENSE.CATEGORIES if CONSTANTS_LOADED else BackupConstants.EXPENSE.CATEGORIES
            
            if category not in categories:
                logger.warning(f"無效開支類別: {category}")
                return False, f"開支類別 {category} 無效"
            
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO expenses (expense_date, category, amount, description)
                    VALUES (%s, %s, %s, %s)
                """, (expense_date, category, amount, description))
                
                log_db_operation("INSERT", "expenses", True, 1)
                logger.info(f"開支新增: {category} NT${amount:,.0f}")
                return True, "開支新增成功"
        
        except Exception as e:
            log_db_operation("INSERT", "expenses", False, error=str(e))
            logger.error(f"新增開支失敗: {str(e)}")
            return False, f"新增失敗: {str(e)[:100]}"
    
    def get_expenses(self, limit: int = 50) -> pd.DataFrame:
        """取得最近開支
        
        Args:
            limit: 筆數限制
        
        Returns:
            開支 DataFrame
        """
        def query():
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT id, expense_date, category, amount, description, created_at
                    FROM expenses
                    ORDER BY expense_date DESC
                    LIMIT %s
                """, (limit,))
                
                columns = [desc[0] for desc in cur.description]
                data = cur.fetchall()
                
                log_db_operation("SELECT", "expenses", True, len(data))
                return pd.DataFrame(data, columns=columns)
        
        return self.retry_on_failure(query)
    
    # ==================== 電費管理 ====================
    
    def add_electricity_period(self, year: int, month_start: int,
                               month_end: int) -> Tuple[bool, str, Optional[int]]:
        """新增電費計費週期"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO electricity_periods (
                        period_year, period_month_start, period_month_end
                    ) VALUES (%s, %s, %s)
                    RETURNING id
                """, (year, month_start, month_end))
                
                period_id = cur.fetchone()[0]
                log_db_operation("INSERT", "electricity_periods", True, 1)
                logger.info(f"電費週期新增: {year}/{month_start}-{month_end}")
                return True, f"{year} 年 {month_start}-{month_end} 月計費週期新增成功", period_id
        
        except Exception as e:
            log_db_operation("INSERT", "electricity_periods", False, error=str(e))
            logger.error(f"新增電費週期失敗: {str(e)}")
            return False, str(e), None
    
    def get_all_periods(self) -> List[Dict]:
        """取得所有電費週期"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, period_year, period_month_start, period_month_end, created_at
                    FROM electricity_periods
                    ORDER BY period_year DESC, period_month_start DESC
                """)
                
                rows = cursor.fetchall()
                result = [
                    {
                        'id': row[0],
                        'period_year': row[1],
                        'period_month_start': row[2],
                        'period_month_end': row[3],
                        'created_at': row[4]
                    }
                    for row in rows
                ]
                
                log_db_operation("SELECT", "electricity_periods", True, len(result))
                return result
        
        except Exception as e:
            log_db_operation("SELECT", "electricity_periods", False, error=str(e))
            logger.error(f"取得電費週期失敗: {str(e)}")
            return []
    
    def delete_electricity_period(self, period_id: int) -> Tuple[bool, str]:
        """刪除電費週期"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM electricity_periods WHERE id = %s
                """, (period_id,))
                
                log_db_operation("DELETE", "electricity_periods", True, 1)
                logger.info(f"電費週期 ID {period_id} 已刪除")
                return True, "刪除成功"
        
        except Exception as e:
            log_db_operation("DELETE", "electricity_periods", False, error=str(e))
            logger.error(f"刪除電費週期失敗: {str(e)}")
            return False, str(e)
    
    def save_electricity_record(self, period_id: int, calc_results: list) -> Tuple[bool, str]:
        """保存電費計算結果"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                for result in calc_results:
                    cursor.execute("""
                        INSERT INTO electricity_records (
                            period_id, room_number, room_type, usage_kwh,
                            public_share_kwh, total_kwh, amount_due, payment_status
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'unpaid')
                        ON CONFLICT (period_id, room_number) DO UPDATE SET
                            room_type = EXCLUDED.room_type,
                            usage_kwh = EXCLUDED.usage_kwh,
                            public_share_kwh = EXCLUDED.public_share_kwh,
                            total_kwh = EXCLUDED.total_kwh,
                            amount_due = EXCLUDED.amount_due
                    """, (
                        period_id, result['room_number'], result['room_type'],
                        result['usage_kwh'], result['public_share_kwh'],
                        result['total_kwh'], result['amount_due']
                    ))
                
                log_db_operation("INSERT", "electricity_records", True, len(calc_results))
                logger.info(f"電費記錄已保存: {len(calc_results)} 筆")
                return True, "電費記錄保存成功"
            
            except Exception as e:
                log_db_operation("INSERT", "electricity_records", False, error=str(e))
                logger.error(f"保存電費記錄失敗: {str(e)}")
                return False, str(e)
    
    def get_electricity_payment_record(self, period_id: int) -> pd.DataFrame:
        """取得電費繳款記錄"""
        try:
            with self.get_connection() as conn:
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
                
                data = [
                    [
                        row[0], row[1], row[2] or 0, row[3],
                        row[4].strftime('%Y-%m-%d') if row[4] else '-',
                        row[5] or '-',
                        row[6].strftime('%Y-%m-%d %H:%M') if row[6] else '-'
                    ]
                    for row in rows
                ]
                
                log_db_operation("SELECT", "electricity_records", True, len(data))
                return pd.DataFrame(data)
        
        except Exception as e:
            log_db_operation("SELECT", "electricity_records", False, error=str(e))
            logger.error(f"取得電費繳款記錄失敗: {str(e)}")
            return pd.DataFrame()
    
    def update_electricity_payment(self, period_id: int, room_number: str,
                                   payment_status: str, paid_amount: int = 0,
                                   payment_date: str = None, notes: str = "") -> Tuple[bool, str]:
        """更新電費繳款狀態"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE electricity_records
                    SET payment_status = %s, paid_amount = %s, payment_date = %s,
                        notes = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE period_id = %s AND room_number = %s
                """, (payment_status, paid_amount, payment_date, notes, period_id, room_number))
                
                log_db_operation("UPDATE", "electricity_records", True, 1)
                logger.info(f"電費繳款更新: {room_number} - {payment_status}")
                return True, f"房間 {room_number} 繳款狀態已更新"
        
        except Exception as e:
            log_db_operation("UPDATE", "electricity_records", False, error=str(e))
            logger.error(f"更新電費繳款失敗: {str(e)}")
            return False, str(e)
    
    def get_electricity_payment_summary(self, period_id: int) -> dict:
        """取得電費繳款摘要"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT
                        SUM(amount_due) as total_due,
                        SUM(paid_amount) as total_paid,
                        COUNT(CASE WHEN payment_status = 'paid' THEN 1 END) as paid_rooms,
                        COUNT(CASE WHEN payment_status = 'unpaid' THEN 1 END) as unpaid_rooms,
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
                
                collection_rate = (total_paid / total_due * 100) if total_due > 0 else 0
                
                log_db_operation("SELECT", "electricity_records (summary)", True, total_rooms)
                logger.debug(
                    f"電費摘要: 應收 ${total_due:,.0f}，"
                    f"實收 ${total_paid:,.0f}，收款率 {collection_rate:.1f}%"
                )
                
                return {
                    'total_due': total_due,
                    'total_paid': total_paid,
                    'total_balance': total_due - total_paid,
                    'paid_rooms': paid_rooms,
                    'unpaid_rooms': unpaid_rooms,
                    'total_rooms': total_rooms,
                    'collection_rate': collection_rate
                }
        
        except Exception as e:
            log_db_operation("SELECT", "electricity_records (summary)", False, error=str(e))
            logger.error(f"取得電費摘要失敗: {str(e)}")
            return {}
    
    def calculate_electricity_cost(self, kwh: float, is_summer: bool = False) -> float:
        """計算電費成本
        
        Args:
            kwh: 度數
            is_summer: 是否為夏季
        
        Returns:
            費用
        """
        try:
            if CONSTANTS_LOADED and ELECTRICITY:
                return ELECTRICITY.calculate_progressive_fee(kwh, is_summer)
            else:
                logger.warning("使用備用電費計算")
                return round(kwh * 4.5, 2)
        
        except Exception as e:
            logger.error(f"計算電費失敗: {str(e)}")
            return 0.0


@st.cache_resource
def get_db() -> SupabaseDB:
    """單例模式 - 透過 Streamlit 快取取得資料庫實例
    
    Returns:
        SupabaseDB 實例
    """
    logger.info("初始化 SupabaseDB 實例")
    return SupabaseDB()


if __name__ == "__main__":
    logger.info("services/db.py 開始執行")
    
    # 1. 測試常數驗證
    print("測試 1: 常數驗證")
    try:
        validate_constants()
        print("✅ 常數驗證通過")
    except Exception as e:
        print(f"❌ 常數驗證失敗: {e}")
    
    # 2. 測試連線池初始化
    print("\n測試 2: 連線池初始化")
    try:
        pool = DatabaseConnectionPool()
        print("✅ 連線池初始化成功")
    except Exception as e:
        print(f"❌ 連線池初始化失敗: {e}")
    
    logger.info("services/db.py 測試完成")
