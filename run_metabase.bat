@echo off
echo ========================================================
echo   Lancement de Metabase - Banking Analytics Platform
echo ========================================================
cd /d "%~dp0metabase"
docker compose up -d
echo.
echo Metabase demarre (90 secondes environ)...
timeout /t 90 /nobreak > nul
echo.
echo Configuration automatique des dashboards...
cd /d "%~dp0"
uv run python metabase/setup_metabase.py
echo.
echo Ouverture de Metabase dans le navigateur...
start http://localhost:3000
echo.
echo Identifiants Metabase :
echo   - URL      : http://localhost:3000
echo   - Email    : admin@banking.local
echo   - Password : Admin123!
echo ========================================================
pause
