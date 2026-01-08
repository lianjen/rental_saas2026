from typing import List, Dict, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from services.logger import logger
from repository.payment_repository import PaymentRepository
from repository.tenant_repository import TenantRepository


@dataclass
class PaymentInfo:
    """Value Object - 租金資訊"""
    room_number: str
    tenant_name: str
    payment_year: int
    payment_month: int
    amount: float
    due_date: datetime
    status: str
    
    def is_overdue(self) -> bool:
        """檢查是否逾期"""
        return self.status == 'overdue' or (
            self.status == 'unpaid' and datetime.now().date() > self.due_date.date()
        )
    
    def days_until_due(self) -> int:
        """計算距離到期日的天數"""
        delta = self.due_date.date() - datetime.now().date()
        return delta.days


class PaymentService:
    """租金管理 Service"""
    
    def __init__(self):
        self.payment_repo = PaymentRepository()
        self.tenant_repo = TenantRepository()
    
    def create_monthly_schedule(self, year: int, month: int) -> Dict[str, int]:
        """
        建立指定月份的全部租金排程
        
        Returns:
            {
                'created': 5,      # 新建筆數
                'skipped': 2,      # 已存在筆數
                'errors': 0        # 失敗筆數
            }
        """
        logger.info(f"開始建立 {year} 年 {month} 月的租金排程")
        
        try:
            # 取得所有活躍房客
            active_tenants = self.tenant_repo.get_active_tenants()
            results = {'created': 0, 'skipped': 0, 'errors': 0}
            
            for tenant in active_tenants:
                try:
                    # 1. 檢查是否已存在
                    if self.payment_repo.schedule_exists(
                        tenant['room_number'], year, month
                    ):
                        results['skipped'] += 1
                        logger.debug(f"房間 {tenant['room_number']} {year}/{month} 已存在")
                        continue
                    
                    # 2. 計算租金
                    amount = self.calculate_rent_amount(tenant, year, month)
                    logger.debug(f"房間 {tenant['room_number']} 計算月租：${amount:,.0f}")
                    
                    # 3. 設定到期日期
                    due_date = datetime(year, month, 5)
                    logger.debug(f"到期日期：{due_date.date()}")
                    
                    # 4. 建立排程
                    self.payment_repo.create_schedule(
                        room_number=tenant['room_number'],
                        tenant_name=tenant['tenant_name'],
                        payment_year=year,
                        payment_month=month,
                        amount=amount,
                        due_date=due_date,
                        payment_method=tenant.get('payment_method', '月繳')
                    )
                    results['created'] += 1
                    logger.debug(f"房間 {tenant['room_number']} {year}/{month} 建立成功")
                
                except Exception as e:
                    results['errors'] += 1
                    logger.error(f"房間 {tenant['room_number']} 建立失敗：{str(e)}")
            
            logger.info(f"建立完成 - 新增：{results['created']}，跳過：{results['skipped']}，失敗：{results['errors']}")
            return results
        
        except Exception as e:
            logger.error(f"建立月份排程失敗：{str(e)}")
            raise
    
    def calculate_rent_amount(self, tenant: Dict, year: int, month: int) -> float:
        """
        計算月租金
        
        邏輯：
        1. 基本月租 = base_rent - (100 如果有水費) = 4100 或 4000
        2. 如果有年繳折扣，計算年度折扣月份
            - 年費 = base_rent × (12 - 折扣月份)
            - 例：5000 × 11 = 55000，月租 = 55000 / 12 = 4583.33
        3. 加上水費 50 元
        
        Args:
            tenant: 房客資料
            year: 年份
            month: 月份
        
        Returns:
            月租金額（已四捨五入）
        """
        try:
            base_rent = float(tenant.get('base_rent', 0))
            payment_method = tenant.get('payment_method', '月繳')
            annual_discount_months = int(tenant.get('annual_discount_months', 0))
            
            # 計算基本月租
            if payment_method and annual_discount_months > 0:
                # 年繳折扣計算
                months_to_pay = 12 - annual_discount_months  # 例：12 - 1 = 11
                annual_total = base_rent * months_to_pay  # 例：5000 × 11 = 55000
                monthly_amount = annual_total / 12  # 例：55000 / 12 = 4583.33
                logger.debug(
                    f"年繳計算 - 折扣月份：{annual_discount_months}，"
                    f"年度總額：${annual_total:,.0f}，月租：${monthly_amount:,.0f}"
                )
            else:
                # 一般月繳
                monthly_amount = base_rent
                logger.debug(f"月繳租金：${monthly_amount:,.0f}")
            
            # 加上水費
            water_fee = 0
            if tenant.get('has_water_fee', False) and not tenant.get('water_fee_waived', False):
                water_fee = 50
                logger.debug(f"加入水費：${water_fee}")
            
            total = monthly_amount + water_fee
            logger.debug(f"最終月租：${total:,.0f}")
            
            return round(total, 0)
        
        except Exception as e:
            logger.error(f"計算租金失敗：{str(e)}")
            raise
    
    def calculate_rent_detail(self, tenant: Dict) -> Dict:
        """
        計算租金詳細資訊
        
        Returns:
            {
                'base_rent': 5000,
                'monthly_rent': 4583,
                'has_water_discount': True,
                'annual_discount_months': 1,
                'annual_total': 55000,
                'payment_method': '年繳'
            }
        """
        try:
            base_rent = float(tenant.get('base_rent', 0))
            has_water_fee = tenant.get('has_water_fee', False)
            payment_method = tenant.get('payment_method', '月繳')
            annual_discount_months = int(tenant.get('annual_discount_months', 0))
            
            # 計算月租
            monthly_rent = self.calculate_rent_amount(tenant, datetime.now().year, datetime.now().month)
            
            # 計算年度總額
            annual_total = 0
            if payment_method and annual_discount_months > 0:
                months_to_pay = 12 - annual_discount_months
                annual_total = base_rent * months_to_pay
            else:
                annual_total = base_rent * 12
            
            return {
                'base_rent': base_rent,
                'monthly_rent': monthly_rent,
                'has_water_discount': has_water_fee,
                'annual_discount_months': annual_discount_months,
                'annual_total': annual_total,
                'payment_method': payment_method
            }
        
        except Exception as e:
            logger.error(f"計算租金詳細資訊失敗：{str(e)}")
            raise
    
    def get_overdue_payments(self) -> List[PaymentInfo]:
        """
        取得所有逾期租金
        
        Returns:
            [PaymentInfo, ...]
        """
        try:
            raw_data = self.payment_repo.get_by_status('overdue')
            logger.info(f"取得逾期租金：{len(raw_data)} 筆")
            
            return [
                PaymentInfo(
                    room_number=p['room_number'],
                    tenant_name=p['tenant_name'],
                    payment_year=p['payment_year'],
                    payment_month=p['payment_month'],
                    amount=p['amount'],
                    due_date=p['due_date'],
                    status=p['status']
                )
                for p in raw_data
            ]
        
        except Exception as e:
            logger.error(f"取得逾期租金失敗：{str(e)}")
            raise
    
    def mark_as_paid(
        self,
        payment_id: int,
        paid_amount: float,
        paid_date: Optional[datetime] = None,
        notes: str = ""
    ) -> bool:
        """
        標記為已繳
        
        Args:
            payment_id: 租金記錄 ID
            paid_amount: 繳款金額
            paid_date: 繳款日期（預設今天）
            notes: 備註
        
        Returns:
            是否成功
        """
        try:
            if paid_date is None:
                paid_date = datetime.now()
            
            logger.info(f"開始標記租金 ID {payment_id} 為已繳")
            
            # 1. 取得原始記錄
            schedule = self.payment_repo.get_by_id(payment_id)
            if not schedule:
                logger.error(f"找不到租金記錄 ID {payment_id}")
                return False
            
            # 2. 檢查繳款金額
            expected = schedule['amount']
            if abs(paid_amount - expected) > 0.01:
                logger.warning(
                    f"房間 {schedule['room_number']} 繳款金額不符 - "
                    f"應繳：${expected:,.0f}，實繳：${paid_amount:,.0f}，"
                    f"差額：${paid_amount - expected:,.0f}"
                )
            
            # 3. 更新狀態
            success = self.payment_repo.update_payment_status(
                payment_id=payment_id,
                status='paid',
                paid_amount=paid_amount,
                paid_date=paid_date,
                notes=notes
            )
            
            if success:
                logger.info(
                    f"房間 {schedule['room_number']} {schedule['payment_year']}/"
                    f"{schedule['payment_month']} 標記為已繳 - "
                    f"繳款金額：${paid_amount:,.0f}"
                )
                return True
            else:
                logger.error(f"標記租金 ID {payment_id} 失敗")
                return False
        
        except Exception as e:
            logger.error(f"標記為已繳失敗：{str(e)}")
            raise
    
    def get_payment_summary(self, year: int, month: int) -> Dict:
        """
        取得指定月份的收款摘要
        
        Returns:
            {
                'total_expected': 60000,      # 應收總額
                'total_received': 55000,      # 實收總額
                'unpaid_count': 2,            # 待繳筆數
                'overdue_count': 1,           # 逾期筆數
                'collection_rate': 0.917      # 收款率
            }
        """
        try:
            logger.info(f"取得 {year}/{month} 的收款摘要")
            
            # 取得該月份的所有排程
            schedules = self.payment_repo.get_by_period(year, month)
            
            total_expected = sum(s['amount'] for s in schedules)
            total_received = sum(
                s['paid_amount']
                for s in schedules
                if s['status'] == 'paid' and s['paid_amount']
            )
            unpaid = [s for s in schedules if s['status'] == 'unpaid']
            overdue = [s for s in schedules if s['status'] == 'overdue']
            
            collection_rate = (
                total_received / total_expected
                if total_expected > 0
                else 0
            )
            
            result = {
                'total_expected': total_expected,
                'total_received': total_received,
                'unpaid_count': len(unpaid),
                'overdue_count': len(overdue),
                'collection_rate': collection_rate
            }
            
            logger.debug(
                f"摘要統計 - 應收：${total_expected:,.0f}，"
                f"實收：${total_received:,.0f}，"
                f"待繳：{len(unpaid)} 筆，"
                f"逾期：{len(overdue)} 筆，"
                f"收款率：{collection_rate:.1%}"
            )
            
            return result
        
        except Exception as e:
            logger.error(f"取得收款摘要失敗：{str(e)}")
            raise
    
    def get_payment_trends(self, year: int) -> List[Dict]:
        """
        取得全年收款趨勢
        
        Returns:
            [
                {
                    'month': 1,
                    'total_amount': 60000,
                    'paid_amount': 55000,
                    'payment_rate': 0.917
                },
                ...
            ]
        """
        try:
            logger.info(f"取得 {year} 年的收款趨勢")
            trends = []
            
            for month in range(1, 13):
                summary = self.get_payment_summary(year, month)
                if summary['total_expected'] > 0:
                    trends.append({
                        'month': month,
                        'total_amount': summary['total_expected'],
                        'paid_amount': summary['total_received'],
                        'payment_rate': summary['collection_rate']
                    })
            
            logger.info(f"取得 {len(trends)} 個月份的趨勢數據")
            return trends
        
        except Exception as e:
            logger.error(f"取得收款趨勢失敗：{str(e)}")
            raise
    
    def batch_mark_paid(self, payment_ids: List[int], paid_amount
: float, paid_date: Optional[datetime] = None) -> Dict[str, int]:
        """
        批量標記為已繳
        
        Args:
            payment_ids: 租金記錄 ID 列表
            paid_amount: 繳款金額
            paid_date: 繳款日期
        
        Returns:
            {
                'success': 5,     # 成功筆數
                'failed': 0,      # 失敗筆數
                'errors': []      # 錯誤訊息
            }
        """
        try:
            if paid_date is None:
                paid_date = datetime.now()
            
            logger.info(f"開始批量標記 {len(payment_ids)} 筆租金為已繳")
            
            results = {
                'success': 0,
                'failed': 0,
                'errors': []
            }
            
            for payment_id in payment_ids:
                try:
                    success = self.mark_as_paid(
                        payment_id,
                        paid_amount,
                        paid_date
                    )
                    
                    if success:
                        results['success'] += 1
                    else:
                        results['failed'] += 1
                        results['errors'].append(f"ID {payment_id} 標記失敗")
                
                except Exception as e:
                    results['failed'] += 1
                    error_msg = f"ID {payment_id} 異常：{str(e)}"
                    results['errors'].append(error_msg)
                    logger.error(error_msg)
            
            logger.info(
                f"批量標記完成 - 成功：{results['success']}，"
                f"失敗：{results['failed']}"
            )
            
            return results
        
        except Exception as e:
            logger.error(f"批量標記失敗：{str(e)}")
            raise
    
    def get_overdue_report(self) -> Dict:
        """
        取得逾期報告
        
        Returns:
            {
                'total_overdue_count': 5,
                'total_overdue_amount': 25000,
                'overdue_payments': [PaymentInfo, ...]
            }
        """
        try:
            logger.info("生成逾期報告")
            
            overdue_payments = self.get_overdue_payments()
            total_overdue_amount = sum(p.amount for p in overdue_payments)
            
            report = {
                'total_overdue_count': len(overdue_payments),
                'total_overdue_amount': total_overdue_amount,
                'overdue_payments': overdue_payments
            }
            
            logger.info(
                f"逾期報告 - 筆數：{len(overdue_payments)}，"
                f"金額：${total_overdue_amount:,.0f}"
            )
            
            return report
        
        except Exception as e:
            logger.error(f"生成逾期報告失敗：{str(e)}")
            raise
    
    def get_tenant_payment_status(self, tenant_id: int) -> Dict:
        """
        取得房客的繳款狀態
        
        Returns:
            {
                'tenant_name': '王小明',
                'room_number': '1A',
                'total_amount': 50000,
                'paid_amount': 40000,
                'unpaid_amount': 10000,
                'payment_rate': 0.8,
                'status_summary': '待繳 2 筆，逾期 1 筆'
            }
        """
        try:
            logger.info(f"取得房客 ID {tenant_id} 的繳款狀態")
            
            schedules = self.payment_repo.get_by_tenant(tenant_id)
            
            if not schedules:
                logger.warning(f"找不到房客 ID {tenant_id} 的租金記錄")
                return {}
            
            tenant_info = schedules[0]
            total_amount = sum(s['amount'] for s in schedules)
            paid_amount = sum(
                s['paid_amount']
                for s in schedules
                if s['status'] == 'paid' and s['paid_amount']
            )
            unpaid_amount = total_amount - paid_amount
            payment_rate = paid_amount / total_amount if total_amount > 0 else 0
            
            unpaid_count = len([s for s in schedules if s['status'] == 'unpaid'])
            overdue_count = len([s for s in schedules if s['status'] == 'overdue'])
            
            status_summary = f"待繳 {unpaid_count} 筆" if unpaid_count > 0 else ""
            if overdue_count > 0:
                status_summary += f"，逾期 {overdue_count} 筆" if status_summary else f"逾期 {overdue_count} 筆"
            
            result = {
                'tenant_name': tenant_info['tenant_name'],
                'room_number': tenant_info['room_number'],
                'total_amount': total_amount,
                'paid_amount': paid_amount,
                'unpaid_amount': unpaid_amount,
                'payment_rate': payment_rate,
                'status_summary': status_summary or '全部已繳'
            }
            
            logger.debug(
                f"房客 {tenant_info['tenant_name']} - "
                f"應繳：${total_amount:,.0f}，"
                f"已繳：${paid_amount:,.0f}，"
                f"繳款率：{payment_rate:.1%}"
            )
            
            return result
        
        except Exception as e:
            logger.error(f"取得房客繳款狀態失敗：{str(e)}")
            raise
    
    def validate_schedule(self, year: int, month: int) -> Dict[str, any]:
        """
        驗證排程完整性
        
        Returns:
            {
                'is_valid': True,
                'total_tenants': 10,
                'scheduled_tenants': 10,
                'missing_tenants': [],
                'duplicate_schedules': []
            }
        """
        try:
            logger.info(f"驗證 {year}/{month} 的排程完整性")
            
            # 取得所有活躍房客
            all_tenants = self.tenant_repo.get_active_tenants()
            
            # 取得已排程的租金
            schedules = self.payment_repo.get_by_period(year, month)
            scheduled_rooms = {s['room_number'] for s in schedules}
            
            # 找出缺失的房客
            all_rooms = {t['room_number'] for t in all_tenants}
            missing_tenants = all_rooms - scheduled_rooms
            
            # 檢查重複的排程
            duplicate_schedules = []
            room_counts = {}
            for schedule in schedules:
                room = schedule['room_number']
                room_counts[room] = room_counts.get(room, 0) + 1
                if room_counts[room] > 1:
                    duplicate_schedules.append(room)
            
            is_valid = len(missing_tenants) == 0 and len(duplicate_schedules) == 0
            
            result = {
                'is_valid': is_valid,
                'total_tenants': len(all_tenants),
                'scheduled_tenants': len(scheduled_rooms),
                'missing_tenants': list(missing_tenants),
                'duplicate_schedules': list(set(duplicate_schedules))
            }
            
            if is_valid:
                logger.info(f"排程驗證成功 - 所有 {len(all_tenants)} 位房客均已排程")
            else:
                logger.warning(
                    f"排程驗證失敗 - 缺失：{len(missing_tenants)} 位房客，"
                    f"重複：{len(set(duplicate_schedules))} 間房間"
                )
            
            return result
        
        except Exception as e:
            logger.error(f"驗證排程失敗：{str(e)}")
            raise

