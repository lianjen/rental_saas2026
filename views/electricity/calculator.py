"""
電費計算引擎
負責所有電費相關的計算邏輯
"""

from typing import Dict, List, Tuple
from datetime import date
import logging

logger = logging.getLogger(__name__)


class ElectricityCalculator:
    """電費計算器"""
    
    def __init__(self, sharing_rooms: List[str], exclusive_rooms: List[str]):
        """
        初始化計算器
        
        Args:
            sharing_rooms: 需要分攤公用電的房間
            exclusive_rooms: 獨享電錶的房間
        """
        self.sharing_rooms = sharing_rooms
        self.exclusive_rooms = exclusive_rooms
    
    def calculate_unit_price(self, total_amount: float, total_kwh: float) -> float:
        """
        計算平均電價
        
        Args:
            total_amount: 台電總金額
            total_kwh: 台電總度數
        
        Returns:
            每度電單價
        """
        if total_kwh <= 0:
            raise ValueError("總度數必須大於 0")
        
        return round(total_amount / total_kwh, 2)
    
    def calculate_public_electricity(self, 
                                     taipower_kwh: float,
                                     room_readings: Dict[str, float]) -> float:
        """
        計算公用電度數
        
        Args:
            taipower_kwh: 台電總度數
            room_readings: 各房間讀數 {房號: 度數}
        
        Returns:
            公用電度數
        """
        total_room_kwh = sum(room_readings.values())
        public_kwh = taipower_kwh - total_room_kwh
        
        if public_kwh < 0:
            logger.warning(f"公用電為負數: {public_kwh} (台電: {taipower_kwh}, 房間總計: {total_room_kwh})")
            return 0
        
        return round(public_kwh, 2)
    
    def calculate_shared_electricity(self,
                                     public_kwh: float,
                                     sharing_room_count: int) -> float:
        """
        計算每個分攤房間應分攤的公用電
        
        Args:
            public_kwh: 公用電總度數
            sharing_room_count: 分攤房間數量
        
        Returns:
            每間應分攤度數
        """
        if sharing_room_count <= 0:
            return 0
        
        return round(public_kwh / sharing_room_count, 2)
    
    def calculate_room_charge(self,
                              room_number: str,
                              room_kwh: float,
                              unit_price: float,
                              shared_kwh: float = 0) -> Dict:
        """
        計算單一房間應繳電費
        
        Args:
            room_number: 房號
            room_kwh: 房間度數
            unit_price: 單位電價
            shared_kwh: 應分攤公用電度數
        
        Returns:
            {
                'room': 房號,
                'room_kwh': 房間度數,
                'shared_kwh': 分攤度數,
                'total_kwh': 總度數,
                'charge': 應繳金額
            }
        """
        # 判斷是否為分攤房間
        is_sharing = room_number in self.sharing_rooms
        actual_shared_kwh = shared_kwh if is_sharing else 0
        
        total_kwh = room_kwh + actual_shared_kwh
        charge = round(total_kwh * unit_price)
        
        return {
            'room': room_number,
            'room_kwh': round(room_kwh, 2),
            'shared_kwh': round(actual_shared_kwh, 2),
            'total_kwh': round(total_kwh, 2),
            'charge': charge,
            'is_sharing': is_sharing
        }
    
    def calculate_all_rooms(self,
                           taipower_amount: float,
                           taipower_kwh: float,
                           room_readings: Dict[str, float]) -> Dict:
        """
        計算所有房間電費
        
        Args:
            taipower_amount: 台電總金額
            taipower_kwh: 台電總度數
            room_readings: 各房間讀數 {房號: 度數}
        
        Returns:
            {
                'unit_price': 單位電價,
                'public_kwh': 公用電度數,
                'shared_kwh_per_room': 每間分攤度數,
                'room_charges': [房間計費明細],
                'total_charge': 總計金額,
                'difference': 與台電差異
            }
        """
        try:
            # 1. 計算單位電價
            unit_price = self.calculate_unit_price(taipower_amount, taipower_kwh)
            
            # 2. 計算公用電
            public_kwh = self.calculate_public_electricity(taipower_kwh, room_readings)
            
            # 3. 計算每間分攤房間應分攤的度數
            sharing_count = len([r for r in room_readings.keys() if r in self.sharing_rooms])
            shared_kwh_per_room = self.calculate_shared_electricity(public_kwh, sharing_count)
            
            # 4. 計算各房間電費
            room_charges = []
            for room, kwh in room_readings.items():
                charge_detail = self.calculate_room_charge(
                    room, kwh, unit_price, shared_kwh_per_room
                )
                room_charges.append(charge_detail)
            
            # 5. 計算總計
            total_charge = sum(c['charge'] for c in room_charges)
            difference = total_charge - taipower_amount
            
            return {
                'unit_price': unit_price,
                'public_kwh': public_kwh,
                'shared_kwh_per_room': shared_kwh_per_room,
                'sharing_room_count': sharing_count,
                'room_charges': sorted(room_charges, key=lambda x: x['room']),
                'total_charge': total_charge,
                'taipower_amount': taipower_amount,
                'difference': round(difference, 2)
            }
        
        except Exception as e:
            logger.error(f"電費計算失敗: {e}")
            raise
    
    def validate_readings(self,
                         current_readings: Dict[str, float],
                         previous_readings: Dict[str, float] = None) -> Tuple[bool, List[str]]:
        """
        驗證抄表數據
        
        Args:
            current_readings: 本期讀數
            previous_readings: 上期讀數 (可選)
        
        Returns:
            (是否通過, 錯誤訊息列表)
        """
        errors = []
        
        # 檢查讀數是否為負數
        for room, reading in current_readings.items():
            if reading < 0:
                errors.append(f"{room}: 讀數不能為負數")
        
        # 檢查是否與上期比較倒退
        if previous_readings:
            for room, current in current_readings.items():
                if room in previous_readings:
                    previous = previous_readings[room]
                    if current < previous:
                        errors.append(
                            f"{room}: 本期讀數 ({current}) 不能小於上期 ({previous})"
                        )
        
        return len(errors) == 0, errors


# ============== 輔助函數 ==============

def format_charge_summary(result: Dict) -> str:
    """
    格式化計費摘要
    
    Args:
        result: calculate_all_rooms 的返回值
    
    Returns:
        格式化的摘要文字
    """
    summary = f"""
📊 **計費摘要**

**基本資訊**
- 台電金額: ${result['taipower_amount']:,} 元
- 單位電價: ${result['unit_price']:.2f} 元/度
- 公用電度數: {result['public_kwh']:.2f} 度
- 分攤房間數: {result['sharing_room_count']} 間
- 每間分攤: {result['shared_kwh_per_room']:.2f} 度

**收費總計**
- 房間總計: ${result['total_charge']:,} 元
- 與台電差異: ${result['difference']:+,.0f} 元
"""
    return summary


def export_charge_details(result: Dict) -> List[Dict]:
    """
    匯出計費明細 (for DataFrame)
    
    Args:
        result: calculate_all_rooms 的返回值
    
    Returns:
        計費明細列表
    """
    details = []
    for charge in result['room_charges']:
        details.append({
            '房號': charge['room'],
            '房間度數': charge['room_kwh'],
            '分攤度數': charge['shared_kwh'] if charge['is_sharing'] else '-',
            '總度數': charge['total_kwh'],
            '應繳金額': f"${charge['charge']:,}",
            '是否分攤': '是' if charge['is_sharing'] else '否'
        })
    
    return details