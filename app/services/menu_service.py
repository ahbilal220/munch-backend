from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models.models import MenuItem, Category, Review, ItemAvailability
from app.schemas.schemas import MenuItemCreate, MenuItemUpdate, CategoryCreate


# ── Categories ────────────────────────────────────────────────────────────────

async def get_categories(db: AsyncSession) -> List[Category]:
    result = await db.execute(
        select(Category).where(Category.is_active == True).order_by(Category.display_order)
    )
    return result.scalars().all()


async def create_category(db: AsyncSession, data: CategoryCreate) -> Category:
    cat = Category(**data.model_dump())
    db.add(cat)
    await db.flush()
    await db.refresh(cat)
    return cat


# ── Menu Items ────────────────────────────────────────────────────────────────

async def get_menu_items(
    db: AsyncSession,
    category_id: Optional[int] = None,
    search: Optional[str] = None,
    available_only: bool = True,
) -> List[MenuItem]:
    """
    FR-02: Display all items with price & availability.
    FR-03: Search by item name.
    FR-20: Real-time In-Stock/Sold-Out status.
    """
    query = (
        select(MenuItem)
        .options(selectinload(MenuItem.category))
        .where(MenuItem.is_active == True)
    )
    if available_only:
        query = query.where(MenuItem.availability == ItemAvailability.in_stock)
    if category_id:
        query = query.where(MenuItem.category_id == category_id)
    if search:
        query = query.where(MenuItem.name.ilike(f"%{search}%"))

    result = await db.execute(query.order_by(MenuItem.name))
    items = result.scalars().all()

    # Attach average ratings
    for item in items:
        avg = await get_item_average_rating(db, item.id)
        item.average_rating = avg

    return items


async def get_menu_item_by_id(db: AsyncSession, item_id: int) -> Optional[MenuItem]:
    result = await db.execute(
        select(MenuItem)
        .options(selectinload(MenuItem.category))
        .where(MenuItem.id == item_id)
    )
    return result.scalar_one_or_none()


async def create_menu_item(db: AsyncSession, data: MenuItemCreate) -> MenuItem:
    item = MenuItem(**data.model_dump())
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return item


async def update_menu_item(db: AsyncSession, item: MenuItem, data: MenuItemUpdate) -> MenuItem:
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(item, field, value)
    await db.flush()
    await db.refresh(item)
    return item


async def toggle_item_availability(
    db: AsyncSession, item: MenuItem, availability: ItemAvailability
) -> MenuItem:
    """FR-24: Quick-Toggle for instant item availability (5.2.2)."""
    item.availability = availability
    await db.flush()
    await db.refresh(item)
    return item


async def delete_menu_item(db: AsyncSession, item: MenuItem) -> None:
    item.is_active = False
    await db.flush()


async def get_low_stock_items(db: AsyncSession) -> List[MenuItem]:
    """FR-15: Low-stock alerts for canteen staff."""
    result = await db.execute(
        select(MenuItem).where(
            MenuItem.is_active == True,
            MenuItem.stock_quantity <= MenuItem.low_stock_threshold,
        )
    )
    return result.scalars().all()


async def adjust_stock(
    db: AsyncSession, item: MenuItem, delta: int
) -> MenuItem:
    """Decrease or increase stock; auto-toggle sold out."""
    from app.models.models import InventoryLog

    item.stock_quantity = max(0, item.stock_quantity + delta)
    if item.stock_quantity == 0:
        item.availability = ItemAvailability.sold_out
    elif item.availability == ItemAvailability.sold_out and item.stock_quantity > 0:
        item.availability = ItemAvailability.in_stock
    await db.flush()
    return item


# ── Reviews ───────────────────────────────────────────────────────────────────

async def get_item_average_rating(db: AsyncSession, item_id: int) -> Optional[float]:
    result = await db.execute(
        select(func.avg(Review.rating)).where(Review.menu_item_id == item_id)
    )
    val = result.scalar()
    return round(float(val), 1) if val else None


async def get_item_reviews(db: AsyncSession, item_id: int) -> List[Review]:
    result = await db.execute(
        select(Review)
        .where(Review.menu_item_id == item_id)
        .order_by(Review.created_at.desc())
    )
    return result.scalars().all()


async def create_review(
    db: AsyncSession, user_id: int, item_id: int, rating: int, comment: Optional[str]
) -> Review:
    review = Review(
        user_id=user_id,
        menu_item_id=item_id,
        rating=rating,
        comment=comment,
    )
    db.add(review)
    await db.flush()
    await db.refresh(review)
    return review
