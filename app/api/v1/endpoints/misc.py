from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.core.security import get_current_user, get_current_admin
from app.models.models import MenuItem, InventoryLog, UserRole
from app.schemas.schemas import (
    InventoryAdjust, InventoryLogOut, NotificationOut, RecommendationOut, MenuItemOut,
)
from app.services import menu_service, notification_service, recommendation_service

router = APIRouter(tags=["misc"])


# ── Inventory (Admin) ─────────────────────────────────────────────────────────

@router.post("/admin/inventory/{item_id}/adjust", response_model=MenuItemOut)
async def adjust_inventory(
    item_id: int,
    data: InventoryAdjust,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin),
):
    """Admin manually adjusts stock (restock or waste reduction)."""
    item = await menu_service.get_menu_item_by_id(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    await menu_service.adjust_stock(db, item, data.delta)

    # Log it
    log = InventoryLog(
        menu_item_id=item.id,
        changed_by_id=current_user.id,
        delta=data.delta,
        reason=data.reason or "Manual adjustment",
    )
    db.add(log)
    await db.flush()
    await db.refresh(item)
    return item


@router.get("/admin/inventory/logs/{item_id}", response_model=List[InventoryLogOut])
async def get_inventory_logs(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_admin),
):
    result = await db.execute(
        select(InventoryLog)
        .where(InventoryLog.menu_item_id == item_id)
        .order_by(InventoryLog.created_at.desc())
        .limit(100)
    )
    return result.scalars().all()


# ── Notifications ─────────────────────────────────────────────────────────────

@router.get("/notifications", response_model=List[NotificationOut])
async def get_notifications(
    unread_only: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """FR-13: Browser notifications for order readiness."""
    return await notification_service.get_user_notifications(db, current_user.id, unread_only)


@router.post("/notifications/mark-read")
async def mark_notifications_read(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    count = await notification_service.mark_all_read(db, current_user.id)
    return {"marked_read": count}


# ── AI Recommendations ────────────────────────────────────────────────────────

@router.get("/recommendations", response_model=RecommendationOut)
async def get_recommendations(
    limit: int = 5,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    FR-07 / FR-08: Hybrid AI recommendations based on user history + time of day.
    NFR-06: Only aggregate data queried — no PII in model.
    """
    items, strategy = await recommendation_service.get_recommendations(
        db, current_user.id, limit
    )
    # Attach ratings
    for item in items:
        item.average_rating = await menu_service.get_item_average_rating(db, item.id)
    return RecommendationOut(items=items, strategy=strategy)
