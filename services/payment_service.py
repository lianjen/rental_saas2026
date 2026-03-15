"""
租金管理服務 - v5.5
✅ 拆分為排程、收款、催繳三個獨立 Service class
✅ 保留 PaymentService facade，維持既有 import 路徑與 API
✅ 高頻唯讀查詢保留 cache_data，寫入後自動清 cache
✅ 向後兼容 views.rent / views.notifications / services.db_legacy
"""

from typing import Dict, List, Optional, Tuple

from services.cache_utils import cache_data, clear_cached_functions, get_cache_scope
from services.payment_collection_service import PaymentCollectionService
from services.payment_reminder_service import PaymentReminderService
from services.payment_schedule_service import PaymentScheduleService


@cache_data(ttl=60)
def _cached_get_overdue_payments(user_id: str, dev_mode: bool) -> List[Dict]:
    return PaymentReminderService().get_overdue_payments()


@cache_data(ttl=60)
def _cached_get_pending_notifications(user_id: str, dev_mode: bool) -> List[Dict]:
    return PaymentReminderService().get_pending_notifications()


@cache_data(ttl=300)
def _cached_get_all_payments(user_id: str, dev_mode: bool) -> List[Dict]:
    return PaymentCollectionService().get_all_payments()


@cache_data(ttl=60)
def _cached_get_unpaid_payments(user_id: str, dev_mode: bool) -> List[Dict]:
    return PaymentCollectionService().get_unpaid_payments()


@cache_data(ttl=300)
def _cached_get_paid_payments(user_id: str, dev_mode: bool) -> List[Dict]:
    return PaymentCollectionService().get_paid_payments()


@cache_data(ttl=300)
def _cached_get_payments_by_period(
    year: int,
    month: int,
    user_id: str,
    dev_mode: bool,
) -> List[Dict]:
    return PaymentCollectionService().get_payments_by_period(year, month)


@cache_data(ttl=60)
def _cached_get_monthly_summary(
    year: int,
    month: int,
    user_id: str,
    dev_mode: bool,
) -> Dict:
    return PaymentCollectionService().get_monthly_summary(year, month)


def clear_payment_cache() -> None:
    clear_cached_functions(
        _cached_get_overdue_payments,
        _cached_get_pending_notifications,
        _cached_get_all_payments,
        _cached_get_unpaid_payments,
        _cached_get_paid_payments,
        _cached_get_payments_by_period,
        _cached_get_monthly_summary,
    )


class PaymentService(
    PaymentScheduleService,
    PaymentCollectionService,
    PaymentReminderService,
):
    """租金管理 facade，整合排程、收款、催繳三個子服務。"""

    def __init__(self):
        super().__init__()

    def get_overdue_payments(self) -> List[Dict]:
        user_id, dev_mode = get_cache_scope(self)
        return _cached_get_overdue_payments(user_id, dev_mode)

    def get_pending_notifications(self) -> List[Dict]:
        user_id, dev_mode = get_cache_scope(self)
        return _cached_get_pending_notifications(user_id, dev_mode)

    def get_all_payments(self) -> List[Dict]:
        user_id, dev_mode = get_cache_scope(self)
        return _cached_get_all_payments(user_id, dev_mode)

    def get_unpaid_payments(self) -> List[Dict]:
        user_id, dev_mode = get_cache_scope(self)
        return _cached_get_unpaid_payments(user_id, dev_mode)

    def get_paid_payments(self) -> List[Dict]:
        user_id, dev_mode = get_cache_scope(self)
        return _cached_get_paid_payments(user_id, dev_mode)

    def get_payments_by_period(self, year: int, month: int) -> List[Dict]:
        user_id, dev_mode = get_cache_scope(self)
        return _cached_get_payments_by_period(year, month, user_id, dev_mode)

    def get_monthly_summary(self, year: int, month: int) -> Dict:
        user_id, dev_mode = get_cache_scope(self)
        return _cached_get_monthly_summary(year, month, user_id, dev_mode)

    def add_payment_schedule(
        self,
        room: str,
        tenant_name: str,
        year: int,
        month: int,
        amount: float,
        payment_method: str,
        due_date=None,
    ) -> Tuple[bool, str]:
        ok, msg = super().add_payment_schedule(
            room=room,
            tenant_name=tenant_name,
            year=year,
            month=month,
            amount=amount,
            payment_method=payment_method,
            due_date=due_date,
        )
        if ok:
            clear_payment_cache()
        return ok, msg

    def create_monthly_schedule(
        self,
        room_number: str,
        year: int,
        month: int,
    ) -> Tuple[bool, str]:
        ok, msg = super().create_monthly_schedule(room_number, year, month)
        if ok:
            clear_payment_cache()
        return ok, msg

    def batch_create_payment_schedule(
        self,
        schedules: List[Dict],
    ) -> Tuple[int, int, int]:
        success_count, skip_count, fail_count = super().batch_create_payment_schedule(schedules)
        if success_count > 0:
            clear_payment_cache()
        return success_count, skip_count, fail_count

    def mark_payment_done(
        self,
        payment_id: int,
        paid_amount: Optional[float] = None,
    ) -> Tuple[bool, str]:
        ok, msg = super().mark_payment_done(payment_id, paid_amount)
        if ok:
            clear_payment_cache()
        return ok, msg

    def batch_mark_paid(self, payment_ids: List[int]) -> Dict[str, int]:
        result = super().batch_mark_paid(payment_ids)
        if result.get("success", 0) > 0:
            clear_payment_cache()
        return result

    def update_payment_amount(self, payment_id: int, new_amount: float) -> Tuple[bool, str]:
        ok, msg = super().update_payment_amount(payment_id, new_amount)
        if ok:
            clear_payment_cache()
        return ok, msg

    def delete_payment_schedule(self, payment_id: int) -> Tuple[bool, str]:
        ok, msg = super().delete_payment_schedule(payment_id)
        if ok:
            clear_payment_cache()
        return ok, msg


__all__ = [
    "PaymentService",
    "PaymentScheduleService",
    "PaymentCollectionService",
    "PaymentReminderService",
    "clear_payment_cache",
]
