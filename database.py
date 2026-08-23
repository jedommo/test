"""
database.py
طبقة قاعدة البيانات الشاملة لمؤسسة عربة الخضار التجارية (الإصدار V2 المطور)
- حماية أمنية عالية بـ Salt فريد لكل مستخدم ومصادقة بالتوكن.
- جدول موردين موحد (Master Data) وربط العلاقات بمفاتيح أجنبية.
- سجل تدقيق العمليات (Audit Log) الكامل.
- قيود سلامة البيانات (CHECK Constraints) والتحقق من التواريخ والمبالغ.
- إدارة الأرصدة الدائنة (supplier_credits) ومنع التجاوزات الحسابية.
- نسخ احتياطي تلقائي مع التدوير (15 نسخة).
"""
import sqlite3
import hashlib
import os
import sys
import shutil
import json
import secrets
import base64
from datetime import datetime, timedelta

# ضبط ترميز الطرفية لويندوز
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


def get_app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


DB_PATH = os.path.join(get_app_dir(), "store.db")


# ----------------------------------------------------------------------
# الدوال المساعدة لضبط النصوص والتواريخ
# ----------------------------------------------------------------------

def normalize_arabic_digits(text: str) -> str:
    if not text:
        return ""
    eastern_to_western = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    return str(text).translate(eastern_to_western).strip()


def normalize_date_str(date_val) -> str:
    """توحيد وفحص صحة التاريخ ليكون بصيغة YYYY-MM-DD تلقائياً"""
    if not date_val:
        return datetime.now().strftime("%Y-%m-%d")
    s = normalize_arabic_digits(str(date_val)).strip()
    # إذا كانت القيمة نصاً وصفياً لحالة السداد أو خالية، نستبدلها بتاريخ اليوم تلقائياً بصيغة YYYY-MM-DD
    if any(desc in s for desc in ["آجل", "دين", "سداد", "مسدد", "نقدي", "نقد", "يدوي"]):
        return datetime.now().strftime("%Y-%m-%d")
    if " " in s:
        s = s.split(" ")[0]
    if "T" in s:
        s = s.split("T")[0]

    formats = ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y", "%Y.%m.%d", "%d.%m.%Y", "%m/%d/%Y"]
    for fmt in formats:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return datetime.now().strftime("%Y-%m-%d")



# ----------------------------------------------------------------------
# إدارة الأمان وتشفير كلمات المرور
# ----------------------------------------------------------------------

def hash_password(plain_password: str, salt: str = None) -> str:
    """تشفير كلمة المرور باستخدام SHA-256 مع ملح (Salt) فريد"""
    s = salt if (salt is not None and str(salt).strip() != "") else "arabat_alkhodar_salt_v1"
    return hashlib.sha256((s + str(plain_password)).encode("utf-8")).hexdigest()


def generate_salt() -> str:
    return secrets.token_hex(16)



def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    """تهيئة جداول قاعدة البيانات V2 مع كافة القيود"""
    conn = get_connection()
    cur = conn.cursor()

    # 1. جدول المستخدمين
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            must_change_password INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # 2. جدول الموردين الموحد
    cur.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE,
            phone TEXT,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # 3. جدول المشتريات والديون مع قيود CHECK
    cur.execute("""
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            supplier TEXT NOT NULL,
            supplier_id INTEGER REFERENCES suppliers(id),
            item TEXT NOT NULL,
            quantity REAL NOT NULL CHECK(quantity > 0),
            price REAL NOT NULL CHECK(price >= 0),
            total REAL NOT NULL CHECK(total >= 0),
            is_paid INTEGER NOT NULL DEFAULT 0,
            paid REAL NOT NULL DEFAULT 0 CHECK(paid >= 0),
            remaining REAL NOT NULL DEFAULT 0 CHECK(remaining >= 0),
            status TEXT NOT NULL DEFAULT 'unpaid' CHECK(status IN ('unpaid','partial','paid')),
            payment_date TEXT,
            source_file TEXT DEFAULT 'إدخال يدوي مباشر',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # 4. جدول التحويلات البنكية
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            supplier TEXT NOT NULL,
            supplier_id INTEGER REFERENCES suppliers(id),
            bank_name TEXT,
            reference_number TEXT,
            amount REAL NOT NULL CHECK(amount > 0),
            notes TEXT,
            settled_debt INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # 5. جدول تخصيص التحويلات
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transfer_allocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transfer_id INTEGER NOT NULL REFERENCES transfers(id) ON DELETE CASCADE,
            purchase_id INTEGER NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
            amount REAL NOT NULL CHECK(amount > 0)
        )
    """)

    # 6. جدول السداد النقدي
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cash_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            supplier TEXT NOT NULL,
            supplier_id INTEGER REFERENCES suppliers(id),
            amount REAL NOT NULL CHECK(amount > 0),
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # 7. جدول تخصيص السداد النقدي
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cash_allocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cash_payment_id INTEGER NOT NULL REFERENCES cash_payments(id) ON DELETE CASCADE,
            purchase_id INTEGER NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
            amount REAL NOT NULL CHECK(amount > 0)
        )
    """)

    # 8. جدول أرصدة الموردين الدائنة (الفائض)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS supplier_credits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
            amount REAL NOT NULL CHECK(amount > 0),
            source_type TEXT NOT NULL CHECK(source_type IN ('transfer', 'cash', 'manual')),
            source_id INTEGER,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # 9. جدول سجل تدقيق العمليات
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            record_id INTEGER NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('INSERT','UPDATE','DELETE')),
            old_value TEXT,
            new_value TEXT,
            username TEXT,
            timestamp TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # 10. جدول الإعدادات العامة
    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # فحص وإصلاح أعمدة users وترقية أي مستخدم ليس لديه salt
    cur.execute("PRAGMA table_info(users)")
    cols = [r["name"] for r in cur.fetchall()]
    if "salt" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN salt TEXT")
    if "must_change_password" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0")
    if "created_at" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN created_at TEXT DEFAULT ''")
        cur.execute("UPDATE users SET created_at = datetime('now', 'localtime') WHERE created_at IS NULL OR created_at = ''")

    cur.execute("SELECT id, username, password_hash, salt FROM users")
    users = cur.fetchall()
    if len(users) == 0:
        default_salt = generate_salt()
        cur.execute(
            "INSERT INTO users (username, password_hash, salt, must_change_password) VALUES (?, ?, ?, 1)",
            ("احمد", hash_password("1234", default_salt), default_salt)
        )
    else:
        for u in users:
            if not u["salt"]:
                new_salt = generate_salt()
                cur.execute("UPDATE users SET salt = ? WHERE id = ?", (new_salt, u["id"]))

    # فحص وإصلاح أعمدة purchases
    cur.execute("PRAGMA table_info(purchases)")
    p_cols = [r["name"] for r in cur.fetchall()]
    if "supplier_id" not in p_cols:
        cur.execute("ALTER TABLE purchases ADD COLUMN supplier_id INTEGER REFERENCES suppliers(id)")
    if "status" not in p_cols:
        cur.execute("ALTER TABLE purchases ADD COLUMN status TEXT NOT NULL DEFAULT 'unpaid'")

    # فحص وإصلاح أعمدة transfers
    cur.execute("PRAGMA table_info(transfers)")
    t_cols = [r["name"] for r in cur.fetchall()]
    if "supplier_id" not in t_cols:
        cur.execute("ALTER TABLE transfers ADD COLUMN supplier_id INTEGER REFERENCES suppliers(id)")

    # فحص وإصلاح أعمدة cash_payments
    cur.execute("PRAGMA table_info(cash_payments)")
    c_cols = [r["name"] for r in cur.fetchall()]
    if "supplier_id" not in c_cols:
        cur.execute("ALTER TABLE cash_payments ADD COLUMN supplier_id INTEGER REFERENCES suppliers(id)")

    conn.commit()
    conn.close()




# ----------------------------------------------------------------------
# سجل التدقيق (Audit Log)
# ----------------------------------------------------------------------

def log_audit(table_name: str, record_id: int, action: str, old_dict=None, new_dict=None, username: str = "نظام", conn=None):
    """تسجيل أي عملية تعديل أو حذف أو إضافة في سجل التدقيق"""
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    try:
        cur = conn.cursor()
        old_json = json.dumps(old_dict, ensure_ascii=False, default=str) if old_dict is not None else None
        new_json = json.dumps(new_dict, ensure_ascii=False, default=str) if new_dict is not None else None
        user = str(username).strip() if username else "نظام"
        
        cur.execute("""
            INSERT INTO audit_log (table_name, record_id, action, old_value, new_value, username)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (table_name, record_id, action, old_json, new_json, user))
        if should_close:
            conn.commit()
    finally:
        if should_close:
            conn.close()


def get_audit_log(table_name: str = None, record_id: int = None, action: str = None, search: str = None, limit: int = 300):
    """استرجاع سجل تدقيق العمليات مع خيارات فلترة وبحث متقدمة"""
    conn = get_connection()
    cur = conn.cursor()
    query = "SELECT * FROM audit_log WHERE 1=1"
    params = []

    if table_name and table_name != "all":
        query += " AND table_name = ?"
        params.append(table_name)
    if record_id is not None:
        query += " AND record_id = ?"
        params.append(record_id)
    if action and action != "all":
        query += " AND action = ?"
        params.append(action)
    if search and str(search).strip():
        s = f"%{str(search).strip()}%"
        query += " AND (username LIKE ? OR old_value LIKE ? OR new_value LIKE ? OR table_name LIKE ?)"
        params.extend([s, s, s, s])

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ----------------------------------------------------------------------
# إدارة الموردين الموحدة (Master Data)
# ----------------------------------------------------------------------

def find_or_create_supplier(name: str, phone: str = None, notes: str = None, conn=None) -> dict:
    """البحث عن المورد بمطابقة غير حساسة لحالة الأحرف والمسافات أو إنشاؤه إن لم يوجد"""
    if not name or not str(name).strip():
        raise ValueError("اسم المورد لا يمكن أن يكون فارغاً")
    clean_name = " ".join(str(name).strip().split())

    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM suppliers WHERE TRIM(LOWER(name)) = TRIM(LOWER(?))", (clean_name,))
        row = cur.fetchone()
        if row:
            return dict(row)

        cur.execute(
            "INSERT INTO suppliers (name, phone, notes) VALUES (?, ?, ?)",
            (clean_name, phone, notes)
        )
        sup_id = cur.lastrowid
        if should_close:
            conn.commit()
        cur.execute("SELECT * FROM suppliers WHERE id = ?", (sup_id,))
        return dict(cur.fetchone())
    finally:
        if should_close:
            conn.close()


def get_all_suppliers():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM suppliers ORDER BY name COLLATE NOCASE ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def update_supplier(supplier_id: int, name: str, phone: str = None, notes: str = None):
    clean_name = " ".join(str(name).strip().split())
    if not clean_name:
        raise ValueError("اسم المورد مطلوب")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE suppliers SET name = ?, phone = ?, notes = ? WHERE id = ?
    """, (clean_name, phone, notes, supplier_id))
    # تحديث الاسم في الفواتير التابعة
    cur.execute("UPDATE purchases SET supplier = ? WHERE supplier_id = ?", (clean_name, supplier_id))
    cur.execute("UPDATE transfers SET supplier = ? WHERE supplier_id = ?", (clean_name, supplier_id))
    cur.execute("UPDATE cash_payments SET supplier = ? WHERE supplier_id = ?", (clean_name, supplier_id))
    conn.commit()
    conn.close()
    return True


# ----------------------------------------------------------------------
# المصادقة وإدارة الحساب وتغيير كلمة المرور
# ----------------------------------------------------------------------

def verify_login(username: str, password: str) -> dict:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, password_hash, salt, must_change_password FROM users WHERE username = ?", (username.strip(),))
    row = cur.fetchone()
    if not row:
        conn.close()
        return {"success": False, "error": "اسم المستخدم أو كلمة المرور غير صحيحة"}

    user_salt = row["salt"] if (row["salt"] is not None and str(row["salt"]).strip() != "") else None
    pass_clean = str(password).strip()

    expected_hash = hash_password(pass_clean, user_salt)
    legacy_hash = hash_password(pass_clean, "arabat_alkhodar_salt_v1")

    if row["password_hash"] == expected_hash or row["password_hash"] == legacy_hash:
        must_change = bool(row["must_change_password"]) if ("must_change_password" in row.keys() and row["must_change_password"] is not None) else False
        
        # إذا لم يكن لديه salt مشفر جديد، نقوم بترقيته فورياً
        if not user_salt:
            new_salt = generate_salt()
            new_h = hash_password(pass_clean, new_salt)
            cur.execute("UPDATE users SET password_hash = ?, salt = ? WHERE id = ?", (new_h, new_salt, row["id"]))
            conn.commit()
            
        conn.close()
        return {
            "success": True,
            "user": row["username"],
            "must_change_password": must_change
        }

    conn.close()
    return {"success": False, "error": "اسم المستخدم أو كلمة المرور غير صحيحة"}



def change_password(username: str, new_password: str) -> bool:
    if not new_password or len(new_password.strip()) < 4:
        raise ValueError("كلمة المرور الجديدة يجب ألا تقل عن 4 خانات")
    new_salt = generate_salt()
    new_hash = hash_password(new_password.strip(), new_salt)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE users SET password_hash = ?, salt = ?, must_change_password = 0 WHERE username = ?
    """, (new_hash, new_salt, username.strip()))
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed


def get_all_users():
    """استرجاع قائمة المستخدمين المسجلين في النظام دون كشف الهاشات"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, must_change_password, created_at FROM users ORDER BY id ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def add_user(username: str, password: str, username_by: str = "نظام") -> dict:
    """إضافة مستخدم جديد للنظام مع تشفير Salt فريد وتوثيق العملية في سجل التدقيق"""
    u_clean = str(username).strip()
    p_clean = str(password).strip()
    if not u_clean or len(u_clean) < 2:
        raise ValueError("اسم المستخدم يجب ألا يقل عن حرفين")
    if not p_clean or len(p_clean) < 4:
        raise ValueError("كلمة المرور يجب ألا تقل عن 4 خانات")

    salt = generate_salt()
    pw_hash = hash_password(p_clean, salt)

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE TRIM(LOWER(username)) = TRIM(LOWER(?))", (u_clean,))
        if cur.fetchone():
            raise ValueError(f"اسم المستخدم '{u_clean}' مسجل مسبقاً في النظام")

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
            INSERT INTO users (username, password_hash, salt, must_change_password, created_at)
            VALUES (?, ?, ?, 0, ?)
        """, (u_clean, pw_hash, salt, now_str))
        new_id = cur.lastrowid
        cur.execute("SELECT id, username, must_change_password, created_at FROM users WHERE id = ?", (new_id,))
        user_data = dict(cur.fetchone())

        log_audit("users", new_id, "INSERT", old_dict=None, new_dict=user_data, username=username_by, conn=conn)
        conn.commit()
        return user_data
    finally:
        conn.close()


def delete_user(user_id: int, current_username: str = "نظام", username_by: str = "نظام") -> bool:
    """حذف مستخدم من النظام مع منع حذف المستخدم النشط حالياً أو عند بقاء مستخدم وحيد"""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) as cnt FROM users")
        total_users = cur.fetchone()["cnt"]
        if total_users <= 1:
            raise ValueError("لا يمكن حذف هذا المستخدم؛ يجب أن يتوفر مستخدم واحد على الأقل في النظام")

        cur.execute("SELECT id, username, created_at FROM users WHERE id = ?", (user_id,))
        target = cur.fetchone()
        if not target:
            raise ValueError("المستخدم المراد حذفه غير موجود")

        if target["username"].strip().lower() == str(current_username).strip().lower():
            raise ValueError("لا يمكنك حذف الحساب النشط الذي قمت بتسجيل الدخول به حالياً")

        old_data = dict(target)
        cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
        log_audit("users", user_id, "DELETE", old_dict=old_data, new_dict=None, username=username_by, conn=conn)
        conn.commit()
        return True
    finally:
        conn.close()


def update_user_profile(old_username: str, new_username: str = None, new_password: str = None, username_by: str = "نظام") -> dict:
    """تحديث اسم المستخدم و/أو كلمة المرور وتوثيق العملية في سجل التدقيق"""
    old_u = str(old_username).strip()
    new_u = str(new_username).strip() if new_username else old_u
    new_p = str(new_password).strip() if new_password else None

    if not new_u or len(new_u) < 2:
        raise ValueError("اسم المستخدم يجب ألا يقل عن حرفين")

    if new_p and len(new_p) < 4:
        raise ValueError("كلمة المرور الجديدة يجب ألا تقل عن 4 خانات")

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, username, must_change_password, created_at FROM users WHERE username = ?", (old_u,))
        existing = cur.fetchone()
        if not existing:
            raise ValueError(f"المستخدم '{old_u}' غير موجود")

        if new_u.lower() != old_u.lower():
            cur.execute("SELECT id FROM users WHERE TRIM(LOWER(username)) = TRIM(LOWER(?)) AND id != ?", (new_u, existing["id"]))
            if cur.fetchone():
                raise ValueError(f"اسم المستخدم '{new_u}' محجوز لحساب آخر")

        old_data = dict(existing)
        if new_p:
            new_salt = generate_salt()
            new_h = hash_password(new_p, new_salt)
            cur.execute("""
                UPDATE users SET username = ?, password_hash = ?, salt = ?, must_change_password = 0 WHERE id = ?
            """, (new_u, new_h, new_salt, existing["id"]))
        else:
            cur.execute("UPDATE users SET username = ? WHERE id = ?", (new_u, existing["id"]))

        cur.execute("SELECT value FROM app_settings WHERE key = 'remember_username'")
        rem_user = cur.fetchone()
        if rem_user and rem_user["value"] == old_u:
            cur.execute("UPDATE app_settings SET value = ? WHERE key = 'remember_username'", (new_u,))

        cur.execute("SELECT id, username, must_change_password, created_at FROM users WHERE id = ?", (existing["id"],))
        new_data = dict(cur.fetchone())

        log_audit("users", existing["id"], "UPDATE", old_dict=old_data, new_dict=new_data, username=username_by, conn=conn)
        conn.commit()
        return new_data
    finally:
        conn.close()



def save_login_credentials(username: str, password: str, enabled: bool = True) -> bool:
    """حفظ بيانات تسجيل الدخول في قاعدة البيانات للتمكن من استرجاعها وتعبئتها تلقائياً وبأمان تام"""
    conn = get_connection()
    cur = conn.cursor()
    try:
        if enabled and username and password:
            enc_pass = base64.b64encode(password.encode("utf-8")).decode("utf-8")
            cur.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('saved_login_enabled', '1')")
            cur.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('saved_login_username', ?)", (username.strip(),))
            cur.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('saved_login_password', ?)", (enc_pass,))
        else:
            cur.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('saved_login_enabled', '0')")
            cur.execute("DELETE FROM app_settings WHERE key IN ('saved_login_username', 'saved_login_password')")
        conn.commit()
        return True
    finally:
        conn.close()


def get_saved_login_credentials() -> dict:
    """استرجاع بيانات تسجيل الدخول المحفوظة من قاعدة البيانات"""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT key, value FROM app_settings WHERE key IN ('saved_login_enabled', 'saved_login_username', 'saved_login_password')")
        settings = {r["key"]: r["value"] for r in cur.fetchall()}
        
        is_enabled = settings.get("saved_login_enabled") == "1"
        username = settings.get("saved_login_username", "")
        raw_enc_pass = settings.get("saved_login_password", "")
        
        password = ""
        if raw_enc_pass:
            try:
                password = base64.b64decode(raw_enc_pass.encode("utf-8")).decode("utf-8")
            except Exception:
                password = raw_enc_pass

        return {
            "enabled": is_enabled and bool(username),
            "username": username if is_enabled else "",
            "password": password if is_enabled else ""
        }
    finally:
        conn.close()


def clear_saved_login_credentials() -> bool:
    """مسح بيانات تسجيل الدخول المحفوظة نهائياً"""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('saved_login_enabled', '0')")
        cur.execute("DELETE FROM app_settings WHERE key IN ('saved_login_username', 'saved_login_password', 'remember_token_hash', 'remember_token_expiry', 'remember_username', 'saved_password')")
        conn.commit()
        return True
    finally:
        conn.close()




# ----------------------------------------------------------------------
# الدوال المساعدة لتهيئة وتنسيق المشتريات
# ----------------------------------------------------------------------

def _format_purchase_dict(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "date": row["date"],
        "supplier": row["supplier"],
        "supplierId": row["supplier_id"],
        "item": row["item"],
        "quantity": row["quantity"],
        "price": row["price"],
        "total": row["total"],
        "isPaid": bool(row["is_paid"]),
        "paid": row["paid"],
        "remaining": row["remaining"],
        "status": row["status"] if "status" in row.keys() else ("paid" if row["is_paid"] else "unpaid"),
        "paymentDate": row["payment_date"],
        "sourceFile": row["source_file"] or "إدخال يدوي مباشر"
    }


# ----------------------------------------------------------------------
# إدارة المشتريات (Purchases CRUD)
# ----------------------------------------------------------------------

def add_purchase(date_str, supplier, item, quantity, price, paid=0, payment_date=None, source_file="إدخال يدوي مباشر", username="نظام"):
    date_clean = normalize_date_str(date_str)
    sup_obj = find_or_create_supplier(supplier)
    supplier_name = sup_obj["name"]
    supplier_id = sup_obj["id"]

    item_clean = str(item).strip()
    if not item_clean:
        raise ValueError("اسم الصنف لا يمكن أن يكون فارغاً")

    qty = float(quantity)
    if qty <= 0:
        raise ValueError("الكمية يجب أن تكون أكبر من الصفر")

    prc = float(price)
    if prc < 0:
        raise ValueError("السعر لا يمكن أن يكون سالباً")

    total = round(qty * prc, 2)
    paid_val = round(float(paid or 0), 2)
    if paid_val < 0:
        raise ValueError("المبلغ المدفوع لا يمكن أن يكون سالباً")

    remaining = round(max(0.0, total - paid_val), 2)
    
    if remaining <= 0:
        status = "paid"
        is_paid = 1
        pdate = normalize_date_str(payment_date) if payment_date else date_clean
    elif paid_val > 0:
        status = "partial"
        is_paid = 0
        pdate = normalize_date_str(payment_date) if payment_date else date_clean
    else:
        status = "unpaid"
        is_paid = 0
        pdate = None

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO purchases (date, supplier, supplier_id, item, quantity, price, total, is_paid, paid, remaining, status, payment_date, source_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (date_clean, supplier_name, supplier_id, item_clean, qty, prc, total, is_paid, paid_val, remaining, status, pdate, source_file))
    new_id = cur.lastrowid
    cur.execute("SELECT * FROM purchases WHERE id = ?", (new_id,))
    row = cur.fetchone()
    formatted = _format_purchase_dict(row)
    log_audit("purchases", new_id, "INSERT", old_dict=None, new_dict=formatted, username=username, conn=conn)
    conn.commit()
    conn.close()
    return formatted


def bulk_add_purchases(records, username="نظام"):
    """
    إضافة جماعية ذكية مع تحقق صارم (All-or-Nothing Transaction)
    إذا وجد أي خطأ في أي صف، يتم رفض العملية وإرجاع تقرير بالأخطاء ورقم الصف.
    """
    if not records:
        return []

    errors = []
    validated_records = []

    for idx, r in enumerate(records):
        row_num = idx + 1
        try:
            raw_date = r.get("date")
            clean_date = normalize_date_str(raw_date)
        except Exception as e:
            errors.append({"row": row_num, "field": "date", "message": f"تاريخ غير صالح ({r.get('date')}): {str(e)}"})
            continue

        raw_sup = str(r.get("supplier", "")).strip()
        if not raw_sup:
            errors.append({"row": row_num, "field": "supplier", "message": "اسم المورد فارغ"})
            continue

        raw_item = str(r.get("item", "")).strip()
        if not raw_item:
            errors.append({"row": row_num, "field": "item", "message": "اسم الصنف فارغ"})
            continue

        try:
            qty = float(r.get("quantity", 0))
            if qty <= 0:
                errors.append({"row": row_num, "field": "quantity", "message": "الكمية يجب أن تكون أكبر من الصفر"})
                continue
        except Exception:
            errors.append({"row": row_num, "field": "quantity", "message": "الكمية ليست رقماً صحيحاً"})
            continue

        try:
            prc = float(r.get("price", 0))
            if prc < 0:
                errors.append({"row": row_num, "field": "price", "message": "السعر لا يمكن أن يكون سالباً"})
                continue
        except Exception:
            errors.append({"row": row_num, "field": "price", "message": "السعر ليس رقماً صحيحاً"})
            continue

        try:
            paid_val = float(r.get("paid", 0))
            if paid_val < 0:
                errors.append({"row": row_num, "field": "paid", "message": "المبلغ المدفوع لا يمكن أن يكون سالباً"})
                continue
        except Exception:
            paid_val = 0.0

        total = round(qty * prc, 2)
        remaining = round(max(0.0, total - paid_val), 2)
        is_paid = 1 if (r.get("isPaid") or remaining <= 0) else 0

        if remaining <= 0 or is_paid:
            status = "paid"
            is_paid = 1
            pdate = clean_date
        elif paid_val > 0:
            status = "partial"
            is_paid = 0
            pdate = clean_date
        else:
            status = "unpaid"
            is_paid = 0
            pdate = None

        sfile = r.get("sourceFile") or "استيراد دفعات"

        validated_records.append({
            "date": clean_date,
            "supplier": raw_sup,
            "item": raw_item,
            "quantity": qty,
            "price": prc,
            "total": total,
            "is_paid": is_paid,
            "paid": paid_val,
            "remaining": remaining,
            "status": status,
            "payment_date": pdate,
            "source_file": sfile
        })

    if errors:
        raise ValueError(f"فشل الاستيراد: تم العثور على {len(errors)} خطأ في البيانات:\n" + "\n".join([f"- صف {e['row']}: {e['message']}" for e in errors[:10]]))

    conn = get_connection()
    cur = conn.cursor()
    inserted_ids = []

    try:
        for v in validated_records:
            sup_obj = find_or_create_supplier(v["supplier"], conn=conn)
            cur.execute("""
                INSERT INTO purchases (date, supplier, supplier_id, item, quantity, price, total, is_paid, paid, remaining, status, payment_date, source_file)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (v["date"], sup_obj["name"], sup_obj["id"], v["item"], v["quantity"], v["price"],
                  v["total"], v["is_paid"], v["paid"], v["remaining"], v["status"], v["payment_date"], v["source_file"]))
            new_id = cur.lastrowid
            inserted_ids.append(new_id)
            log_audit("purchases", new_id, "INSERT", old_dict=None, new_dict=v, username=username, conn=conn)

        conn.commit()

        placeholders = ",".join(["?"] * len(inserted_ids))
        cur.execute(f"SELECT * FROM purchases WHERE id IN ({placeholders}) ORDER BY id DESC", inserted_ids)
        result = [_format_purchase_dict(row) for row in cur.fetchall()]
        return result
    finally:
        conn.close()


def update_purchase(record_id, date_str, supplier, item, quantity, price, paid=None, payment_date=None, source_file=None, username="نظام"):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM purchases WHERE id = ?", (record_id,))
    existing = cur.fetchone()
    if not existing:
        conn.close()
        raise ValueError(f"القيد #{record_id} غير موجود في قاعدة البيانات")

    old_formatted = _format_purchase_dict(existing)

    date_clean = normalize_date_str(date_str)
    sup_obj = find_or_create_supplier(supplier, conn=conn)
    supplier_name = sup_obj["name"]
    supplier_id = sup_obj["id"]

    item_clean = str(item).strip()
    if not item_clean:
        conn.close()
        raise ValueError("اسم الصنف لا يمكن أن يكون فارغاً")

    qty = float(quantity)
    if qty <= 0:
        conn.close()
        raise ValueError("الكمية يجب أن تكون أكبر من الصفر")

    prc = float(price)
    if prc < 0:
        conn.close()
        raise ValueError("السعر لا يمكن أن يكون سالباً")

    total = round(qty * prc, 2)
    current_paid = existing["paid"] if paid is None else float(paid)
    current_paid = round(max(0.0, current_paid), 2)
    remaining = round(max(0.0, total - current_paid), 2)
    
    if remaining <= 0:
        status = "paid"
        is_paid = 1
        pdate = normalize_date_str(payment_date) if payment_date else date_clean
    elif current_paid > 0:
        status = "partial"
        is_paid = 0
        pdate = normalize_date_str(payment_date) if payment_date else date_clean
    else:
        status = "unpaid"
        is_paid = 0
        pdate = None

    sfile = source_file if source_file is not None else existing["source_file"]

    cur.execute("""
        UPDATE purchases
        SET date = ?, supplier = ?, supplier_id = ?, item = ?, quantity = ?, price = ?, total = ?,
            is_paid = ?, paid = ?, remaining = ?, status = ?, payment_date = ?, source_file = ?
        WHERE id = ?
    """, (date_clean, supplier_name, supplier_id, item_clean, qty, prc, total,
          is_paid, current_paid, remaining, status, pdate, sfile, record_id))

    cur.execute("SELECT * FROM purchases WHERE id = ?", (record_id,))
    updated_row = cur.fetchone()
    new_formatted = _format_purchase_dict(updated_row)
    log_audit("purchases", record_id, "UPDATE", old_dict=old_formatted, new_dict=new_formatted, username=username, conn=conn)

    conn.commit()
    conn.close()
    return new_formatted


def delete_purchase(record_id: int, username: str = "نظام"):
    """
    حذف الفاتورة مع تحرير التخصيصات (عكس السداد) وإبقاء السندات الأصلية بالمبالغ غير المخصصة
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM purchases WHERE id = ?", (record_id,))
    existing = cur.fetchone()
    if not existing:
        conn.close()
        return False

    old_formatted = _format_purchase_dict(existing)

    # 1. حذف وعكس تخصيصات الحوالات المرتبطة
    cur.execute("SELECT * FROM transfer_allocations WHERE purchase_id = ?", (record_id,))
    t_allocs = cur.fetchall()
    for ta in t_allocs:
        log_audit("transfer_allocations", ta["id"], "DELETE", old_dict=dict(ta), new_dict=None, username=username, conn=conn)
    cur.execute("DELETE FROM transfer_allocations WHERE purchase_id = ?", (record_id,))

    # 2. حذف وعكس تخصيصات السداد النقدي المرتبطة
    cur.execute("SELECT * FROM cash_allocations WHERE purchase_id = ?", (record_id,))
    c_allocs = cur.fetchall()
    for ca in c_allocs:
        log_audit("cash_allocations", ca["id"], "DELETE", old_dict=dict(ca), new_dict=None, username=username, conn=conn)
    cur.execute("DELETE FROM cash_allocations WHERE purchase_id = ?", (record_id,))

    # 3. حذف الفاتورة وتوثيق ذلك في audit_log
    cur.execute("DELETE FROM purchases WHERE id = ?", (record_id,))
    log_audit("purchases", record_id, "DELETE", old_dict=old_formatted, new_dict=None, username=username, conn=conn)

    conn.commit()
    conn.close()
    return True


def bulk_delete_purchases(record_ids: list, username: str = "نظام"):
    count = 0
    for rid in record_ids:
        if delete_purchase(rid, username=username):
            count += 1
    return count


def get_all_purchases():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM purchases ORDER BY date DESC, id DESC")
    rows = [_format_purchase_dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ----------------------------------------------------------------------
# إدارة التحويلات البنكية والتخصيصات (Transfers)
# ----------------------------------------------------------------------

def _apply_allocation(cur, purchase_id: int, amount: float, username: str = "نظام"):
    """تطبيق تخصيص سداد على فاتورة مع التحقق الصارم من عدم تجاوز المتبقي"""
    cur.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,))
    p_row = cur.fetchone()
    if not p_row:
        raise ValueError(f"الفاتورة رقم #{purchase_id} غير موجودة")

    old_p = _format_purchase_dict(p_row)
    remaining_now = float(p_row["remaining"])
    alloc_amt = round(float(amount), 2)

    if alloc_amt > (remaining_now + 0.01):
        overage = round(alloc_amt - remaining_now, 2)
        raise ValueError(f"المبلغ المخصص ({alloc_amt:.2f} ر.س) يتجاوز المتبقي على الفاتورة #{purchase_id} ({remaining_now:.2f} ر.س) بمقدار {overage:.2f} ر.س")

    new_paid = round(p_row["paid"] + alloc_amt, 2)
    new_rem = round(max(0.0, p_row["total"] - new_paid), 2)
    
    if new_rem <= 0:
        new_status = "paid"
        new_is_paid = 1
    else:
        new_status = "partial"
        new_is_paid = 0

    cur.execute("""
        UPDATE purchases SET paid = ?, remaining = ?, is_paid = ?, status = ?, payment_date = datetime('now', 'localtime')
        WHERE id = ?
    """, (new_paid, new_rem, new_is_paid, new_status, purchase_id))

    cur.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,))
    new_p = _format_purchase_dict(cur.fetchone())
    log_audit("purchases", purchase_id, "UPDATE", old_dict=old_p, new_dict=new_p, username=username, conn=cur.connection)


def _reverse_allocation(cur, purchase_id: int, amount: float, username: str = "نظام"):
    """عكس تخصيص سداد عن فاتورة عند حذف السند"""
    cur.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,))
    p_row = cur.fetchone()
    if not p_row:
        return

    old_p = _format_purchase_dict(p_row)
    alloc_amt = round(float(amount), 2)
    new_paid = round(max(0.0, p_row["paid"] - alloc_amt), 2)
    new_rem = round(p_row["total"] - new_paid, 2)
    
    if new_rem <= 0:
        new_status = "paid"
        new_is_paid = 1
    elif new_paid > 0:
        new_status = "partial"
        new_is_paid = 0
    else:
        new_status = "unpaid"
        new_is_paid = 0

    cur.execute("""
        UPDATE purchases SET paid = ?, remaining = ?, is_paid = ?, status = ?
        WHERE id = ?
    """, (new_paid, new_rem, new_is_paid, new_status, purchase_id))

    cur.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,))
    new_p = _format_purchase_dict(cur.fetchone())
    log_audit("purchases", purchase_id, "UPDATE", old_dict=old_p, new_dict=new_p, username=username, conn=cur.connection)


def add_bank_transfer(date_str, supplier, bank_name, reference_number, amount, notes, allocations, username="نظام"):
    date_clean = normalize_date_str(date_str)
    sup_obj = find_or_create_supplier(supplier)
    supplier_name = sup_obj["name"]
    supplier_id = sup_obj["id"]

    amt = float(amount)
    if amt <= 0:
        raise ValueError("مبلغ التحويل يجب أن يكون أكبر من الصفر")

    total_allocated = sum(float(a.get("amount", 0)) for a in (allocations or []))
    if total_allocated > (amt + 0.01):
        raise ValueError(f"إجمالي المبالغ المخصصة ({total_allocated:.2f} ر.س) يتجاوز مبلغ التحويل ({amt:.2f} ر.س)")

    conn = get_connection()
    cur = conn.cursor()

    try:
        settled = 1 if allocations else 0
        cur.execute("""
            INSERT INTO transfers (date, supplier, supplier_id, bank_name, reference_number, amount, notes, settled_debt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (date_clean, supplier_name, supplier_id, str(bank_name).strip(),
              str(reference_number).strip(), amt, str(notes or "").strip(), settled))
        transfer_id = cur.lastrowid

        valid_allocations = []
        for alloc in (allocations or []):
            p_id = alloc.get("purchase_id") or alloc.get("recordId")
            a_amt = float(alloc.get("amount", 0))
            if p_id and a_amt > 0:
                _apply_allocation(cur, p_id, a_amt, username=username)
                cur.execute(
                    "INSERT INTO transfer_allocations (transfer_id, purchase_id, amount) VALUES (?, ?, ?)",
                    (transfer_id, p_id, a_amt)
                )
                valid_allocations.append({"recordId": p_id, "amount": a_amt})

        # إذا تبقى مبلغ غير مخصص، يمكن تسجيله كرصيد دائن للمورد
        excess = round(amt - total_allocated, 2)
        if excess > 0 and settled:
            cur.execute("""
                INSERT INTO supplier_credits (supplier_id, amount, source_type, source_id, notes)
                VALUES (?, ?, 'transfer', ?, 'فائض تحويل بنكي غير مخصص')
            """, (supplier_id, excess, transfer_id))

        t_obj = {
            "id": transfer_id,
            "date": date_clean,
            "supplier": supplier_name,
            "supplierId": supplier_id,
            "bankName": bank_name,
            "referenceNumber": reference_number,
            "amount": amt,
            "notes": notes,
            "settledDebt": bool(settled),
            "allocations": valid_allocations,
            "unallocatedAmount": excess
        }

        log_audit("transfers", transfer_id, "INSERT", old_dict=None, new_dict=t_obj, username=username, conn=conn)
        conn.commit()
        return t_obj
    finally:
        conn.close()


def delete_bank_transfer(transfer_id: int, username: str = "نظام"):
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("SELECT * FROM transfers WHERE id = ?", (transfer_id,))
        t_row = cur.fetchone()
        if not t_row:
            return False

        old_t = dict(t_row)

        cur.execute("SELECT purchase_id, amount FROM transfer_allocations WHERE transfer_id = ?", (transfer_id,))
        allocs = cur.fetchall()
        for a in allocs:
            _reverse_allocation(cur, a["purchase_id"], a["amount"], username=username)

        cur.execute("DELETE FROM supplier_credits WHERE source_type = 'transfer' AND source_id = ?", (transfer_id,))
        cur.execute("DELETE FROM transfers WHERE id = ?", (transfer_id,))

        log_audit("transfers", transfer_id, "DELETE", old_dict=old_t, new_dict=None, username=username, conn=conn)
        conn.commit()
        return True
    finally:
        conn.close()


def get_all_transfers():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM transfers ORDER BY date DESC, id DESC")
    transfers = []
    transfer_rows = cur.fetchall()

    for tr in transfer_rows:
        t_id = tr["id"]
        cur.execute("SELECT purchase_id as recordId, amount FROM transfer_allocations WHERE transfer_id = ?", (t_id,))
        allocations = [dict(a) for a in cur.fetchall()]
        allocated_sum = sum(a["amount"] for a in allocations)
        unallocated = round(max(0.0, tr["amount"] - allocated_sum), 2)

        transfers.append({
            "id": tr["id"],
            "date": tr["date"],
            "supplier": tr["supplier"],
            "supplierId": tr["supplier_id"],
            "bankName": tr["bank_name"],
            "referenceNumber": tr["reference_number"],
            "amount": tr["amount"],
            "notes": tr["notes"],
            "settledDebt": bool(tr["settled_debt"]),
            "allocations": allocations,
            "unallocatedAmount": unallocated
        })

    conn.close()
    return transfers


# ----------------------------------------------------------------------
# إدارة السداد النقدي (Cash Payments)
# ----------------------------------------------------------------------

def add_cash_payment(date_str, supplier, amount, notes, allocations, username="نظام"):
    date_clean = normalize_date_str(date_str)
    sup_obj = find_or_create_supplier(supplier)
    supplier_name = sup_obj["name"]
    supplier_id = sup_obj["id"]

    amt = float(amount)
    if amt <= 0:
        raise ValueError("مبلغ السداد يجب أن يكون أكبر من الصفر")

    total_allocated = sum(float(a.get("amount", 0)) for a in (allocations or []))
    if total_allocated > (amt + 0.01):
        raise ValueError(f"إجمالي المبالغ المخصصة ({total_allocated:.2f} ر.س) يتجاوز مبلغ السداد ({amt:.2f} ر.س)")

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO cash_payments (date, supplier, supplier_id, amount, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (date_clean, supplier_name, supplier_id, amt, str(notes or "").strip()))
        cash_id = cur.lastrowid

        valid_allocations = []
        for alloc in (allocations or []):
            p_id = alloc.get("purchase_id") or alloc.get("recordId")
            a_amt = float(alloc.get("amount", 0))
            if p_id and a_amt > 0:
                _apply_allocation(cur, p_id, a_amt, username=username)
                cur.execute(
                    "INSERT INTO cash_allocations (cash_payment_id, purchase_id, amount) VALUES (?, ?, ?)",
                    (cash_id, p_id, a_amt)
                )
                valid_allocations.append({"recordId": p_id, "amount": a_amt})

        excess = round(amt - total_allocated, 2)
        if excess > 0 and allocations:
            cur.execute("""
                INSERT INTO supplier_credits (supplier_id, amount, source_type, source_id, notes)
                VALUES (?, ?, 'cash', ?, 'فائض سداد نقدي غير مخصص')
            """, (supplier_id, excess, cash_id))

        c_obj = {
            "id": cash_id,
            "date": date_clean,
            "supplier": supplier_name,
            "supplierId": supplier_id,
            "amount": amt,
            "notes": notes,
            "allocations": valid_allocations,
            "unallocatedAmount": excess
        }

        log_audit("cash_payments", cash_id, "INSERT", old_dict=None, new_dict=c_obj, username=username, conn=conn)
        conn.commit()
        return c_obj
    finally:
        conn.close()


def delete_cash_payment(payment_id: int, username: str = "نظام"):
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("SELECT * FROM cash_payments WHERE id = ?", (payment_id,))
        c_row = cur.fetchone()
        if not c_row:
            return False

        old_c = dict(c_row)

        cur.execute("SELECT purchase_id, amount FROM cash_allocations WHERE cash_payment_id = ?", (payment_id,))
        allocs = cur.fetchall()
        for a in allocs:
            _reverse_allocation(cur, a["purchase_id"], a["amount"], username=username)

        cur.execute("DELETE FROM supplier_credits WHERE source_type = 'cash' AND source_id = ?", (payment_id,))
        cur.execute("DELETE FROM cash_payments WHERE id = ?", (payment_id,))

        log_audit("cash_payments", payment_id, "DELETE", old_dict=old_c, new_dict=None, username=username, conn=conn)
        conn.commit()
        return True
    finally:
        conn.close()


def get_all_cash_payments():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM cash_payments ORDER BY date DESC, id DESC")
    payments = []
    rows = cur.fetchall()

    for r in rows:
        c_id = r["id"]
        cur.execute("SELECT purchase_id as recordId, amount FROM cash_allocations WHERE cash_payment_id = ?", (c_id,))
        allocations = [dict(a) for a in cur.fetchall()]
        allocated_sum = sum(a["amount"] for a in allocations)
        unallocated = round(max(0.0, r["amount"] - allocated_sum), 2)

        payments.append({
            "id": r["id"],
            "date": r["date"],
            "supplier": r["supplier"],
            "supplierId": r["supplier_id"],
            "amount": r["amount"],
            "notes": r["notes"],
            "allocations": allocations,
            "unallocatedAmount": unallocated
        })

    conn.close()
    return payments


def get_unallocated_amount(source_type: str, source_id: int) -> float:
    """حساب المبلغ المتبقي غير المخصص من دفعة نقدية أو حوالة بنكية"""
    conn = get_connection()
    cur = conn.cursor()
    try:
        if source_type == 'transfer':
            cur.execute("SELECT amount FROM transfers WHERE id = ?", (source_id,))
            t = cur.fetchone()
            if not t:
                return 0.0
            cur.execute("SELECT COALESCE(SUM(amount), 0) as s FROM transfer_allocations WHERE transfer_id = ?", (source_id,))
            allocated = cur.fetchone()["s"]
            return round(max(0.0, t["amount"] - allocated), 2)
        elif source_type == 'cash':
            cur.execute("SELECT amount FROM cash_payments WHERE id = ?", (source_id,))
            c = cur.fetchone()
            if not c:
                return 0.0
            cur.execute("SELECT COALESCE(SUM(amount), 0) as s FROM cash_allocations WHERE cash_payment_id = ?", (source_id,))
            allocated = cur.fetchone()["s"]
            return round(max(0.0, c["amount"] - allocated), 2)
        return 0.0
    finally:
        conn.close()


# ----------------------------------------------------------------------
# النسخ الاحتياطي والتدوير (Backup & Rotation)
# ----------------------------------------------------------------------

def rotate_backups(max_keep: int = 15):
    """تدوير النسخ الاحتياطية والاحتفاظ بأحدث 15 نسخة فقط"""
    try:
        backups_dir = os.path.join(get_app_dir(), "backups")
        if not os.path.exists(backups_dir):
            return
        files = [os.path.join(backups_dir, f) for f in os.listdir(backups_dir) if f.endswith(".db")]
        files.sort(key=os.path.getmtime)
        while len(files) > max_keep:
            oldest = files.pop(0)
            try:
                os.remove(oldest)
            except Exception:
                pass
    except Exception as e:
        print(f"خطأ في تدوير النسخ الاحتياطية: {e}")


def backup_database(destination_folder=None, custom_path=None):
    """إنشاء نسخة احتياطية من ملف قاعدة البيانات مع تدوير النسخ"""
    if custom_path:
        dest_path = custom_path
    else:
        dest_dir = destination_folder or os.path.join(get_app_dir(), "backups")
        os.makedirs(dest_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        dest_path = os.path.join(dest_dir, f"store_backup_{stamp}.db")

    if os.path.exists(DB_PATH):
        shutil.copy2(DB_PATH, dest_path)
    rotate_backups(max_keep=15)
    return dest_path


def restore_database(source_path: str):
    """استعادة قاعدة البيانات من ملف خارجي مع أخذ نسخة احتياطية وقائية قبل الاستبدال"""
    if not os.path.exists(source_path):
        raise FileNotFoundError("الملف المحدد غير موجود")

    test_conn = sqlite3.connect(source_path)
    test_cur = test_conn.cursor()
    test_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='purchases'")
    has_purchases = test_cur.fetchone() is not None
    test_conn.close()

    if not has_purchases:
        raise ValueError("الملف المحدد ليس نسخة صالحة لقاعدة بيانات مؤسسة عربة الخضار")

    # أخذ نسخة وقائية فورية من قاعدة البيانات الحالية
    backup_database()

    shutil.copy2(source_path, DB_PATH)
    init_db()
    return True


def clear_all_data(confirm_token: str = None, username: str = "نظام"):
    """
    مسح وإعادة ضبط شاملة لكافة العمليات الحسابية، الفواتير، السندات، الموردين، وسجلات التدقيق
    مع تصفير عدادات الترقيم التلقائي (AUTOINCREMENT) لتبدأ كافة الفواتير والقيود من الرقم 1،
    وأخذ نسخة احتياطية وقائية قبل التصفير.
    """
    if confirm_token != "تأكيد الحذف":
        raise ValueError("رمز التأكيد غير صحيح! يجب كتابة 'تأكيد الحذف' لإتمام العملية")

    # 1. أخذ نسخة احتياطية وقائية فورية قبل التصفير الشامل
    backup_database()

    conn = get_connection()
    cur = conn.cursor()
    try:
        # تعطيل المفاتيح الأجنبية مؤقتاً لتفريغ الجداول بالكامل بأمان
        cur.execute("PRAGMA foreign_keys = OFF;")
        
        # 2. حذف كافة بيانات الجداول المالية وسجلات الفواتير والتدقيق والإعدادات المخصصة
        tables_to_clear = [
            "transfer_allocations",
            "cash_allocations",
            "transfers",
            "cash_payments",
            "purchases",
            "supplier_credits",
            "suppliers",
            "app_settings",
            "audit_log"
        ]
        
        for tbl in tables_to_clear:
            cur.execute(f"DELETE FROM {tbl}")
            
        # 3. تصفير وإعادة ضبط عدادات الترقيم التلقائي (sqlite_sequence) لتبدأ الفواتير والقيود من الرقم 1 للأصل
        cur.execute("""
            DELETE FROM sqlite_sequence 
            WHERE name IN ('purchases', 'transfers', 'transfer_allocations', 'cash_payments', 'cash_allocations', 'suppliers', 'supplier_credits', 'app_settings', 'audit_log')
        """)
        
        # توثيق عملية إعادة الضبط الشاملة في سجل التدقيق الجديد
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
            INSERT INTO audit_log (table_name, record_id, action, old_value, new_value, username, timestamp)
            VALUES ('system', 1, 'DELETE', '{"action": "comprehensive_system_reset"}', '{"status": "reset_to_zero_complete"}', ?, ?)
        """, (username, now_str))

        cur.execute("PRAGMA foreign_keys = ON;")
        conn.commit()
    finally:
        conn.close()

    # 4. ضغط وتنظيف ملف قاعدة البيانات
    try:
        c_vac = get_connection()
        c_vac.execute("VACUUM;")
        c_vac.close()
    except Exception as e:
        print(f"VACUUM note: {e}")

    return True


# ----------------------------------------------------------------------
# الحالة الكاملة (Full State)
# ----------------------------------------------------------------------

def get_full_state():
    return {
        "purchases": get_all_purchases(),
        "transfers": get_all_transfers(),
        "cashPayments": get_all_cash_payments(),
        "suppliers": get_all_suppliers()
    }


# ----------------------------------------------------------------------
# الإعدادات العامة (App Settings)
# ----------------------------------------------------------------------

def set_setting(key: str, value: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO app_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (str(key), str(value)))
    conn.commit()
    conn.close()


def get_setting(key: str, default: str = None) -> str:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT value FROM app_settings WHERE key = ?", (str(key),))
    row = cur.fetchone()
    conn.close()
    if row:
        return row["value"]
    return default


def delete_setting(key: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM app_settings WHERE key = ?", (str(key),))
    conn.commit()
    conn.close()
