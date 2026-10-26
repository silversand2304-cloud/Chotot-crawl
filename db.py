import json
import os
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    list_id TEXT PRIMARY KEY,
    title TEXT,
    price INTEGER,
    key TEXT,
    label TEXT,
    market TEXT,
    condition TEXT,
    region TEXT,
    seller TEXT,
    url TEXT,
    posted_at REAL,
    first_seen REAL,
    last_seen REAL,
    attrs TEXT,
    battery REAL,
    cosmetic REAL,
    orig_posted_at REAL,
    checked_at REAL,
    gone_at REAL,
    gone_status TEXT
);
CREATE INDEX IF NOT EXISTS idx_key_seen ON listings(key, first_seen);
CREATE TABLE IF NOT EXISTS alerts (
    list_id TEXT PRIMARY KEY,
    kind TEXT,
    price INTEGER,
    median REAL,
    discount REAL,
    n INTEGER,
    created_at REAL,
    sent INTEGER,
    adj_price REAL
);
CREATE INDEX IF NOT EXISTS idx_alert_time ON alerts(created_at);
CREATE TABLE IF NOT EXISTS status (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS sim_truth (list_id TEXT PRIMARY KEY, truth TEXT, fair INTEGER);
-- 1 tin có thể khớp nhiều từ khóa ("macbook air" và "macbook air m2"; "iphone 15" và "iphone 15 pro max"):
-- mỗi (tin, nhóm, từ khóa) 1 dòng, để thống kê và xuất dữ liệu theo từ khóa không thiếu tin.
-- watch = '' : tin từ bản cũ chưa gắn từ khóa. listings.key/label = nhóm của từ khóa thấy tin đầu tiên.
CREATE TABLE IF NOT EXISTS listing_keys (
    list_id TEXT NOT NULL,
    key TEXT NOT NULL,
    label TEXT,
    watch TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (list_id, key, watch)
);
CREATE INDEX IF NOT EXISTS idx_lk_key ON listing_keys(key);
CREATE INDEX IF NOT EXISTS idx_lk_watch ON listing_keys(watch);
-- Tin bị loại kèm lý do (không lưu mô tả): tab "Tin bỏ qua". Mỗi (tin, từ khóa) 1 dòng, thấy lại thì cập nhật last_seen.
CREATE TABLE IF NOT EXISTS skipped (
    list_id TEXT NOT NULL,
    watch TEXT NOT NULL DEFAULT '',
    reason TEXT,
    detail TEXT,
    title TEXT,
    price INTEGER,
    region TEXT,
    seller TEXT,
    category TEXT,
    url TEXT,
    first_seen REAL,
    last_seen REAL,
    PRIMARY KEY (list_id, watch)
);
CREATE INDEX IF NOT EXISTS idx_skipped_seen ON skipped(last_seen);
CREATE INDEX IF NOT EXISTS idx_skipped_watch ON skipped(watch, reason);
-- Cài đặt đặt từ dashboard (vd. nhịp quét mặc định), khác bảng status (trạng thái collector tự ghi)
CREATE TABLE IF NOT EXISTS settings (k TEXT PRIMARY KEY, v TEXT);
"""

LISTING_COLS = ("list_id", "title", "price", "key", "label", "market", "condition", "region",
                "seller", "url", "posted_at", "first_seen", "last_seen", "attrs", "battery", "cosmetic",
                "orig_posted_at")
NEW_COLS = {"listings": {"attrs": "TEXT", "battery": "REAL", "cosmetic": "REAL", "orig_posted_at": "REAL",
                         "checked_at": "REAL", "gone_at": "REAL", "gone_status": "TEXT"},
            "alerts": {"adj_price": "REAL"}}


def _migrate(conn):
    """DB tạo từ bản cũ thiếu cột mới thì thêm vào (không mất dữ liệu)."""
    for table, cols in NEW_COLS.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, kind in cols.items():
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {kind}")
    # tin ghi bởi bản cũ (chưa có listing_keys) — kể cả khi bản cũ vẫn đang chạy song song
    conn.execute("INSERT OR IGNORE INTO listing_keys (list_id, key, label) "
                 "SELECT list_id, key, label FROM listings l WHERE key IS NOT NULL AND NOT EXISTS "
                 "(SELECT 1 FROM listing_keys k WHERE k.list_id = l.list_id)")
    conn.commit()


def connect(path):
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if path != ":memory:":
        conn.execute("PRAGMA journal_mode=WAL")  # web đọc trong khi collector ghi
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def insert_if_new(conn, row):
    """Thêm tin mới; tin đã có thì chỉ cập nhật last_seen (= lần cuối biết chắc tin còn đăng).
    Trả True nếu là tin mới. attrs (mã thô của Chợ Tốt) lưu dạng JSON để chuẩn hóa lại khi luật thay đổi.
    row["watch"] (tùy chọn) = tên từ khóa đã tìm thấy tin; tin cũng được ghi vào nhóm của từ khóa đó."""
    if row.get("key"):
        add_key(conn, row["list_id"], row["key"], row.get("label"), row.get("watch"), commit=False)
    row = {c: row.get(c) for c in LISTING_COLS}
    if isinstance(row["attrs"], dict):
        row["attrs"] = json.dumps(row["attrs"])
    row["last_seen"] = row["last_seen"] or row["first_seen"]
    cur = conn.execute(
        f"INSERT OR IGNORE INTO listings ({', '.join(LISTING_COLS)}) "
        f"VALUES ({', '.join(':' + c for c in LISTING_COLS)})",
        row,
    )
    if cur.rowcount != 1:  # thấy lại trong kết quả tìm kiếm: còn đăng (kể cả từng bị ẩn rồi hiện lại)
        conn.execute("UPDATE listings SET last_seen = ?, gone_at = NULL, gone_status = NULL WHERE list_id = ?",
                     (row["last_seen"], row["list_id"]))
    conn.commit()
    return cur.rowcount == 1


def add_key(conn, list_id, key, label, watch=None, commit=True):
    """Ghi tin vào nhóm `key` của từ khóa `watch`. Trả True nếu tin mới với từ khóa này."""
    watch = watch or ""
    cur = conn.execute("INSERT OR IGNORE INTO listing_keys (list_id, key, label, watch) VALUES (?, ?, ?, ?)",
                       (list_id, key, label, watch))
    if watch:  # đã biết từ khóa: bỏ dòng "chưa gắn từ khóa" của bản cũ
        conn.execute("DELETE FROM listing_keys WHERE list_id = ? AND key = ? AND watch = ''", (list_id, key))
    if commit:
        conn.commit()
    return cur.rowcount == 1


def assign_watches(conn, watch_of):
    """Gắn tên từ khóa cho các dòng chưa có (dữ liệu từ bản cũ). watch_of(key) -> tên hoặc None."""
    n = 0
    for (key,) in conn.execute("SELECT DISTINCT key FROM listing_keys WHERE watch = ''").fetchall():
        name = watch_of(key)
        if name:
            n += conn.execute("UPDATE OR REPLACE listing_keys SET watch = ? WHERE key = ? AND watch = ''",
                              (name, key)).rowcount
    conn.commit()
    return n


def has_watch(conn, name):
    return conn.execute("SELECT 1 FROM listing_keys WHERE watch = ? LIMIT 1", (name,)).fetchone() is not None


def watch_counts(conn, since):
    """{tên từ khóa: (số tin trong cửa sổ, tổng số tin, số nhóm, lần cuối thấy tin mới)}."""
    return {r[0]: tuple(r[1:]) for r in conn.execute(
        "SELECT k.watch, COUNT(DISTINCT CASE WHEN l.first_seen >= ? THEN l.list_id END), "
        "COUNT(DISTINCT l.list_id), COUNT(DISTINCT k.key), MAX(l.first_seen) "
        "FROM listing_keys k JOIN listings l USING (list_id) WHERE k.watch != '' GROUP BY k.watch",
        (since,)).fetchall()}


def forget_watch(conn, name):
    """Xóa dữ liệu của 1 từ khóa: bỏ tin khỏi các nhóm của từ khóa đó; tin không còn thuộc từ khóa nào
    thì xóa hẳn. Trả số tin bị xóa hẳn."""
    conn.execute("DELETE FROM listing_keys WHERE watch = ?", (name,))
    conn.execute("DELETE FROM skipped WHERE watch = ?", (name,))
    conn.execute("DELETE FROM status WHERE k IN (?, ?)", (f"seeded:{name}", f"scanned:{name}"))  # thêm lại thì nạp lại
    return purge_orphans(conn)


def purge_orphans(conn):
    """Xóa tin không còn thuộc nhóm nào; nhóm chính của tin (listings.key) phải là 1 trong các nhóm còn
    lại của tin đó. Trả số tin bị xóa."""
    n = conn.execute("DELETE FROM listings WHERE list_id NOT IN (SELECT list_id FROM listing_keys)").rowcount
    conn.execute("DELETE FROM alerts WHERE list_id NOT IN (SELECT list_id FROM listings)")
    conn.execute("UPDATE listings SET key = k.key, label = k.label FROM "
                 "(SELECT list_id, MIN(key) AS key, MIN(label) AS label FROM listing_keys GROUP BY list_id) k "
                 "WHERE k.list_id = listings.list_id AND listings.key NOT IN "
                 "(SELECT key FROM listing_keys WHERE list_id = listings.list_id)")
    conn.commit()
    return n


# ---------------------------------------------------------------- theo dõi tin còn/mất
def due_for_check(conn, now, interval_hours, track_days, limit, flagged=()):
    """Tin cần kiểm tra lại: chưa mất, thấy trong `track_days` ngày gần đây, lâu chưa xác nhận còn.
    Ưu tiên tin cá nhân (bán 1 máy, biến mất ≈ đã bán) và máy zin; tin lâu chưa xác nhận nhất trước."""
    marks = ",".join("?" * len(flagged)) or "''"
    return [r[0] for r in conn.execute(
        f"SELECT list_id FROM listings WHERE gone_at IS NULL AND first_seen >= ? AND last_seen <= ? "
        f"ORDER BY (seller != 'cá nhân'), (condition IN ({marks})), last_seen LIMIT ?",
        (now - track_days * 86400, now - interval_hours * 3600, *flagged, limit)).fetchall()]


def mark_alive(conn, list_id, now, orig_posted_at=None):
    conn.execute("UPDATE listings SET last_seen = ?, checked_at = ?, "
                 "orig_posted_at = COALESCE(orig_posted_at, ?) WHERE list_id = ?",
                 (now, now, orig_posted_at, list_id))
    conn.commit()


def mark_gone(conn, list_id, now, status):
    conn.execute("UPDATE listings SET gone_at = ?, gone_status = ?, checked_at = ? WHERE list_id = ?",
                 (now, status, now, list_id))
    conn.commit()


def tracking_rows(conn):
    return conn.execute(
        "SELECT list_id, key, condition, price, battery, cosmetic, seller, first_seen, last_seen, "
        "gone_at, gone_status, orig_posted_at FROM listings WHERE orig_posted_at IS NOT NULL").fetchall()


def set_key(conn, list_id, norm, attrs=None, old_key=None):
    """Chuyển tin sang nhóm khác (sau khi đọc mô tả / đổi luật). old_key: nhóm cũ trong listing_keys
    (mặc định = nhóm chính của tin)."""
    if old_key is None:
        r = conn.execute("SELECT key FROM listings WHERE list_id = ?", (list_id,)).fetchone()
        old_key = r[0] if r else None
    conn.execute("UPDATE OR REPLACE listing_keys SET key = ?, label = ? WHERE list_id = ? AND key = ?",
                 (norm["key"], norm["label"], list_id, old_key))
    if not conn.execute("SELECT 1 FROM listing_keys WHERE list_id = ?", (list_id,)).fetchone():
        add_key(conn, list_id, norm["key"], norm["label"], commit=False)
    conn.execute("UPDATE listings SET key = ?, label = ?, market = ?, condition = ? WHERE list_id = ? AND "
                 "(key = ? OR key IS NULL)",
                 (norm["key"], norm["label"], norm["market"], norm["condition"], list_id, old_key))
    if attrs is not None:
        conn.execute("UPDATE listings SET attrs = ?, battery = ?, cosmetic = ? WHERE list_id = ?",
                     (json.dumps(attrs), attrs.get("battery"), attrs.get("cosmetic"), list_id))
    conn.commit()


# tin thuộc nhóm (qua bất kỳ từ khóa nào), mỗi tin tính 1 lần
_IN_GROUP = ("FROM listings l WHERE l.list_id IN (SELECT list_id FROM listing_keys WHERE key = ?) "
             "AND l.first_seen >= ? AND l.list_id != ?")


def prices(conn, key, since, exclude=None, until=None):
    sql = "SELECT l.price " + _IN_GROUP
    args = [key, since, exclude or ""]
    if until is not None:
        sql += " AND l.first_seen < ?"
        args.append(until)
    return [r[0] for r in conn.execute(sql, args).fetchall()]


def history(conn, key, since, exclude=None):
    """[(giá, pin %, ngoại hình %)] của 1 nhóm — để quy đổi giá theo tình trạng máy trước khi so."""
    return [tuple(r) for r in conn.execute(
        "SELECT l.price, l.battery, l.cosmetic " + _IN_GROUP, (key, since, exclude or "")).fetchall()]


def key_counts(conn, since, watch=None):
    sql = ("SELECT k.key, MAX(k.label), COUNT(DISTINCT k.list_id) FROM listing_keys k JOIN listings l "
           "USING (list_id) WHERE l.first_seen >= ?")
    args = [since]
    if watch:
        sql += " AND k.watch = ?"
        args.append(watch)
    return conn.execute(sql + " GROUP BY k.key ORDER BY COUNT(DISTINCT k.list_id) DESC", args).fetchall()


def count(conn):
    return conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]


def add_alert(conn, list_id, res, created_at, sent):
    conn.execute(
        "INSERT OR REPLACE INTO alerts (list_id, kind, price, median, discount, n, created_at, sent, adj_price) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (list_id, res["label"], res["price"], res["median"], res["discount"], res["n"],
         created_at, int(sent), res.get("adj_price")),
    )
    conn.commit()


def recent_alerts(conn, limit=50, kind=None, watch=None):
    sql = ("SELECT a.*, l.title, l.label, l.market, l.region, l.seller, l.url, l.key, l.battery, l.cosmetic, t.truth "
           "FROM alerts a JOIN listings l USING (list_id) LEFT JOIN sim_truth t USING (list_id) WHERE 1=1")
    args = []
    if kind:
        sql += " AND a.kind = ?"
        args.append(kind)
    if watch:
        sql += " AND a.list_id IN (SELECT list_id FROM listing_keys WHERE watch = ?)"
        args.append(watch)
    sql += " ORDER BY a.created_at DESC LIMIT ?"
    args.append(limit)
    return conn.execute(sql, args).fetchall()


_ROW_COLS = ", ".join(f"l.{c}" for c in LISTING_COLS + ("checked_at", "gone_at", "gone_status")
                      if c not in ("key", "label"))


def listings(conn, key=None, q=None, since=None, limit=200, watch=None):
    """Tin mới nhất trước. Lọc theo nhóm (key) hoặc theo từ khóa (watch): khi đó cột key/label là nhóm
    của tin trong từ khóa đó."""
    by_kw = bool(key or watch)
    groups, args = "", []
    if by_kw:  # 1 dòng/tin: nhóm của tin trong từ khóa / nhóm đang lọc
        groups = ("JOIN (SELECT list_id, MIN(key) AS key, MIN(label) AS label FROM listing_keys WHERE 1=1"
                  + (" AND key = ?" if key else "") + (" AND watch = ?" if watch else "")
                  + " GROUP BY list_id) k USING (list_id) ")
        args += [x for x in (key, watch) if x]
    sql = (f"SELECT {_ROW_COLS}, {'k' if by_kw else 'l'}.key AS key, {'k' if by_kw else 'l'}.label AS label, "
           "a.kind AS alert, a.discount AS alert_discount, t.truth FROM listings l " + groups
           + "LEFT JOIN alerts a USING (list_id) LEFT JOIN sim_truth t USING (list_id) WHERE 1=1")
    if q:
        sql += " AND l.title LIKE ?"
        args.append(f"%{q}%")
    if since is not None:
        sql += " AND l.first_seen >= ?"
        args.append(since)
    sql += " ORDER BY l.first_seen DESC LIMIT ?"
    args.append(limit)
    return conn.execute(sql, args).fetchall()


def set_status(conn, **kv):
    conn.executemany("INSERT OR REPLACE INTO status (k, v) VALUES (?, ?)",
                     [(k, str(v)) for k, v in kv.items()])
    conn.commit()


def get_status(conn):
    return {r[0]: r[1] for r in conn.execute("SELECT k, v FROM status").fetchall()}


def get_setting(conn, key, default=None):
    r = conn.execute("SELECT v FROM settings WHERE k = ?", (key,)).fetchone()
    return default if r is None else r[0]


def set_setting(conn, key, value):
    """value rỗng/None = xóa cài đặt (về mặc định)."""
    if value in (None, ""):
        conn.execute("DELETE FROM settings WHERE k = ?", (key,))
    else:
        conn.execute("INSERT OR REPLACE INTO settings (k, v) VALUES (?, ?)", (key, str(value)))
    conn.commit()


# ---------------------------------------------------------------- tin bỏ qua
def add_skipped(conn, watch, item, reason, detail="", now=None):
    """Ghi 1 tin bị loại (item: kết quả collector.parse_ad / skip_view). Thấy lại thì cập nhật lý do, giá, last_seen."""
    now = time.time() if now is None else now
    conn.execute(
        "INSERT INTO skipped (list_id, watch, reason, detail, title, price, region, seller, category, url, "
        "first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(list_id, watch) DO UPDATE SET reason = excluded.reason, detail = excluded.detail, "
        "title = excluded.title, price = excluded.price, last_seen = excluded.last_seen",
        (item["list_id"], watch or "", reason, detail, item.get("title"), item.get("price"), item.get("region"),
         item.get("seller"), (item.get("attrs") or {}).get("category_name"), item.get("url"), now, now))
    conn.commit()


def unskip(conn, list_id, watch):
    """Tin từng bị loại nay được nhận (giá sửa lại, đổi khoảng giá…): bỏ khỏi danh sách bỏ qua."""
    if conn.execute("DELETE FROM skipped WHERE list_id = ? AND watch = ?", (list_id, watch or "")).rowcount:
        conn.commit()


def prune_skipped(conn, before):
    n = conn.execute("DELETE FROM skipped WHERE last_seen < ?", (before,)).rowcount
    conn.commit()
    return n


def skipped_rows(conn, watch=None, reason=None, q=None, limit=300, since=None):
    sql, args = "SELECT * FROM skipped WHERE 1=1", []
    for col, val in (("watch", watch), ("reason", reason)):
        if val:
            sql += f" AND {col} = ?"
            args.append(val)
    if q:
        sql += " AND title LIKE ?"
        args.append(f"%{q}%")
    if since is not None:
        sql += " AND last_seen >= ?"
        args.append(since)
    return conn.execute(sql + " ORDER BY last_seen DESC, first_seen DESC LIMIT ?", (*args, limit)).fetchall()


def skipped_counts(conn, watch=None, since=None):
    """[(mã lý do, số tin)] nhiều nhất trước."""
    sql, args = "SELECT reason, COUNT(*) FROM skipped WHERE 1=1", []
    if watch:
        sql += " AND watch = ?"
        args.append(watch)
    if since is not None:
        sql += " AND last_seen >= ?"
        args.append(since)
    return [tuple(r) for r in conn.execute(sql + " GROUP BY reason ORDER BY COUNT(*) DESC", args).fetchall()]


def skipped_by_watch(conn):
    return dict(conn.execute("SELECT watch, COUNT(*) FROM skipped GROUP BY watch").fetchall())
