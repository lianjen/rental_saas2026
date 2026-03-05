"""
房客 Pydantic Schema - v2.2 (pricing + v2 config)
✅ 欄位名稱對應 DB 實際欄位（rent / deposit / lease_start / lease_end）
✅ 新增 base_rent / payment_cycle / annual_discount_months
✅ rent = 折扣後月租（由 utils.rent_pricing 統一計算）
✅ 移除 rent_due_day（DB 已不存在此欄）
✅ [FIX] id_number regex: \\d → \d（raw string 修正）
✅ [FIX] status 改用 Literal（v2 建議）
✅ [FIX] rent 改為 Optional[float]，避免 default 0 觸發 gt 驗證失敗
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from utils.rent_pricing import PaymentCycle, calc_effective_monthly_rent


class TenantBase(BaseModel):
    """房客基本資料（對應資料庫欄位）"""

    name: str = Field(..., min_length=2, max_length=100, description="房客姓名", examples=["王小明"])
    room_number: str = Field(..., min_length=1, max_length=20, description="房號", examples=["4C"])
    phone: Optional[str] = Field(None, description="電話", examples=["0912-345-678"])
    email: Optional[EmailStr] = Field(None, description="Email", examples=["tenant@example.com"])
    id_number: Optional[str] = Field(None, min_length=10, max_length=50, description="身分證字號", examples=["A123456789"])

    # ── 計價欄位（DB 欄位）───────────────────────────────
    base_rent: float = Field(..., gt=0, description="原月租（未折扣）", examples=[5000.0])
    payment_cycle: PaymentCycle = Field(default="月繳", description="繳費週期", examples=["月繳"])
    annual_discount_months: int = Field(default=0, ge=0, le=12, description="年繳折扣月數（0=不折扣）", examples=[1])

    # rent = 折扣後月租（DB 欄位 rent，用於列表顯示/統計）
    # Optional + default None：避免欄位驗證先吃到 default 0 而失敗
    rent: Optional[float] = Field(default=None, gt=0, description="折扣後月租（系統自動計算）", examples=[4583.33])

    deposit: float = Field(default=0, ge=0, description="押金", examples=[12000.0])
    lease_start: date = Field(..., description="入住日期", examples=["2025-06-01"])
    lease_end: Optional[date] = Field(None, description="退租日期", examples=["2026-06-01"])
    status: Literal["active", "inactive"] = Field(default="active", description="狀態", examples=["active"])
    notes: Optional[str] = Field(None, max_length=1000, description="備註", examples=["優良房客"])

    @model_validator(mode="after")
    def compute_rent(self) -> "TenantBase":
        """
        非年繳時，強制 annual_discount_months = 0。
        rent 統一由 base_rent/payment_cycle/discount 計算。
        """
        if self.payment_cycle != "年繳":
            self.annual_discount_months = 0

        self.rent = calc_effective_monthly_rent(
            base_rent=self.base_rent,
            payment_cycle=self.payment_cycle,
            annual_discount_months=self.annual_discount_months,
            round_to=2,
        )
        return self

    @field_validator("lease_end")
    @classmethod
    def validate_lease_end(cls, v, info):
        """退租日期必須晚於入住日期"""
        if v and info.data.get("lease_start"):
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
            # ✅ FIX: raw string 內應用 \d（\\d 會匹配字面 \d）
            if not re.match(r"^[A-Z][12]\d{8}$", v):
                raise ValueError("身分證字號格式錯誤（應為 1 個英文字母 + 9 個數字）")
        return v


class TenantCreate(TenantBase):
    """新增房客"""
    pass


class TenantUpdate(BaseModel):
    """
    更新房客（所有欄位可選，只更新有傳入的欄位）
    注意：更新時 rent 建議由 service 用「既有資料 + 更新欄位」重新計算後寫入 DB
    """
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    room_number: Optional[str] = Field(None, min_length=1, max_length=20)
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    id_number: Optional[str] = Field(None, min_length=10, max_length=50)

    base_rent: Optional[float] = Field(None, gt=0)
    payment_cycle: Optional[PaymentCycle] = None
    annual_discount_months: Optional[int] = Field(None, ge=0, le=12)

    # 兼容：允許接收 rent（例如前端傳入預覽值），但建議最後仍由 service 覆蓋計算
    rent: Optional[float] = Field(None, gt=0)

    deposit: Optional[float] = Field(None, ge=0)
    lease_start: Optional[date] = None
    lease_end: Optional[date] = None
    status: Optional[Literal["active", "inactive"]] = None
    notes: Optional[str] = Field(None, max_length=1000)

    @field_validator("lease_end")
    @classmethod
    def validate_lease_end(cls, v, info):
        if v and info.data.get("lease_start"):
            if v < info.data["lease_start"]:
                raise ValueError("退租日期不能早於入住日期")
        return v


class TenantResponse(TenantBase):
    """房客回應（含 ID 和時間戳）"""
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TenantListItem(BaseModel):
    """房客列表項目（精簡版）"""
    id: str
    name: str
    room_number: str

    # 顯示/統計用：rent = 折扣後月租
    rent: float

    # 讓列表也能看得到「原月租 / 週期 / 折扣」
    base_rent: Optional[float] = None
    payment_cycle: Optional[str] = None
    annual_discount_months: Optional[int] = None

    status: str
    phone: Optional[str] = None
    lease_start: date

    model_config = ConfigDict(from_attributes=True)


class TenantSearchResult(BaseModel):
    """搜尋結果"""
    total: int
    items: list[TenantListItem]
