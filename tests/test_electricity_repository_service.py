"""
electricity repository bridge tests - v1.1.0
驗證 electricity_billing_service.py 已改為透過 repository 協作，
並與 electricity_service facade 相容。
"""

import unittest
from unittest.mock import Mock, patch

from repository import ElectricityRepository
from services.electricity_billing_service import ElectricityBillingService
from services.electricity_service import ElectricityService


class ElectricityRepositoryBridgeTest(unittest.TestCase):
    """驗證電費 billing service 與 repository 的委派關係。"""

    @staticmethod
    def _make_service() -> ElectricityBillingService:
        service = object.__new__(ElectricityBillingService)
        service.repository = Mock()
        return service

    def test_repository_package_exports_electricity_repository(self):
        self.assertTrue(issubclass(ElectricityRepository, object))

    def test_facade_still_inherits_billing_service(self):
        self.assertTrue(issubclass(ElectricityService, ElectricityBillingService))

    def test_save_taipower_bills_delegates_to_repository(self):
        service = self._make_service()
        service.repository.save_taipower_bills.return_value = (True, 2)
        bills = [
            {"floor_label": "1F", "amount": 1000, "kwh": 100},
            {"floor_label": "234F", "amount": 2000, "kwh": 200},
        ]

        with patch("services.electricity_billing_service.clear_electricity_cache") as clear_cache:
            ok, msg = service.save_taipower_bills(7, bills)

        self.assertTrue(ok)
        self.assertIn("2", msg)
        service.repository.save_taipower_bills.assert_called_once_with(7, bills)
        clear_cache.assert_called_once()

    def test_add_period_uses_repository_for_duplicate_check_and_create(self):
        service = self._make_service()
        service.repository.period_exists.return_value = (True, False)
        service.repository.create_period.return_value = (True, 99)

        with patch("services.electricity_billing_service.clear_electricity_cache") as clear_cache:
            ok, msg, period_id = service.add_period(2026, 1, 2, "2026-02-01")

        self.assertTrue(ok)
        self.assertEqual(period_id, 99)
        self.assertIn("2026", msg)
        service.repository.period_exists.assert_called_once_with(2026, 1, 2)
        service.repository.create_period.assert_called_once_with(2026, 1, 2, "2026-02-01")
        clear_cache.assert_called_once()

    def test_save_reading_computes_total_kwh_before_upsert(self):
        service = self._make_service()
        service.repository.upsert_reading.return_value = (True, 1)

        with patch("services.electricity_billing_service.clear_electricity_cache") as clear_cache:
            ok, msg = service.save_reading(
                period_id=5,
                room="2A",
                previous=100,
                current=120,
                kwh_used=20,
                unit_price=3.2,
                public_share_kwh=4,
                amount_due=77,
                room_type="shared",
            )

        self.assertTrue(ok)
        self.assertIn("2A", msg)
        service.repository.upsert_reading.assert_called_once_with(
            5,
            "2A",
            100,
            120,
            20,
            3.2,
            4,
            24,
            77,
            "shared",
        )
        clear_cache.assert_called_once()

    def test_get_deposit_balance_converts_repository_result_to_float(self):
        service = self._make_service()
        service.repository.get_deposit_balance.return_value = (True, 123.45)

        balance = service.get_deposit_balance("3B")

        self.assertEqual(balance, 123.45)
        service.repository.get_deposit_balance.assert_called_once_with("3B")


if __name__ == "__main__":
    unittest.main()
