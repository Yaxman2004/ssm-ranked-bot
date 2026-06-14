import asyncpg
import os

_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(os.getenv("DATABASE_URL"), ssl="require")
    return _pool

async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                discord_id   BIGINT PRIMARY KEY,
                ign          TEXT UNIQUE NOT NULL,
                elo          INTEGER DEFAULT 1000,
                wins         INTEGER DEFAULT 0,
                losses       INTEGER DEFAULT 0,
                streak       INTEGER DEFAULT 0,
                registered_at TIMESTAMP DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS matches (
                id                  SERIAL PRIMARY KEY,
                p1_id               BIGINT NOT NULL,
                p2_id               BIGINT NOT NULL,
                winner_id           BIGINT,
                loser_id            BIGINT,
                winner_elo_before   INTEGER,
                loser_elo_before    INTEGER,
                winner_elo_after    INTEGER,
                loser_elo_after     INTEGER,
                status              TEXT DEFAULT 'active',
                created_at          TIMESTAMP DEFAULT NOW(),
                finished_at         TIMESTAMP
            );
        """)

class Database:
    async def get_player(self, discord_id):
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM players WHERE discord_id = $1", discord_id)
            return dict(row) if row else None

    async def ign_taken(self, ign):
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT 1 FROM players WHERE LOWER(ign) = LOWER($1)", ign)
            return row is not None

    async def register(self, discord_id, ign):
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("INSERT INTO players (discord_id, ign) VALUES ($1, $2)", discord_id, ign)

    async def set_elo(self, discord_id, elo):
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE players SET elo = $1 WHERE discord_id = $2", elo, discord_id)

    async def get_leaderboard(self, limit=10):
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT ign, elo, wins, losses FROM players ORDER BY elo DESC LIMIT $1", limit)
            return [dict(r) for r in rows]

    async def in_active_match(self, discord_id):
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM matches WHERE (p1_id = $1 OR p2_id = $1) AND status = 'active'",
                discord_id
            )
            return row is not None

    async def create_match(self, p1_id, p2_id):
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO matches (p1_id, p2_id) VALUES ($1, $2) RETURNING id",
                p1_id, p2_id
            )
            return row["id"]

    async def get_active_match(self, uid1, uid2):
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM matches
                WHERE ((p1_id = $1 AND p2_id = $2) OR (p1_id = $2 AND p2_id = $1))
                AND status = 'active'
                ORDER BY created_at DESC LIMIT 1
            """, uid1, uid2)
            return dict(row) if row else None

    async def get_active_match_single(self, uid):
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM matches
                WHERE (p1_id = $1 OR p2_id = $1) AND status = 'active'
                ORDER BY created_at DESC LIMIT 1
            """, uid)
            return dict(row) if row else None

    async def get_match_by_id(self, match_id):
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM matches WHERE id = $1", match_id)
            return dict(row) if row else None

    async def record_result(self, match_id, winner_id, loser_id, new_w_elo, new_l_elo):
        pool = await get_pool()
        async with pool.acquire() as conn:
            w = dict(await conn.fetchrow("SELECT * FROM players WHERE discord_id = $1", winner_id))
            l = dict(await conn.fetchrow("SELECT * FROM players WHERE discord_id = $1", loser_id))

            await conn.execute("""
                UPDATE matches SET
                    winner_id = $1, loser_id = $2,
                    winner_elo_before = $3, loser_elo_before = $4,
                    winner_elo_after = $5, loser_elo_after = $6,
                    status = 'finished', finished_at = NOW()
                WHERE id = $7
            """, winner_id, loser_id, w["elo"], l["elo"], new_w_elo, new_l_elo, match_id)

            new_w_streak = w["streak"] + 1 if w["streak"] >= 0 else 1
            await conn.execute(
                "UPDATE players SET elo = $1, wins = wins + 1, streak = $2 WHERE discord_id = $3",
                new_w_elo, new_w_streak, winner_id
            )

            new_l_streak = l["streak"] - 1 if l["streak"] <= 0 else -1
            await conn.execute(
                "UPDATE players SET elo = $1, losses = losses + 1, streak = $2 WHERE discord_id = $3",
                new_l_elo, new_l_streak, loser_id
            )

    async def get_history(self, discord_id, limit=10):
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    m.id, m.winner_id, m.loser_id,
                    m.winner_elo_before, m.winner_elo_after,
                    m.loser_elo_before,  m.loser_elo_after,
                    pw.ign AS winner_ign,
                    pl.ign AS loser_ign
                FROM matches m
                JOIN players pw ON pw.discord_id = m.winner_id
                JOIN players pl ON pl.discord_id = m.loser_id
                WHERE (m.p1_id = $1 OR m.p2_id = $1) AND m.status = 'finished'
                ORDER BY m.finished_at DESC
                LIMIT $2
            """, discord_id, limit)
            return [dict(r) for r in rows]
