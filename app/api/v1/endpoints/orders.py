from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import get_current_user, get_current_admin, get_kitchen_or_admin
from app.models.models import OrderStatus
from app.schemas.schemas import (
    CartItemAdd, CartItemOut, CartItemUpdate, CartOut,
    OrderCreate, OrderOut, OrderStatusUpdate, OrderSummary,
)
from app.services import order_service

router = APIRouter(tags=["orders"])


# ── Cart ──────────────────────────────────────────────────────────────────────

@router.get("/cart", response_model=CartOut)
async def get_cart(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """FR-12: View cart with total price."""
    items = await order_service.get_cart(db, current_user.id)
    cart_items = [CartItemOut.from_orm_with_subtotal(i) for i in items]
    total = sum(i.subtotal for i in cart_items)
    return CartOut(items=cart_items, total=round(total, 2), item_count=len(cart_items))


@router.post("/cart", response_model=CartOut, status_code=201)
async def add_to_cart(
    data: CartItemAdd,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """FR-12: Add item to cart."""
    await order_service.add_to_cart(db, current_user.id, data.menu_item_id, data.quantity)
    items = await order_service.get_cart(db, current_user.id)
    cart_items = [CartItemOut.from_orm_with_subtotal(i) for i in items]
    total = sum(i.subtotal for i in cart_items)
    return CartOut(items=cart_items, total=round(total, 2), item_count=len(cart_items))


@router.patch("/cart/{cart_item_id}", response_model=CartOut)
async def update_cart_item(
    cart_item_id: int,
    data: CartItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """FR-12: Update cart item quantity."""
    await order_service.update_cart_item(db, current_user.id, cart_item_id, data.quantity)
    items = await order_service.get_cart(db, current_user.id)
    cart_items = [CartItemOut.from_orm_with_subtotal(i) for i in items]
    total = sum(i.subtotal for i in cart_items)
    return CartOut(items=cart_items, total=round(total, 2), item_count=len(cart_items))


@router.delete("/cart/{cart_item_id}", status_code=204)
async def remove_from_cart(
    cart_item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """FR-12: Remove item from cart."""
    await order_service.remove_from_cart(db, current_user.id, cart_item_id)


@router.delete("/cart", status_code=204)
async def clear_cart(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await order_service.clear_cart(db, current_user.id)


# ── Orders ────────────────────────────────────────────────────────────────────

@router.post("/orders", response_model=OrderOut, status_code=201)
async def place_order(
    data: OrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    FR-04 / FR-22: Place order from cart.
    FR-19: Generates unique Order Token.
    NFR-07: Row-level lock prevents race conditions.
    """
    return await order_service.place_order(db, current_user.id, data.notes)


@router.get("/orders", response_model=List[OrderOut])
async def my_orders(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """FR-06: Order history for student."""
    return await order_service.get_orders_for_user(db, current_user.id)


@router.get("/orders/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """FR-05: Real-time order status (Received/Preparing/Ready)."""
    order = await order_service.get_order_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.user_id != current_user.id and current_user.role == "student":
        raise HTTPException(status_code=403, detail="Not your order")
    return order


@router.post("/orders/{order_id}/cancel", response_model=OrderOut)
async def cancel_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """FR-17: Cancel order only if kitchen hasn't started."""
    order = await order_service.get_order_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return await order_service.cancel_order(db, order, current_user.id)


# ── Admin / Kitchen ───────────────────────────────────────────────────────────

@router.get("/admin/orders", response_model=List[OrderOut])
async def admin_all_orders(
    status_filter: Optional[OrderStatus] = Query(None, alias="status"),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_admin),
):
    """FR-10 / FR-25: Admin — view and manage all orders."""
    return await order_service.get_all_orders(db, status_filter, limit)


@router.get("/admin/queue", response_model=List[OrderOut])
async def kitchen_queue(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_kitchen_or_admin),
):
    """FR-18: Live kitchen order queue (Received + Preparing)."""
    return await order_service.get_active_queue(db)


@router.patch("/admin/orders/{order_id}/status", response_model=OrderOut)
async def update_order_status(
    order_id: int,
    data: OrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_kitchen_or_admin),
):
    """FR-05 / FR-18: Kitchen marks order Received → Preparing → Ready → Completed."""
    order = await order_service.get_order_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return await order_service.update_order_status(db, order, data.status, current_user.id)
