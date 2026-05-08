from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import get_current_user, get_current_admin
from app.schemas.schemas import (
    CategoryCreate, CategoryOut, MenuItemCreate, MenuItemOut,
    MenuItemUpdate, MenuItemAvailabilityToggle, ReviewCreate, ReviewOut,
)
from app.services import menu_service

router = APIRouter(prefix="/menu", tags=["menu"])


# ── Categories ────────────────────────────────────────────────────────────────

@router.get("/categories", response_model=List[CategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)):
    return await menu_service.get_categories(db)


@router.post("/categories", response_model=CategoryOut, status_code=201)
async def create_category(
    data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_admin),
):
    return await menu_service.create_category(db, data)


# ── Menu Items ────────────────────────────────────────────────────────────────

@router.get("/items", response_model=List[MenuItemOut])
async def list_items(
    category_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None, description="Search by item name (FR-03)"),
    available_only: bool = Query(True, description="Show only in-stock items"),
    db: AsyncSession = Depends(get_db),
):
    """FR-02, FR-03, FR-20: Browse menu with real-time In-Stock/Sold-Out status."""
    return await menu_service.get_menu_items(db, category_id, search, available_only)


@router.get("/items/{item_id}", response_model=MenuItemOut)
async def get_item(item_id: int, db: AsyncSession = Depends(get_db)):
    item = await menu_service.get_menu_item_by_id(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item.average_rating = await menu_service.get_item_average_rating(db, item_id)
    return item


@router.post("/items", response_model=MenuItemOut, status_code=201)
async def create_item(
    data: MenuItemCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_admin),
):
    """FR-23: Admin — add menu items."""
    return await menu_service.create_menu_item(db, data)


@router.patch("/items/{item_id}", response_model=MenuItemOut)
async def update_item(
    item_id: int,
    data: MenuItemUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_admin),
):
    """FR-23: Admin — update menu items."""
    item = await menu_service.get_menu_item_by_id(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return await menu_service.update_menu_item(db, item, data)


@router.delete("/items/{item_id}", status_code=204)
async def delete_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_admin),
):
    """FR-23: Admin — delete (soft-delete) menu items."""
    item = await menu_service.get_menu_item_by_id(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    await menu_service.delete_menu_item(db, item)


@router.patch("/items/{item_id}/availability", response_model=MenuItemOut)
async def toggle_availability(
    item_id: int,
    data: MenuItemAvailabilityToggle,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_admin),
):
    """FR-24: Quick-Toggle instant item availability (5.2.2)."""
    item = await menu_service.get_menu_item_by_id(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return await menu_service.toggle_item_availability(db, item, data.availability)


# ── Reviews ───────────────────────────────────────────────────────────────────

@router.get("/items/{item_id}/reviews", response_model=List[ReviewOut])
async def get_reviews(item_id: int, db: AsyncSession = Depends(get_db)):
    return await menu_service.get_item_reviews(db, item_id)


@router.post("/items/{item_id}/reviews", response_model=ReviewOut, status_code=201)
async def post_review(
    item_id: int,
    data: ReviewCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """FR-16: Student review and rating for food items."""
    item = await menu_service.get_menu_item_by_id(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    try:
        return await menu_service.create_review(
            db, current_user.id, item_id, data.rating, data.comment
        )
    except Exception:
        raise HTTPException(status_code=400, detail="You have already reviewed this item")


# ── Low Stock Alerts ──────────────────────────────────────────────────────────

@router.get("/low-stock", response_model=List[MenuItemOut])
async def low_stock_items(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_admin),
):
    """FR-15: Low-stock alerts for canteen staff."""
    return await menu_service.get_low_stock_items(db)
