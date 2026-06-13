import sqlite3
import os
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "ssm_ranked.db")

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init()

    def _init(self):
        c = self.conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS players (
                discord_id   INTEGER PRIMARY KEY,
                ign          TEXT    UNIQUE NOT NULL,
                elo          INTEGER DEFAULT 1000,
                wins         INTEGER DEFAULT 0,
                losses       INTEGER DEFAULT 0,
                streak       INTEGER DEFAULT 0,
                registered_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS matches (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                p1_id        INTEGER NOT NULL,
                p2_id        INTEGER NOT NULL,
                winner_id    INTEGER,
                loser_id     INTEGER,
                winner_elo_before INTEGER,
                loser_elo_before  INTEGER,
                winner_elo_after  INTEGER,
                loser_elo_after   INTEGER,
                status       TEXT DEFAULT 'active',
                created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
                finished_at  TEXT
            );
        """)
        self.conn.commit()

    # ── Players ──────────────────────────────────────────────
    def get_player(self, discord_id):
        c = self.conn.cursor()
        c.execute("SELECT * FROM players WHERE discord_id = ?", (discord_id,))
        row = c.fetchone()
        return dict(row) if row else None

    def ign_taken(self, ign):
        c = self.conn.cursor()
        c.execute("SELECT 1 FROM players WHERE LOWER(ign) = LOWER(?)", (ign,))
        return c.fetchone() is not None

    def register(self, discord_id, ign):
        c = self.conn.cursor()
        c.execute("INSERT INTO players (discord_id, ign) VALUES (?, ?)", (discord_id, ign))
        self.conn.commit()

    def set_elo(self, discord_id, elo):
        c = self.conn.cursor()
        c.execute("UPDATE players SET elo = ? WHERE discord_id = ?", (elo, discord_id))
        self.conn.commit()

    def get_leaderboard(self, limit=10):
        c = self.conn.cursor()
        c.execute("""
            SELECT ign, elo, wins, losses
            FROM players
            ORDER BY elo DESC
            LIMIT ?
        """, (limit,))
        return [dict(r) for r in c.fetchall()]

    # ── Matches ──────────────────────────────────────────────
    def in_active_match(self, discord_id):
        c = self.conn.cursor()
        c.execute("""
            SELECT 1 FROM matches
            WHERE (p1_id = ? OR p2_id = ?) AND status = 'active'
        """, (discord_id, discord_id))
        return c.fetchone() is not None

    def create_match(self, p1_id, p2_id):
        c = self.conn.cursor()
        c.execute("INSERT INTO matches (p1_id, p2_id) VALUES (?, ?)", (p1_id, p2_id))
        self.conn.commit()
        return c.lastrowid

    def get_active_match(self, uid1, uid2):
        c = self.conn.cursor()
        c.execute("""
            SELECT * FROM matches
            WHERE ((p1_id = ? AND p2_id = ?) OR (p1_id = ? AND p2_id = ?))
            AND status = 'active'
            ORDER BY created_at DESC LIMIT 1
        """, (uid1, uid2, uid2, uid1))
        row = c.fetchone()
        return dict(row) if row else None

    def get_active_match_single(self, uid):
        c = self.conn.cursor()
        c.execute("""
            SELECT * FROM matches
            WHERE (p1_id = ? OR p2_id = ?) AND status = 'active'
            ORDER BY created_at DESC LIMIT 1
        """, (uid, uid))
        row = c.fetchone()
        return dict(row) if row else None

    def record_result(self, match_id, winner_id, loser_id, new_w_elo, new_l_elo):
        c = self.conn.cursor()

        # Get before elos
        w = self.get_player(winner_id)
        l = self.get_player(loser_id)

        # Update match
        c.execute("""
            UPDATE matches SET
                winner_id = ?, loser_id = ?,
                winner_elo_before = ?, loser_elo_before = ?,
                winner_elo_after = ?,  loser_elo_after = ?,
                status = 'finished',   finished_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (winner_id, loser_id, w["elo"], l["elo"], new_w_elo, new_l_elo, match_id))

        # Update winner
        new_w_streak = w["streak"] + 1 if w["streak"] >= 0 else 1
        c.execute("""
            UPDATE players SET elo = ?, wins = wins + 1, streak = ?
            WHERE discord_id = ?
        """, (new_w_elo, new_w_streak, winner_id))

        # Update loser
        new_l_streak = l["streak"] - 1 if l["streak"] <= 0 else -1
        c.execute("""
            UPDATE players SET elo = ?, losses = losses + 1, streak = ?
            WHERE discord_id = ?
        """, (new_l_elo, new_l_streak, loser_id))

        self.conn.commit()

    def get_history(self, discord_id, limit=10):
        c = self.conn.cursor()
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
            WHERE (m.p1_id = ? OR m.p2_id = ?) AND m.status = 'finished'
            ORDER BY m.finished_at DESC
            LIMIT ?
        """, (discord_id, discord_id, limit))
        return [dict(r) for r in c.fetchall()]
