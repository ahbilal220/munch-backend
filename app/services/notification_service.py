from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Notification


async def create_notification(
    db: AsyncSession, user_id: int, message: str, order_id: Optional[int] = None
) -> Notification:
    notif = Notification(user_id=user_id, order_id=order_id, message=message)
    db.add(notif)
    await db.flush()
    return notif


async def get_user_notifications(
    db: AsyncSession, user_id: int, unread_only: bool = False
) -> List[Notification]:
    query = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        query = query.where(Notification.is_read == False)
    query = query.order_by(Notification.created_at.desc()).limit(50)
    result = await db.execute(query)
    return result.scalars().all()


async def mark_all_read(db: AsyncSession, user_id: int) -> int:
    result = await db.execute(
        select(Notification).where(
            Notification.user_id == user_id, Notification.is_read == False
        )
    )
    notifs = result.scalars().all()
    for n in notifs:
        n.is_read = True
    await db.flush()
    return len(notifs)
