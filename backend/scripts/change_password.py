"""Change a user's password. Runs standalone — no FastAPI process needed.

Usage:
  python scripts/change_password.py --username admin --password newpass123
  python scripts/change_password.py --username admin --password newpass123 --db-url postgresql+asyncpg://...

In production:
  docker exec junshituan-backend python scripts/change_password.py --username admin --password newpass123
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import bcrypt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def get_db_url(explicit: str | None) -> str:
    if explicit:
        return explicit
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url
    try:
        from app.core.config import settings
        return settings.database_url
    except Exception:
        pass
    print("ERROR: No --db-url, DATABASE_URL env, or app config found.")
    sys.exit(1)


async def main():
    parser = argparse.ArgumentParser(description="Change a user's password")
    parser.add_argument("--username", required=True, help="Username")
    parser.add_argument("--password", required=True, help="New plaintext password")
    parser.add_argument("--db-url", default=None,
                        help="Database URL (reads DATABASE_URL env or config if omitted)")
    args = parser.parse_args()

    db_url = get_db_url(args.db_url)
    hashed = bcrypt.hashpw(args.password.encode(), bcrypt.gensalt()).decode()

    engine = create_async_engine(db_url)

    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT id, display_name, role FROM users WHERE username = :uname"),
            {"uname": args.username},
        )
        row = result.fetchone()
        if not row:
            print(f"User not found: {args.username}")
            sys.exit(1)

        user_id, display_name, role = row
        await conn.execute(
            text("UPDATE users SET hashed_password = :hp WHERE username = :uname"),
            {"hp": hashed, "uname": args.username},
        )

    await engine.dispose()
    print(f"Password changed: {args.username} ({display_name}, role={role})")


asyncio.run(main())
