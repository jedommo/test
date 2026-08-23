@echo off
chcp 65001 >nul
title بناء ملف EXE - مؤسسة عربة الخضار التجارية

echo ========================================================
echo   جاري بناء ملف تشغيل التطبيق المستقل (EXE)...
echo ========================================================
echo.

echo [1/2] التحقق من تثبيت متطلبات بايثون...
python -m pip install -r requirements.txt

echo.
echo [2/2] تجميع وحزم البرنامج في ملف EXE واحد مستقل...
python -m PyInstaller --onefile --windowed --name "ArabatAlKhodar" ^
  --icon="logo.ico" ^
  --add-data "index.html;." ^
  --add-data "logo.jpg;." ^
  --add-data "logo.ico;." ^
  --add-data "bridge.js;." ^
  --clean main.py

echo.
echo ========================================================
echo   تم اكتمال البناء بنجاح!
echo   الملف التنفيذي جاهز في المجلد: dist\ArabatAlKhodar.exe
echo   يمكنك نقله لأي جهاز وتشغيله مباشرة بدون بايثون!
echo ========================================================
pause
