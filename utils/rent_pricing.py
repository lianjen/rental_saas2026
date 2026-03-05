from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Literal, Optional, Tuple


PaymentCycle = Literal["月繳", "半年繳", "年繳"]


def _to_decimal_money(value: float | int | str | Decimal) -> Decimal:
    return Decimal(str(value))


def _round_money(d: Decimal, ndigits: int = 2) -> Decimal:
    q = Decimal("1") if ndigits == 0 else Decimal("1." + ("0" * ndigits))
    return d.quantize(q, rounding=ROUND_HALF_UP)


def normalize_pricing(
    base_rent: float,
    payment_cycle: PaymentCycle,
    annual_discount_months: int = 0,
) -> Tuple[float, PaymentCycle, int]:
    if base_rent is None:
        raise ValueError("base_rent 不可為 None")
    base_rent_f = float(base_rent)
    if base_rent_f <= 0:
        raise ValueError("base_rent 必須 > 0")

    if annual_discount_months is None:
        annual_discount_months = 0
    annual_discount_months_i = int(annual_discount_months)
    if annual_discount_months_i < 0 or annual_discount_months_i > 12:
        raise ValueError("annual_discount_months 必須介於 0~12")

    if payment_cycle != "年繳":
        annual_discount_months_i = 0

    return base_rent_f, payment_cycle, annual_discount_months_i


def calc_effective_monthly_rent(
    base_rent: float,
    payment_cycle: PaymentCycle,
    annual_discount_months: int = 0,
    *,
    round_to: int = 2,
) -> float:
    """
    回傳「折扣後月租」（用於 tenants.rent 顯示/統計）
    - 月繳/半年繳：rent = base_rent
    - 年繳：rent = base_rent * (12 - discount_months) / 12
      ex: 5000, discount=1 => 4583.33
    """
    base_rent_f, payment_cycle, annual_discount_months_i = normalize_pricing(
        base_rent, payment_cycle, annual_discount_months
    )

    b = _to_decimal_money(base_rent_f)

    if payment_cycle == "年繳":
        pay_months = 12 - annual_discount_months_i
        if pay_months <= 0:
            raise ValueError("年繳折扣月數過大，至少需支付 1 個月")
        eff = b * Decimal(pay_months) / Decimal(12)
    else:
        eff = b

    return float(_round_money(eff, round_to))


def calc_cycle_charge_amount(
    base_rent: float,
    payment_cycle: PaymentCycle,
    annual_discount_months: int = 0,
    *,
    round_to: int = 0,
) -> float:
    """
    回傳「本期應收金額」（收款用）
    - 月繳：base_rent * 1
    - 半年繳：base_rent * 6
    - 年繳：base_rent * (12 - discount_months)
    """
    base_rent_f, payment_cycle, annual_discount_months_i = normalize_pricing(
        base_rent, payment_cycle, annual_discount_months
    )
    b = _to_decimal_money(base_rent_f)

    if payment_cycle == "月繳":
        amt = b
    elif payment_cycle == "半年繳":
        amt = b * Decimal(6)
    elif payment_cycle == "年繳":
        pay_months = 12 - annual_discount_months_i
        if pay_months <= 0:
            raise ValueError("年繳折扣月數過大，至少需支付 1 個月")
        amt = b * Decimal(pay_months)
    else:
        raise ValueError(f"未知 payment_cycle: {payment_cycle}")

    return float(_round_money(amt, round_to))


@dataclass(frozen=True)
class PricingPreview:
    base_rent: float
    payment_cycle: PaymentCycle
    annual_discount_months: int
    effective_monthly_rent: float
    cycle_charge_amount: float
    annual_savings: float  # 相對於 base_rent*12


def preview_pricing(
    base_rent: float,
    payment_cycle: PaymentCycle,
    annual_discount_months: int = 0,
) -> PricingPreview:
    base_rent_f, payment_cycle, annual_discount_months_i = normalize_pricing(
        base_rent, payment_cycle, annual_discount_months
    )

    eff = calc_effective_monthly_rent(
        base_rent_f, payment_cycle, annual_discount_months_i, round_to=2
    )
    charge = calc_cycle_charge_amount(
        base_rent_f, payment_cycle, annual_discount_months_i, round_to=0
    )

    base_annual = _to_decimal_money(base_rent_f) * Decimal(12)
    if payment_cycle == "年繳":
        paid_annual = _to_decimal_money(charge)
        savings = base_annual - paid_annual
    else:
        savings = Decimal(0)

    return PricingPreview(
        base_rent=base_rent_f,
        payment_cycle=payment_cycle,
        annual_discount_months=annual_discount_months_i,
        effective_monthly_rent=eff,
        cycle_charge_amount=charge,
        annual_savings=float(_round_money(savings, 0)),
    )
