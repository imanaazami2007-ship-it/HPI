import aiosqlite
from datetime import datetime, timedelta, timezone
from .config import DATABASE_PATH

PLANS = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0, 10: 0, 11: 0, 12: 0}

async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            expires_at TEXT
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            months INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            receipt_file_id TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS plans (
            months INTEGER PRIMARY KEY,
            price INTEGER NOT NULL
        )''')
        for months, price in PLANS.items():
            await db.execute(
                "INSERT OR IGNORE INTO plans(months, price) VALUES(?, ?)",
                (months, price)
            )
        await db.commit()

async def get_plans():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("SELECT months, price FROM plans ORDER BY months")
        return await cur.fetchall()

async def set_price(months: int, price: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO plans(months, price) VALUES(?, ?) "
            "ON CONFLICT(months) DO UPDATE SET price=excluded.price",
            (months, price)
        )
        await db.commit()

async def create_payment(user_id, months, amount, receipt_file_id):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "INSERT INTO payments(user_id, months, amount, receipt_file_id, created_at) "
            "VALUES(?, ?, ?, ?, ?)",
            (user_id, months, amount, receipt_file_id, datetime.now(timezone.utc).isoformat())
        )
        await db.commit()
        return cur.lastrowid

async def get_payment(payment_id):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT id, user_id, months, amount, status FROM payments WHERE id=?",
            (payment_id,)
        )
        return await cur.fetchone()

async def decide_payment(payment_id, approve: bool):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT user_id, months, status FROM payments WHERE id=?",
            (payment_id,)
        )
        row = await cur.fetchone()
        if not row or row[2] != "pending":
            return None
        user_id, months, _ = row
        status = "approved" if approve else "rejected"
        await db.execute("UPDATE payments SET status=? WHERE id=?", (status, payment_id))
        if approve:
            cur = await db.execute("SELECT expires_at FROM users WHERE user_id=?", (user_id,))
            existing = await cur.fetchone()
            now = datetime.now(timezone.utc)
            if existing and existing[0]:
                try:
                    current_expiry = datetime.fromisoformat(existing[0])
                    if current_expiry > now:
                        now = current_expiry
                except ValueError:
                    pass
            expiry = now + timedelta(days=30 * months)
            await db.execute(
                "INSERT INTO users(user_id, expires_at) VALUES(?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET expires_at=excluded.expires_at",
                (user_id, expiry.isoformat())
            )
        await db.commit()
        if approve:
            return (user_id, expiry.isoformat())
        return (user_id, None)

async def get_user_expiry(user_id):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("SELECT expires_at FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else None

async def pending_count():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM payments WHERE status='pending'")
        return (await cur.fetchone())[0]
