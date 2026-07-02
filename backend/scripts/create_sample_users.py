"""Create sample users with bcrypt-hashed passwords (demo123)."""
import sys, asyncio, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import bcrypt

DB = "postgresql+asyncpg://junshituan:junshituan_secret@localhost:5432/junshituan"

SAMPLE_USERS = [
    ("libai", "李白", "user"),
    ("caocao", "曹操", "user"),
    ("songhuizong", "宋徽宗", "user"),
    ("admin", "管理员", "super_admin"),
]

async def main():
    engine = create_async_engine(DB)
    hashed = bcrypt.hashpw("demo123".encode(), bcrypt.gensalt()).decode()

    async with engine.begin() as conn:
        for username, display_name, role in SAMPLE_USERS:
            result = await conn.execute(
                text("SELECT id FROM users WHERE username = :uname"),
                {"uname": username},
            )
            existing = result.fetchone()

            if existing:
                await conn.execute(
                    text("UPDATE users SET hashed_password = :hp, display_name = :dn, role = :role WHERE username = :uname"),
                    {"hp": hashed, "dn": display_name, "role": role, "uname": username},
                )
                print(f"  Updated: {username} (role={role})")
            else:
                from uuid import uuid4
                uid = uuid4().hex[:12]
                await conn.execute(
                    text("INSERT INTO users (id, username, hashed_password, display_name, role) VALUES (:id, :uname, :hp, :dn, :role)"),
                    {"id": uid, "uname": username, "hp": hashed, "dn": display_name, "role": role},
                )
                print(f"  Created: {username} (id={uid}, role={role})")

    await engine.dispose()
    print("Done. All sample users password = demo123")

asyncio.run(main())
