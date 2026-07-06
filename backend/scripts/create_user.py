"""Create or update a user. Runs standalone — no FastAPI process needed.

Usage:
  python scripts/create_user.py --username testuser --password demo123
  python scripts/create_user.py --username testuser --password demo123 --role admin --display-name "测试用户"
  python scripts/create_user.py --username testuser --password demo123 --db-url postgresql+asyncpg://user:pass@host:5432/db

In production (via docker exec):
  docker exec junshituan-backend python scripts/create_user.py --username testuser --password demo123
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import bcrypt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

VALID_ROLES = ("user", "admin", "viewer", "super_admin")


def get_db_url(explicit: str | None) -> str:
    if explicit:
        return explicit
    # Try environment first, then app config
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
    parser = argparse.ArgumentParser(description="Create or update a user")
    parser.add_argument("--username", required=True, help="Login username")
    parser.add_argument("--password", required=True, help="Plaintext password")
    parser.add_argument("--display-name", default=None, help="Display name (defaults to username)")
    parser.add_argument("--role", default="user", choices=VALID_ROLES, help="Role (default: user)")
    parser.add_argument("--db-url", default=None, help="Database URL (reads DATABASE_URL env or config if omitted)")
    args = parser.parse_args()

    db_url = get_db_url(args.db_url)
    display_name = args.display_name or args.username
    hashed = bcrypt.hashpw(args.password.encode(), bcrypt.gensalt()).decode()

    engine = create_async_engine(db_url)

    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT id FROM users WHERE username = :uname"),
            {"uname": args.username},
        )
        existing = result.fetchone()

        if existing:
            await conn.execute(
                text(
                    "UPDATE users SET hashed_password = :hp, display_name = :dn, role = :role "
                    "WHERE username = :uname"
                ),
                {"hp": hashed, "dn": display_name, "role": args.role, "uname": args.username},
            )
            print(f"Updated: {args.username} (role={args.role})")
        else:
            from uuid import uuid4

            uid = uuid4().hex[:12]
            await conn.execute(
                text(
                    "INSERT INTO users (id, username, hashed_password, display_name, role) "
                    "VALUES (:id, :uname, :hp, :dn, :role)"
                ),
                {"id": uid, "uname": args.username, "hp": hashed, "dn": display_name, "role": args.role},
            )
            print(f"Created: {args.username} (id={uid}, role={args.role})")

    await engine.dispose()
    print(f"Done. Login: {args.username} / {args.password}")


asyncio.run(main())
