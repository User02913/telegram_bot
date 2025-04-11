#!/bin/bash
echo "📦 Установка зависимостей..."
pip install -r requirements.txt

echo "🌐 Установка браузеров для Playwright..."
python3 -m playwright install chromium
