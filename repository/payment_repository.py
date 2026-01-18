# repository/payment_repository.py
"""
租金資料存取層
職責：純資料庫 CRUD 操作，不含業務邏輯
"""
from typing import List, Dict, Optional
from datetime import datetime
from services.db import SupabaseDB
from psycopg2.extras import RealDictCursor
from services.logger import logger

class PaymentRepository:
    """租金資料存取物件（Repository Pattern）"""
    
    def __init__(self):
        self.db = SupabaseDB()
    
    def create_schedule(self, schedule_data: Dict) -> int:
        """新增租金排程
        
        Args:
            schedule_data: 排程資料字典
        
        Returns:
            新增的排程 ID
        """
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            query = """
                INSERT INTO payment_schedule (
                    room_number, tenant_name, payment_year, payment_month,
                    amount, due_date, payment_method, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """
            cur.execute(query, (
                schedule_data['room_number'],
                schedule_data['tenant_name'],
                schedule_data['payment_year'],
                schedule_data['payment_month'],
                schedule_data['amount'],
                schedule_data['due_date'],
                schedule_data['payment_method'],
                schedule_data.get('status', 'unpaid')
            ))
            schedule_id = cur.fetchone()[0]
            return schedule_id
    
    def schedule_exists(self, room_number: str, year: int, month: int) -> bool:
        """檢查排程是否已存在"""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT 1 FROM payment_schedule
                WHERE room_number = %s
                  AND payment_year = %s
                  AND payment_month = %s
            """, (room_number, year, month))
            exists = cur.fetchone() is not None
            return exists
    
    def get_by_status(self, status: str) -> List[Dict]:
        """依狀態查詢"""
        with self.db.get_connection() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT * FROM payment_schedule
                WHERE status = %s
                ORDER BY due_date
            """, (status,))
            results = cur.fetchall()
            return [dict(r) for r in results]
    
    def get_by_id(self, payment_id: int) -> Optional[Dict]:
        """依 ID 查詢單筆"""
        with self.db.get_connection() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                "SELECT * FROM payment_schedule WHERE id = %s",
                (payment_id,)
            )
            result = cur.fetchone()
            return dict(result) if result else None
    
    def find_by_id(self, payment_id: int) -> Optional[Dict]:
        """依 ID 查詢單筆（別名方法，與 get_by_id 相同）"""
        return self.get_by_id(payment_id)
    
    def update_payment_status(self, payment_id: int, **kwargs) -> bool:
        """更新付款狀態"""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE payment_schedule
                SET status = %s, paid_amount = %s, paid_date = %s, notes = %s
                WHERE id = %s
            """, (
                kwargs['status'], kwargs['paid_amount'],
                kwargs['paid_date'], kwargs['notes'], payment_id
            ))
            success = cur.rowcount > 0
            return success
    
    def mark_as_paid(self, payment_id: int, paid_amount: float, 
                     paid_date: datetime, notes: str = "") -> bool:
        """標記為已繳款
        
        Args:
            payment_id: 排程 ID
            paid_amount: 繳款金額
            paid_date: 繳款日期
            notes: 備註
        
        Returns:
            是否成功
        """
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE payment_schedule
                SET status = 'paid',
                    paid_amount = %s,
                    paid_date = %s,
                    notes = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (paid_amount, paid_date, notes, payment_id))
            success = cur.rowcount > 0
            return success
    
    def get_by_period(self, year: int, month: int) -> List[Dict]:
        """依期間查詢
        
        Args:
            year: 年份
            month: 月份
        
        Returns:
            租金記錄列表
        """
        with self.db.get_connection() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT * FROM payment_schedule
                WHERE payment_year = %s AND payment_month = %s
                ORDER BY room_number
            """, (year, month))
            results = cur.fetchall()
            return [dict(r) for r in results]
    
    def get_by_room_and_period(self, room_number: str, year: int, month: int) -> List[Dict]:
        """取得指定房間和期間的租金記錄（新增方法）
        
        Args:
            room_number: 房號
            year: 年份
            month: 月份
        
        Returns:
            租金記錄列表（自動判斷逾期狀態）
        """
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute("""
                    SELECT 
                        ps.*,
                        CASE 
                            WHEN ps.status = 'unpaid' AND ps.due_date < CURRENT_DATE 
                            THEN 'overdue'
                            ELSE ps.status
                        END as status
                    FROM payment_schedule ps
                    WHERE ps.room_number = %s
                        AND ps.payment_year = %s
                        AND ps.payment_month = %s
                    ORDER BY ps.due_date DESC
                """, (room_number, year, month))
                
                results = cur.fetchall()
                logger.info(f"查詢房間租金記錄: {room_number} {year}/{month} - {len(results)} 筆")
                return [dict(r) for r in results]
        
        except Exception as e:
            logger.error(f"查詢房間租金記錄失敗: {str(e)}", exc_info=True)
            return []
    
    def get_payment_summary(self, year: int, month: int) -> Dict:
        """取得租金摘要統計
        
        Args:
            year: 年份
            month: 月份
        
        Returns:
            包含統計數據的字典：
            {
                'total_expected': 應收總額,
                'total_received': 實收總額,
                'unpaid_count': 未繳筆數,
                'paid_count': 已繳筆數,
                'overdue_count': 逾期筆數,
                'collection_rate': 收款率 (0-1)
            }
        """
        with self.db.get_connection() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT
                    COUNT(*) as total_count,
                    SUM(amount) as total_expected,
                    SUM(CASE WHEN status = 'paid' THEN paid_amount ELSE 0 END) as total_received,
                    COUNT(CASE WHEN status = 'unpaid' THEN 1 END) as unpaid_count,
                    COUNT(CASE WHEN status = 'paid' THEN 1 END) as paid_count,
                    COUNT(CASE WHEN status = 'unpaid' AND due_date < CURRENT_DATE THEN 1 END) as overdue_count
                FROM payment_schedule
                WHERE payment_year = %s AND payment_month = %s
            """, (year, month))
            
            result = cur.fetchone()
            
            if not result or result['total_count'] == 0:
                return {
                    'total_expected': 0,
                    'total_received': 0,
                    'unpaid_count': 0,
                    'paid_count': 0,
                    'overdue_count': 0,
                    'collection_rate': 0.0
                }
            
            total_expected = float(result['total_expected'] or 0)
            total_received = float(result['total_received'] or 0)
            collection_rate = total_received / total_expected if total_expected > 0 else 0.0
            
            return {
                'total_expected': total_expected,
                'total_received': total_received,
                'unpaid_count': int(result['unpaid_count'] or 0),
                'paid_count': int(result['paid_count'] or 0),
                'overdue_count': int(result['overdue_count'] or 0),
                'collection_rate': collection_rate
            }
    
    def get_overdue_payments(self) -> List[Dict]:
        """取得所有逾期未繳的租金記錄"""
        with self.db.get_connection() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT * FROM payment_schedule
                WHERE status = 'unpaid' AND due_date < CURRENT_DATE
                ORDER BY due_date ASC
            """)
            results = cur.fetchall()
            return [dict(r) for r in results]
    
    def batch_mark_paid(self, payment_ids: List[int], paid_amount: float = None) -> Dict:
        """批量標記為已繳
        
        Args:
            payment_ids: 要標記的 payment ID 列表
            paid_amount: 繳款金額（None 表示使用原應繳金額）
        
        Returns:
            {'success': 成功筆數, 'failed': 失敗筆數}
        """
        success_count = 0
        failed_count = 0
        
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            
            for payment_id in payment_ids:
                try:
                    if paid_amount is not None:
                        cur.execute("""
                            UPDATE payment_schedule
                            SET status = 'paid',
                                paid_amount = %s,
                                paid_date = CURRENT_DATE,
                                updated_at = NOW()
                            WHERE id = %s
                        """, (paid_amount, payment_id))
                    else:
                        cur.execute("""
                            UPDATE payment_schedule
                            SET status = 'paid',
                                paid_amount = amount,
                                paid_date = CURRENT_DATE,
                                updated_at = NOW()
                            WHERE id = %s
                        """, (payment_id,))
                    
                    if cur.rowcount > 0:
                        success_count += 1
                    else:
                        failed_count += 1
                
                except Exception as e:
                    failed_count += 1
        
        return {'success': success_count, 'failed': failed_count}
    
    def get_tenant_payment_history(self, room_number: str, limit: int = 12) -> List[Dict]:
        """取得房客繳款歷史
        
        Args:
            room_number: 房號
            limit: 限制筆數
        
        Returns:
            繳款歷史列表
        """
        with self.db.get_connection() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT 
                    payment_year, payment_month, amount,
                    paid_amount, status, paid_date, due_date, notes
                FROM payment_schedule
                WHERE room_number = %s
                ORDER BY payment_year DESC, payment_month DESC
                LIMIT %s
            """, (room_number, limit))
            results = cur.fetchall()
            return [dict(r) for r in results]
    
    def update_overdue_status(self) -> int:
        """更新逾期狀態（將過期未繳標記為 overdue）
        
        Returns:
            更新的記錄數
        """
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE payment_schedule
                SET status = 'overdue', updated_at = NOW()
                WHERE status = 'unpaid'
                  AND due_date < CURRENT_DATE
            """)
            updated_count = cur.rowcount
            return updated_count
    
    def get_all_payments(self, year: Optional[int] = None, 
                        month: Optional[int] = None,
                        status: Optional[str] = None) -> List[Dict]:
        """取得所有租金記錄（支援篩選）
        
        Args:
            year: 年份篩選（可選）
            month: 月份篩選（可選）
            status: 狀態篩選（可選）
        
        Returns:
            租金記錄列表
        """
        with self.db.get_connection() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            conditions = []
            params = []
            
            if year:
                conditions.append("payment_year = %s")
                params.append(year)
            
            if month:
                conditions.append("payment_month = %s")
                params.append(month)
            
            if status:
                conditions.append("status = %s")
                params.append(status)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            query = f"""
                SELECT * FROM payment_schedule
                WHERE {where_clause}
                ORDER BY payment_year DESC, payment_month DESC, room_number
            """
            
            cur.execute(query, tuple(params))
            results = cur.fetchall()
            return [dict(r) for r in results]
