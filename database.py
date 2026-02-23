import sqlite3
import config

def get_conn():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        price REAL NOT NULL,
        auto_delivery INTEGER DEFAULT 0,
        stock_count INTEGER DEFAULT 0,
        enabled INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        used INTEGER DEFAULT 0,
        order_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        username TEXT,
        product_id INTEGER NOT NULL,
        product_name TEXT,
        amount REAL NOT NULL,
        payment_address TEXT,
        status TEXT DEFAULT 'pending',
        auto_delivery INTEGER DEFAULT 0,
        delivery_content TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        paid_at TIMESTAMP,
        delivered_at TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        banned INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

# ===== 商品 =====
def get_products(enabled_only=True):
    conn = get_conn()
    if enabled_only:
        rows = conn.execute("SELECT * FROM products WHERE enabled=1 ORDER BY id").fetchall()
    else:
        rows = conn.execute("SELECT * FROM products ORDER BY id").fetchall()
    conn.close()
    return rows

def get_product(pid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    conn.close()
    return row

def add_product(name, description, price, auto_delivery):
    conn = get_conn()
    conn.execute("INSERT INTO products (name,description,price,auto_delivery) VALUES (?,?,?,?)",
                 (name, description, price, auto_delivery))
    conn.commit()
    pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return pid

def update_product_price(pid, price):
    conn = get_conn()
    conn.execute("UPDATE products SET price=? WHERE id=?", (price, pid))
    conn.commit()
    conn.close()

def toggle_product(pid, enabled):
    conn = get_conn()
    conn.execute("UPDATE products SET enabled=? WHERE id=?", (enabled, pid))
    conn.commit()
    conn.close()

def delete_product(pid):
    conn = get_conn()
    conn.execute("DELETE FROM products WHERE id=?", (pid,))
    conn.execute("DELETE FROM cards WHERE product_id=?", (pid,))
    conn.commit()
    conn.close()

def update_stock_count(pid):
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM cards WHERE product_id=? AND used=0", (pid,)).fetchone()[0]
    conn.execute("UPDATE products SET stock_count=? WHERE id=?", (count, pid))
    conn.commit()
    conn.close()

# ===== 卡密 =====
def add_cards(pid, contents):
    conn = get_conn()
    for c in contents:
        c = c.strip()
        if c:
            conn.execute("INSERT INTO cards (product_id,content) VALUES (?,?)", (pid, c))
    conn.commit()
    conn.close()
    update_stock_count(pid)

def get_available_card(pid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM cards WHERE product_id=? AND used=0 LIMIT 1", (pid,)).fetchone()
    conn.close()
    return row

def mark_card_used(card_id, order_id):
    conn = get_conn()
    conn.execute("UPDATE cards SET used=1,order_id=? WHERE id=?", (order_id, card_id))
    conn.commit()
    conn.close()

# ===== 订单 =====
def create_order(user_id, username, pid, product_name, amount, auto_delivery):
    conn = get_conn()
    conn.execute(
        "INSERT INTO orders (user_id,username,product_id,product_name,amount,payment_address,auto_delivery) VALUES (?,?,?,?,?,?,?)",
        (user_id, username, pid, product_name, amount, config.USDT_WALLET, auto_delivery)
    )
    conn.commit()
    oid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return oid

def get_order(oid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    conn.close()
    return row

def get_user_orders(user_id, limit=10):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                        (user_id, limit)).fetchall()
    conn.close()
    return rows

def get_pending_orders():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM orders WHERE status='pending' ORDER BY created_at ASC").fetchall()
    conn.close()
    return rows

def get_paid_orders():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM orders WHERE status='paid' AND auto_delivery=0 ORDER BY created_at DESC").fetchall()
    conn.close()
    return rows

def get_all_orders(limit=20):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return rows

def mark_order_paid(oid):
    conn = get_conn()
    conn.execute("UPDATE orders SET status='paid',paid_at=CURRENT_TIMESTAMP WHERE id=?", (oid,))
    conn.commit()
    conn.close()

def mark_order_delivered(oid, content):
    conn = get_conn()
    conn.execute("UPDATE orders SET status='delivered',delivery_content=?,delivered_at=CURRENT_TIMESTAMP WHERE id=?",
                 (content, oid))
    conn.commit()
    conn.close()

def cancel_order(oid):
    conn = get_conn()
    conn.execute("UPDATE orders SET status='cancelled' WHERE id=?", (oid,))
    conn.commit()
    conn.close()

# ===== 用户 =====
def upsert_user(user_id, username, first_name):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO users (user_id,username,first_name) VALUES (?,?,?)",
                 (user_id, username, first_name))
    conn.commit()
    conn.close()

def is_banned(user_id):
    conn = get_conn()
    row = conn.execute("SELECT banned FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row and row['banned'] == 1

def ban_user(user_id, ban=True):
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.execute("UPDATE users SET banned=? WHERE user_id=?", (1 if ban else 0, user_id))
    conn.commit()
    conn.close()

def get_all_users():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    conn.close()
    return rows
