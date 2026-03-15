"""
Services package helpers.

Keep package imports lightweight so pure utility modules can be tested
without pulling in every database dependency.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


def _optional_import(module_name: str, attr_name: str) -> Any:
    try:
        module = import_module(module_name)
        return getattr(module, attr_name)
    except Exception:
        return None


logger = _optional_import("services.logger", "logger")
BaseDBService = _optional_import("services.base_db", "BaseDBService")
TenantService = _optional_import("services.tenant_service", "TenantService")
PaymentService = _optional_import("services.payment_service", "PaymentService")
PaymentScheduleService = _optional_import(
    "services.payment_service",
    "PaymentScheduleService",
)
PaymentCollectionService = _optional_import(
    "services.payment_service",
    "PaymentCollectionService",
)
PaymentReminderService = _optional_import(
    "services.payment_service",
    "PaymentReminderService",
)
ElectricityService = _optional_import("services.electricity_service", "ElectricityService")
ExpenseService = _optional_import("services.expense_service", "ExpenseService")
SystemService = _optional_import("services.system_service", "SystemService")
ElectricityCalculator = _optional_import(
    "services.electricity_calculator",
    "ElectricityCalculator",
)

__all__ = [
    "logger",
    "BaseDBService",
    "TenantService",
    "PaymentService",
    "PaymentScheduleService",
    "PaymentCollectionService",
    "PaymentReminderService",
    "ElectricityService",
    "ExpenseService",
    "SystemService",
    "ElectricityCalculator",
]
