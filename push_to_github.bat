@echo off
title Push LeakAI to GitHub
color 0A

echo ========================================================
echo               LeakAI - GitHub Push Utility
echo ========================================================
echo.

cd /d "%~dp0"

:: Check if git is initialized
if not exist ".git" (
    echo [+] Initializing Git repository...
    git init
    git branch -M main
    git remote add origin https://github.com/ERPNICOLETTI/LEAKAI.git
    echo.
)

:: Set commit message
if "%~1"=="--no-pause" (
    set COMMIT_MSG=Auto-update LeakAI software
) else (
    set /p COMMIT_MSG="Enter commit message (Press Enter for default: 'Update LeakAI software'): "
)
if "%COMMIT_MSG%"=="" set COMMIT_MSG=Update LeakAI software

echo.
echo [+] Staging files...
git add .

echo [+] Committing changes...
git commit -m "%COMMIT_MSG%" >nul 2>&1

echo [+] Pushing to GitHub (https://github.com/ERPNICOLETTI/LEAKAI)...
git push -u origin main

echo.
if %errorlevel% equ 0 (
    echo ========================================================
    echo [SUCCESS] Code pushed to https://github.com/ERPNICOLETTI/LEAKAI successfully!
    echo ========================================================
) else (
    echo ========================================================
    echo [ERROR] Push failed. Please check your internet or credentials.
    echo ========================================================
)

echo.
if not "%~1"=="--no-pause" pause
