@echo off
echo ========================================
echo Invoice Data Extractor - Setup Script
echo ========================================
echo.

echo Installing Python dependencies...
pip install -r requirements.txt

echo.
echo ========================================
echo Setup complete!
echo ========================================
echo.
echo Next steps:
echo 1. Create a .env file (copy from .env.example)
echo 2. Add your Gemini API key to .env
echo 3. Run: streamlit run app.py
echo.
pause
