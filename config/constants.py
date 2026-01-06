"""
系統常數與設定 - 單一真相來源
所有硬編碼數值統一在此管理
"""

from dataclasses import dataclass
from typing import List


@dataclass
class RoomConfig:
    """房間設定"""
    ALL_ROOMS: List[str] = None
    EXCLUSIVE_ROOMS: List[str] = None  # 獨享房間 (不分攤公用電)
    SHARING_ROOMS: List[str] = None     # 分攤房間
    
    def __post_init__(self):
        self.ALL_ROOMS = [
            "1A", "1B", "2A", "2B", "3A", "3B", 
            "3C", "3D", "4A", "4B", "4C", "4D"
        ]
        self.EXCLUSIVE_ROOMS = ["1A", "1B"]
        self.SHARING_ROOMS = [
            "2A", "2B", "3A", "3B", "3C", "3D", 
            "4A", "4B", "4C", "4D"
        ]
    
    def get_room_type(self, room: str) -> str:
        """取得房間類型"""
        if room in self.EXCLUSIVE_ROOMS:
            return "exclusive"
        elif room in self.SHARING_ROOMS:
            return "sharing"
        return "unknown"


@dataclass
class PaymentConfig:
    """繳費設定"""
    METHODS: List[str] = None
    STATUSES: List[str] = None
    DEFAULT_WATER_FEE: int = 100  # 水費
    
    def __post_init__(self):
        self.METHODS = ["月繳", "半年繳", "年繳"]
        self.STATUSES = ["未繳", "已繳"]


@dataclass
class ExpenseConfig:
    """支出設定"""
    CATEGORIES: List[str] = None
    
    def __post_init__(self):
        self.CATEGORIES = [
            "維修", "雜項", "貸款", "水電費", "網路費"
        ]


@dataclass
class ElectricityConfig:
    """電費設定"""
    # 台電累進費率 (夏月 6-9月)
    TIER_SUMMER: List[tuple] = None
    # 非夏月費率
    TIER_NON_SUMMER: List[tuple] = None
    
    def __post_init__(self):
        # (度數上限, 每度單價)
        self.TIER_SUMMER = [
            (120, 1.63),
            (330, 2.38),
            (500, 3.52),
            (700, 4.80),
            (1000, 5.66),
            (float('inf'), 6.41)
        ]
        
        self.TIER_NON_SUMMER = [
            (120, 1.63),
            (330, 2.10),
            (500, 2.89),
            (700, 3.94),
            (1000, 4.60),
            (float('inf'), 5.03)
        ]
    
    def calculate_progressive_fee(self, kwh: float, is_summer: bool = False) -> float:
        """
        計算累進電費
        
        Args:
            kwh: 用電度數
            is_summer: 是否為夏月
        
        Returns:
            電費金額
        """
        tiers = self.TIER_SUMMER if is_summer else self.TIER_NON_SUMMER
        total_fee = 0
        remaining = kwh
        prev_limit = 0
        
        for limit, rate in tiers:
            if remaining <= 0:
                break
            
            tier_kwh = min(remaining, limit - prev_limit)
            total_fee += tier_kwh * rate
            remaining -= tier_kwh
            prev_limit = limit
        
        return round(total_fee, 2)


@dataclass
class UIConfig:
    """UI 設定"""
    PAGE_ICON: str = "🏠"
    PAGE_TITLE: str = "租屋管理系統"
    ITEMS_PER_PAGE: int = 50
    DATE_FORMAT: str = "%Y-%m-%d"
    CURRENCY_SYMBOL: str = "NT$"


@dataclass
class SystemConfig:
    """系統設定"""
    LOG_LEVEL: str = "INFO"
    CONNECTION_POOL_MIN: int = 2
    CONNECTION_POOL_MAX: int = 10
    QUERY_TIMEOUT: int = 30  # 秒
    RETRY_MAX_ATTEMPTS: int = 3
    RETRY_DELAY: int = 1  # 秒


# ============== 全域常數實例 ==============
ROOMS = RoomConfig()
PAYMENT = PaymentConfig()
EXPENSE = ExpenseConfig()
ELECTRICITY = ElectricityConfig()
UI = UIConfig()
SYSTEM = SystemConfig()


# ============== 輔助函數 ==============
def get_all_rooms() -> List[str]:
    """取得所有房號"""
    return ROOMS.ALL_ROOMS.copy()


def get_sharing_rooms() -> List[str]:
    """取得分攤房間"""
    return ROOMS.SHARING_ROOMS.copy()


def get_exclusive_rooms() -> List[str]:
    """取得獨享房間"""
    return ROOMS.EXCLUSIVE_ROOMS.copy()


def is_sharing_room(room: str) -> bool:
    """判斷是否為分攤房間"""
    return room in ROOMS.SHARING_ROOMS


def get_payment_methods() -> List[str]:
    """取得繳款方式"""
    return PAYMENT.METHODS.copy()


def get_expense_categories() -> List[str]:
    """取得支出分類"""
    return EXPENSE.CATEGORIES.copy()


# ============== 使用範例 ==============
if __name__ == "__main__":
    # 測試電費計算
    print(f"300 度電費 (夏月): {ELECTRICITY.calculate_progressive_fee(300, True)}")
    print(f"300 度電費 (非夏月): {ELECTRICITY.calculate_progressive_fee(300, False)}")
    
    # 測試房間類型
    print(f"1A 房型: {ROOMS.get_room_type('1A')}")
    print(f"2A 房型: {ROOMS.get_room_type('2A')}")