"""
電費資料管理層
負責電費相關的資料庫操作
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import date
import pandas as pd

logger = logging.getLogger(__name__)


class ElectricityStorage:
    """電費資料存取層"""
    
    def __init__(self, db):
        """
        初始化
        
        Args:
            db: 資料庫實例
        """
        self.db = db
    
    # ============== 計費期間管理 ==============
    
    def create_period(self, year: int, month_start: int, month_end: int) -> Tuple[bool, int, str]:
        """
        建立計費期間
        
        Args:
            year: 年份
            month_start: 開始月份
            month_end: 結束月份
        
        Returns:
            (成功與否, 期間ID, 訊息)
        """
        try:
            with self.db._get_connection() as conn:
                cur = conn.cursor()
                
                # 檢查是否重複
                cur.execute("""
                    SELECT id FROM electricity_periods
                    WHERE period_year = %s 
                    AND period_month_start = %s 
                    AND period_month_end = %s
                """, (year, month_start, month_end))
                
                existing = cur.fetchone()
                if existing:
                    return False, existing[0], "⚠️ 該期間已存在"
                
                # 建立新期間
                cur.execute("""
                    INSERT INTO electricity_periods 
                    (period_year, period_month_start, period_month_end)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """, (year, month_start, month_end))
                
                period_id = cur.fetchone()[0]
                logger.info(f"✅ 建立計費期間: {year}/{month_start}-{month_end} (ID: {period_id})")
                
                return True, period_id, "✅ 建立成功"
        
        except Exception as e:
            logger.error(f"建立期間失敗: {e}")
            return False, -1, f"❌ 建立失敗: {str(e)}"
    
    def get_periods(self, limit: int = 20) -> pd.DataFrame:
        """
        取得計費期間列表
        
        Args:
            limit: 限制筆數
        
        Returns:
            DataFrame
        """
        try:
            with self.db._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT 
                        id,
                        period_year,
                        period_month_start,
                        period_month_end,
                        created_at
                    FROM electricity_periods
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))
                
                columns = [desc[0] for desc in cur.description]
                data = cur.fetchall()
                
                return pd.DataFrame(data, columns=columns)
        
        except Exception as e:
            logger.error(f"查詢期間失敗: {e}")
            return pd.DataFrame()
    
    def get_period_by_id(self, period_id: int) -> Optional[Dict]:
        """
        取得單一期間資訊
        
        Args:
            period_id: 期間 ID
        
        Returns:
            期間資訊字典或 None
        """
        try:
            with self.db._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT id, period_year, period_month_start, period_month_end
                    FROM electricity_periods
                    WHERE id = %s
                """, (period_id,))
                
                row = cur.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'year': row[1],
                        'month_start': row[2],
                        'month_end': row[3]
                    }
                return None
        
        except Exception as e:
            logger.error(f"查詢期間失敗: {e}")
            return None
    
    # ============== 台電單據管理 ==============
    
    def save_taipower_bill(self,
                           period_id: int,
                           floor: str,
                           amount: float,
                           kwh: float) -> Tuple[bool, str]:
        """
        儲存台電單據
        
        Args:
            period_id: 計費期間 ID
            floor: 樓層標識 (例如: "1F", "2-4F")
            amount: 金額
            kwh: 度數
        
        Returns:
            (成功與否, 訊息)
        """
        try:
            with self.db._get_connection() as conn:
                cur = conn.cursor()
                
                # Upsert 操作
                cur.execute("""
                    INSERT INTO electricity_taipower_bills 
                    (period_id, floor_label, amount, kwh)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (period_id, floor_label)
                    DO UPDATE SET
                        amount = EXCLUDED.amount,
                        kwh = EXCLUDED.kwh,
                        updated_at = NOW()
                """, (period_id, floor, amount, kwh))
                
                return True, "✅ 儲存成功"
        
        except Exception as e:
            logger.error(f"儲存台電單據失敗: {e}")
            return False, f"❌ 儲存失敗: {str(e)}"
    
    def get_taipower_bills(self, period_id: int) -> pd.DataFrame:
        """
        取得台電單據
        
        Args:
            period_id: 計費期間 ID
        
        Returns:
            DataFrame
        """
        try:
            with self.db._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT floor_label, amount, kwh
                    FROM electricity_taipower_bills
                    WHERE period_id = %s
                    ORDER BY floor_label
                """, (period_id,))
                
                columns = [desc[0] for desc in cur.description]
                data = cur.fetchall()
                
                return pd.DataFrame(data, columns=columns)
        
        except Exception as e:
            logger.error(f"查詢台電單據失敗: {e}")
            return pd.DataFrame()
    
    # ============== 抄表管理 ==============
    
    def save_meter_reading(self,
                          period_id: int,
                          room: str,
                          reading: float,
                          reading_date: date) -> Tuple[bool, str]:
        """
        儲存抄表讀數
        
        Args:
            period_id: 計費期間 ID
            room: 房號
            reading: 讀數
            reading_date: 抄表日期
        
        Returns:
            (成功與否, 訊息)
        """
        try:
            with self.db._get_connection() as conn:
                cur = conn.cursor()
                
                cur.execute("""
                    INSERT INTO electricity_meter_readings
                    (period_id, room_number, reading_value, reading_date)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (period_id, room_number)
                    DO UPDATE SET
                        reading_value = EXCLUDED.reading_value,
                        reading_date = EXCLUDED.reading_date,
                        updated_at = NOW()
                """, (period_id, room, reading, reading_date))
                
                return True, "✅ 儲存成功"
        
        except Exception as e:
            logger.error(f"儲存抄表失敗: {e}")
            return False, f"❌ 儲存失敗: {str(e)}"
    
    def get_meter_readings(self, period_id: int) -> Dict[str, float]:
        """
        取得抄表讀數
        
        Args:
            period_id: 計費期間 ID
        
        Returns:
            {房號: 讀數} 字典
        """
        try:
            with self.db._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT room_number, reading_value
                    FROM electricity_meter_readings
                    WHERE period_id = %s
                """, (period_id,))
                
                return {row[0]: float(row[1]) for row in cur.fetchall()}
        
        except Exception as e:
            logger.error(f"查詢抄表失敗: {e}")
            return {}
    
    def get_previous_readings(self, current_period_id: int) -> Dict[str, float]:
        """
        取得上期讀數 (用於驗證)
        
        Args:
            current_period_id: 當前期間 ID
        
        Returns:
            {房號: 讀數} 字典
        """
        try:
            with self.db._get_connection() as conn:
                cur = conn.cursor()
                
                # 找到上一期
                cur.execute("""
                    SELECT id FROM electricity_periods
                    WHERE id < %s
                    ORDER BY id DESC
                    LIMIT 1
                """, (current_period_id,))
                
                prev_period = cur.fetchone()
                if not prev_period:
                    return {}
                
                # 取得上期讀數
                cur.execute("""
                    SELECT room_number, reading_value
                    FROM electricity_meter_readings
                    WHERE period_id = %s
                """, (prev_period[0],))
                
                return {row[0]: float(row[1]) for row in cur.fetchall()}
        
        except Exception as e:
            logger.error(f"查詢上期讀數失敗: {e}")
            return {}
    
    # ============== 計費結果管理 ==============
    
    def save_charge_results(self,
                           period_id: int,
                           calculation_result: Dict) -> Tuple[bool, str]:
        """
        儲存計費結果
        
        Args:
            period_id: 計費期間 ID
            calculation_result: calculator.calculate_all_rooms() 的返回值
        
        Returns:
            (成功與否, 訊息)
        """
        try:
            with self.db._get_connection() as conn:
                cur = conn.cursor()
                
                # 先刪除舊記錄
                cur.execute("""
                    DELETE FROM electricity_charges
                    WHERE period_id = %s
                """, (period_id,))
                
                # 插入新記錄
                for charge in calculation_result['room_charges']:
                    cur.execute("""
                        INSERT INTO electricity_charges
                        (period_id, room_number, room_kwh, shared_kwh, 
                         total_kwh, charge_amount, is_sharing_room)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        period_id,
                        charge['room'],
                        charge['room_kwh'],
                        charge['shared_kwh'],
                        charge['total_kwh'],
                        charge['charge'],
                        charge['is_sharing']
                    ))
                
                # 儲存摘要資訊
                cur.execute("""
                    INSERT INTO electricity_period_summary
                    (period_id, unit_price, public_kwh, shared_kwh_per_room,
                     total_charge, taipower_amount, difference)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (period_id)
                    DO UPDATE SET
                        unit_price = EXCLUDED.unit_price,
                        public_kwh = EXCLUDED.public_kwh,
                        shared_kwh_per_room = EXCLUDED.shared_kwh_per_room,
                        total_charge = EXCLUDED.total_charge,
                        taipower_amount = EXCLUDED.taipower_amount,
                        difference = EXCLUDED.difference,
                        updated_at = NOW()
                """, (
                    period_id,
                    calculation_result['unit_price'],
                    calculation_result['public_kwh'],
                    calculation_result['shared_kwh_per_room'],
                    calculation_result['total_charge'],
                    calculation_result['taipower_amount'],
                    calculation_result['difference']
                ))
                
                return True, "✅ 計費結果已儲存"
        
        except Exception as e:
            logger.error(f"儲存計費結果失敗: {e}")
            return False, f"❌ 儲存失敗: {str(e)}"
    
    def get_charge_history(self, limit: int = 10) -> pd.DataFrame:
        """
        取得歷史計費記錄
        
        Args:
            limit: 限制筆數
        
        Returns:
            DataFrame
        """
        try:
            with self.db._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT 
                        p.period_year,
                        p.period_month_start,
                        p.period_month_end,
                        s.unit_price,
                        s.public_kwh,
                        s.total_charge,
                        s.taipower_amount,
                        s.difference,
                        p.created_at
                    FROM electricity_periods p
                    LEFT JOIN electricity_period_summary s ON p.id = s.period_id
                    ORDER BY p.created_at DESC
                    LIMIT %s
                """, (limit,))
                
                columns = [desc[0] for desc in cur.description]
                data = cur.fetchall()
                
                return pd.DataFrame(data, columns=columns)
        
        except Exception as e:
            logger.error(f"查詢歷史記錄失敗: {e}")
            return pd.DataFrame()


# ============== 資料庫 Schema 建立 ==============

def create_electricity_tables(db):
    """
    建立電費相關資料表
    
    Args:
        db: 資料庫實例
    """
    try:
        with db._get_connection() as conn:
            cur = conn.cursor()
            
            # 計費期間表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS electricity_periods (
                    id SERIAL PRIMARY KEY,
                    period_year INT NOT NULL,
                    period_month_start INT NOT NULL,
                    period_month_end INT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(period_year, period_month_start, period_month_end)
                )
            """)
            
            # 台電單據表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS electricity_taipower_bills (
                    id SERIAL PRIMARY KEY,
                    period_id INT REFERENCES electricity_periods(id) ON DELETE CASCADE,
                    floor_label VARCHAR(20) NOT NULL,
                    amount DECIMAL(10,2) NOT NULL,
                    kwh DECIMAL(10,2) NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(period_id, floor_label)
                )
            """)
            
            # 抄表讀數表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS electricity_meter_readings (
                    id SERIAL PRIMARY KEY,
                    period_id INT REFERENCES electricity_periods(id) ON DELETE CASCADE,
                    room_number VARCHAR(10) NOT NULL,
                    reading_value DECIMAL(10,2) NOT NULL,
                    reading_date DATE NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(period_id, room_number)
                )
            """)
            
            # 計費結果表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS electricity_charges (
                    id SERIAL PRIMARY KEY,
                    period_id INT REFERENCES electricity_periods(id) ON DELETE CASCADE,
                    room_number VARCHAR(10) NOT NULL,
                    room_kwh DECIMAL(10,2) NOT NULL,
                    shared_kwh DECIMAL(10,2) DEFAULT 0,
                    total_kwh DECIMAL(10,2) NOT NULL,
                    charge_amount INT NOT NULL,
                    is_sharing_room BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(period_id, room_number)
                )
            """)
            
            # 期間摘要表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS electricity_period_summary (
                    id SERIAL PRIMARY KEY,
                    period_id INT UNIQUE REFERENCES electricity_periods(id) ON DELETE CASCADE,
                    unit_price DECIMAL(10,2) NOT NULL,
                    public_kwh DECIMAL(10,2) NOT NULL,
                    shared_kwh_per_room DECIMAL(10,2) NOT NULL,
                    total_charge INT NOT NULL,
                    taipower_amount INT NOT NULL,
                    difference INT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            logger.info("✅ 電費資料表建立完成")
    
    except Exception as e:
        logger.error(f"建立資料表失敗: {e}")
        raise