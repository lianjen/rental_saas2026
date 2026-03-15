"""
payment_service facade 測試 - v1.0.0
驗證 payment_service.py 已拆成 facade，並維持既有公開 API
"""

import unittest

from services.payment_collection_service import PaymentCollectionService
from services.payment_reminder_service import PaymentReminderService
from services.payment_schedule_service import PaymentScheduleService
from services.payment_service import PaymentService


class PaymentServiceFacadeTest(unittest.TestCase):
    """驗證 facade 仍然可作為既有入口使用。"""

    def test_payment_service_inherits_split_services(self):
        self.assertTrue(issubclass(PaymentService, PaymentScheduleService))
        self.assertTrue(issubclass(PaymentService, PaymentCollectionService))
        self.assertTrue(issubclass(PaymentService, PaymentReminderService))

    def test_payment_service_keeps_public_api(self):
        expected_methods = [
            "get_payment_schedule",
            "get_payment_by_id",
            "add_payment_schedule",
            "create_monthly_schedule",
            "batch_create_payment_schedule",
            "check_payment_exists",
            "get_all_payments",
            "get_unpaid_payments",
            "get_paid_payments",
            "get_payments_by_period",
            "get_room_payments",
            "get_monthly_summary",
            "mark_payment_done",
            "batch_mark_paid",
            "update_payment_amount",
            "delete_payment_schedule",
            "get_payment_statistics",
            "get_payment_trends",
            "get_room_payment_history",
            "get_tenant_history",
            "get_overdue_payments",
            "get_pending_notifications",
        ]

        for method_name in expected_methods:
            with self.subTest(method_name=method_name):
                self.assertTrue(hasattr(PaymentService, method_name))


if __name__ == "__main__":
    unittest.main()
