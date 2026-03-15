"""
租金管理服務 - v5.4
✅ 拆分為排程、收款、催繳三個獨立 Service class
✅ 保留 PaymentService facade，維持既有 import 路徑與 API
✅ 向後兼容 views.rent / views.notifications / services.db_legacy
"""

from services.payment_collection_service import PaymentCollectionService
from services.payment_reminder_service import PaymentReminderService
from services.payment_schedule_service import PaymentScheduleService


class PaymentService(
    PaymentScheduleService,
    PaymentCollectionService,
    PaymentReminderService,
):
    """租金管理 facade，整合排程、收款、催繳三個子服務。"""

    def __init__(self):
        super().__init__()


__all__ = [
    "PaymentService",
    "PaymentScheduleService",
    "PaymentCollectionService",
    "PaymentReminderService",
]
