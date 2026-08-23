"""
main.py
نقطة تشغيل تطبيق مؤسسة عربة الخضار التجارية (الإصدار V2 المطور)
- نسخ احتياطي تلقائي وقائي عند الفتح وعند الإغلاق مع التدوير (15 نسخة).
- ربط محرك PyWebView بـ SQLite API V2.
"""
import os
import sys
import webview

import database as db
from api import Api


def resource_path(relative_path):
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def on_closing():
    """أخذ نسخة احتياطية تلقائية آمنة قبل إغلاق التطبيق مباشرة"""
    try:
        db.backup_database()
    except Exception as e:
        print(f"خطأ في النسخ الاحتياطي عند الإغلاق: {e}")


def main():
    # 1. تهيئة قاعدة البيانات وأخذ نسخة احتياطية فورية عند بدء التشغيل
    db.init_db()
    try:
        db.backup_database()
    except Exception as e:
        print(f"خطأ في النسخ الاحتياطي عند بدء التشغيل: {e}")

    api = Api()
    html_path = resource_path("index.html")

    window = webview.create_window(
        title="مؤسسة عربة الخضار التجارية | نظام المشتريات وكشف الدين",
        url=html_path,
        js_api=api,
        width=1440,
        height=900,
        min_size=(1024, 700),
        text_select=True,
        maximized=True,
    )
    api.set_window(window)

    # ربط حدث إغلاق النافذة
    window.events.closing += on_closing

    webview.start(debug=False)


if __name__ == "__main__":
    main()
