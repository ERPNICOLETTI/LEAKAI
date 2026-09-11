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
    echo [!] Initializing Git repository...
    git init
    git branch -M main
    echo.
)

:: Check if remote origin is set
git remote get-url origin >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Remote origin URL not set.
    set /p REPO_URL="Enter your GitHub repository URL (e.g., https://github.com/username/leakai.git): "
    if not "%REPO_URL%"=="" (
        git remote add origin %REPO_URL%
    ) else (
        echo [X] Error: No repository URL provided. Aborting.
        pause
        exit /b 1
    )
    echo.
)

:: Prompt for commit message
set /p COMMIT_MSG="Enter commit message (Press Enter for default: 'Update LeakAI MVP'): "
if "%COMMIT_MSG%"=="" set COMMIT_MSG=Update LeakAI MVP

echo.
echo [+] Staging files...
git add .

echo [+] Committing changes...
git commit -m "%COMMIT_MSG%"

echo [+] Pushing to GitHub (main branch)...
git push -u origin main

echo.
if %errorlevel% equ 0 (
    echo ========================================================
    echo [SUCCESS] Code pushed to GitHub successfully!
    echo ========================================================
) else (
    echo ========================================================
    echo [ERROR] Push failed. Please check your GitHub remote or credentials.
    echo ========================================================
)

echo.
pause
