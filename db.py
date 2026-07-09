import os
import sqlite3
import pymysql
from flask import g, current_app


def _init_sqlite_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            phone TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            duration TEXT NOT NULL,
            category TEXT DEFAULT 'General',
            image_url TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            selected_services TEXT NOT NULL,
            preferred_date TEXT NOT NULL,
            preferred_time TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            comment TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )

    conn.execute(
        "INSERT OR IGNORE INTO users (full_name, username, phone, email, password_hash, is_admin) VALUES (?,?,?,?,?,?)",
        (
            'Komali',
            'komali',
            '0000000000',
            'komali@newshades.com',
            '$2b$12$zA9WEAEz5EdojsMEXZZ7iuUxep7B/inOz.kiEWIZeDVB9pl1VttYe',
            1,
        ),
    )

    conn.execute("SELECT COUNT(*) AS c FROM services")
    if conn.execute("SELECT COUNT(*) AS c FROM services").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO services (service_name, description, price, duration, category) VALUES (?,?,?,?,?)",
            [
                ('Hair Cut', 'Professional haircut styled to your preference', 300.00, '30 mins', 'Hair'),
                ('Beard Trim', 'Clean beard shaping and trimming', 150.00, '20 mins', 'Beard'),
                ('Hair Color', 'Full hair coloring with premium products', 800.00, '90 mins', 'Hair'),
                ('Facial', 'Deep cleansing facial treatment', 500.00, '45 mins', 'Skin'),
                ('Head Massage', 'Relaxing scalp and head massage', 250.00, '30 mins', 'Wellness'),
                ('Hair Spa', 'Nourishing hair spa treatment', 600.00, '60 mins', 'Hair'),
            ],
        )
    conn.commit()


def _connect_sqlite():
    db_path = current_app.config.get('SQLITE_DB_PATH') or os.path.join(current_app.root_path, 'salon_app.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA foreign_keys = ON')
        _init_sqlite_schema(conn)
    except Exception:
        conn.close()
        raise
    return conn


def get_db():
    if 'db' not in g:
        cfg = current_app.config
        try:
            g.db = pymysql.connect(
                host=cfg['MYSQL_HOST'],
                user=cfg['MYSQL_USER'],
                password=cfg['MYSQL_PASSWORD'],
                database=cfg['MYSQL_DB'],
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,
            )
            g.db_backend = 'mysql'
        except Exception:
            g.db = _connect_sqlite()
            g.db_backend = 'sqlite'
    else:
        if g.get('db_backend') == 'mysql':
            try:
                g.db.ping(reconnect=True)
            except Exception:
                g.pop('db', None)
                g.pop('db_backend', None)
                return get_db()
        else:
            try:
                g.db.execute('SELECT 1')
            except Exception:
                g.pop('db', None)
                g.pop('db_backend', None)
                return get_db()
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db:
        db.close()
    g.pop('db_backend', None)


def _normalize_sql(sql):
    import re
    sql = sql.replace('%s', '?')
    sql = re.sub(r'ON DUPLICATE KEY UPDATE\s+\S+\s*=\s*\?', '', sql)
    sql = sql.replace('INSERT INTO', 'INSERT OR REPLACE INTO')
    sql = re.sub(r'`(\w+)`', r'\1', sql)
    return sql


def query(sql, args=(), one=False):
    conn = get_db()
    if g.get('db_backend') == 'sqlite':
        cur = conn.execute(_normalize_sql(sql), tuple(args))
        rows = [dict(row) for row in cur.fetchall()]
        return (rows[0] if rows else None) if one else rows

    cur = conn.cursor()
    cur.execute(sql, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv


def execute(sql, args=()):
    conn = get_db()
    if g.get('db_backend') == 'sqlite':
        cur = conn.execute(_normalize_sql(sql), tuple(args))
        conn.commit()
        return cur.lastrowid

    cur = conn.cursor()
    cur.execute(sql, args)
    cur.close()
    return cur.lastrowid
