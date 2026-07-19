import os
import re
import sqlite3
import pymysql
from flask import g, current_app

# ── Seed data (no hardcoded credentials) ─────────────────────────────────────

def _seed_admin_params():
    """Return admin seed params from env or safe defaults (no real password hardcoded)."""
    return (
        os.environ.get('SEED_ADMIN_NAME',     'Admin'),
        os.environ.get('SEED_ADMIN_USERNAME', 'admin'),
        os.environ.get('SEED_ADMIN_PHONE',    '0000000000'),
        os.environ.get('SEED_ADMIN_EMAIL',    'admin@newshades.com'),
        os.environ.get('SEED_ADMIN_HASH',     '$2b$12$zA9WEAEz5EdojsMEXZZ7iuUxep7B/inOz.kiEWIZeDVB9pl1VttYe'),
    )

_DEFAULT_SERVICES = [
    ('Hair Cut',     'Professional haircut styled to your preference', 300.00, '30 mins', 'Hair'),
    ('Beard Trim',   'Clean beard shaping and trimming',               150.00, '20 mins', 'Beard'),
    ('Hair Color',   'Full hair coloring with premium products',       800.00, '90 mins', 'Hair'),
    ('Facial',       'Deep cleansing facial treatment',                500.00, '45 mins', 'Skin'),
    ('Head Massage', 'Relaxing scalp and head massage',                250.00, '30 mins', 'Wellness'),
    ('Hair Spa',     'Nourishing hair spa treatment',                  600.00, '60 mins', 'Hair'),
]


# ── Schema helpers ────────────────────────────────────────────────────────────

def _init_sqlite_schema(conn):
    conn.executescript("""
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
            ticket_id TEXT,
            ticket_expires_at TEXT,
            total_price REAL DEFAULT 0,
            discount_percent REAL DEFAULT 0,
            offer_applied TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS blocked_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            block_date TEXT NOT NULL,
            block_time TEXT,
            reason TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS salon_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
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
        CREATE TABLE IF NOT EXISTS gallery (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            caption TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            discount_text TEXT DEFAULT '',
            discount_percent REAL DEFAULT 0,
            applicable_services TEXT DEFAULT '',
            valid_from DATE,
            valid_until DATE,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    params = _seed_admin_params()
    conn.execute(
        "INSERT OR IGNORE INTO users (full_name, username, phone, email, password_hash, is_admin) VALUES (?,?,?,?,?,?)",
        (*params, 1),
    )
    if conn.execute("SELECT COUNT(*) FROM services").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO services (service_name, description, price, duration, category) VALUES (?,?,?,?,?)",
            _DEFAULT_SERVICES,
        )
    conn.commit()


def _init_pg_schema(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            full_name VARCHAR(100) NOT NULL,
            username VARCHAR(50) UNIQUE NOT NULL,
            phone VARCHAR(20) NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            is_admin SMALLINT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS services (
            id SERIAL PRIMARY KEY,
            service_name VARCHAR(100) NOT NULL,
            description TEXT,
            price NUMERIC(10,2) NOT NULL,
            duration VARCHAR(50) NOT NULL,
            category VARCHAR(50) DEFAULT 'General',
            image_url VARCHAR(255) DEFAULT '',
            is_active SMALLINT DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS appointments (
            id SERIAL PRIMARY KEY,
            user_id INT NOT NULL,
            selected_services TEXT NOT NULL,
            preferred_date DATE NOT NULL,
            preferred_time VARCHAR(20),
            status VARCHAR(20) DEFAULT 'Pending',
            ticket_id VARCHAR(20),
            ticket_expires_at TIMESTAMP,
            total_price NUMERIC(10,2) DEFAULT 0,
            discount_percent NUMERIC(5,2) DEFAULT 0,
            offer_applied VARCHAR(150) DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS blocked_slots (
            id SERIAL PRIMARY KEY,
            block_date DATE NOT NULL,
            block_time VARCHAR(20),
            reason VARCHAR(255) DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS salon_config (
            key VARCHAR(100) PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (
            key VARCHAR(100) PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reviews (
            id SERIAL PRIMARY KEY,
            user_id INT NOT NULL,
            rating INT NOT NULL CHECK(rating BETWEEN 1 AND 5),
            comment TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS gallery (
            id SERIAL PRIMARY KEY,
            filename VARCHAR(255) NOT NULL,
            caption VARCHAR(255) DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS offers (
            id SERIAL PRIMARY KEY,
            title VARCHAR(150) NOT NULL,
            description TEXT DEFAULT '',
            discount_text VARCHAR(100) DEFAULT '',
            discount_percent NUMERIC(5,2) DEFAULT 0,
            applicable_services TEXT DEFAULT '',
            valid_from DATE,
            valid_until DATE,
            is_active SMALLINT DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    params = _seed_admin_params()
    cur.execute("""
        INSERT INTO users (full_name, username, phone, email, password_hash, is_admin)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON CONFLICT (username) DO NOTHING
    """, (*params, 1))
    cur.execute("SELECT COUNT(*) FROM services")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO services (service_name, description, price, duration, category) VALUES (%s,%s,%s,%s,%s)",
            _DEFAULT_SERVICES,
        )
    conn.commit()
    cur.close()


def _init_mysql_schema(conn):
    cur = conn.cursor()
    stmts = [
        """CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            full_name VARCHAR(100) NOT NULL,
            username VARCHAR(50) UNIQUE NOT NULL,
            phone VARCHAR(20) NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            is_admin TINYINT(1) DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) CHARACTER SET utf8mb4""",
        """CREATE TABLE IF NOT EXISTS services (
            id INT AUTO_INCREMENT PRIMARY KEY,
            service_name VARCHAR(100) NOT NULL,
            description TEXT,
            price DECIMAL(10,2) NOT NULL,
            duration VARCHAR(50) NOT NULL,
            category VARCHAR(50) DEFAULT 'General',
            image_url VARCHAR(255) DEFAULT '',
            is_active TINYINT(1) DEFAULT 1
        ) CHARACTER SET utf8mb4""",
        """CREATE TABLE IF NOT EXISTS appointments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            selected_services TEXT NOT NULL,
            preferred_date DATE NOT NULL,
            preferred_time VARCHAR(20),
            status ENUM('Pending','Confirmed','Cancelled','Rejected','Checked In','Completed') DEFAULT 'Pending',
            ticket_id VARCHAR(20),
            ticket_expires_at DATETIME,
            total_price DECIMAL(10,2) DEFAULT 0,
            discount_percent DECIMAL(5,2) DEFAULT 0,
            offer_applied VARCHAR(150) DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) CHARACTER SET utf8mb4""",
        """CREATE TABLE IF NOT EXISTS blocked_slots (
            id INT AUTO_INCREMENT PRIMARY KEY,
            block_date DATE NOT NULL,
            block_time VARCHAR(20),
            reason VARCHAR(255) DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) CHARACTER SET utf8mb4""",
        """CREATE TABLE IF NOT EXISTS salon_config (
            `key` VARCHAR(100) PRIMARY KEY,
            value TEXT NOT NULL
        ) CHARACTER SET utf8mb4""",
        """CREATE TABLE IF NOT EXISTS settings (
            `key` VARCHAR(100) PRIMARY KEY,
            value TEXT NOT NULL
        ) CHARACTER SET utf8mb4""",
        """CREATE TABLE IF NOT EXISTS reviews (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            rating INT NOT NULL,
            comment TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) CHARACTER SET utf8mb4""",
        """CREATE TABLE IF NOT EXISTS gallery (
            id INT AUTO_INCREMENT PRIMARY KEY,
            filename VARCHAR(255) NOT NULL,
            caption VARCHAR(255) DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) CHARACTER SET utf8mb4""",
        """CREATE TABLE IF NOT EXISTS offers (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(150) NOT NULL,
            description TEXT DEFAULT '',
            discount_text VARCHAR(100) DEFAULT '',
            discount_percent DECIMAL(5,2) DEFAULT 0,
            applicable_services TEXT DEFAULT '',
            valid_from DATE,
            valid_until DATE,
            is_active TINYINT(1) DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) CHARACTER SET utf8mb4""",
    ]
    for stmt in stmts:
        try:
            cur.execute(stmt)
        except pymysql.err.OperationalError as e:
            current_app.logger.warning('Schema stmt failed: %s', e)

    cur.execute("SHOW COLUMNS FROM appointments")
    existing_cols = {row['Field'] for row in cur.fetchall()}
    alter_stmts = [
        ("ALTER TABLE appointments ADD COLUMN ticket_expires_at DATETIME",          "ticket_expires_at"),
        ("ALTER TABLE appointments ADD COLUMN total_price DECIMAL(10,2) DEFAULT 0", "total_price"),
        ("ALTER TABLE appointments ADD COLUMN discount_percent DECIMAL(5,2) DEFAULT 0", "discount_percent"),
        ("ALTER TABLE appointments ADD COLUMN offer_applied VARCHAR(150) DEFAULT ''", "offer_applied"),
        ("ALTER TABLE appointments ADD COLUMN ticket_id VARCHAR(20)",               "ticket_id"),
    ]
    for stmt, col in alter_stmts:
        if col not in existing_cols:
            try:
                cur.execute(stmt)
            except pymysql.err.OperationalError as e:
                current_app.logger.warning('ALTER failed (%s): %s', col, e)

    params = _seed_admin_params()
    cur.execute(
        "INSERT IGNORE INTO users (full_name, username, phone, email, password_hash, is_admin) VALUES (%s,%s,%s,%s,%s,%s)",
        (*params, 1)
    )
    cur.execute("SELECT COUNT(*) as c FROM services")
    if cur.fetchone()['c'] == 0:
        cur.executemany(
            "INSERT INTO services (service_name, description, price, duration, category) VALUES (%s,%s,%s,%s,%s)",
            _DEFAULT_SERVICES
        )
    cur.close()


# ── Connection ────────────────────────────────────────────────────────────────

def _connect_sqlite():
    db_path = current_app.config.get('SQLITE_DB_PATH') or \
              os.path.join(current_app.root_path, 'salon_app.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        _init_sqlite_schema(conn)
        return conn
    except sqlite3.DatabaseError:
        conn.close()
        raise


def get_db():
    if 'db' not in g:
        cfg    = current_app.config
        db_url = cfg.get('DATABASE_URL', '')

        # 1. PostgreSQL (Render / production)
        if db_url:
            try:
                import psycopg2
                import psycopg2.extras
                if db_url.startswith('postgres://'):
                    db_url = db_url.replace('postgres://', 'postgresql://', 1)
                g.db = psycopg2.connect(db_url, cursor_factory=psycopg2.extras.RealDictCursor,
                                        connect_timeout=10)
                g.db.autocommit = False
                g.db_backend = 'postgres'
                _init_pg_schema(g.db)
                return g.db
            except Exception as e:
                current_app.logger.warning('PostgreSQL connection failed: %s', e)

        # 2. MySQL (local dev)
        try:
            conn = pymysql.connect(
                host=cfg['MYSQL_HOST'],
                user=cfg['MYSQL_USER'],
                password=cfg['MYSQL_PASSWORD'],
                database=cfg['MYSQL_DB'],
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,
                connect_timeout=5,
            )
            _init_mysql_schema(conn)
            g.db = conn
            g.db_backend = 'mysql'
            return g.db
        except Exception as e:
            current_app.logger.warning('MySQL connection failed: %s', e)

        # 3. SQLite fallback
        g.db = _connect_sqlite()
        g.db_backend = 'sqlite'

    else:
        # Health-check existing connection
        backend = g.get('db_backend')
        if backend == 'postgres':
            try:
                cur = g.db.cursor()
                cur.execute('SELECT 1')
                cur.close()
            except Exception:
                g.pop('db', None)
                g.pop('db_backend', None)
                return get_db()
        elif backend == 'mysql':
            try:
                g.db.ping(reconnect=True)
            except Exception:
                g.pop('db', None)
                g.pop('db_backend', None)
                return get_db()

    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db:
        try:
            db.close()
        except Exception:
            pass
    g.pop('db_backend', None)


# ── SQL normalisation (SQLite only) ──────────────────────────────────────────

def _normalize_sql(sql):
    sql = sql.replace('%s', '?')
    sql = re.sub(r'ON DUPLICATE KEY UPDATE\s+\S+\s*=\s*\?', '', sql)
    sql = re.sub(r'\bINSERT INTO\b', 'INSERT OR IGNORE INTO', sql)
    sql = re.sub(r'`(\w+)`', r'\1', sql)
    return sql


# ── Public API ────────────────────────────────────────────────────────────────

def query(sql, args=(), one=False):
    conn    = get_db()
    backend = g.get('db_backend')

    if backend == 'sqlite':
        cur  = conn.execute(_normalize_sql(sql), tuple(args))
        rows = [dict(r) for r in cur.fetchall()]
        return (rows[0] if rows else None) if one else rows

    if backend == 'postgres':
        sql = re.sub(r'`(\w+)`', r'"\1"', sql)
        sql = _pg_upsert(sql)
        cur = conn.cursor()
        cur.execute(sql, args)
        rows = cur.fetchall()
        cur.close()
        return (rows[0] if rows else None) if one else (rows or [])

    # MySQL
    cur = conn.cursor()
    cur.execute(sql, args)
    rv  = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv


def execute(sql, args=()):
    conn    = get_db()
    backend = g.get('db_backend')

    if backend == 'sqlite':
        cur = conn.execute(_normalize_sql(sql), tuple(args))
        conn.commit()
        return cur.lastrowid

    if backend == 'postgres':
        sql = re.sub(r'`(\w+)`', r'"\1"', sql)
        sql = _pg_upsert(sql)
        cur = conn.cursor()
        if sql.strip().upper().startswith('INSERT'):
            cur.execute(sql + ' RETURNING id', args)
            row = cur.fetchone()
            conn.commit()
            cur.close()
            return row['id'] if row else None
        cur.execute(sql, args)
        conn.commit()
        cur.close()
        return None

    # MySQL
    cur     = conn.cursor()
    cur.execute(sql, args)
    last_id = cur.lastrowid
    cur.close()
    return last_id


def _pg_upsert(sql):
    pattern = re.compile(
        r"INSERT INTO\s+(`?\w+`?)\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)\s*ON DUPLICATE KEY UPDATE\s+(.+)",
        re.IGNORECASE | re.DOTALL
    )
    m = pattern.match(sql.strip())
    if not m:
        return sql
    table   = m.group(1).strip('`"')
    cols    = [c.strip().strip('`"') for c in m.group(2).split(',')]
    vals    = m.group(3)
    updates = m.group(4).strip()
    set_parts = []
    for part in re.split(r',\s*(?=\w)', updates):
        col_match = re.match(r'`?(\w+)`?\s*=\s*(.+)', part.strip())
        if col_match:
            set_parts.append(f'"{col_match.group(1)}" = {col_match.group(2)}')
    cols_quoted = ', '.join(f'"{c}"' for c in cols)
    return (
        f'INSERT INTO "{table}" ({cols_quoted}) VALUES ({vals}) '
        f'ON CONFLICT ("{cols[0]}") DO UPDATE SET {", ".join(set_parts)}'
    )
