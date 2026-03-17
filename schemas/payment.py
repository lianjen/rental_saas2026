"""
租金記錄 Pydantic Schema - Supabase 適配版
✅ 完全對應實際資料庫欄位
✅ 移除 UUID，使用 int (serial)
✅ 修正欄位：rent_month → payment_year + payment_month
✅ 移除不存在的欄位：paid_date, notes
"""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional
from datetime import date, datetime


class PaymentBase(BaseModel):
    """租金記錄基本資料（對應資料庫欄位）"""
    room_number: str = Field(
        ..., 
        min_length=1, 
        max_length=20, 
        description="房號",
        examples=["4C"]
    )
    tenant_name: str = Field(
        ..., 
        min_length=2, 
        max_length=100, 
        description="房客姓名",
        examples=["王小明"]
    )
    payment_year: int = Field(
        ..., 
        ge=2000, 
        le=2100, 
        description="租金年份",
        examples=[2026]
    )
    payment_month: int = Field(
        ..., 
        ge=1, 
        le=12, 
        description="租金月份",
        examples=[2]
    )
    amount: float = Field(
        ..., 
        gt=0, 
        description="應繳金額",
        examples=[6000.0]
    )
    due_date: date = Field(
        ..., 
        description="到期日",
        examples=["2026-02-05"]
    )
    payment_method: str = Field(
        default="transfer", 
        max_length=50, 
        description="繳費方式",
        examples=["transfer", "cash", "credit_card"]
    )
    status: str = Field(
        default="unpaid", 
        pattern="^(unpaid|paid|overdue)$",
        description="狀態",
        examples=["unpaid"]
    )
    paid_amount: float = Field(
        default=0, 
        ge=0, 
        description="已繳金額",
        examples=[0.0]
    )
    
    @field_validator('payment_month')
    @classmethod
    def validate_month(cls, v):
        """驗證月份範圍"""
        if not 1 <= v <= 12:
            raise ValueError('月份必須在 1-12 之間')
        return v
    
    @field_validator('payment_year')
    @classmethod
    def validate_year(cls, v):
        """驗證年份合理範圍"""
        if not 2000 <= v <= 2100:
            raise ValueError('年份必須在 2000-2100 之間')
        return v


class PaymentCreate(PaymentBase):
    """新增租金記錄"""
    pass


class PaymentUpdate(BaseModel):
    """更新租金記錄"""
    status: Optional[str] = Field(None, pattern="^(unpaid|paid|overdue)$")
    paid_amount: Optional[float] = Field(None, ge=0)
    payment_method: Optional[str] = Field(None, max_length=50)
    amount: Optional[float] = Field(None, gt=0)
    due_date: Optional[date] = None


class PaymentResponse(PaymentBase):
    """租金記錄回應"""
    id: int  # ✅ 修正：使用 int 而非 UUID
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class PaymentListItem(BaseModel):
    """租金列表項目（精簡版）"""
    id: int
    room_number: str
    tenant_name: str
    payment_year: int
    payment_month: int
    amount: float
    paid_amount: float
    status: str
    due_date: date
    
    model_config = ConfigDict(from_attributes=True)


class PaymentSummary(BaseModel):
    """租金摘要統計"""
    total_expected: float = Field(description="應收總額")
    total_received: float = Field(description="實收總額")
    unpaid_count: int = Field(description="未繳筆數")
    paid_count: int = Field(description="已繳筆數")
    overdue_count: int = Field(description="逾期筆數")
    collection_rate: float = Field(description="收繳率", ge=0, le=1)
    
    model_config = ConfigDict(from_attributes=True)


class PaymentMarkPaid(BaseModel):
    """標記已繳款"""
    paid_amount: float = Field(..., gt=0, description="實際繳款金額")
    
    @field_validator('paid_amount')
    @classmethod
    def validate_paid_amount(cls, v):
        """驗證繳款金額"""
        if v <= 0:
            raise ValueError('繳款金額必須大於 0')
        return v
