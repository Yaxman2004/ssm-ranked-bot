import psycopg
import os

_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await psycopg.AsyncConnection.connect(os.getenv("DATABASE_URL"))
    return _pool

async def init_db():
    conn = await get_pool()
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS players (
            discord_id   BIGINT PRIMARY KEY,
            ign          TEXT UNIQUE NOT NULL,
            elo          INTEGER DEFAULT 1000,
            wins         INTEGER DEFAULT 0,
            losses       INTEGER DEFAULT 0,
            streak       INTEGER DEFAULT 0,
            registered_at TIMESTAMP DEFAULT NOW()
        )
    """)
    await conn.execute("""
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
        )
    """)
    await conn.commit()

async def fetchone(query, *args):
    conn = await get_pool()
    async with conn.cursor(row_factory=psycopg.rows.dict_row) as c:
        await c.execute(query, args)
        return await c.fetchone()

async def fetchall(query, *args):
    conn = await get_pool()
    async with conn.cursor(row_factory=psycopg.rows.dict_row) as c:
        await c.execute(query, args)
        return await c.fetchall()

async def execute(query, *args):
    conn = await get_pool()
    await conn.execute(query, args)
    await conn.commit()

async def fetchval(query, *args):
    conn = await get_pool()
    async with conn.cursor() as c:
        await c.execute(query, args)
        row = await c.fetchone()
        return row[0] if row else None

class Database:
    async def get_player(self, discord_id):
        return await fetchone("SELECT * FROM players WHERE discord_id = %s", discord_id)

    async def ign_taken(self, ign):
        row = await fetchone("SELECT 1 FROM players WHERE LOWER(ign) = LOWER(%s)", ign)
        return row is not None

    async def register(self, discord_id, ign):
        await execute("INSERT INTO players (discord_id, ign) VALUES (%s, %s)", discord_id, ign)

    async def set_elo(self, discord_id, elo):
        await execute("UPDATE players SET elo = %s WHERE discord_id = %s", elo, discord_id)

    async def get_leaderboard(self, limit=10):
        return await fetchall("SELECT ign, elo, wins, losses FROM players ORDER BY elo DESC LIMIT %s", limit)

    async def in_active_match(self, discord_id):
        row = await fetchone(
            "SELECT 1 FROM matches WHERE (p1_id = %s OR p2_id = %s) AND status = 'active'",
            discord_id, discord_id
        )
        return row is not None

    async def create_match(self, p1_id, p2_id):
        return await fetchval(
            "INSERT INTO matches (p1_id, p2_id) VALUES (%s, %s) RETURNING id",
            p1_id, p2_id
        )

    async def get_active_match(self, uid1, uid2):
        return await fetchone("""
            SELECT * FROM matches
            WHERE ((p1_id = %s AND p2_id = %s) OR (p1_id = %s AND p2_id = %s))
            AND status = 'active'
            ORDER BY created_at DESC LIMIT 1
        """, uid1, uid2, uid2, uid1)

    async def get_active_match_single(self, uid):
        return await fetchone("""
            SELECT * FROM matches
            WHERE (p1_id = %s OR p2_id = %s) AND status = 'active'
            ORDER BY created_at DESC LIMIT 1
        """, uid, uid)

    async def get_match_by_id(self, match_id):
        return await fetchone("SELECT * FROM matches WHERE id = %s", match_id)

    async def record_result(self, match_id, winner_id, loser_id, new_w_elo, new_l_elo):
        w = await fetchone("SELECT * FROM players WHERE discord_id = %s", winner_id)
        l = await fetchone("SELECT * FROM players WHERE discord_id = %s", loser_id)

        await execute("""
            UPDATE matches SET
                winner_id = %s, loser_id = %s,
                winner_elo_before = %s, loser_elo_before = %s,
                winner_elo_after = %s, loser_elo_after = %s,
                status = 'finished', finished_at = NOW()
            WHERE id = %s
        """, winner_id, loser_id, w["elo"], l["elo"], new_w_elo, new_l_elo, match_id)

        new_w_streak = w["streak"] + 1 if w["streak"] >= 0 else 1
        await execute(
            "UPDATE players SET elo = %s, wins = wins + 1, streak = %s WHERE discord_id = %s",
            new_w_elo, new_w_streak, winner_id
        )

        new_l_streak = l["streak"] - 1 if l["streak"] <= 0 else -1
        await execute(
            "UPDATE players SET elo = %s, losses = losses + 1, streak = %s WHERE discord_id = %s",
            new_l_elo, new_l_streak, loser_id
        )

    async def get_history(self, discord_id, limit=10):
        return await fetchall("""
            SELECT
                m.id, m.winner_id, m.loser_id,
                m.winner_elo_before, m.winner_elo_after,
                m.loser_elo_before,  m.loser_elo_after,
                pw.ign AS winner_ign,
                pl.ign AS loser_ign
            FROM matches m
            JOIN players pw ON pw.discord_id = m.winner_id
            JOIN players pl ON pl.discord_id = m.loser_id
            WHERE (m.p1_id = %s OR m.p2_id = %s) AND m.status = 'finished'
            ORDER BY m.finished_at DESC
            LIMIT %s
        """, discord_id, discord_id, limit)
