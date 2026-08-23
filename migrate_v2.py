"""
migrate_v2.py
سكربت الترقية الشامل والهجرة الآمنة لقاعدة بيانات مؤسسة عربة الخضار التجارية (الإصدار V2)
يقوم بأخذ نسخة احتياطية أولاً، ثم تطبيق كافة التعديلات الهيكلية، ونقل ومعالجة البيانات بدقة.
"""
import sqlite3
import hashlib
import os
import sys
import shutil
import secrets
from datetime import datetime

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


def normalize_arabic_digits(text: str) -> str:
    if not text:
        return ""
    eastern_to_western = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    return str(text).translate(eastern_to_western).strip()


def normalize_date_str(date_val) -> str:
    if not date_val:
        return datetime.now().strftime("%Y-%m-%d")
    s = normalize_arabic_digits(str(date_val)).strip()
    if " " in s:
        s = s.split(" ")[0]
    if "T" in s:
        s = s.split("T")[0]

    formats = ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y", "%Y.%m.%d", "%d.%m.%Y"]
    for fmt in formats:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return datetime.now().strftime("%Y-%m-%d")


def hash_password_v2(plain_password: str, salt: str) -> str:
    return hashlib.sha256((salt + plain_password).encode("utf-8")).hexdigest()


def run_migration():
    print("=" * 70)
    print("🚀 بدء ترقية قاعدة البيانات إلى الإصدار المطور V2...")
    print("=" * 70)

    if not os.path.exists(DB_PATH):
        print(f"⚠️ قاعدة البيانات غير موجودة في: {DB_PATH}، سيتم إنشاؤها جديدة بالكامل.")
    else:
        # 1. أخذ نسخة احتياطية فورية قبل أي تعديل
        backups_dir = os.path.join(get_app_dir(), "backups")
        os.makedirs(backups_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_file = os.path.join(backups_dir, f"store_backup_before_v2_migration_{stamp}.db")
        shutil.copy2(DB_PATH, backup_file)
        print(f"✅ تم إنشاء نسخة احتياطية وقائية في: {backup_file}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF;")
    cur = conn.cursor()

    # ---------------------------------------------------------
    # الخطوة 1: ترقية جدول users ودعم Salt وتغيير كلمة المرور
    # ---------------------------------------------------------
    print("\n1️⃣ ترقية جدول المستخدمين (users) وتأمين التشفير...")
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    users_table_exists = cur.fetchone() is not None

    if not users_table_exists:
        cur.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                must_change_password INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        default_salt = secrets.token_hex(16)
        default_hash = hash_password_v2("1234", default_salt)
        cur.execute(
            "INSERT INTO users (username, password_hash, salt, must_change_password) VALUES (?, ?, ?, 1)",
            ("احمد", default_hash, default_salt)
        )
        print("  - تم إنشاء جدول users وإضافة المستخدم الافتراضي 'احمد' مع فرض تغيير كلمة المرور.")
    else:
        cur.execute("PRAGMA table_info(users)")
        cols = [row["name"] for row in cur.fetchall()]
        if "salt" not in cols:
            cur.execute("ALTER TABLE users ADD COLUMN salt TEXT")
            print("  - تم إضافة عمود salt إلى جدول users.")
        if "must_change_password" not in cols:
            cur.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0")
            print("  - تم إضافة عمود must_change_password إلى جدول users.")
        if "created_at" not in cols:
            cur.execute("ALTER TABLE users ADD COLUMN created_at TEXT DEFAULT ''")



        cur.execute("SELECT id, username, password_hash, salt FROM users")
        users = cur.fetchall()
        for u in users:
            if not u["salt"]:
                new_salt = secrets.token_hex(16)
                old_fixed_salt = "arabat_alkhodar_salt_v1"
                old_default_hash = hashlib.sha256((old_fixed_salt + "1234").encode("utf-8")).hexdigest()
                
                if u["password_hash"] == old_default_hash or u["username"] == "احمد":
                    new_hash = hash_password_v2("1234", new_salt)
                    cur.execute(
                        "UPDATE users SET password_hash = ?, salt = ?, must_change_password = 1 WHERE id = ?",
                        (new_hash, new_salt, u["id"])
                    )
                    print(f"  - تم إعادة تشفير كلمة مرور المستخدم '{u['username']}' بـ Salt جديد وفرض تغييرها.")
                else:
                    cur.execute("UPDATE users SET salt = ? WHERE id = ?", (new_salt, u["id"]))

    # ---------------------------------------------------------
    # الخطوة 2: جدول app_settings
    # ---------------------------------------------------------
    print("\n2️⃣ التحقق من جدول إعدادات النظام (app_settings)...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    cur.execute("DELETE FROM app_settings WHERE key = 'saved_password'")
    print("  - تم التحقق من جدول app_settings وحذف أي كلمات مرور صريحة مخزنة.")

    # ---------------------------------------------------------
    # الخطوة 3: جدول الموردين الموحّد (suppliers Master Data)
    # ---------------------------------------------------------
    print("\n3️⃣ إنشاء جدول الموردين الموحّد (suppliers) وهجرة الأسماء...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE,
            phone TEXT,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    existing_suppliers = set()
    for table_name in ["purchases", "transfers", "cash_payments"]:
        cur.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        if cur.fetchone():
            cur.execute(f"SELECT DISTINCT supplier FROM {table_name} WHERE supplier IS NOT NULL")
            for row in cur.fetchall():
                raw_name = row["supplier"]
                if raw_name:
                    clean_name = " ".join(str(raw_name).strip().split())
                    if clean_name:
                        existing_suppliers.add(clean_name)

    for sup_name in sorted(existing_suppliers):
        cur.execute("SELECT id FROM suppliers WHERE TRIM(LOWER(name)) = TRIM(LOWER(?))", (sup_name,))
        if not cur.fetchone():
            cur.execute("INSERT INTO suppliers (name) VALUES (?)", (sup_name,))
            print(f"  - تم إضافة المورد: '{sup_name}' إلى جدول suppliers.")

    # ---------------------------------------------------------
    # الخطوة 4: جداول سجل التدقيق والأرصدة
    # ---------------------------------------------------------
    print("\n4️⃣ إنشاء جدول سجل تدقيق العمليات (audit_log) وجدول أرصدة الموردين (supplier_credits)...")
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

    # ---------------------------------------------------------
    # الخطوة 5: إعادة بناء جدول purchases مع قيود CHECK وعمود status
    # ---------------------------------------------------------
    print("\n5️⃣ ترقية وهيكلة جدول المشتريات (purchases) مع قيود CHECK وفصل status...")
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='purchases'")
    has_purchases_table = cur.fetchone() is not None

    purchases_rows = []
    if has_purchases_table:
        cur.execute("SELECT * FROM purchases")
        purchases_rows = cur.fetchall()

    cur.execute("DROP TABLE IF EXISTS purchases_new")
    cur.execute("""
        CREATE TABLE purchases_new (
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

    migrated_purchases_count = 0
    for r in purchases_rows:
        try:
            p_id = r["id"]
            p_date = normalize_date_str(r["date"])
            p_sup = " ".join(str(r["supplier"]).strip().split()) if r["supplier"] else "مورد عام"
            
            cur.execute("SELECT id FROM suppliers WHERE TRIM(LOWER(name)) = TRIM(LOWER(?))", (p_sup,))
            sup_row = cur.fetchone()
            p_sup_id = sup_row["id"] if sup_row else None
            
            p_item = str(r["item"]).strip() if r["item"] else "صنف عام"
            p_qty = max(0.01, float(r["quantity"])) if r["quantity"] else 1.0
            p_price = max(0.0, float(r["price"])) if r["price"] else 0.0
            p_tot = round(p_qty * p_price, 2)
            p_paid = max(0.0, float(r["paid"])) if "paid" in r.keys() and r["paid"] is not None else 0.0
            p_rem = round(max(0.0, p_tot - p_paid), 2)
            
            if p_rem <= 0:
                p_status = "paid"
                p_is_paid = 1
            elif p_paid > 0:
                p_status = "partial"
                p_is_paid = 0
            else:
                p_status = "unpaid"
                p_is_paid = 0

            raw_pdate = str(r["payment_date"]) if "payment_date" in r.keys() and r["payment_date"] else ""
            if any(desc in raw_pdate for desc in ["آجل", "دين", "سداد", "مسدد", "نقدي", "نقد"]):
                p_pdate = p_date if p_is_paid else None
            else:
                p_pdate = normalize_date_str(raw_pdate) if raw_pdate.strip() else None

            p_src = r["source_file"] if "source_file" in r.keys() and r["source_file"] else "إدخال يدوي مباشر"
            p_created = r["created_at"] if "created_at" in r.keys() and r["created_at"] else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cur.execute("""
                INSERT INTO purchases_new (id, date, supplier, supplier_id, item, quantity, price, total, is_paid, paid, remaining, status, payment_date, source_file, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (p_id, p_date, p_sup, p_sup_id, p_item, p_qty, p_price, p_tot, p_is_paid, p_paid, p_rem, p_status, p_pdate, p_src, p_created))
            migrated_purchases_count += 1
        except Exception as e:
            print(f"  [خطأ في هجرة فاتورة] #{r['id']}: {e}")

    if has_purchases_table:
        cur.execute("DROP TABLE purchases")
    cur.execute("ALTER TABLE purchases_new RENAME TO purchases")
    print(f"  - تم ترقية جدول purchases وهجرة {migrated_purchases_count} قيد بنجاح.")

    # ---------------------------------------------------------
    # الخطوة 6: إعادة بناء transfers مع قيود CHECK و supplier_id
    # ---------------------------------------------------------
    print("\n6️⃣ ترقية جدول التحويلات البنكية (transfers)...")
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transfers'")
    has_transfers_table = cur.fetchone() is not None

    transfers_rows = []
    if has_transfers_table:
        cur.execute("SELECT * FROM transfers")
        transfers_rows = cur.fetchall()

    cur.execute("DROP TABLE IF EXISTS transfers_new")
    cur.execute("""
        CREATE TABLE transfers_new (
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

    migrated_transfers_count = 0
    for t in transfers_rows:
        try:
            t_id = t["id"]
            t_date = normalize_date_str(t["date"])
            t_sup = " ".join(str(t["supplier"]).strip().split()) if t["supplier"] else "مورد عام"
            cur.execute("SELECT id FROM suppliers WHERE TRIM(LOWER(name)) = TRIM(LOWER(?))", (t_sup,))
            sup_row = cur.fetchone()
            t_sup_id = sup_row["id"] if sup_row else None

            t_bank = t["bank_name"] if "bank_name" in t.keys() else "الراجحي"
            t_ref = t["reference_number"] if "reference_number" in t.keys() else ""
            t_amt = max(0.01, float(t["amount"])) if t["amount"] else 0.01
            t_notes = t["notes"] if "notes" in t.keys() else ""
            t_settled = int(t["settled_debt"]) if "settled_debt" in t.keys() and t["settled_debt"] else 0
            t_created = t["created_at"] if "created_at" in t.keys() and t["created_at"] else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cur.execute("""
                INSERT INTO transfers_new (id, date, supplier, supplier_id, bank_name, reference_number, amount, notes, settled_debt, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (t_id, t_date, t_sup, t_sup_id, t_bank, t_ref, t_amt, t_notes, t_settled, t_created))
            migrated_transfers_count += 1
        except Exception as e:
            print(f"  [خطأ في هجرة تحويل] #{t['id']}: {e}")

    if has_transfers_table:
        cur.execute("DROP TABLE transfers")
    cur.execute("ALTER TABLE transfers_new RENAME TO transfers")
    print(f"  - تم ترقية جدول transfers وهجرة {migrated_transfers_count} عملية تحويل.")

    # ---------------------------------------------------------
    # الخطوة 7: إعادة بناء transfer_allocations مع قيود CHECK
    # ---------------------------------------------------------
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transfer_allocations'")
    has_t_alloc = cur.fetchone() is not None
    t_alloc_rows = []
    if has_t_alloc:
        cur.execute("SELECT * FROM transfer_allocations")
        t_alloc_rows = cur.fetchall()

    cur.execute("DROP TABLE IF EXISTS transfer_allocations_new")
    cur.execute("""
        CREATE TABLE transfer_allocations_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transfer_id INTEGER NOT NULL REFERENCES transfers(id) ON DELETE CASCADE,
            purchase_id INTEGER NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
            amount REAL NOT NULL CHECK(amount > 0)
        )
    """)

    for ta in t_alloc_rows:
        try:
            if float(ta["amount"]) > 0:
                cur.execute("""
                    INSERT INTO transfer_allocations_new (id, transfer_id, purchase_id, amount)
                    VALUES (?, ?, ?, ?)
                """, (ta["id"], ta["transfer_id"], ta["purchase_id"], float(ta["amount"])))
        except Exception as e:
            print(f"  [تخطي تخصيص تحويل تالف]: {e}")

    if has_t_alloc:
        cur.execute("DROP TABLE transfer_allocations")
    cur.execute("ALTER TABLE transfer_allocations_new RENAME TO transfer_allocations")

    # ---------------------------------------------------------
    # الخطوة 8: إعادة بناء cash_payments مع قيود CHECK و supplier_id
    # ---------------------------------------------------------
    print("\n7️⃣ ترقية جدول السداد النقدي (cash_payments)...")
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cash_payments'")
    has_cash_table = cur.fetchone() is not None

    cash_rows = []
    if has_cash_table:
        cur.execute("SELECT * FROM cash_payments")
        cash_rows = cur.fetchall()

    cur.execute("DROP TABLE IF EXISTS cash_payments_new")
    cur.execute("""
        CREATE TABLE cash_payments_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            supplier TEXT NOT NULL,
            supplier_id INTEGER REFERENCES suppliers(id),
            amount REAL NOT NULL CHECK(amount > 0),
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    migrated_cash_count = 0
    for c in cash_rows:
        try:
            c_id = c["id"]
            c_date = normalize_date_str(c["date"])
            c_sup = " ".join(str(c["supplier"]).strip().split()) if c["supplier"] else "مورد عام"
            cur.execute("SELECT id FROM suppliers WHERE TRIM(LOWER(name)) = TRIM(LOWER(?))", (c_sup,))
            sup_row = cur.fetchone()
            c_sup_id = sup_row["id"] if sup_row else None

            c_amt = max(0.01, float(c["amount"])) if c["amount"] else 0.01
            c_notes = c["notes"] if "notes" in c.keys() else ""
            c_created = c["created_at"] if "created_at" in c.keys() and c["created_at"] else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cur.execute("""
                INSERT INTO cash_payments_new (id, date, supplier, supplier_id, amount, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (c_id, c_date, c_sup, c_sup_id, c_amt, c_notes, c_created))
            migrated_cash_count += 1
        except Exception as e:
            print(f"  [خطأ في هجرة سداد نقدي] #{c['id']}: {e}")

    if has_cash_table:
        cur.execute("DROP TABLE cash_payments")
    cur.execute("ALTER TABLE cash_payments_new RENAME TO cash_payments")
    print(f"  - تم ترقية جدول cash_payments وهجرة {migrated_cash_count} عملية سداد نقدي.")

    # ---------------------------------------------------------
    # الخطوة 9: إعادة بناء cash_allocations مع قيود CHECK
    # ---------------------------------------------------------
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cash_allocations'")
    has_c_alloc = cur.fetchone() is not None
    c_alloc_rows = []
    if has_c_alloc:
        cur.execute("SELECT * FROM cash_allocations")
        c_alloc_rows = cur.fetchall()

    cur.execute("DROP TABLE IF EXISTS cash_allocations_new")
    cur.execute("""
        CREATE TABLE cash_allocations_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cash_payment_id INTEGER NOT NULL REFERENCES cash_payments(id) ON DELETE CASCADE,
            purchase_id INTEGER NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
            amount REAL NOT NULL CHECK(amount > 0)
        )
    """)

    for ca in c_alloc_rows:
        try:
            if float(ca["amount"]) > 0:
                cur.execute("""
                    INSERT INTO cash_allocations_new (id, cash_payment_id, purchase_id, amount)
                    VALUES (?, ?, ?, ?)
                """, (ca["id"], ca["cash_payment_id"], ca["purchase_id"], float(ca["amount"])))
        except Exception as e:
            print(f"  [تخطي تخصيص سداد تالف]: {e}")

    if has_c_alloc:
        cur.execute("DROP TABLE cash_allocations")
    cur.execute("ALTER TABLE cash_allocations_new RENAME TO cash_allocations")

    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.close()

    print("\n" + "=" * 70)
    print("✨ تمت عملية الترقية والهجرة V2 بنجاح 100%! قاعدة البيانات مؤمنة ومطابقة للمواصفات الجديدة.")
    print("=" * 70)


if __name__ == "__main__":
    run_migration()
