"""
Order Service
Handles cart → order placement with PostgreSQL row-level locking (NFR-07)
to prevent two students from ordering the last item simultaneously.
"""

from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    CartItem, MenuItem, Order, OrderItem, OrderStatus,
    ItemAvailability, Notification, InventoryLog,
)
from app.services.notification_service import create_notification


# ── Cart ──────────────────────────────────────────────────────────────────────

async def get_cart(db: AsyncSession, user_id: int) -> List[CartItem]:
    result = await db.execute(
        select(CartItem)
        .options(selectinload(CartItem.menu_item).selectinload(MenuItem.category))
        .where(CartItem.user_id == user_id)
    )
    return result.scalars().all()


async def add_to_cart(db: AsyncSession, user_id: int, menu_item_id: int, quantity: int) -> CartItem:
    # Check item exists and is in stock
    item_result = await db.execute(
        select(MenuItem).where(MenuItem.id == menu_item_id, MenuItem.is_active == True)
    )
    item = item_result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Menu item not found")
    if item.availability == ItemAvailability.sold_out:
        raise HTTPException(status_code=400, detail="Item is sold out")

    # Upsert cart item
    existing_result = await db.execute(
        select(CartItem).where(
            CartItem.user_id == user_id, CartItem.menu_item_id == menu_item_id
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.quantity += quantity
        await db.flush()
        await db.refresh(existing)
        return existing
    else:
        cart_item = CartItem(user_id=user_id, menu_item_id=menu_item_id, quantity=quantity)
        db.add(cart_item)
        await db.flush()
        await db.refresh(cart_item)
        return cart_item


async def update_cart_item(db: AsyncSession, user_id: int, cart_item_id: int, quantity: int) -> CartItem:
    result = await db.execute(
        select(CartItem).where(CartItem.id == cart_item_id, CartItem.user_id == user_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    item.quantity = quantity
    await db.flush()
    await db.refresh(item)
    return item


async def remove_from_cart(db: AsyncSession, user_id: int, cart_item_id: int) -> None:
    result = await db.execute(
        select(CartItem).where(CartItem.id == cart_item_id, CartItem.user_id == user_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    await db.delete(item)
    await db.flush()


async def clear_cart(db: AsyncSession, user_id: int) -> None:
    result = await db.execute(select(CartItem).where(CartItem.user_id == user_id))
    items = result.scalars().all()
    for item in items:
        await db.delete(item)
    await db.flush()


# ── Order Placement ───────────────────────────────────────────────────────────

async def place_order(db: AsyncSession, user_id: int, notes: Optional[str] = None) -> Order:
    """
    FR-04 / FR-22: Place order from cart.
    NFR-07: PostgreSQL FOR UPDATE SKIP LOCKED prevents race conditions.
    """
    cart_result = await db.execute(
        select(CartItem)
        .options(selectinload(CartItem.menu_item))
        .where(CartItem.user_id == user_id)
    )
    cart_items = cart_result.scalars().all()

    if not cart_items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    order_items_data = []
    total_amount = 0.0

    for cart_item in cart_items:
        # Row-level lock — prevents concurrent depletion of the same stock (NFR-07)
        locked_result = await db.execute(
            select(MenuItem)
            .where(MenuItem.id == cart_item.menu_item_id)
            .with_for_update(skip_locked=False)  # Block until lock available
        )
        item = locked_result.scalar_one_or_none()

        if not item or not item.is_active:
            raise HTTPException(
                status_code=400, detail=f"'{cart_item.menu_item.name}' is no longer available"
            )
        if item.availability == ItemAvailability.sold_out:
            raise HTTPException(
                status_code=400, detail=f"'{item.name}' is sold out"
            )
        if item.stock_quantity < cart_item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Only {item.stock_quantity} of '{item.name}' remaining",
            )

        # Deduct stock
        item.stock_quantity -= cart_item.quantity
        if item.stock_quantity == 0:
            item.availability = ItemAvailability.sold_out

        order_items_data.append({
            "menu_item_id": item.id,
            "item_name": item.name,
            "item_price": item.price,
            "quantity": cart_item.quantity,
        })
        total_amount += item.price * cart_item.quantity

        # Log inventory change
        log = InventoryLog(
            menu_item_id=item.id,
            changed_by_id=user_id,
            delta=-cart_item.quantity,
            reason=f"Order by user {user_id}",
        )
        db.add(log)

    # Create order
    order = Order(
        user_id=user_id,
        status=OrderStatus.received,
        total_amount=round(total_amount, 2),
        notes=notes,
    )
    db.add(order)
    await db.flush()  # Get order.id before adding items

    for item_data in order_items_data:
        order_item = OrderItem(order_id=order.id, **item_data)
        db.add(order_item)

    # Clear cart
    for cart_item in cart_items:
        await db.delete(cart_item)

    await db.flush()
    await db.refresh(order)

    # Notify student
    await create_notification(
        db,
        user_id=user_id,
        order_id=order.id,
        message=f"Order #{order.order_token} received! We're preparing your food.",
    )

    return order


# ── Order Retrieval ───────────────────────────────────────────────────────────

async def get_order_by_id(db: AsyncSession, order_id: int) -> Optional[Order]:
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id)
    )
    return result.scalar_one_or_none()


async def get_orders_for_user(db: AsyncSession, user_id: int) -> List[Order]:
    """FR-06: Order history."""
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.user_id == user_id)
        .order_by(Order.created_at.desc())
    )
    return result.scalars().all()


async def get_all_orders(
    db: AsyncSession,
    status_filter: Optional[OrderStatus] = None,
    limit: int = 100,
) -> List[Order]:
    """FR-10: Admin — view all orders / live queue."""
    query = (
        select(Order)
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc())
        .limit(limit)
    )
    if status_filter:
        query = query.where(Order.status == status_filter)
    result = await db.execute(query)
    return result.scalars().all()


async def get_active_queue(db: AsyncSession) -> List[Order]:
    """FR-18: Kitchen order queue (received + preparing)."""
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.status.in_([OrderStatus.received, OrderStatus.preparing]))
        .order_by(Order.created_at.asc())
    )
    return result.scalars().all()


async def update_order_status(
    db: AsyncSession, order: Order, new_status: OrderStatus, actor_user_id: int
) -> Order:
    """FR-05: Update real-time status. FR-13: Notify on 'ready'."""
    order.status = new_status
    await db.flush()

    if new_status == OrderStatus.ready and order.user_id:
        await create_notification(
            db,
            user_id=order.user_id,
            order_id=order.id,
            message=f"🍽️ Your order #{order.order_token} is READY for pickup!",
        )
    elif new_status == OrderStatus.preparing and order.user_id:
        await create_notification(
            db,
            user_id=order.user_id,
            order_id=order.id,
            message=f"👨‍🍳 Your order #{order.order_token} is being prepared.",
        )

    await db.refresh(order)
    return order


async def cancel_order(db: AsyncSession, order: Order, user_id: int) -> Order:
    """
    FR-17: User cancels order only if kitchen hasn't started yet.
    Restores inventory on cancel.
    """
    if order.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not your order")
    if order.status != OrderStatus.received:
        raise HTTPException(
            status_code=400,
            detail="Order cannot be cancelled — kitchen has already started",
        )

    # Restore stock
    for oi in order.items:
        if oi.menu_item_id:
            item_result = await db.execute(
                select(MenuItem).where(MenuItem.id == oi.menu_item_id)
            )
            item = item_result.scalar_one_or_none()
            if item:
                item.stock_quantity += oi.quantity
                if item.availability == ItemAvailability.sold_out and item.stock_quantity > 0:
                    item.availability = ItemAvailability.in_stock
                log = InventoryLog(
                    menu_item_id=item.id,
                    changed_by_id=user_id,
                    delta=oi.quantity,
                    reason=f"Order #{order.order_token} cancelled",
                )
                db.add(log)

    order.status = OrderStatus.cancelled
    await db.flush()
    await db.refresh(order)
    return order
