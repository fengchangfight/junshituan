"""Delete a user and ALL related data — Postgres + Milvus.

Cascade surface:
  Postgres: sessions → chat_messages, agent_checkpoints
            user_memories
            personas → knowledge_documents
  Milvus:   persona vectors in junshituan_knowledge collection

Usage:
  python scripts/delete_user.py --username testuser
  python scripts/delete_user.py --username testuser --yes       (skip confirm)
  python scripts/delete_user.py --username testuser --keep-personas  (orphan personas, don't delete)

In production:
  docker exec junshituan-backend python scripts/delete_user.py --username testuser --yes
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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


async def _count(conn, query: str, params: dict) -> int:
    result = await conn.execute(text(query), params)
    row = result.fetchone()
    return row[0] if row else 0


async def main():
    parser = argparse.ArgumentParser(description="Delete a user and all related data")
    parser.add_argument("--username", required=True, help="Username to delete")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--keep-personas", action="store_true",
                        help="Orphan personas (set creator_id=NULL) instead of deleting them")
    parser.add_argument("--db-url", default=None,
                        help="Database URL (reads DATABASE_URL env or config if omitted)")
    parser.add_argument("--milvus-host", default=None, help="Milvus host (default: from config)")
    parser.add_argument("--milvus-port", default=None, help="Milvus port (default: from config)")
    args = parser.parse_args()

    db_url = get_db_url(args.db_url)
    engine = create_async_engine(db_url)

    async with engine.begin() as conn:
        # ── Locate user ──────────────────────────────────────────────────
        result = await conn.execute(
            text("SELECT id, username, display_name, role FROM users WHERE username = :uname"),
            {"uname": args.username},
        )
        user_row = result.fetchone()
        if not user_row:
            print(f"User not found: {args.username}")
            sys.exit(1)

        user_id, username, display_name, role = user_row

        # ── Count what will be deleted ───────────────────────────────────
        persona_ids: list[str] = []
        if not args.keep_personas:
            p_result = await conn.execute(
                text("SELECT id FROM personas WHERE creator_id = :uid"), {"uid": user_id}
            )
            persona_ids = [r[0] for r in p_result.fetchall()]

        session_count = await _count(
            conn, "SELECT COUNT(*) FROM sessions WHERE user_id = :uid", {"uid": user_id}
        )
        msg_count = await _count(
            conn,
            "SELECT COUNT(*) FROM chat_messages WHERE session_id IN (SELECT id FROM sessions WHERE user_id = :uid)",
            {"uid": user_id},
        )
        ckpt_count = await _count(
            conn,
            "SELECT COUNT(*) FROM agent_checkpoints WHERE session_id IN (SELECT id FROM sessions WHERE user_id = :uid)",
            {"uid": user_id},
        )
        mem_count = await _count(
            conn, "SELECT COUNT(*) FROM user_memories WHERE user_id = :uid", {"uid": user_id}
        )
        doc_count = 0
        if persona_ids:
            doc_count = await _count(
                conn,
                "SELECT COUNT(*) FROM knowledge_documents WHERE persona_id = ANY(:pids)",
                {"pids": persona_ids},
            )

        # ── Show summary ─────────────────────────────────────────────────
        print(f"\nUser: {username} (id={user_id}, display={display_name}, role={role})")
        print(f"  Sessions:           {session_count}")
        print(f"  Chat messages:      {msg_count}")
        print(f"  Agent checkpoints:  {ckpt_count}")
        print(f"  User memories:      {mem_count}")
        if args.keep_personas:
            print(f"  Personas:           (kept — creator_id will be set NULL)")
        else:
            print(f"  Personas:           {len(persona_ids)}  (ids: {persona_ids})")
            print(f"  Knowledge docs:     {doc_count}")
            print(f"  Milvus vectors:     per persona above (collection: junshituan_knowledge)")

        # ── Confirm ──────────────────────────────────────────────────────
        if not args.yes:
            print()
            resp = input("Delete ALL above data? Type DELETE to confirm: ")
            if resp != "DELETE":
                print("Aborted.")
                sys.exit(0)

        # ── Milvus cleanup ───────────────────────────────────────────────
        milvus_deleted = 0
        if persona_ids:
            try:
                from pymilvus import MilvusClient
                milvus_host = args.milvus_host or os.getenv("MILVUS_HOST", "localhost")
                milvus_port = int(args.milvus_port or os.getenv("MILVUS_PORT", "19530"))
                client = MilvusClient(uri=f"http://{milvus_host}:{milvus_port}")

                for pid in persona_ids:
                    expr = f'persona_id == "{pid}"'
                    result = client.delete(collection_name="junshituan_knowledge", filter=expr)
                    count = result.get("delete_count", 0) if isinstance(result, dict) else 0
                    milvus_deleted += count
                    print(f"  Milvus: deleted {count} vectors for persona {pid}")
            except Exception as e:
                print(f"  WARNING: Milvus cleanup failed — {e}")

        # ── Docstore file cleanup ─────────────────────────────────────────
        docstore_removed = 0
        if persona_ids:
            import glob as _glob
            docstore_dir = os.path.join("data", "docstore")
            for pid in persona_ids:
                path = os.path.join(docstore_dir, f"{pid}.json")
                if os.path.exists(path):
                    os.remove(path)
                    docstore_removed += 1
                    print(f"  Docstore: removed {path}")

        # ── Postgres cleanup ─────────────────────────────────────────────
        # Order matters — delete children before parents

        # 1. knowledge_documents → personas
        if persona_ids:
            await conn.execute(
                text("DELETE FROM knowledge_documents WHERE persona_id = ANY(:pids)"),
                {"pids": persona_ids},
            )

        # 2. agent_checkpoints → sessions
        await conn.execute(
            text(
                "DELETE FROM agent_checkpoints WHERE session_id IN "
                "(SELECT id FROM sessions WHERE user_id = :uid)"
            ),
            {"uid": user_id},
        )

        # 3. chat_messages → sessions
        await conn.execute(
            text(
                "DELETE FROM chat_messages WHERE session_id IN "
                "(SELECT id FROM sessions WHERE user_id = :uid)"
            ),
            {"uid": user_id},
        )

        # 4. sessions → user
        await conn.execute(
            text("DELETE FROM sessions WHERE user_id = :uid"), {"uid": user_id}
        )

        # 5. user_memories → user
        await conn.execute(
            text("DELETE FROM user_memories WHERE user_id = :uid"), {"uid": user_id}
        )

        # 6. personas → user
        if persona_ids:
            await conn.execute(
                text("DELETE FROM personas WHERE creator_id = :uid"), {"uid": user_id}
            )
        elif args.keep_personas:
            await conn.execute(
                text("UPDATE personas SET creator_id = NULL WHERE creator_id = :uid"),
                {"uid": user_id},
            )

        # 7. user
        await conn.execute(
            text("DELETE FROM users WHERE id = :uid"), {"uid": user_id}
        )

    await engine.dispose()

    print(f"\nDeleted user: {username}")
    print(f"  Postgres: {session_count} sessions + {msg_count} msgs + {ckpt_count} ckpts "
          f"+ {mem_count} memories + {len(persona_ids)} personas + {doc_count} docs")
    print(f"  Milvus:   {milvus_deleted} vectors")
    print(f"  Docstore: {docstore_removed} files")
    print("Done.")


asyncio.run(main())
