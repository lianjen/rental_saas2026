"""
房客 Pydantic Schema - v2.1
✅ 欄位名稱對應 DB 實際欄位（rent / deposit / lease_start / lease_end）
✅ 新增 base_rent / payment_cycle / annual_discount_months
✅ rent = 折扣後月租（model_validator 自動計算，不靠 caller 填）
✅ 移除 rent_due_day（DB 已不存在此欄）
✅ [FIX] id_number regex: \\d → \d（raw string 修正）
✅ [FIX] status 改用 Literal（v2 建議）
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


# ── 繳費週期型別（唯一來源） ──────────────────────────────────────
PaymentCycle = Literal["月繳", "半年繳", "年繳"]


# ── 計算折扣後月租（self-contained，不依賴外部 utils） ─────────────
def _calc_effective_rent(
    base_rent: float,
    payment_cycle: PaymentCycle,
    annual_discount_months: int,
) -> float:
    """
    年繳才計算折扣，月繳/半年繳不折扣。
    例：base_rent=5000, 年繳, discount=1  →  5000 × 11/12 ≈ 4583.33
    """
    if payment_cycle == "年繳":
        pay_months = 12 - annual_discount_months
        if pay_months <= 0:
            raise ValueError("年繳折扣月數過大，至少需支付 1 個月")
        return base_rent * pay_months / 12.0
    return float(base_rent)


# ══════════════════════════════════════════════════════════════════
class TenantBase(BaseModel):
    """房客基本資料（對應資料庫欄位）"""

    name: str = Field(..., min_length=2, max_length=100, description="房客姓名", examples=["王小明"])
    room_number: str = Field(..., min_length=1, max_length=20, description="房號", examples=["4C"])
    phone: Optional[str] = Field(None, description="電話", examples=["0912-345-678"])
    email: Optional[EmailStr] = Field(None, description="Email", examples=["tenant@example.com"])
    id_number: Optional[str] = Field(None, min_length=10, max_length=50, description="身分證字號", examples=["A123456789"])

    # ── 計價欄位（DB 實際欄位）──────────────────────────
    base_rent: float = Field(..., gt=0, description="原月租（未折扣）", examples=[5000.0])
    payment_cycle: PaymentCycle = Field(default="月繳", description="繳費週期")
    annual_discount_months: int = Field(default=0, ge=0, le=12, description="年繳折扣月數（0=不折扣）")

    # rent = 折扣後月租，由 model_validator 自動計算寫入 DB
    # 預設 0.0 讓欄位存在，model_validator 立刻覆寫為正確值
    rent: float = Field(default=0.0, ge=0, description="折扣後月租（系統自動計算）", examples=[4583.0])

    deposit: float = Field(default=0, ge=0, description="押金", examples=[12000.0])
    lease_start: date = Field(..., description="入住日期", examples=["2025-06-01"])
    lease_end: Optional[date] = Field(None, description="退租日期", examples=["2026-06-01"])
    status: Literal["active", "inactive"] = Field(default="active", description="狀態")
    notes: Optional[str] = Field(None, max_length=1000, description="備註", examples=["優良房客"])

    # ── model_validator：計算 rent ────────────────────────────────
    @model_validator(mode="after")
    def compute_rent(self) -> "TenantBase":
        """
        非年繳時，強制 annual_discount_months = 0。
        自動用 base_rent + payment_cycle + discount 計算 rent。
        """
        if self.payment_cycle != "年繳":
            self.annual_discount_months = 0

        self.rent = round(
            _calc_effective_rent(self.base_rent, self.payment_cycle, self.annual_discount_months),
            2,
        )
        return self

    # ── field validators ──────────────────────────────────────────
    @field_validator("lease_end")
    @classmethod
    def validate_lease_end(cls, v, info):
        """退租日期必須晚於入住日期"""
        if v and "lease_start" in info.data and info.data["lease_start"]:
            if v < info.data["lease_start"]:
                raise ValueError("退租日期不能早於入住日期")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        """台灣手機或市話格式驗證"""
        if v:
            digits = "".join(filter(str.isdigit, v))
            if len(digits) < 7:
                raise ValueError("電話號碼長度不足")
            if digits.startswith("09") and len(digits) != 10:
                raise ValueError("手機號碼應為 10 碼")
        return v

    @field_validator("id_number")
    @classmethod
    def validate_id_number(cls, v):
        """台灣身分證字號格式：1 英文 + 1~2 + 8 數字"""
        if v:
            v = v.strip().upper()
            # ✅ [FIX] raw string 內 \d 不需雙斜線（\\d 會匹配字面 \ 再接 d）
            if not re.match(r"^[A-Z][12]\d{8}$", v):
                raise ValueError("身分證字號格式錯誤（應為 1 個英文字母 + 9 個數字）")
        return v


# ══════════════════════════════════════════════════════════════════
class TenantCreate(TenantBase):
    """新增房客（繼承 TenantBase，rent 自動計算）"""
    pass


# ══════════════════════════════════════════════════════════════════
class TenantUpdate(BaseModel):
    """
    更新房客（所有欄位可選，只更新有傳入的欄位）。
    rent 不由 caller 填；Service 層拿 base_rent/payment_cycle/discount
    重新計算後寫入 DB。
    """
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    room_number: Optional[str] = Field(None, min_length=1, max_length=20)
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    id_number: Optional[str] = Field(None, min_length=10, max_length=50)

    # ── 計價欄位 ──────────────────────────────────────────────────
    base_rent: Optional[float] = Field(None, gt=0)
    payment_cycle: Optional[PaymentCycle] = None
    annual_discount_months: Optional[int] = Field(None, ge=0, le=12)
    # rent 不開放 caller 直接填，Service 層計算完再寫
    # 但允許接收（避免反向相容問題）
    rent: Optional[float] = Field(None, gt=0)

    deposit: Optional[float] = Field(None, ge=0)
    lease_start: Optional[date] = None
    lease_end: Optional[date] = None
    status: Optional[Literal["active", "inactive"]] = None
    notes: Optional[str] = Field(None, max_length=1000)

    @field_validator("lease_end")
    @classmethod
    def validate_lease_end(cls, v, info):
        if v and "lease_start" in info.data and info.data["lease_start"]:
            if v < info.data["lease_start"]:
                raise ValueError("退租日期不能早於入住日期")
        return v


# ══════════════════════════════════════════════════════════════════
class TenantResponse(TenantBase):
    """房客回應（含 ID 和時間戳）"""
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════════
class TenantListItem(BaseModel):
    """房客列表項目（精簡版）"""
    id: str
    name: str
    room_number: str
    rent: float               # 折扣後月租
    base_rent: Optional[float] = None
    payment_cycle: Optional[str] = None
    status: str
    phone: Optional[str] = None
    lease_start: date

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════════
class TenantSearchResult(BaseModel):
    """搜尋結果"""
    total: int
    items: list[TenantListItem]
