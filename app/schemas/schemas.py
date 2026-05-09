"""
Munch – Pydantic Schemas (Request / Response DTOs)
"""

from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator,computed_field

from app.models.models import ItemAvailability, OrderStatus, UserRole


# ── Shared ────────────────────────────────────────────────────────────────────

class Msg(BaseModel):
    detail: str


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=2)

    @field_validator("email")
    @classmethod
    def must_be_university_email(cls, v: str) -> str:
        from app.core.config import settings
        if not v.lower().endswith(f"@{settings.ALLOWED_EMAIL_DOMAIN}"):
            raise ValueError(f"Email must be a @{settings.ALLOWED_EMAIL_DOMAIN} address")
        return v.lower()


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    refresh_token: str


# ── Users ─────────────────────────────────────────────────────────────────────

class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=8)


# ── Categories ────────────────────────────────────────────────────────────────

class CategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: Optional[str] = None
    display_order: int = 0


class CategoryOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    display_order: int
    is_active: bool

    model_config = {"from_attributes": True}


# ── Menu Items ────────────────────────────────────────────────────────────────

class MenuItemCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: Optional[str] = None
    price: float = Field(gt=0)
    category_id: Optional[int] = None
    stock_quantity: int = Field(default=100, ge=0)
    low_stock_threshold: int = Field(default=10, ge=0)
    image_url: Optional[str] = None


class MenuItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = Field(default=None, gt=0)
    category_id: Optional[int] = None
    stock_quantity: Optional[int] = Field(default=None, ge=0)
    low_stock_threshold: Optional[int] = Field(default=None, ge=0)
    image_url: Optional[str] = None
    is_active: Optional[bool] = None


class MenuItemAvailabilityToggle(BaseModel):
    availability: ItemAvailability


class MenuItemOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    price: float
    category_id: Optional[int]
    category: Optional[CategoryOut]
    availability: ItemAvailability
    stock_quantity: int
    low_stock_threshold: int
    is_low_stock: bool
    image_url: Optional[str]
    is_active: bool
    average_rating: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Cart ──────────────────────────────────────────────────────────────────────

class CartItemAdd(BaseModel):
    menu_item_id: int
    quantity: int = Field(default=1, ge=1)


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1)


class CartItemOut(BaseModel):
    id: int
    menu_item_id: int
    menu_item: MenuItemOut
    quantity: int
    added_at: datetime

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def subtotal(self) -> float:
        return round(self.menu_item.price * self.quantity, 2)


class CartOut(BaseModel):
    items: List[CartItemOut]
    total: float
    item_count: int


# ── Orders ────────────────────────────────────────────────────────────────────

class OrderItemOut(BaseModel):
    id: int
    menu_item_id: Optional[int]
    item_name: str
    item_price: float
    quantity: int

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def subtotal(self) -> float:
        return round(self.item_price * self.quantity, 2)


class OrderCreate(BaseModel):
    notes: Optional[str] = None


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class OrderOut(BaseModel):
    id: int
    order_token: str
    status: OrderStatus
    total_amount: float
    notes: Optional[str]
    items: List[OrderItemOut]
    created_at: datetime
    updated_at: datetime
    user_id: Optional[int]

    model_config = {"from_attributes": True}


class OrderSummary(BaseModel):
    """Lightweight order for queue view (kitchen staff)."""
    id: int
    order_token: str
    status: OrderStatus
    total_amount: float
    item_count: int
    created_at: datetime

    model_config = {"from_attributes": True}
# ── Reviews ───────────────────────────────────────────────────────────────────

class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = None


class ReviewOut(BaseModel):
    id: int
    user_id: int
    menu_item_id: int
    rating: int
    comment: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Notifications ─────────────────────────────────────────────────────────────

class NotificationOut(BaseModel):
    id: int
    order_id: Optional[int]
    message: str
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Inventory ─────────────────────────────────────────────────────────────────

class InventoryAdjust(BaseModel):
    delta: int    # positive = restock, negative = manual reduction
    reason: Optional[str] = None


class InventoryLogOut(BaseModel):
    id: int
    menu_item_id: int
    delta: int
    reason: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── AI Recommendations ────────────────────────────────────────────────────────

class RecommendationOut(BaseModel):
    items: List[MenuItemOut]
    strategy: str   # "history", "time_of_day", "top_selling", "hybrid"
