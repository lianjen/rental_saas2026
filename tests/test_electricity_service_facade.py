"""
electricity_service facade 測試 - v1.0.0
驗證 electricity_service.py 已收斂為 facade，並維持既有公開 API。
"""

import unittest

from services.electricity_billing_service import ElectricityBillingService
from services.electricity_service import ElectricityService, clear_electricity_cache


class ElectricityServiceFacadeTest(unittest.TestCase):
    """驗證 facade 與 billing service 的關係。"""

    def test_electricity_service_inherits_billing_service(self):
        self.assertTrue(issubclass(ElectricityService, ElectricityBillingService))

    def test_electricity_service_keeps_public_api(self):
        expected_methods = [
            "save_taipower_bills",
            "get_taipower_bills",
            "delete_taipower_bills",
            "add_deposit",
            "deduct_electricity",
            "get_deposit_balance",
            "get_deposit_ledger",
            "get_all_rooms_deposit_summary",
            "add_period",
            "get_all_periods",
            "get_period_by_id",
            "delete_period",
            "update_period_remind_date",
            "get_latest_meter_reading",
            "get_all_readings",
            "save_reading",
            "mark_paid",
            "mark_unpaid",
            "get_payment_record",
            "get_period_records",
            "get_payment_summary",
            "save_records",
            "update_payment",
            "batch_update_payments",
        ]

        for method_name in expected_methods:
            with self.subTest(method_name=method_name):
                self.assertTrue(hasattr(ElectricityService, method_name))

    def test_clear_electricity_cache_is_callable(self):
        self.assertTrue(callable(clear_electricity_cache))


if __name__ == "__main__":
    unittest.main()
