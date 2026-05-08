"""
Munch – Database Models
Covers: Users, Menu Items, Categories, Cart, Orders, Order Items,
        Reviews, Notifications, Inventory Logs, Cleaning Checklists
"""

import enum
import secrets
import string
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint, event,
)
from sqlalchemy.orm import relationship

from app.db.session import Base


def utcnow():
    return datetime.now(timezone.utc)


def generate_order_token(length: int = 6) -> str:
    """Generate a human-readable alphanumeric order token (FR-19)."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ── Enums ─────────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    student = "student"
    admin = "admin"
    kitchen_staff = "kitchen_staff"


class OrderStatus(str, enum.Enum):
    received = "received"       # Order placed
    preparing = "preparing"     # Kitchen started
    ready = "ready"             # Ready for pickup
    completed = "completed"     # Picked up
    cancelled = "cancelled"     # Cancelled by user


class ItemAvailability(str, enum.Enum):
    in_stock = "in_stock"
    sold_out = "sold_out"


# ── Users ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.student, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    orders = relationship("Order", back_populates="user", lazy="selectin")
    cart_items = relationship("CartItem", back_populates="user", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="user")


# ── Menu ──────────────────────────────────────────────────────────────────────

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    display_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    items = relationship("MenuItem", back_populates="category")


class MenuItem(Base):
    __tablename__ = "menu_items"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=False)
    image_url = Column(String(500), nullable=True)
    availability = Column(Enum(ItemAvailability), default=ItemAvailability.in_stock, nullable=False)
    stock_quantity = Column(Integer, default=100)
    low_stock_threshold = Column(Integer, default=10)
    is_active = Column(Boolean, default=True)  # Admin can hide items permanently
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    category = relationship("Category", back_populates="items")
    order_items = relationship("OrderItem", back_populates="menu_item")
    cart_items = relationship("CartItem", back_populates="menu_item")
    reviews = relationship("Review", back_populates="menu_item")
    inventory_logs = relationship("InventoryLog", back_populates="menu_item")

    @property
    def is_low_stock(self) -> bool:
        return self.stock_quantity <= self.low_stock_threshold


# ── Cart ──────────────────────────────────────────────────────────────────────

class CartItem(Base):
    """Ephemeral cart per user (FR-12). Cleared after order placement."""
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    added_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("user_id", "menu_item_id", name="uq_user_cart_item"),)

    user = relationship("User", back_populates="cart_items")
    menu_item = relationship("MenuItem", back_populates="cart_items")


# ── Orders ────────────────────────────────────────────────────────────────────

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    order_token = Column(String(10), unique=True, nullable=False, index=True)
    status = Column(Enum(OrderStatus), default=OrderStatus.received, nullable=False)
    total_amount = Column(Float, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan", lazy="selectin")
    notifications = relationship("Notification", back_populates="order")


@event.listens_for(Order, "before_insert")
def set_order_token(mapper, connection, target):
    if not target.order_token:
        target.order_token = generate_order_token()


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id", ondelete="SET NULL"), nullable=True)
    item_name = Column(String(200), nullable=False)   # Snapshot at time of order
    item_price = Column(Float, nullable=False)         # Snapshot at time of order
    quantity = Column(Integer, nullable=False)

    order = relationship("Order", back_populates="items")
    menu_item = relationship("MenuItem", back_populates="order_items")


# ── Notifications ─────────────────────────────────────────────────────────────

class Notification(Base):
    """Browser push notifications for order readiness (FR-13)."""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=True)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    order = relationship("Order", back_populates="notifications")


# ── Reviews ───────────────────────────────────────────────────────────────────

class Review(Base):
    """Student review and rating for food items (FR-16)."""
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id", ondelete="CASCADE"), nullable=False)
    rating = Column(Integer, nullable=False)   # 1–5
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("user_id", "menu_item_id", name="uq_user_item_review"),)

    user = relationship("User", back_populates="reviews")
    menu_item = relationship("MenuItem", back_populates="reviews")


# ── Inventory Log ─────────────────────────────────────────────────────────────

class InventoryLog(Base):
    """Tracks stock changes for audit trail."""
    __tablename__ = "inventory_logs"

    id = Column(Integer, primary_key=True, index=True)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id", ondelete="CASCADE"), nullable=False)
    changed_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    delta = Column(Integer, nullable=False)     # positive = restock, negative = consumed
    reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    menu_item = relationship("MenuItem", back_populates="inventory_logs")
