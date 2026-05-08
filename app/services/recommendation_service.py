"""
Munch – Hybrid AI Recommendation Engine (FR-07, FR-08)
Strategy:
  1. "history"    – items frequently ordered by this user (collaborative filter)
  2. "time_of_day" – items popular during the current hour bracket
  3. "top_selling" – fallback for new users (cold start)
  4. "hybrid"     – combined score

NFR-06: All data is queried in aggregate form — no PII is stored in the model.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple
from collections import Counter

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import MenuItem, Order, OrderItem, OrderStatus, ItemAvailability


# ── Time-of-Day Brackets ─────────────────────────────────────────────────────

def _get_time_bracket(hour: int) -> str:
    if 6 <= hour < 11:
        return "breakfast"
    elif 11 <= hour < 15:
        return "lunch"
    elif 15 <= hour < 18:
        return "snack"
    else:
        return "dinner"


# ── History-Based (FR-07) ────────────────────────────────────────────────────

async def _get_user_history_scores(
    db: AsyncSession, user_id: int
) -> dict[int, float]:
    """
    Returns {menu_item_id: normalized_score} based on how often user ordered it.
    NFR-06: We only query aggregate counts, never raw PII.
    """
    result = await db.execute(
        select(OrderItem.menu_item_id, func.sum(OrderItem.quantity).label("total"))
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.user_id == user_id,
            Order.status.in_([OrderStatus.completed, OrderStatus.ready]),
            OrderItem.menu_item_id.isnot(None),
        )
        .group_by(OrderItem.menu_item_id)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(20)
    )
    rows = result.all()
    if not rows:
        return {}
    max_count = max(r.total for r in rows) or 1
    return {r.menu_item_id: r.total / max_count for r in rows}


# ── Time-of-Day Based (FR-08) ────────────────────────────────────────────────

async def _get_time_of_day_scores(
    db: AsyncSession, bracket: str
) -> dict[int, float]:
    """
    Returns items popular during the same time bracket.
    Looks back 30 days of completed orders.
    """
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)

    # Determine hour range for bracket
    bracket_hours = {
        "breakfast": (6, 11),
        "lunch": (11, 15),
        "snack": (15, 18),
        "dinner": (18, 24),
    }
    start_h, end_h = bracket_hours.get(bracket, (0, 24))

    result = await db.execute(
        select(OrderItem.menu_item_id, func.sum(OrderItem.quantity).label("total"))
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.created_at >= thirty_days_ago,
            Order.status.in_([OrderStatus.completed, OrderStatus.ready]),
            func.extract("hour", Order.created_at) >= start_h,
            func.extract("hour", Order.created_at) < end_h,
            OrderItem.menu_item_id.isnot(None),
        )
        .group_by(OrderItem.menu_item_id)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(20)
    )
    rows = result.all()
    if not rows:
        return {}
    max_count = max(r.total for r in rows) or 1
    return {r.menu_item_id: r.total / max_count for r in rows}


# ── Top Selling Fallback ─────────────────────────────────────────────────────

async def _get_top_selling_scores(db: AsyncSession) -> dict[int, float]:
    result = await db.execute(
        select(OrderItem.menu_item_id, func.sum(OrderItem.quantity).label("total"))
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.status.in_([OrderStatus.completed, OrderStatus.ready]),
            OrderItem.menu_item_id.isnot(None),
        )
        .group_by(OrderItem.menu_item_id)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(20)
    )
    rows = result.all()
    if not rows:
        return {}
    max_count = max(r.total for r in rows) or 1
    return {r.menu_item_id: r.total / max_count for r in rows}


# ── Available Items Lookup ────────────────────────────────────────────────────

async def _get_available_items(db: AsyncSession) -> List[MenuItem]:
    result = await db.execute(
        select(MenuItem).where(
            MenuItem.is_active == True,
            MenuItem.availability == ItemAvailability.in_stock,
        )
    )
    return result.scalars().all()


# ── Main Recommendation Function ─────────────────────────────────────────────

async def get_recommendations(
    db: AsyncSession,
    user_id: int,
    limit: int = 5,
) -> Tuple[List[MenuItem], str]:
    """
    Returns (recommended_items, strategy_used).
    Hybrid: weight user history (0.6) + time-of-day (0.4).
    Falls back to top_selling for cold-start users.
    """
    available = await _get_available_items(db)
    if not available:
        return [], "none"

    available_ids = {item.id for item in available}
    available_map = {item.id: item for item in available}

    now = datetime.now(timezone.utc)
    bracket = _get_time_bracket(now.hour)

    history_scores = await _get_user_history_scores(db, user_id)
    time_scores = await _get_time_of_day_scores(db, bracket)

    # Filter to only available items
    history_scores = {k: v for k, v in history_scores.items() if k in available_ids}
    time_scores = {k: v for k, v in time_scores.items() if k in available_ids}

    strategy = "hybrid"

    if history_scores and time_scores:
        # Weighted hybrid
        all_ids = available_ids & (history_scores.keys() | time_scores.keys())
        combined = {}
        for item_id in all_ids:
            h = history_scores.get(item_id, 0)
            t = time_scores.get(item_id, 0)
            combined[item_id] = 0.6 * h + 0.4 * t
    elif history_scores:
        combined = history_scores
        strategy = "history"
    elif time_scores:
        combined = time_scores
        strategy = "time_of_day"
    else:
        # Cold start: top selling
        top_scores = await _get_top_selling_scores(db)
        top_scores = {k: v for k, v in top_scores.items() if k in available_ids}
        if not top_scores:
            # Truly no data — return random available items
            return available[:limit], "top_selling"
        combined = top_scores
        strategy = "top_selling"

    ranked = sorted(combined.items(), key=lambda x: x[1], reverse=True)
    result_ids = [item_id for item_id, _ in ranked[:limit]]
    items = [available_map[i] for i in result_ids if i in available_map]

    # Pad with other available items if needed
    if len(items) < limit:
        existing = {i.id for i in items}
        extras = [a for a in available if a.id not in existing]
        items += extras[: limit - len(items)]

    return items, strategy
