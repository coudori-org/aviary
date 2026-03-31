"""Seed test agents and teams into the database.

Usage: python scripts/seed-test-data.py
Requires: DATABASE_URL env var or defaults to local dev database.
"""

import asyncio
import os
import uuid

import asyncpg


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://aviary:aviary@localhost:5432/aviary",
)


async def main():
    conn = await asyncpg.connect(DATABASE_URL)

    try:
        # Create test users (normally created on OIDC login, but useful for seeding)
        admin_id = uuid.uuid4()
        user1_id = uuid.uuid4()
        user2_id = uuid.uuid4()

        for user_id, ext_id, email, name, is_admin in [
            (admin_id, "admin-sub-001", "admin@test.com", "Admin User", True),
            (user1_id, "user1-sub-002", "user1@test.com", "User One", False),
            (user2_id, "user2-sub-003", "user2@test.com", "User Two", False),
        ]:
            await conn.execute(
                """
                INSERT INTO users (id, external_id, email, display_name, is_platform_admin)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (external_id) DO NOTHING
                """,
                user_id, ext_id, email, name, is_admin,
            )

        # Create a test team
        team_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO teams (id, name, description)
            VALUES ($1, $2, $3)
            ON CONFLICT (name) DO NOTHING
            """,
            team_id, "engineering", "Engineering team",
        )

        # Add members to team
        for uid in [admin_id, user1_id]:
            await conn.execute(
                """
                INSERT INTO team_members (team_id, user_id, role)
                VALUES ($1, $2, $3)
                ON CONFLICT DO NOTHING
                """,
                team_id, uid, "member",
            )

        # Create a test agent
        agent_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO agents (id, name, slug, description, owner_id, instruction, model_config, tools, policy, visibility)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (slug) DO NOTHING
            """,
            agent_id,
            "Code Assistant",
            "code-assistant",
            "A helpful coding assistant",
            admin_id,
            "You are a helpful coding assistant. Help users write, debug, and review code.",
            '{"backend": "claude", "model": "default", "temperature": 0.7, "maxTokens": 8192}',
            '["read_file", "write_file", "run_command"]',
            '{"maxConcurrentSessions": 20, "sessionTimeout": 30, "allowShellExec": true}',
            "public",
        )

        print("Test data seeded successfully.")
        print(f"  Admin user:  {admin_id}")
        print(f"  User 1:      {user1_id}")
        print(f"  User 2:      {user2_id}")
        print(f"  Team:        {team_id}")
        print(f"  Agent:       {agent_id}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
