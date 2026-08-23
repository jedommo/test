"""
api.py
طبقة API المربوطة بـ pywebview للاتصال المباشر بقاعدة بيانات SQLite (الإصدار V2 المطور)
"""
import database as db


class Api:

    def __init__(self):
        self.current_user = "نظام"
        self._window = None

    def set_window(self, window):
        self._window = window

    # ---------------- المصادقة والأمان ----------------

    def login(self, username, password):
        res = db.verify_login(username, password)
        if res.get("success"):
            self.current_user = res.get("user")
            return res
        return {"success": False, "error": res.get("error", "اسم المستخدم أو كلمة المرور غير صحيحة")}

    def save_login_credentials(self, username, password, enabled=True):
        try:
            ok = db.save_login_credentials(username, password, enabled)
            return {"success": ok}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_saved_login_credentials(self):
        try:
            data = db.get_saved_login_credentials()
            return {"success": True, "data": data}
        except Exception as e:
            return {"success": False, "error": str(e), "data": {"enabled": False}}

    def clear_saved_login_credentials(self):
        try:
            ok = db.clear_saved_login_credentials()
            return {"success": ok}
        except Exception as e:
            return {"success": False, "error": str(e)}


    def logout(self):
        self.current_user = "نظام"
        return {"success": True}

    def change_password(self, username, new_password):
        try:
            ok = db.change_password(username, new_password)
            return {"success": ok}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_all_users(self):
        try:
            users = db.get_all_users()
            return {"success": True, "users": users, "currentUser": self.current_user}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def add_user(self, username, password):
        try:
            user = db.add_user(username, password, username_by=self.current_user)
            return {"success": True, "user": user}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_user(self, user_id):
        try:
            ok = db.delete_user(user_id, current_username=self.current_user, username_by=self.current_user)
            return {"success": ok}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def update_user_profile(self, new_username=None, new_password=None):
        try:
            user = db.update_user_profile(self.current_user, new_username, new_password, username_by=self.current_user)
            if new_username:
                self.current_user = new_username
            return {"success": True, "user": user}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ---------------- الحالة الأولية والموردين ----------------

    def get_initial_data(self):
        try:
            state = db.get_full_state()
            return {"success": True, "data": state}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_all_suppliers(self):
        try:
            sups = db.get_all_suppliers()
            return {"success": True, "suppliers": sups}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def find_or_create_supplier(self, name, phone=None, notes=None):
        try:
            sup = db.find_or_create_supplier(name, phone, notes)
            return {"success": True, "supplier": sup}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ---------------- المشتريات ----------------

    def add_purchase(self, date_str, supplier, item, quantity, price, paid=0, payment_date=None, source_file="إدخال يدوي مباشر"):
        try:
            record = db.add_purchase(date_str, supplier, item, quantity, price, paid, payment_date, source_file, username=self.current_user)
            return {"success": True, "record": record}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def bulk_add_purchases(self, records):
        try:
            inserted = db.bulk_add_purchases(records, username=self.current_user)
            return {"success": True, "records": inserted, "count": len(inserted)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def update_purchase(self, record_id, date_str, supplier, item, quantity, price, paid=None, payment_date=None, source_file=None):
        try:
            updated = db.update_purchase(record_id, date_str, supplier, item, quantity, price, paid, payment_date, source_file, username=self.current_user)
            return {"success": True, "record": updated}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_purchase(self, record_id):
        try:
            ok = db.delete_purchase(record_id, username=self.current_user)
            return {"success": ok}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def bulk_delete_purchases(self, record_ids):
        try:
            count = db.bulk_delete_purchases(record_ids, username=self.current_user)
            return {"success": True, "count": count}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_all_purchases(self):
        return db.get_all_purchases()

    # ---------------- التحويلات البنكية ----------------

    def get_all_transfers(self):
        return db.get_all_transfers()

    def add_bank_transfer(self, date_str, supplier, bank_name, reference_number, amount, notes, allocations):
        try:
            transfer = db.add_bank_transfer(date_str, supplier, bank_name, reference_number, amount, notes, allocations, username=self.current_user)
            return {"success": True, "transfer": transfer}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_bank_transfer(self, transfer_id):
        try:
            ok = db.delete_bank_transfer(transfer_id, username=self.current_user)
            return {"success": ok}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ---------------- السداد النقدي ----------------

    def get_all_cash_payments(self):
        return db.get_all_cash_payments()

    def add_cash_payment(self, date_str, supplier, amount, notes, allocations):
        try:
            payment = db.add_cash_payment(date_str, supplier, amount, notes, allocations, username=self.current_user)
            return {"success": True, "payment": payment}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_cash_payment(self, payment_id):
        try:
            ok = db.delete_cash_payment(payment_id, username=self.current_user)
            return {"success": ok}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_unallocated_amount(self, source_type, source_id):
        try:
            amt = db.get_unallocated_amount(source_type, source_id)
            return {"success": True, "unallocatedAmount": amt}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ---------------- سجل التدقيق ----------------

    def get_audit_log(self, table_name=None, record_id=None, action=None, search=None, limit=300):
        try:
            logs = db.get_audit_log(table_name, record_id, action, search, limit)
            return {"success": True, "logs": logs}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ---------------- تصفير البيانات ----------------

    def clear_all_data(self, confirm_token=""):
        try:
            db.clear_all_data(confirm_token=confirm_token, username=self.current_user)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ---------------- النسخ الاحتياطي والاستعادة ----------------

    def backup_now(self):
        try:
            path = db.backup_database()
            return {"success": True, "path": path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def restore_backup_file(self, file_path):
        try:
            db.restore_database(file_path)
            state = db.get_full_state()
            return {"success": True, "data": state}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def select_restore_file(self):
        """فتح نافذة حوار لاختيار ملف نسخة احتياطية .db"""
        try:
            import webview
            if self._window:
                dialog_type = getattr(getattr(webview, 'FileDialog', None), 'OPEN', getattr(webview, 'OPEN_DIALOG', 10))
                result = self._window.create_file_dialog(
                    dialog_type,
                    allow_multiple=False,
                    file_types=('ملفات قاعدة بيانات SQLite (*.db;*.sqlite)', 'جميع الملفات (*.*)')
                )
                if result and len(result) > 0:
                    chosen_file = result[0]
                    db.restore_database(chosen_file)
                    state = db.get_full_state()
                    return {"success": True, "data": state, "path": chosen_file}
            return {"success": False, "canceled": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ---------------- الإعدادات العامة (Settings, Stamp, Signature, PIN) ----------------

    def get_setting(self, key, default=None):
        try:
            val = db.get_setting(key, default)
            return {"success": True, "value": val, "data": val}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def set_setting(self, key, value):
        try:
            db.set_setting(key, value)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ---------------- حفظ وإدارة ملفات فواتير PDF في مجلد مخصص ----------------

    def _get_invoices_dir(self):
        import os
        base_dir = os.path.dirname(os.path.abspath(__file__))
        invoices_dir = os.path.join(base_dir, "فواتير_المؤسسة_PDF")
        os.makedirs(invoices_dir, exist_ok=True)
        return invoices_dir

    def save_pdf_invoice(self, filename, base64_data):
        import os
        import base64
        try:
            invoices_dir = self._get_invoices_dir()
            if "," in base64_data:
                base64_data = base64_data.split(",", 1)[1]
            file_bytes = base64.b64decode(base64_data)

            # تنظيف اسم الملف وضمان امتداد .pdf
            safe_name = "".join([c for c in filename if c.isalnum() or c in (' ', '_', '-', '.', '(', ')')]).strip()
            if not safe_name.lower().endswith('.pdf'):
                safe_name += '.pdf'

            full_path = os.path.join(invoices_dir, safe_name)
            with open(full_path, "wb") as f:
                f.write(file_bytes)

            return {
                "success": True,
                "path": full_path,
                "filename": safe_name,
                "dir": invoices_dir,
                "size": len(file_bytes)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def open_invoices_folder(self):
        import os
        import subprocess
        try:
            invoices_dir = self._get_invoices_dir()
            if os.name == 'nt':
                os.startfile(invoices_dir)
            else:
                subprocess.Popen(['xdg-open', invoices_dir])
            return {"success": True, "dir": invoices_dir}
        except Exception as e:
            return {"success": False, "error": str(e)}

