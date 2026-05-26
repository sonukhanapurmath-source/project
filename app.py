from flask import Flask, render_template, request, redirect, session, jsonify, flash
import sqlite3
import hashlib
import os

app = Flask(__name__)
app.secret_key = "balloon_secret_key_2024"

# balloon.db is saved in the SAME folder as app.py
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "balloon.db")


# ────────────────────────────────────────────
# Password hashing
# ────────────────────────────────────────────

def hash_password(password):
    salt = "balloon_salt_xyz"
    return hashlib.sha256((salt + password).encode()).hexdigest()


# ────────────────────────────────────────────
# Database init + migration
# ────────────────────────────────────────────

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode=WAL")

        # ── TABLE 1: users ───────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id        INTEGER  PRIMARY KEY AUTOINCREMENT,
                username  TEXT     NOT NULL UNIQUE,
                password  TEXT     NOT NULL,
                created   DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── TABLE 2: scores ──────────────────
        # Always drop and recreate scores so the UNIQUE constraint is guaranteed.
        # Old data is migrated: we keep only the best row per player.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scores_old AS
            SELECT * FROM scores WHERE 0
        """)   # dummy — just to check existence safely

        # Check if scores table already exists
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='scores'"
        ).fetchone()

        if existing:
            # Check if UNIQUE constraint exists on player column
            has_unique = False
            for row in conn.execute("PRAGMA index_list(scores)"):
                idx_name = row[1]
                unique   = row[2]
                if unique:
                    cols = conn.execute(f"PRAGMA index_info({idx_name})").fetchall()
                    if any(c[2] == 'player' for c in cols):
                        has_unique = True
                        break

            if not has_unique:
                print("⚙  Migrating scores table — adding UNIQUE constraint on player...")
                # Save best score per player from old table
                old_rows = conn.execute("""
                    SELECT player, MAX(score) as score,
                           accuracy, combo, level
                    FROM scores
                    GROUP BY player
                """).fetchall()

                conn.execute("DROP TABLE scores")

                conn.execute("""
                    CREATE TABLE scores (
                        id        INTEGER  PRIMARY KEY AUTOINCREMENT,
                        player    TEXT     NOT NULL UNIQUE,
                        score     INTEGER  NOT NULL DEFAULT 0,
                        accuracy  REAL     NOT NULL DEFAULT 0,
                        combo     INTEGER  NOT NULL DEFAULT 0,
                        level     INTEGER  NOT NULL DEFAULT 1,
                        updated   DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                for r in old_rows:
                    conn.execute("""
                        INSERT OR IGNORE INTO scores
                            (player, score, accuracy, combo, level)
                        VALUES (?, ?, ?, ?, ?)
                    """, (r[0], r[1], r[2] or 0, r[3] or 0, r[4] or 1))

                print(f"✅ Migration done — {len(old_rows)} player(s) kept.")
        else:
            # Fresh install — create scores table directly
            conn.execute("""
                CREATE TABLE scores (
                    id        INTEGER  PRIMARY KEY AUTOINCREMENT,
                    player    TEXT     NOT NULL UNIQUE,
                    score     INTEGER  NOT NULL DEFAULT 0,
                    accuracy  REAL     NOT NULL DEFAULT 0,
                    combo     INTEGER  NOT NULL DEFAULT 0,
                    level     INTEGER  NOT NULL DEFAULT 1,
                    updated   DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

        # Drop the dummy table we may have accidentally created
        conn.execute("DROP TABLE IF EXISTS scores_old")
        conn.commit()

    print(f"✅ Database ready: {DB_PATH}")


# ────────────────────────────────────────────
# DB helpers – users
# ────────────────────────────────────────────

def create_user(username, password):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, hash_password(password))
            )
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # username taken


def verify_user(username, password):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT password FROM users WHERE username = ?", (username,)
        ).fetchone()
    return row is not None and row[0] == hash_password(password)


# ────────────────────────────────────────────
# DB helpers – scores (upsert: keep best only)
# ────────────────────────────────────────────

def upsert_score(player, score, accuracy, combo, level):
    with sqlite3.connect(DB_PATH) as conn:
        existing = conn.execute(
            "SELECT score FROM scores WHERE player = ?", (player,)
        ).fetchone()

        if existing is None:
            # First game for this player
            conn.execute("""
                INSERT INTO scores (player, score, accuracy, combo, level, updated)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (player, score, accuracy, combo, level))
            print(f"  ↳ New entry: {player} → {score}")

        elif score > existing[0]:
            # New personal best
            conn.execute("""
                UPDATE scores
                SET score=?, accuracy=?, combo=?, level=?, updated=CURRENT_TIMESTAMP
                WHERE player=?
            """, (score, accuracy, combo, level, player))
            print(f"  ↳ Updated PB: {player} → {score} (was {existing[0]})")

        else:
            print(f"  ↳ No update: {player} scored {score}, best is {existing[0]}")

        conn.commit()


def get_scores(limit=10):
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """SELECT player, score, accuracy, combo, level
               FROM scores
               ORDER BY score DESC
               LIMIT ?""",
            (limit,)
        ).fetchall()
    return rows


def get_player_count():
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]


# ────────────────────────────────────────────
# Auth guard
# ────────────────────────────────────────────

def logged_in():
    return "player" in session


# ────────────────────────────────────────────
# Page routes
# ────────────────────────────────────────────

@app.route('/')
def home():
    if logged_in():
        return redirect('/index')
    return redirect('/register')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('name', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash('Username and password are required.', 'error')
            return render_template('registration.html')
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('registration.html')
        if create_user(username, password):
            session['player'] = username
            return redirect('/index')
        else:
            flash('Username already taken — try another or log in.', 'error')
            return render_template('registration.html')

    return render_template('registration.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('name', '').strip()
        password = request.form.get('password', '').strip()

        if verify_user(username, password):
            session['player'] = username
            return redirect('/index')
        else:
            flash('Invalid username or password.', 'error')
            return render_template('login.html')

    return render_template('login.html')


@app.route('/index')
def index():
    if not logged_in():
        return redirect('/login')
    return render_template('index.html', player=session['player'])


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# ────────────────────────────────────────────
# API routes
# ────────────────────────────────────────────

@app.route('/api/save_score', methods=['POST'])
def save_score():
    if not logged_in():
        return jsonify({"status": "error", "message": "not logged in"}), 401

    data     = request.get_json(silent=True) or {}
    player   = session.get('player', 'Player')
    score    = int(data.get('score', 0))
    level    = int(data.get('level', 1))
    accuracy = float(data.get('accuracy', 0))
    combo    = int(data.get('combo', 0))

    print(f"\n💾 save_score: player={player} score={score} level={level} acc={accuracy} combo={combo}")
    upsert_score(player, score, accuracy, combo, level)
    return jsonify({"status": "ok", "player": player, "score": score})


@app.route('/api/leaderboard')
def leaderboard():
    rows = get_scores()
    result = [
        {
            "player":   r[0],
            "score":    r[1],
            "accuracy": round(float(r[2]), 1),
            "combo":    r[3],
            "level":    r[4],
        }
        for r in rows
    ]
    print(f"📊 leaderboard: {len(result)} entries")
    return jsonify(result)


@app.route('/api/best_score')
def best_score():
    rows = get_scores(limit=1)
    if rows:
        return jsonify({"player": rows[0][0], "score": rows[0][1]})
    return jsonify({"player": "-", "score": 0})


@app.route('/api/player_count')
def player_count():
    return jsonify({"players": get_player_count()})


# ── Debug: confirm DB path & tables ───────────
@app.route('/api/db_info')
def db_info():
    exists = os.path.isfile(DB_PATH)
    info   = {"db_path": DB_PATH, "exists": exists}
    if exists:
        info["size_kb"] = round(os.path.getsize(DB_PATH) / 1024, 2)
        with sqlite3.connect(DB_PATH) as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            info["tables"] = tables
            info["user_count"]  = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            info["score_count"] = conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
    return jsonify(info)


# ────────────────────────────────────────────
# Entry point
# ────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    app.run(debug=True)