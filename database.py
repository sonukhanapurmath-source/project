import sqlite3

DB_NAME = "balloon.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            username  TEXT    NOT NULL UNIQUE,
            password  TEXT    NOT NULL,
            created   DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Scores table
    c.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            player    TEXT    NOT NULL DEFAULT 'Player',
            score     INTEGER NOT NULL DEFAULT 0,
            accuracy  REAL    NOT NULL DEFAULT 0,
            combo     INTEGER NOT NULL DEFAULT 0,
            level     INTEGER NOT NULL DEFAULT 1,
            created   DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def insert_score(player, score, accuracy, combo, level):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        "INSERT INTO scores (player, score, accuracy, combo, level) VALUES (?, ?, ?, ?, ?)",
        (player, score, accuracy, combo, level)
    )
    conn.commit()
    conn.close()


def get_scores(limit=10):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT player, score, accuracy, combo, level
        FROM scores
        ORDER BY score DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return rows