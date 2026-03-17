"""
支出記錄 Pydantic Schema - Supabase 適配版
✅ 修正 ID 類型（UUID → int）
✅ 移除 user_id（Week 4 之前不需要）
✅ 修正金額類型（int → float）
✅ 修正時間戳類型（str → datetime）
✅ 新增更多驗證規則
"""
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from typing import Optional
from datetime import date, datetime


class ExpenseBase(BaseModel):
    """支出記錄基本資料"""
    category: str = Field(
        ..., 
        min_length=1, 
        max_length=50, 
        description="支出類別",
        examples=["維修費", "水電費", "管理費", "稅金", "保險費"]
    )
    description: str = Field(
        ..., 
        min_length=1, 
        max_length=500, 
        description="支出說明",
        examples=["修理 4C 房間冷氣"]
    )
    amount: float = Field(
        ..., 
        gt=0, 
        description="金額",
        examples=[2500.0]
    )
    expense_date: date = Field(
        ..., 
        description="支出日期",
        examples=["2026-02-08"]
    )
    room_number: Optional[str] = Field(
        None, 
        max_length=20, 
        description="關聯房號（若與特定房間相關）",
        examples=["4C", "A101"]
    )
    receipt_url: Optional[HttpUrl] = Field(
        None, 
        description="收據圖片 URL",
        examples=["https://storage.supabase.co/receipts/abc123.jpg"]
    )
    notes: Optional[str] = Field(
        None,
        max_length=1000,
        description="額外備註",
        examples=["已與房客確認維修時間"]
    )
    
    @field_validator('category')
    @classmethod
    def validate_category(cls, v):
        """驗證類別格式"""
        # 移除前後空白
        v = v.strip()
        
        if not v:
            raise ValueError('類別不可為空')
        
        return v
    
    @field_validator('expense_date')
    @classmethod
    def validate_expense_date(cls, v):
        """驗證支出日期不可為未來日期"""
        if v > date.today():
            raise ValueError('支出日期不可為未來日期')
        
        # 檢查是否過於久遠（超過 5 年）
        years_ago = (date.today() - v).days / 365
        if years_ago > 5:
            raise ValueError('支出日期不可超過 5 年前')
        
        return v
    
    @field_validator('amount')
    @classmethod
    def validate_amount(cls, v):
        """驗證金額範圍"""
        if v > 1_000_000:
            raise ValueError('單筆支出金額不可超過 100 萬')
        
        if v < 0.01:
            raise ValueError('金額不可小於 0.01')
        
        # 四捨五入到小數點後 2 位
        return round(v, 2)


class ExpenseCreate(ExpenseBase):
    """新增支出記錄"""
    pass


class ExpenseUpdate(BaseModel):
    """更新支出記錄（所有欄位可選）"""
    category: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = Field(None, min_length=1, max_length=500)
    amount: Optional[float] = Field(None, gt=0)
    expense_date: Optional[date] = None
    room_number: Optional[str] = Field(None, max_length=20)
    receipt_url: Optional[HttpUrl] = None
    notes: Optional[str] = Field(None, max_length=1000)


class ExpenseResponse(ExpenseBase):
    """支出記錄回應"""
    id: int  # ✅ 修正：使用 int 而非 UUID
    created_at: datetime  # ✅ 修正：使用 datetime 而非 str
    updated_at: datetime  # ✅ 修正：使用 datetime 而非 str
    
    model_config = ConfigDict(from_attributes=True)


class ExpenseListItem(BaseModel):
    """支出列表項目（精簡版）"""
    id: int
    category: str
    description: str
    amount: float
    expense_date: date
    room_number: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


class ExpenseSummary(BaseModel):
    """支出摘要統計"""
    total_expenses: float = Field(description="總支出金額")
    total_count: int = Field(description="支出筆數")
    category_breakdown: dict[str, float] = Field(
        description="各類別支出統計",
        examples=[{"維修費": 5000, "水電費": 3000}]
    )
    average_expense: float = Field(description="平均支出金額")
    
    model_config = ConfigDict(from_attributes=True)


class ExpenseFilter(BaseModel):
    """支出篩選條件"""
    category: Optional[str] = None
    room_number: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    min_amount: Optional[float] = Field(None, ge=0)
    max_amount: Optional[float] = Field(None, ge=0)
    
    @field_validator('end_date')
    @classmethod
    def validate_date_range(cls, v, info):
        """驗證日期範圍"""
        if v and 'start_date' in info.data and info.data['start_date']:
            if v < info.data['start_date']:
                raise ValueError('結束日期不可早於開始日期')
        return v
    
    @field_validator('max_amount')
    @classmethod
    def validate_amount_range(cls, v, info):
        """驗證金額範圍"""
        if v and 'min_amount' in info.data and info.data['min_amount']:
            if v < info.data['min_amount']:
                raise ValueError('最大金額不可小於最小金額')
        return v
