#!/bin/bash
# Устанавливаем зависимости Python
pip install -r requirements.txt

# Устанавливаем Playwright с опцией для пропуска системных зависимостей
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 playwright install
# Затем вручную устанавливаем только браузер
playwright install chromium