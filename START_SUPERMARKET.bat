@echo off
title SuperMart - Secure Supermarket System
color 0A

echo.
echo  ================================================
echo    SuperMart - Secure Supermarket System
echo    BSc(Hons) Computer Security - PUSL3190
echo    Student: Ranawaka Mihisara - 10953227
echo  ================================================
echo.
echo  Starting server, please wait...
echo.

cd /d "%USERPROFILE%\Desktop\supermarket_system_web\supermarket_system"

if not exist "app.py" (
    echo  ERROR: Could not find the project folder.
    echo  Make sure the folder is on your Desktop and
    echo  named: supermarket_system_web
    echo.
    pause
    exit
)

echo  Server is starting...
echo.
echo  Once you see "Running on http://127.0.0.1:5000"
echo  open your browser and go to: http://localhost:5000
echo.
echo  Login with:
echo    Username : admin
echo    Password : Admin@123
echo.
echo  ================================================
echo.

python app.py

echo.
echo  Server stopped.
pause