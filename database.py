import os
import psycopg2
import psycopg2.extras
from datetime import datetime

def get_conn():
    return psycopg2.connect(os.getenv("DATABASE_URL"), sslmode="require")

class Database:
    def __init__(self):
        self._init()

    def _init(self):
        with get_conn() as conn:
            with conn.cursor() as c:
                c.execute("""
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
            conn.commit()

    def get_player(self, discord_id):
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                c.execute("SELECT * FROM players WHERE discord_id = %s", (discord_id,))
                row = c.fetchone()
                return dict(row) if row else None

    def ign_taken(self, ign):
        with get_conn() as conn:
            with conn.cursor() as c:
                c.execute("SELECT 1 FROM players WHERE LOWER(ign) = LOWER(%s)", (ign,))
                return c.fetchone() is not None

    def register(self, discord_id, ign):
        with get_conn() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO players (discord_id, ign) VALUES (%s, %s)", (discord_id, ign))
            conn.commit()

    def set_elo(self, discord_id, elo):
        with get_conn() as conn:
            with conn.cursor() as c:
                c.execute("UPDATE players SET elo = %s WHERE discord_id = %s", (elo, discord_id))
            conn.commit()

    def get_leaderboard(self, limit=10):
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                c.execute("SELECT ign, elo, wins, losses FROM players ORDER BY elo DESC LIMIT %s", (limit,))
                return [dict(r) for r in c.fetchall()]

    def in_active_match(self, discord_id):
        with get_conn() as conn:
            with conn.cursor() as c:
                c.execute("SELECT 1 FROM matches WHERE (p1_id = %s OR p2_id = %s) AND status = 'active'", (discord_id, discord_id))
                return c.fetchone() is not None

    def create_match(self, p1_id, p2_id):
        with get_conn() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO matches (p1_id, p2_id) VALUES (%s, %s) RETURNING id", (p1_id, p2_id))
                match_id = c.fetchone()[0]
            conn.commit()
            return match_id

    def get_active_match(self, uid1, uid2):
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                c.execute("""
                    SELECT * FROM matches
                    WHERE ((p1_id = %s AND p2_id = %s) OR (p1_id = %s AND p2_id = %s))
                    AND status = 'active'
                    ORDER BY created_at DESC LIMIT 1
                """, (uid1, uid2, uid2, uid1))
                row = c.fetchone()
                return dict(row) if row else None

    def get_active_match_single(self, uid):
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                c.execute("""
                    SELECT * FROM matches
                    WHERE (p1_id = %s OR p2_id = %s) AND status = 'active'
                    ORDER BY created_at DESC LIMIT 1
                """, (uid, uid))
                row = c.fetchone()
                return dict(row) if row else None

    def get_match_by_id(self, match_id):
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                c.execute("SELECT * FROM matches WHERE id = %s", (match_id,))
                row = c.fetchone()
                return dict(row) if row else None

    def record_result(self, match_id, winner_id, loser_id, new_w_elo, new_l_elo):
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                c.execute("SELECT * FROM players WHERE discord_id = %s", (winner_id,))
                w = dict(c.fetchone())
                c.execute("SELECT * FROM players WHERE discord_id = %s", (loser_id,))
                l = dict(c.fetchone())

                c.execute("""
                    UPDATE matches SET
                        winner_id = %s, loser_id = %s,
                        winner_elo_before = %s, loser_elo_before = %s,
                        winner_elo_after = %s, loser_elo_after = %s,
                        status = 'finished', finished_at = NOW()
                    WHERE id = %s
                """, (winner_id, loser_id, w["elo"], l["elo"], new_w_elo, new_l_elo, match_id))

                new_w_streak = w["streak"] + 1 if w["streak"] >= 0 else 1
                c.execute("UPDATE players SET elo = %s, wins = wins + 1, streak = %s WHERE discord_id = %s",
                          (new_w_elo, new_w_streak, winner_id))

                new_l_streak = l["streak"] - 1 if l["streak"] <= 0 else -1
                c.execute("UPDATE players SET elo = %s, losses = losses + 1, streak = %s WHERE discord_id = %s",
                          (new_l_elo, new_l_streak, loser_id))
            conn.commit()

    def get_history(self, discord_id, limit=10):
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                c.execute("""
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
                """, (discord_id, discord_id, limit))
                return [dict(r) for r in c.fetchall()]
