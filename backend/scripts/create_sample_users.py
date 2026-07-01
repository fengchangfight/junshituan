"""Create sample users with bcrypt-hashed passwords (demo123)."""
import sys, asyncio, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import bcrypt

DB = "postgresql+asyncpg://junshituan:junshituan_secret@localhost:5432/junshituan"

SAMPLE_USERS = [
    ("libai", "李白", False),
    ("caocao", "曹操", False),
    ("songhuizong", "宋徽宗", False),
    ("admin", "管理员", True),
]

async def main():
    engine = create_async_engine(DB)
    hashed = bcrypt.hashpw("demo123".encode(), bcrypt.gensalt()).decode()

    async with engine.begin() as conn:
        for username, display_name, is_admin in SAMPLE_USERS:
            result = await conn.execute(
                text("SELECT id FROM users WHERE username = :uname"),
                {"uname": username},
            )
            existing = result.fetchone()

            if existing:
                await conn.execute(
                    text("UPDATE users SET hashed_password = :hp, display_name = :dn WHERE username = :uname"),
                    {"hp": hashed, "dn": display_name, "uname": username},
                )
                print(f"  Updated: {username}")
            else:
                from uuid import uuid4
                uid = uuid4().hex[:12]
                await conn.execute(
                    text("INSERT INTO users (id, username, hashed_password, display_name, is_admin) VALUES (:id, :uname, :hp, :dn, :admin)"),
                    {"id": uid, "uname": username, "hp": hashed, "dn": display_name, "admin": is_admin},
                )
                print(f"  Created: {username} (id={uid})")

    await engine.dispose()
    print("Done. All sample users password = demo123")

asyncio.run(main())
