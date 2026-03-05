"""
房客 Pydantic Schema - v2.0 DB 欄位對齊版
✅ 欄位名稱完全對應 DB 實際欄位
   rent_amount   → rent
   deposit_amount → deposit
   move_in_date  → lease_start
   move_out_date → lease_end
✅ 移除 rent_due_day（DB 已不存在此欄）
✅ TenantCreate / TenantUpdate / TenantResponse 三者一致
"""
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from typing import Optional
from datetime import date, datetime
import re


class TenantBase(BaseModel):
    """房客基本資料（對應資料庫欄位）"""
    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="房客姓名",
        examples=["王小明"]
    )
    room_number: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="房號",
        examples=["4C"]
    )
    phone: Optional[str] = Field(
        None,
        description="電話",
        examples=["0912-345-678"]
    )
    email: Optional[EmailStr] = Field(
        None,
        description="Email",
        examples=["tenant@example.com"]
    )
    id_number: Optional[str] = Field(
        None,
        min_length=10,
        max_length=50,
        description="身分證字號",
        examples=["A123456789"]
    )
    # ✅ DB 實際欄位名：rent（非 rent_amount）
    rent: float = Field(
        ...,
        gt=0,
        description="月租金",
        examples=[6000.0]
    )
    # ✅ DB 實際欄位名：deposit（非 deposit_amount）
    deposit: float = Field(
        default=0,
        ge=0,
        description="押金",
        examples=[12000.0]
    )
    # ✅ DB 實際欄位名：lease_start（非 move_in_date）
    lease_start: date = Field(
        ...,
        description="入住日期",
        examples=["2025-06-01"]
    )
    # ✅ DB 實際欄位名：lease_end（非 move_out_date）
    lease_end: Optional[date] = Field(
        None,
        description="退租日期",
        examples=["2026-06-01"]
    )
    status: str = Field(
        default="active",
        pattern="^(active|inactive)$",
        description="狀態",
        examples=["active"]
    )
    notes: Optional[str] = Field(
        None,
        max_length=1000,
        description="備註",
        examples=["優良房客"]
    )

    @field_validator('lease_end')
    @classmethod
    def validate_lease_end(cls, v, info):
        """確保退租日期晚於入住日期"""
        if v and 'lease_start' in info.data and info.data['lease_start']:
            if v < info.data['lease_start']:
                raise ValueError('退租日期不能早於入住日期')
        return v

    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v):
        """驗證電話格式（台灣手機或市話）"""
        if v:
            digits = ''.join(filter(str.isdigit, v))
            if len(digits) < 7:
                raise ValueError('電話號碼長度不足')
            if digits.startswith('09') and len(digits) != 10:
                raise ValueError('手機號碼應為 10 碼')
        return v

    @field_validator('id_number')
    @classmethod
    def validate_id_number(cls, v):
        """驗證台灣身分證字號格式"""
        if v:
            v = v.strip().upper()
            if not re.match(r'^[A-Z][12]\d{8}$', v):
                raise ValueError('身分證字號格式錯誤（應為 1 個英文字母 + 9 個數字）')
        return v


class TenantCreate(TenantBase):
    """新增房客"""
    pass


class TenantUpdate(BaseModel):
    """更新房客（所有欄位可選，只更新有傳入的欄位）"""
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    room_number: Optional[str] = Field(None, min_length=1, max_length=20)
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    id_number: Optional[str] = Field(None, min_length=10, max_length=50)
    # ✅ 對齊 DB 欄位名
    rent: Optional[float] = Field(None, gt=0)
    deposit: Optional[float] = Field(None, ge=0)
    lease_start: Optional[date] = None
    lease_end: Optional[date] = None
    status: Optional[str] = Field(None, pattern="^(active|inactive)$")
    notes: Optional[str] = Field(None, max_length=1000)

    @field_validator('lease_end')
    @classmethod
    def validate_lease_end(cls, v, info):
        if v and 'lease_start' in info.data and info.data['lease_start']:
            if v < info.data['lease_start']:
                raise ValueError('退租日期不能早於入住日期')
        return v


class TenantResponse(TenantBase):
    """房客回應（含 ID 和時間戳）"""
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TenantListItem(BaseModel):
    """房客列表項目（精簡版）"""
    id: str
    name: str
    room_number: str
    rent: float          # ✅ DB 實際欄位名
    status: str
    phone: Optional[str] = None
    lease_start: date    # ✅ DB 實際欄位名

    class Config:
        from_attributes = True


class TenantSearchResult(BaseModel):
    """搜尋結果"""
    total: int
    items: list[TenantListItem]
