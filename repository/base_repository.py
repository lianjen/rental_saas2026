# repository/base_repository.py
"""
基礎 Repository 類別
提供通用的 CRUD 操作模式
"""
from typing import List, Dict, Optional, Any
from services.db import SupabaseDB
from services.logger import logger
import streamlit as st

class BaseRepository:
    """Repository 基礎類別"""
    
    def __init__(self, table_name: str):
        self.table_name = table_name
        self.db = SupabaseDB()
    
    @st.cache_resource(ttl=60)
    def _get_connection(_self):
        """取得快取的資料庫連線"""
        return _self.db.get_connection()
    
    def _execute_query(self, query: str, params: tuple = None, 
                       fetch: str = 'all') -> Optional[Any]:
        """
        執行 SQL 查詢的統一介面
        
        Args:
            query: SQL 查詢語句
            params: 查詢參數
            fetch: 'all', 'one', 'none' (用於 INSERT/UPDATE/DELETE)
        
        Returns:
            查詢結果或 None
        """
        conn = None
        try:
            conn = self.db.get_connection()
            cur = conn.cursor()
            
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)
            
            result = None
            if fetch == 'all':
                result = cur.fetchall()
            elif fetch == 'one':
                result = cur.fetchone()
            elif fetch == 'none':
                conn.commit()
                result = cur.rowcount
            
            cur.close()
            logger.debug(f"Query executed on {self.table_name}: {fetch}")
            return result
            
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Query error on {self.table_name}: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()
    
    def find_all(self, conditions: Dict[str, Any] = None, 
                 order_by: str = None) -> List[Dict]:
        """
        查詢所有記錄
        
        Args:
            conditions: 查詢條件 {'column': value}
            order_by: 排序欄位 'column_name ASC'
        
        Returns:
            記錄列表
        """
        query = f"SELECT * FROM {self.table_name}"
        params = []
        
        if conditions:
            where_clauses = []
            for col, val in conditions.items():
                where_clauses.append(f"{col} = %s")
                params.append(val)
            query += " WHERE " + " AND ".join(where_clauses)
        
        if order_by:
            query += f" ORDER BY {order_by}"
        
        return self._execute_query(query, tuple(params) if params else None)
    
    def find_by_id(self, id_value: int) -> Optional[Dict]:
        """依 ID 查詢單筆記錄"""
        query = f"SELECT * FROM {self.table_name} WHERE id = %s"
        return self._execute_query(query, (id_value,), fetch='one')
    
    def insert(self, data: Dict[str, Any]) -> int:
        """
        插入新記錄
        
        Args:
            data: 欄位值字典 {'column': value}
        
        Returns:
            新記錄的 ID
        """
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['%s'] * len(data))
        query = f"""
            INSERT INTO {self.table_name} ({columns})
            VALUES ({placeholders})
            RETURNING id
        """
        
        result = self._execute_query(query, tuple(data.values()), fetch='one')
        return result[0] if result else None
    
    def update(self, id_value: int, data: Dict[str, Any]) -> bool:
        """
        更新記錄
        
        Args:
            id_value: 記錄 ID
            data: 要更新的欄位 {'column': new_value}
        
        Returns:
            是否成功
        """
        set_clauses = ', '.join([f"{col} = %s" for col in data.keys()])
        query = f"UPDATE {self.table_name} SET {set_clauses} WHERE id = %s"
        params = tuple(list(data.values()) + [id_value])
        
        rows_affected = self._execute_query(query, params, fetch='none')
        return rows_affected > 0
    
    def delete(self, id_value: int) -> bool:
        """刪除記錄"""
        query = f"DELETE FROM {self.table_name} WHERE id = %s"
        rows_affected = self._execute_query(query, (id_value,), fetch='none')
        return rows_affected > 0


# repository/tenant_repository.py
"""
房客資料存取層
職責：tenants 表的所有 CRUD 操作
"""
from typing import List, Dict, Optional
from datetime import datetime
from repository.base_repository import BaseRepository

class TenantRepository(BaseRepository):
    """房客 Repository"""
    
    def __init__(self):
        super().__init__('tenants')
    
    def get_active_tenants(self) -> List[Dict]:
        """取得所有活躍房客"""
        return self.find_all(
            conditions={'is_active': True},
            order_by='room_number ASC'
        )
    
    def get_by_room_number(self, room_number: str) -> Optional[Dict]:
        """依房間號碼查詢房客"""
        query = """
            SELECT * FROM tenants 
            WHERE room_number = %s AND is_active = true
        """
        return self._execute_query(query, (room_number,), fetch='one')
    
    def create_tenant(self, tenant_data: Dict) -> int:
        """
        新增房客
        
        Args:
            tenant_data: 房客資料字典，包含：
                - room_number
                - tenant_name
                - phone
                - deposit
                - base_rent
                - lease_start
                - lease_end
                - payment_method
                - has_water_fee
                - annual_discount_months (可選)
                - discount_notes (可選)
        
        Returns:
            新房客的 ID
        """
        # 設定預設值
        tenant_data.setdefault('is_active', True)
        tenant_data.setdefault('created_at', datetime.now())
        tenant_data.setdefault('has_water_fee', False)
        tenant_data.setdefault('annual_discount_months', 0)
        
        return self.insert(tenant_data)
    
    def update_tenant(self, tenant_id: int, updates: Dict) -> bool:
        """更新房客資料"""
        updates['updated_at'] = datetime.now()
        return self.update(tenant_id, updates)
    
    def deactivate_tenant(self, tenant_id: int) -> bool:
        """停用房客（軟刪除）"""
        return self.update(tenant_id, {
            'is_active': False,
            'updated_at': datetime.now()
        })
    
    def get_tenants_with_discount(self) -> List[Dict]:
        """取得有折扣方案的房客"""
        query = """
            SELECT * FROM tenants 
            WHERE is_active = true 
            AND annual_discount_months > 0
            ORDER BY room_number
        """
        return self._execute_query(query)
    
    def search_tenants(self, keyword: str) -> List[Dict]:
        """搜尋房客（依姓名或房間號碼）"""
        query = """
            SELECT * FROM tenants 
            WHERE is_active = true 
            AND (tenant_name ILIKE %s OR room_number ILIKE %s)
            ORDER BY room_number
        """
        pattern = f"%{keyword}%"
        return self._execute_query(query, (pattern, pattern))


# repository/payment_repository.py
"""
租金資料存取層
職責：payment_schedule 表的所有 CRUD 操作
"""
from typing import List, Dict, Optional
from datetime import datetime
from repository.base_repository import BaseRepository

class PaymentRepository(BaseRepository):
    """租金 Repository"""
    
    def __init__(self):
        super().__init__('payment_schedule')
    
    def create_schedule(self, schedule_data: Dict) -> int:
        """
        建立租金排程
        
        Args:
            schedule_data: 排程資料，包含：
                - room_number
                - tenant_name
                - payment_year
                - payment_month
                - amount
                - due_date
                - payment_method
                - status (預設 'unpaid')
        
        Returns:
            新排程的 ID
        """
        schedule_data.setdefault('status', 'unpaid')
        schedule_data.setdefault('created_at', datetime.now())
        
        return self.insert(schedule_data)
    
    def schedule_exists(self, room_number: str, year: int, month: int) -> bool:
        """檢查排程是否已存在"""
        query = """
            SELECT 1 FROM payment_schedule 
            WHERE room_number = %s 
            AND payment_year = %s 
            AND payment_month = %s
        """
        result = self._execute_query(query, (room_number, year, month), fetch='one')
        return result is not None
    
    def get_by_period(self, year: int, month: int) -> List[Dict]:
        """取得指定期間的所有排程"""
        return self.find_all(
            conditions={'payment_year': year, 'payment_month': month},
            order_by='room_number ASC'
        )
    
    def get_by_status(self, status: str) -> List[Dict]:
        """依狀態查詢排程"""
        return self.find_all(
            conditions={'status': status},
            order_by='due_date ASC'
        )
    
    def get_unpaid_by_room(self, room_number: str) -> List[Dict]:
        """取得指定房間的未繳租金"""
        query = """
            SELECT * FROM payment_schedule 
            WHERE room_number = %s 
            AND status IN ('unpaid', 'overdue')
            ORDER BY payment_year, payment_month
        """
        return self._execute_query(query, (room_number,))
    
    def mark_as_paid(self, payment_id: int, paid_amount: float, 
                     paid_date: datetime = None, notes: str = "") -> bool:
        """
        標記為已繳款
        
        Args:
            payment_id: 排程 ID
            paid_amount: 實繳金額
            paid_date: 繳款日期（預設今天）
            notes: 備註
        
        Returns:
            是否成功
        """
        if paid_date is None:
            paid_date = datetime.now()
        
        return self.update(payment_id, {
            'status': 'paid',
            'paid_amount': paid_amount,
            'paid_date': paid_date,
            'notes': notes,
            'updated_at': datetime.now()
        })
    
    def batch_mark_paid(self, payment_ids: List[int], paid_amount: float) -> int:
        """
        批量標記已繳款
        
        Returns:
            成功標記的數量
        """
        success_count = 0
        for payment_id in payment_ids:
            if self.mark_as_paid(payment_id, paid_amount):
                success_count += 1
        return success_count
    
    def update_overdue_status(self) -> int:
        """
        更新逾期狀態（將過期未繳改為 overdue）
        
        Returns:
            更新的記錄數
        """
        query = """
            UPDATE payment_schedule 
            SET status = 'overdue', updated_at = %s
            WHERE status = 'unpaid' 
            AND due_date < %s
        """
        now = datetime.now()
        return self._execute_query(
            query, 
            (now, now.date()), 
            fetch='none'
        )
    
    def get_payment_summary(self, year: int, month: int) -> Dict:
        """
        取得期間收款摘要
        
        Returns:
            {
                'total_expected': 60000,
                'total_received': 55000,
                'unpaid_count': 2,
                'overdue_count': 1
            }
        """
        query = """
            SELECT 
                SUM(amount) as total_expected,
                SUM(CASE WHEN status = 'paid' THEN paid_amount ELSE 0 END) as total_received,
                COUNT(CASE WHEN status = 'unpaid' THEN 1 END) as unpaid_count,
                COUNT(CASE WHEN status = 'overdue' THEN 1 END) as overdue_count
            FROM payment_schedule
            WHERE payment_year = %s AND payment_month = %s
        """
        result = self._execute_query(query, (year, month), fetch='one')
        
        if result:
            return {
                'total_expected': float(result[0] or 0),
                'total_received': float(result[1] or 0),
                'unpaid_count': int(result[2] or 0),
                'overdue_count': int(result[3] or 0)
            }
        return {
            'total_expected': 0,
            'total_received': 0,
            'unpaid_count': 0,
            'overdue_count': 0
        }


# repository/__init__.py
"""
Repository Layer 初始化
統一匯出所有 Repository
"""
from repository.tenant_repository import TenantRepository
from repository.payment_repository import PaymentRepository

__all__ = [
    'TenantRepository',
    'PaymentRepository'
]