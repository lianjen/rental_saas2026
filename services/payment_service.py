# services/payment_service.py
"""
租金管理服務層
職責：租金計算、排程管理、收款追蹤
"""
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from repository.payment_repository import PaymentRepository
from repository.tenant_repository import TenantRepository
from services.logger import logger

@dataclass
class RentCalculation:
    """租金計算結果值物件"""
    base_rent: float
    water_fee: float
    discount: float
    final_amount: float
    calculation_notes: str

@dataclass
class PaymentSummary:
    """收款摘要值物件"""
    period: str  # "2026/01"
    total_expected: float
    total_received: float
    unpaid_count: int
    overdue_count: int
    collection_rate: float
    
    def to_dict(self) -> Dict:
        return {
            'period': self.period,
            'total_expected': self.total_expected,
            'total_received': self.total_received,
            'unpaid_count': self.unpaid_count,
            'overdue_count': self.overdue_count,
            'collection_rate': self.collection_rate
        }


class PaymentService:
    """租金管理服務（業務邏輯層）"""
    
    def __init__(self):
        self.payment_repo = PaymentRepository()
        self.tenant_repo = TenantRepository()
        self.WATER_FEE = 50  # 水費固定金額
    
    def calculate_monthly_rent(self, tenant: Dict, target_month: int) -> RentCalculation:
        """
        計算指定月份的應繳租金（核心演算法）
        
        計算邏輯：
        1. 基礎月租 = base_rent
        2. 年繳折扣：若當月在 annual_discount_months 內，該月免租
        3. 水費：has_water_fee = True 且無免除則加 50 元
        
        Args:
            tenant: 房客資料字典
            target_month: 目標月份 (1-12)
        
        Returns:
            RentCalculation 物件
        """
        base_rent = float(tenant['base_rent'])
        water_fee = 0
        discount = 0
        notes = []
        
        # === 年繳折扣邏輯 ===
        annual_discount_months = tenant.get('annual_discount_months', 0)
        if isinstance(annual_discount_months, int) and annual_discount_months > 0:
            # 假設折扣月份為 1 月（可依實際業務調整）
            discount_month_list = list(range(1, annual_discount_months + 1))
            
            if target_month in discount_month_list:
                discount = base_rent
                base_rent = 0
                notes.append(f"年繳折扣（第 {target_month} 月免租）")
        
        # === 水費邏輯 ===
        if tenant.get('has_water_fee', False):
            water_fee = self.WATER_FEE
            notes.append("含水費 $50")
        
        final_amount = base_rent + water_fee
        calculation_notes = "; ".join(notes) if notes else "標準租金"
        
        logger.debug(
            f"租金計算: {tenant['room_number']} - "
            f"基礎 ${base_rent}, 水費 ${water_fee}, "
            f"折扣 -${discount}, 總計 ${final_amount}"
        )
        
        return RentCalculation(
            base_rent=base_rent,
            water_fee=water_fee,
            discount=discount,
            final_amount=final_amount,
            calculation_notes=calculation_notes
        )
    
    def create_monthly_schedule_batch(self, year: int, month: int) -> Dict[str, int]:
        """
        批量建立月租金排程（一鍵產生當月所有房客的租金記錄）
        
        Args:
            year: 年份
            month: 月份 (1-12)
        
        Returns:
            {'created': 5, 'skipped': 2, 'errors': 0}
        """
        logger.info(f"=== 開始建立 {year}/{month:02d} 租金排程 ===")
        
        # 1. 取得所有活躍房客
        active_tenants = self.tenant_repo.get_active_tenants()
        logger.info(f"找到 {len(active_tenants)} 位活躍房客")
        
        results = {'created': 0, 'skipped': 0, 'errors': 0}
        
        for tenant in active_tenants:
            try:
                room_number = tenant['room_number']
                
                # 2. 檢查是否已有排程（避免重複建立）
                if self.payment_repo.schedule_exists(room_number, year, month):
                    logger.debug(f"跳過已存在的排程: {room_number}")
                    results['skipped'] += 1
                    continue
                
                # 3. 計算租金
                rent_calc = self.calculate_monthly_rent(tenant, month)
                
                # 4. 建立排程
                due_date = datetime(year, month, 5)  # 每月 5 號到期
                
                schedule_data = {
                    'room_number': room_number,
                    'tenant_name': tenant['tenant_name'],
                    'payment_year': year,
                    'payment_month': month,
                    'amount': rent_calc.final_amount,
                    'payment_method': tenant.get('payment_method', 'cash'),
                    'due_date': due_date,
                    'status': 'unpaid'
                }
                
                schedule_id = self.payment_repo.create_schedule(schedule_data)
                
                results['created'] += 1
                logger.info(
                    f"✅ 建立排程: {room_number} - {tenant['tenant_name']} - "
                    f"${rent_calc.final_amount} ({rent_calc.calculation_notes})"
                )
                
            except Exception as e:
                results['errors'] += 1
                logger.error(f"❌ 建立排程失敗: {room_number} - {str(e)}", exc_info=True)
        
        logger.info(f"=== 排程建立完成 ===")
        logger.info(f"結果: {results}")
        
        return results
    
    def mark_payment_as_paid(self, payment_id: int, paid_amount: float,
                            paid_date: Optional[datetime] = None,
                            notes: str = "") -> bool:
        """
        標記租金已繳納（單筆）
        
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
        
        # 1. 取得原始排程資料
        schedule = self.payment_repo.find_by_id(payment_id)
        if not schedule:
            logger.error(f"找不到排程 ID: {payment_id}")
            return False
        
        # 2. 檢查金額差異
        expected_amount = float(schedule['amount'])
        difference = paid_amount - expected_amount
        
        if abs(difference) > 0.01:
            logger.warning(
                f"繳款金額異常: {schedule['room_number']} - "
                f"期望 ${expected_amount}, 實收 ${paid_amount}, "
                f"差額 ${difference}"
            )
            notes += f" [金額差異: ${difference:+.2f}]"
        
        # 3. 更新付款狀態
        success = self.payment_repo.mark_as_paid(
            payment_id=payment_id,
            paid_amount=paid_amount,
            paid_date=paid_date,
            notes=notes
        )
        
        if success:
            logger.info(
                f"✅ 標記繳款: {schedule['room_number']} - "
                f"{schedule['payment_year']}/{schedule['payment_month']:02d} - "
                f"${paid_amount}"
            )
        
        return success
    
    def batch_mark_paid(self, payment_ids: List[int], paid_amount: float) -> Dict[str, int]:
        """
        批量標記已繳款
        
        Args:
            payment_ids: 排程 ID 列表
            paid_amount: 統一繳款金額
        
        Returns:
            {'success': 5, 'failed': 1}
        """
        logger.info(f"批量標記繳款: {len(payment_ids)} 筆，金額 ${paid_amount}")
        
        results = {'success': 0, 'failed': 0}
        
        for payment_id in payment_ids:
            if self.mark_payment_as_paid(payment_id, paid_amount):
                results['success'] += 1
            else:
                results['failed'] += 1
        
        logger.info(f"批量標記完成: {results}")
        return results
    
    def get_overdue_payments(self) -> List[Dict]:
        """取得所有逾期租金"""
        return self.payment_repo.get_by_status('overdue')
    
    def get_unpaid_payments(self) -> List[Dict]:
        """取得所有未繳租金"""
        return self.payment_repo.get_by_status('unpaid')
    
    def update_overdue_status(self) -> int:
        """
        更新逾期狀態（定時任務用）
        將過期未繳的租金標記為 overdue
        
        Returns:
            更新的記錄數
        """
        count = self.payment_repo.update_overdue_status()
        logger.info(f"更新逾期狀態: {count} 筆")
        return count
    
    def get_payment_summary(self, year: int, month: int) -> PaymentSummary:
        """
        取得租金收款摘要
        
        Returns:
            PaymentSummary 物件
        """
        raw_summary = self.payment_repo.get_payment_summary(year, month)
        
        collection_rate = 0
        if raw_summary['total_expected'] > 0:
            collection_rate = raw_summary['total_received'] / raw_summary['total_expected']
        
        return PaymentSummary(
            period=f"{year}/{month:02d}",
            total_expected=raw_summary['total_expected'],
            total_received=raw_summary['total_received'],
            unpaid_count=raw_summary['unpaid_count'],
            overdue_count=raw_summary['overdue_count'],
            collection_rate=collection_rate
        )
    
    def get_tenant_payment_history(self, room_number: str, limit: int = 12) -> List[Dict]:
        """
        取得房客繳款歷史（最近 N 期）
        
        Args:
            room_number: 房間號碼
            limit: 記錄數量限制
        
        Returns:
            排程記錄列表
        """
        query = f"""
            SELECT * FROM payment_schedule
            WHERE room_number = %s
            ORDER BY payment_year DESC, payment_month DESC
            LIMIT {limit}
        """
        return self.payment_repo._execute_query(query, (room_number,))
    
    def calculate_annual_rent_total(self, tenant: Dict) -> Tuple[float, str]:
        """
        計算年度應繳總額（含折扣）
        
        Returns:
            (年度總額, 計算說明)
        """
        base_rent = float(tenant['base_rent'])
        annual_discount_months = tenant.get('annual_discount_months', 0)
        has_water_fee = tenant.get('has_water_fee', False)
        
        # 計算實際繳款月數
        months_to_pay = 12 - annual_discount_months
        
        # 年度租金總額
        annual_rent = base_rent * months_to_pay
        
        # 年度水費總額
        annual_water_fee = self.WATER_FEE * 12 if has_water_fee else 0
        
        total = annual_rent + annual_water_fee
        
        explanation = (
            f"基礎月租 ${base_rent} × {months_to_pay} 月 = ${annual_rent}"
        )
        if has_water_fee:
            explanation += f" + 水費 ${self.WATER_FEE} × 12 月 = ${annual_water_fee}"
        explanation += f" = 年度總計 ${total}"
        
        return total, explanation
