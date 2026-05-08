"""
Seed script: python seed.py
Populates DB with categories, menu items, and an admin user.
"""

import asyncio
from app.db.session import AsyncSessionLocal, engine, Base
from app.models.models import User, Category, MenuItem, UserRole, ItemAvailability
from app.core.security import hash_password


CATEGORIES = [
    {"name": "Breakfast", "description": "Morning items", "display_order": 1},
    {"name": "Main Course", "description": "Lunch & dinner", "display_order": 2},
    {"name": "Snacks", "description": "Light bites", "display_order": 3},
    {"name": "Beverages", "description": "Hot & cold drinks", "display_order": 4},
]

MENU_ITEMS = [
    # Breakfast
    {"name": "Paratha with Achar", "description": "Crispy layered flatbread with pickle", "price": 80, "category": "Breakfast", "stock_quantity": 50},
    {"name": "Omelette Sandwich", "description": "Egg omelette in toasted bread", "price": 120, "category": "Breakfast", "stock_quantity": 30},
    {"name": "Halwa Puri", "description": "Sweet semolina with fried bread", "price": 150, "category": "Breakfast", "stock_quantity": 20},
    # Main Course
    {"name": "Chicken Biryani", "description": "Fragrant rice with spiced chicken", "price": 250, "category": "Main Course", "stock_quantity": 40, "low_stock_threshold": 5},
    {"name": "Daal Chawal", "description": "Lentil curry with steamed rice", "price": 180, "category": "Main Course", "stock_quantity": 60},
    {"name": "Chicken Karahi", "description": "Spiced chicken stir-fry", "price": 320, "category": "Main Course", "stock_quantity": 15, "low_stock_threshold": 5},
    {"name": "Vegetable Pulao", "description": "Fragrant vegetable rice", "price": 160, "category": "Main Course", "stock_quantity": 25},
    # Snacks
    {"name": "Samosa (2 pcs)", "description": "Crispy fried pastry with spiced filling", "price": 60, "category": "Snacks", "stock_quantity": 100},
    {"name": "French Fries", "description": "Golden crispy fries with ketchup", "price": 100, "category": "Snacks", "stock_quantity": 80},
    {"name": "Club Sandwich", "description": "Triple-decker toasted sandwich", "price": 200, "category": "Snacks", "stock_quantity": 20},
    {"name": "Bread Pakora", "description": "Spiced battered bread, fried golden", "price": 50, "category": "Snacks", "stock_quantity": 60},
    # Beverages
    {"name": "Chai (Tea)", "description": "Desi milk tea", "price": 40, "category": "Beverages", "stock_quantity": 200},
    {"name": "Cold Coffee", "description": "Chilled blended coffee with milk", "price": 150, "category": "Beverages", "stock_quantity": 50},
    {"name": "Lassi", "description": "Chilled yoghurt drink (sweet or salty)", "price": 120, "category": "Beverages", "stock_quantity": 40},
    {"name": "Fresh Juice", "description": "Seasonal fresh-squeezed juice", "price": 130, "category": "Beverages", "stock_quantity": 30, "low_stock_threshold": 5},
]


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        # Admin user
        from sqlalchemy import select
        existing_admin = await db.execute(select(User).where(User.email == "admin@university.edu"))
        if not existing_admin.scalar_one_or_none():
            admin = User(
                email="admin@university.edu",
                hashed_password=hash_password("Admin@1234"),
                full_name="Canteen Admin",
                role=UserRole.admin,
            )
            kitchen = User(
                email="kitchen@university.edu",
                hashed_password=hash_password("Kitchen@1234"),
                full_name="Kitchen Staff",
                role=UserRole.kitchen_staff,
            )
            student = User(
                email="student@university.edu",
                hashed_password=hash_password("Student@1234"),
                full_name="Test Student",
                role=UserRole.student,
            )
            db.add_all([admin, kitchen, student])
            await db.flush()
            print("✓ Users created")

        # Categories
        cat_map = {}
        for cat_data in CATEGORIES:
            existing = await db.execute(select(Category).where(Category.name == cat_data["name"]))
            cat = existing.scalar_one_or_none()
            if not cat:
                cat = Category(**cat_data)
                db.add(cat)
                await db.flush()
            cat_map[cat.name] = cat.id

        print(f"✓ {len(CATEGORIES)} categories seeded")

        # Menu Items
        count = 0
        for item_data in MENU_ITEMS:
            cat_name = item_data.pop("category")
            cat_id = cat_map.get(cat_name)
            existing = await db.execute(select(MenuItem).where(MenuItem.name == item_data["name"]))
            if not existing.scalar_one_or_none():
                item = MenuItem(
                    category_id=cat_id,
                    low_stock_threshold=item_data.pop("low_stock_threshold", 10),
                    **item_data,
                )
                db.add(item)
                count += 1

        await db.commit()
        print(f"✓ {count} menu items seeded")
        print("\n🍽️  Munch DB seeded successfully!")
        print("   Admin:   admin@university.edu / Admin@1234")
        print("   Kitchen: kitchen@university.edu / Kitchen@1234")
        print("   Student: student@university.edu / Student@1234")


if __name__ == "__main__":
    asyncio.run(seed())
