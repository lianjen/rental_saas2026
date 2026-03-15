"""
電費管理服務 - v5.7
✅ 保留 ElectricityService 作為 facade
✅ repository-backed DB 邏輯移至 electricity_billing_service.py
✅ 純計算邏輯維持在 electricity_calculator.py
✅ 向後兼容既有 import 路徑與 clear_electricity_cache
"""

from services.electricity_billing_service import (
    ElectricityBillingService,
    clear_electricity_cache,
)


class ElectricityService(ElectricityBillingService):
    """電費管理 facade，維持既有外部 API 不變。"""

    def __init__(self):
        super().__init__()


__all__ = [
    "ElectricityService",
    "ElectricityBillingService",
    "clear_electricity_cache",
]
