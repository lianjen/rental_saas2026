"""
Repository package helpers.

Keep package imports lightweight so test code can import individual
repositories without tripping legacy dependencies.
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


BaseRepository = _optional_import("repository.base_repository", "BaseRepository")
TenantRepository = _optional_import("repository.tenant_repository", "TenantRepository")
PaymentRepository = _optional_import("repository.payment_repository", "PaymentRepository")
ElectricityRepository = _optional_import(
    "repository.electricity_repository",
    "ElectricityRepository",
)

__all__ = [
    "BaseRepository",
    "TenantRepository",
    "PaymentRepository",
    "ElectricityRepository",
]
