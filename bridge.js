/**
 * bridge.js — محرك الاتصال المباشر بقاعدة بيانات SQLite store.db (الإصدار V2 المطور)
 * ==============================================================================
 * يعتمد على استدعاءات pywebview المباشرة لقاعدة بيانات SQLite
 * تم إلغاء تخزين بيانات الفواتير والحسابات في localStorage نهائياً.
 */

(function () {
    'use strict';

    // 1. تنظيف أي بيانات فواتير قديمة متروكة في localStorage
    try {
        localStorage.removeItem('araba_purchases_data');
        localStorage.removeItem('araba_transfers_data');
        localStorage.removeItem('araba_cash_payments_data');
        localStorage.removeItem('araba_custom_expenses_names');
    } catch (e) {
        console.warn('تنظيف بيانات التخزين المؤقت:', e);
    }

    // 2. مؤشر الحفظ البصري
    let indicatorEl = null;

    function ensureIndicator() {
        if (indicatorEl && document.body.contains(indicatorEl)) return indicatorEl;
        indicatorEl = document.createElement('div');
        indicatorEl.style.position = 'fixed';
        indicatorEl.style.bottom = '16px';
        indicatorEl.style.right = '16px';
        indicatorEl.style.zIndex = '999999';
        indicatorEl.style.padding = '8px 16px';
        indicatorEl.style.borderRadius = '12px';
        indicatorEl.style.fontFamily = 'Cairo, sans-serif';
        indicatorEl.style.fontSize = '12px';
        indicatorEl.style.fontWeight = '700';
        indicatorEl.style.boxShadow = '0 10px 25px -5px rgba(0,0,0,0.2)';
        indicatorEl.style.transition = 'all 0.3s cubic-bezier(0.16, 1, 0.3, 1)';
        indicatorEl.style.opacity = '0';
        indicatorEl.style.pointerEvents = 'none';
        document.body.appendChild(indicatorEl);
        return indicatorEl;
    }

    window.showSavedIndicator = function (msg) {
        const el = ensureIndicator();
        el.style.background = '#064e3b';
        el.style.color = '#a7f3d0';
        el.style.border = '1px solid #10b981';
        el.textContent = msg || '☑ تم الحفظ تلقائياً في قاعدة البيانات';
        el.style.opacity = '1';
        el.style.transform = 'translateY(0)';
        clearTimeout(el._hideTimer);
        el._hideTimer = setTimeout(() => {
            el.style.opacity = '0';
            el.style.transform = 'translateY(8px)';
        }, 2200);
    };

    window.showSaveErrorIndicator = function (msg) {
        const el = ensureIndicator();
        el.style.background = '#881337';
        el.style.color = '#fecdd3';
        el.style.border = '1px solid #f43f5e';
        el.textContent = msg || '⚠ تعذر حفظ العملية في قاعدة البيانات';
        el.style.opacity = '1';
        el.style.transform = 'translateY(0)';
        clearTimeout(el._hideTimer);
        el._hideTimer = setTimeout(() => {
            el.style.opacity = '0';
            el.style.transform = 'translateY(8px)';
        }, 3500);
    };

    // 3. كائن API الموحد المتاح للواجهة
    window.DB_API = {
        async getInitialData() {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.get_initial_data();
        },
        async login(username, password) {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.login(username, password);
        },
        async saveLoginCredentials(username, password, enabled = true) {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.save_login_credentials(username, password, enabled);
        },
        async getSavedLoginCredentials() {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.get_saved_login_credentials();
        },
        async clearSavedLoginCredentials() {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.clear_saved_login_credentials();
        },
        async changePassword(username, newPassword) {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.change_password(username, newPassword);
        },
        async getAllUsers() {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.get_all_users();
        },
        async addUser(username, password) {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.add_user(username, password);
        },
        async deleteUser(userId) {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.delete_user(userId);
        },
        async updateUserProfile(newUsername, newPassword) {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.update_user_profile(newUsername, newPassword);
        },
        async getAllSuppliers() {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.get_all_suppliers();
        },
        async findOrCreateSupplier(name, phone, notes) {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.find_or_create_supplier(name, phone, notes);
        },
        async addPurchase(record) {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.add_purchase(
                record.date, record.supplier, record.item,
                record.quantity, record.price, record.paid || 0,
                record.paymentDate, record.sourceFile || 'إدخال يدوي مباشر'
            );
        },
        async bulkAddPurchases(records) {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.bulk_add_purchases(records);
        },
        async updatePurchase(record) {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.update_purchase(
                record.id, record.date, record.supplier, record.item,
                record.quantity, record.price, record.paid,
                record.paymentDate, record.sourceFile
            );
        },
        async deletePurchase(recordId) {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.delete_purchase(recordId);
        },
        async bulkDeletePurchases(recordIds) {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.bulk_delete_purchases(recordIds);
        },
        async addBankTransfer(transfer) {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.add_bank_transfer(
                transfer.date, transfer.supplier, transfer.bankName,
                transfer.referenceNumber, transfer.amount, transfer.notes,
                transfer.allocations || []
            );
        },
        async deleteBankTransfer(transferId) {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.delete_bank_transfer(transferId);
        },
        async addCashPayment(payment) {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.add_cash_payment(
                payment.date, payment.supplier, payment.amount,
                payment.notes, payment.allocations || []
            );
        },
        async deleteCashPayment(paymentId) {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.delete_cash_payment(paymentId);
        },
        async getUnallocatedAmount(sourceType, sourceId) {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.get_unallocated_amount(sourceType, sourceId);
        },
        async getAuditLog(tableName, recordId, action, search, limit) {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.get_audit_log(tableName, recordId, action, search, limit);
        },
        async clearAllData(confirmToken) {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.clear_all_data(confirmToken);
        },
        async backupNow() {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.backup_now();
        },
        async selectRestoreFile() {
            if (!window.pywebview || !window.pywebview.api) return null;
            return await window.pywebview.api.select_restore_file();
        },
        async getSetting(key, defVal) {
            if (!window.pywebview || !window.pywebview.api) {
                const v = localStorage.getItem('araba_setting_' + key) || defVal;
                return { success: true, value: v, data: v };
            }
            const res = await window.pywebview.api.get_setting(key, defVal);
            if (res && res.success && res.data === undefined && res.value !== undefined) {
                res.data = res.value;
            }
            return res;
        },
        async setSetting(key, val) {
            localStorage.setItem('araba_setting_' + key, val || '');
            if (!window.pywebview || !window.pywebview.api) return { success: true };
            return await window.pywebview.api.set_setting(key, val);
        },
        async savePdfInvoice(filename, base64Data) {
            if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.save_pdf_invoice !== 'function') {
                return null;
            }
            return await window.pywebview.api.save_pdf_invoice(filename, base64Data);
        },
        async openInvoicesFolder() {
            if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.open_invoices_folder !== 'function') {
                if (typeof window.showToast === 'function') {
                    window.showToast("فتح المجلد مدعوم عند تشغيل تطبيق سطح المكتب", "info");
                }
                return { success: false, error: "Desktop app not running" };
            }
            const res = await window.pywebview.api.open_invoices_folder();
            if (res && res.success) {
                if (typeof window.showToast === 'function') {
                    window.showToast("تم فتح مجلد الفواتير بنجاح 📂", "success");
                }
            }
            return res;
        }
    };

    window.openInvoicesFolder = async function() {
        return await window.DB_API.openInvoicesFolder();
    };

    // 4. النسخ الاحتياطي لقاعدة البيانات
    window.createDatabaseBackup = async function () {
        try {
            const res = await window.DB_API.backupNow();
            if (res && res.success) {
                const msg = `تم إنشاء نسخة احتياطية لقاعدة البيانات بنجاح: ${res.path}`;
                if (typeof window.showToast === 'function') {
                    window.showToast(msg, 'success');
                }
                window.showSavedIndicator('☑ تم حفظ نسخة SQLite');
            } else {
                if (typeof window.showToast === 'function') {
                    window.showToast('فشل إنشاء النسخة الاحتياطية: ' + (res ? res.error : ''), 'error');
                }
            }
        } catch (e) {
            console.error('خطأ أثناء النسخ الاحتياطي:', e);
        }
    };

    // 5. استعادة قاعدة البيانات من ملف .db
    window.restoreDatabaseBackup = async function () {
        if (!confirm('تحذير: استعادة نسخة قاعدة البيانات ستستبدل جميع البيانات الحالية بالبيانات الموجودة في الملف المختار (مع أخذ نسخة وقائية تلقائياً). هل تريد المتابعة؟')) {
            return;
        }
        try {
            const res = await window.DB_API.selectRestoreFile();
            if (res && res.success && res.data) {
                if (typeof window.loadFullAppStateFromDB === 'function') {
                    await window.loadFullAppStateFromDB();
                }
                if (typeof window.showToast === 'function') {
                    window.showToast('تمت استعادة قاعدة البيانات بنجاح من: ' + res.path, 'success');
                }
                window.showSavedIndicator('☑ تمت استعادة قاعدة البيانات');
            } else if (res && res.canceled) {
                // تم الإلغاء
            } else {
                if (typeof window.showToast === 'function') {
                    window.showToast('فشل استعادة قاعدة البيانات: ' + (res ? res.error : 'ملف غير صالح'), 'error');
                }
            }
        } catch (e) {
            console.error('خطأ أثناء استعادة قاعدة البيانات:', e);
            if (typeof window.showToast === 'function') {
                window.showToast('حدث خطأ أثناء استعادة النسخة الاحتياطية', 'error');
            }
        }
    };

})();
