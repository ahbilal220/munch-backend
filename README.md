# 🍽️ Munch – Backend API

**Campus Canteen Food Ordering System**  
FastAPI · PostgreSQL · WebSockets · Scikit-learn AI Recommendations

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API Framework | FastAPI (async) |
| Database | PostgreSQL 16 + SQLAlchemy 2 (async) |
| Auth | JWT (HS256) + bcrypt salt-hashing (NFR-03) |
| Real-time | WebSockets (order tracking + kitchen queue) |
| AI Engine | Scikit-learn hybrid recommendations (FR-07/FR-08) |
| Migrations | Alembic |
| Deployment | Docker + Docker Compose |

---

## Quick Start

### Option A – Docker (recommended)

```bash
cp .env.example .env
docker-compose up --build
```

API live at: http://localhost:8000  
Swagger docs: http://localhost:8000/api/docs

### Option B – Local

```bash
# 1. Python env
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Start PostgreSQL + Redis (e.g. via Docker)
docker run -d --name munch-pg -e POSTGRES_DB=munch_db \
  -e POSTGRES_USER=munch_user -e POSTGRES_PASSWORD=munch_password \
  -p 5432:5432 postgres:16-alpine

docker run -d --name munch-redis -p 6379:6379 redis:7-alpine

# 3. Configure
cp .env.example .env

# 4. Run migrations & seed
alembic upgrade head
python seed.py

# 5. Start server
uvicorn app.main:app --reload
```

---

## API Endpoints

### Auth
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/register` | Register with @university.edu email (FR-01) |
| POST | `/api/v1/auth/login` | Login → JWT tokens |
| POST | `/api/v1/auth/refresh` | Refresh access token |
| GET  | `/api/v1/auth/me` | Current user profile |

### Menu
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/menu/items` | Browse menu (search, filter, availability) (FR-02/03/20) |
| GET | `/api/v1/menu/items/{id}` | Single item detail |
| POST | `/api/v1/menu/items` | Admin: Add item (FR-23) |
| PATCH | `/api/v1/menu/items/{id}` | Admin: Edit item |
| DELETE | `/api/v1/menu/items/{id}` | Admin: Soft-delete item |
| PATCH | `/api/v1/menu/items/{id}/availability` | Admin: Quick-Toggle In-Stock/Sold-Out (FR-24) |
| GET | `/api/v1/menu/low-stock` | Admin: Low-stock alert list (FR-15) |
| GET | `/api/v1/menu/categories` | List categories |
| POST | `/api/v1/menu/categories` | Admin: Create category |
| GET | `/api/v1/menu/items/{id}/reviews` | Item reviews |
| POST | `/api/v1/menu/items/{id}/reviews` | Student: Post rating/review (FR-16) |

### Cart & Orders
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/cart` | View cart with total (FR-12) |
| POST | `/api/v1/cart` | Add item to cart |
| PATCH | `/api/v1/cart/{id}` | Update quantity |
| DELETE | `/api/v1/cart/{id}` | Remove item |
| DELETE | `/api/v1/cart` | Clear cart |
| POST | `/api/v1/orders` | Place order → unique token (FR-04/19/NFR-07) |
| GET | `/api/v1/orders` | My order history (FR-06) |
| GET | `/api/v1/orders/{id}` | Order detail + live status (FR-05) |
| POST | `/api/v1/orders/{id}/cancel` | Cancel if not yet preparing (FR-17) |
| GET | `/api/v1/admin/orders` | Admin: All orders with filter |
| GET | `/api/v1/admin/queue` | Kitchen: Live order queue (FR-18) |
| PATCH | `/api/v1/admin/orders/{id}/status` | Kitchen: Update status → triggers notification |

### Notifications & AI
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/notifications` | Student notifications (FR-13) |
| POST | `/api/v1/notifications/mark-read` | Mark all as read |
| GET | `/api/v1/recommendations` | AI meal recommendations (FR-07/08) |

### Inventory
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/admin/inventory/{id}/adjust` | Admin: Restock or reduce stock |
| GET | `/api/v1/admin/inventory/logs/{id}` | Inventory audit trail |

### WebSockets
| Path | Description |
|------|-------------|
| `WS /api/v1/ws/orders/{order_id}?token=<jwt>` | Student: Live order status (FR-05) |
| `WS /api/v1/ws/kitchen?token=<jwt>` | Kitchen: Live queue updates (FR-18) |

---

## Key Design Decisions

### Transactional Integrity (NFR-07)
`FOR UPDATE` row-level locking in `order_service.place_order()` prevents two students from simultaneously ordering the last available item. PostgreSQL guarantees atomicity.

### AI Recommendations (FR-07/08)
Hybrid engine:
- **60% weight**: User's personal order history
- **40% weight**: Items popular during current time-of-day bracket (breakfast/lunch/snack/dinner)
- **Cold start**: Falls back to all-time top sellers

NFR-06 compliance: only aggregate counts are queried — never raw user PII.

### Authentication (FR-01, NFR-03)
- Email restricted to `@university.edu` domain at registration (validator in schema + security layer)
- Passwords hashed with bcrypt + automatic salt
- Stateless JWT with 60-min access tokens + 7-day refresh tokens

### Real-time Updates (FR-05, FR-13)
WebSocket connections per order ID. When kitchen staff change order status via HTTP, the service can call `manager.broadcast_order_update()` to push to connected students instantly.

---

## Seeded Test Accounts

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@university.edu | Admin@1234 |
| Kitchen Staff | kitchen@university.edu | Kitchen@1234 |
| Student | student@university.edu | Student@1234 |
