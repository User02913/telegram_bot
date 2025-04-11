import asyncio
import time
import logging
import os
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, Updater
from playwright.async_api import async_playwright

# Настраиваем логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получаем токен из переменных окружения или используем существующий
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8155341478:AAFIG7hFNPewG_euxMO0kzAXq1Sq25YiMqY")

# Создаем Flask приложение для веб-сервера (необходимо для Render)
app = Flask(__name__)

# ================== Playwright-парсеры ==================

async def fetch_apr(url, script):
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']  # Необходимо для Render
            )
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(url, timeout=60000)
            await page.wait_for_timeout(10000)
            result = await page.evaluate(script)
            await browser.close()
            return result or "APY не найден"
    except Exception as e:
        logger.error(f"Ошибка при парсинге {url}: {e}")
        return f"Ошибка: {e}"

async def get_usda_apr():
    return await fetch_apr("https://usda.avalonfinance.xyz/swap/",
        """() => [...document.querySelectorAll('*')].map(e => e.textContent.trim()).find(t => /^\d+(\.\d+)?%$/.test(t))""")

async def get_susdf_apr():
    return await fetch_apr("https://app.falcon.finance/overview",
        """() => [...document.querySelectorAll('*')].map(e => e.textContent.trim()).find(t => /^\d+(\.\d+)?%$/.test(t))""")

async def get_usde_apr():
    return await fetch_apr("https://app.ethena.fi/earn",
        """() => [...document.querySelectorAll('*')].map(e => e.textContent.trim()).find(t => /^\d+(\.\d+)?%$/.test(t))""")

async def get_slvl_apr():
    return await fetch_apr("https://app.level.money/",
        """() => {
            const blocks = Array.from(document.querySelectorAll('div.flex')).filter(el =>
                el.textContent.includes('APY') && el.textContent.includes('%'));
            for (const block of blocks) {
                const match = block.textContent.match(/\d+(\.\d+)?%/);
                if (match) return match[0];
            }
            return null;
        }""")

async def get_syrup_apr():
    return await fetch_apr("https://syrup.fi/",
        """() => {
            const apyLabel = Array.from(document.querySelectorAll("span")).find(el => el.textContent.trim() === "APY");
            if (!apyLabel) return null;
            const container = apyLabel.closest('div.MuiStack-root');
            if (!container) return null;
            const percentEl = container.querySelector('h4');
            const percent = percentEl ? percentEl.textContent.trim() : null;
            const hasPercent = container.innerText.includes('%');
            return percent && hasPercent ? percent + "%" : null;
        }""")

async def get_scrvusd_apr():
    return await fetch_apr("https://curve.fi/crvusd/ethereum/scrvUSD/",
        """() => {
            const apyEl = Array.from(document.querySelectorAll('p')).find(el => el.textContent.includes('Estimated APY'));
            if (!apyEl) return null;
            const container = apyEl.closest('div.MuiStack-root');
            if (!container) return null;
            const value = container.querySelector('p.MuiTypography-highlightL');
            const percent = container.querySelector('p.MuiTypography-highlightS');
            return value && percent ? value.textContent.trim() + percent.textContent.trim() : null;
        }""")

async def get_sfrxusd_apr(page):
    try:
        await page.goto("https://app.frax.finance/sfrax/stake", timeout=60000)
        await page.wait_for_timeout(8000)
        # Находим блок с текстом "Est. current APY"
        label = await page.query_selector("text=Est. current APY")
        if not label:
            return "APY не найден"
        container = await label.evaluate_handle("el => el.closest('div.frax-Col-root')")
        apy_div = await container.query_selector("div.frax-1tf5fhe")
        return await apy_div.inner_text() if apy_div else "APY не найден"
    except Exception as e:
        return f"Ошибка: {e}"

async def get_stkgho_apr():
    return await fetch_apr("https://app.aave.com/staking/",
        """() => {
            const label = Array.from(document.querySelectorAll('p')).find(p =>
                p.textContent.trim() === 'Staking APR');
            if (!label) return null;
            const box = label.closest('div')?.parentElement;
            const percentEl = box?.querySelector('p.MuiTypography-root.MuiTypography-secondary14');
            return percentEl && percentEl.textContent.includes('%') ? percentEl.textContent.trim() : null;
        }""")

async def get_stusr_apr():
    return await fetch_apr("https://resolv.xyz/",
        """() => {
            const label = Array.from(document.querySelectorAll('p')).find(el => el.textContent.toLowerCase().includes('usr 7d apy'));
            if (!label) return null;
            const container = label.closest('div');
            const value = container?.nextElementSibling?.querySelector('p.framer-text');
            return value ? value.textContent.trim() + '%' : null;
        }""")

async def get_usdy_apr():
    return await fetch_apr("https://ondo.finance/",
        """() => {
            const apyText = Array.from(document.querySelectorAll('p')).find(p =>
                p.textContent.trim().endsWith('%') && p.textContent.includes('.') && p.textContent.length < 10);
            return apyText ? apyText.textContent.trim() : null;
        }""")

async def get_scusd_apr():
    return await fetch_apr("https://app.rings.money/#/stake",
        """() => {
            const pTags = Array.from(document.querySelectorAll('p')).filter(p =>
                p.textContent.trim().startsWith('~') && p.textContent.includes('%'));
            return pTags.length > 0 ? pTags[0].textContent.trim() : null;
        }""")

# ================== Команды Telegram ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="""
Привет! Я бот для получения APY по стейблкойнам.
Доступные команды:
/usda — APY USDA
/susdf — APY sUSDf
/usde — APY USDe
/slvl — APY slvlUSD
/syrup — APY syrupUSD
/scrvusd — APY scrvUSD
/stkgho — APY stkGHO
/stusr — APY stUSR
/usdy — APY USDY
/scusd — APY scUSD
/sfrxusd — APY sfrxUSD
/all — Все APY сразу
""")

async def send_apr(update: Update, context: ContextTypes.DEFAULT_TYPE, fetch_fn, name):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Получаю APY для {name}...")
    result = await fetch_fn()
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"APY для {name}: {result}")

# Все команды отдельно
async def usda(update, context): await send_apr(update, context, get_usda_apr, "USDA")
async def susdf(update, context): await send_apr(update, context, get_susdf_apr, "sUSDf")
async def usde(update, context): await send_apr(update, context, get_usde_apr, "USDe")
async def slvl(update, context): await send_apr(update, context, get_slvl_apr, "slvlUSD")
async def syrup(update, context): await send_apr(update, context, get_syrup_apr, "syrupUSD")
async def scrvusd(update, context): await send_apr(update, context, get_scrvusd_apr, "scrvUSD")
async def stkgho(update, context): await send_apr(update, context, get_stkgho_apr, "stkGHO")
async def stusr(update, context): await send_apr(update, context, get_stusr_apr, "stUSR")
async def usdy(update, context): await send_apr(update, context, get_usdy_apr, "USDY")
async def scusd(update, context): await send_apr(update, context, get_scusd_apr, "scUSD")
async def sfrxusd(update, context): await send_apr(update, context, get_sfrxusd_apr, "sfrxUSD")

async def all_apr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="🔄 Получаю все APY...")
    start_time = time.time()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']  # Необходимо для Render
        )
        context_browser = await browser.new_context()
        page = await context_browser.new_page()

        results = await asyncio.gather(
            get_usda_apr(), get_susdf_apr(), get_usde_apr(), get_slvl_apr(), get_syrup_apr(),
            get_scrvusd_apr(), get_stkgho_apr(), get_stusr_apr(), get_usdy_apr(), get_scusd_apr(),
            get_sfrxusd_apr(page)  # ← передаём page
        )

        await browser.close()

    elapsed = round(time.time() - start_time, 2)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"""📊 Все APY:
USDA: {results[0]}
sUSDf: {results[1]}
USDe: {results[2]}
slvlUSD: {results[3]}
syrupUSD: {results[4]}
scrvUSD: {results[5]}
stkGHO: {results[6]}
stUSR: {results[7]}
USDY: {results[8]}
scUSD: {results[9]}
sfrxUSD: {results[10]}
⏱ Время: {elapsed} сек""")

# Инициализируем бота глобально, до запуска Flask
bot = ApplicationBuilder().token(BOT_TOKEN).build()

# Регистрация обработчиков команд
bot.add_handler(CommandHandler("start", start))
bot.add_handler(CommandHandler("usda", usda))
bot.add_handler(CommandHandler("susdf", susdf))
bot.add_handler(CommandHandler("usde", usde))
bot.add_handler(CommandHandler("slvl", slvl))
bot.add_handler(CommandHandler("syrup", syrup))
bot.add_handler(CommandHandler("scrvusd", scrvusd))
bot.add_handler(CommandHandler("stkgho", stkgho))
bot.add_handler(CommandHandler("stusr", stusr))
bot.add_handler(CommandHandler("usdy", usdy))
bot.add_handler(CommandHandler("scusd", scusd))
bot.add_handler(CommandHandler("sfrxusd", sfrxusd))
bot.add_handler(CommandHandler("all", all_apr))

# ================== Веб-серверная часть для Render ==================

# Эндпоинт для проверки работоспособности
@app.route('/')
def index():
    return "Бот запущен и работает! Используйте Telegram для взаимодействия с ним."

# Тестовый эндпоинт для проверки
@app.route('/test')
def test():
    return f"Тестовый эндпоинт работает! Токен: {BOT_TOKEN[:5]}... Бот инициализирован: {bot is not None}"

# Эндпоинт для установки вебхука
@app.route('/set_webhook')
def set_webhook():
    logger.info("Получен запрос на установку вебхука")
    render_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://telegram-bot-nhov.onrender.com')
    
    webhook_url = f"{render_url}/webhook"
    logger.info(f"Устанавливаем вебхук на URL: {webhook_url}")
    
    try:
        # Используем напрямую объект бота, который уже инициализирован
        bot.bot.set_webhook(webhook_url)
        logger.info(f"Вебхук успешно установлен на {webhook_url}")
        return f"Вебхук установлен на {webhook_url}"
    except Exception as e:
        logger.error(f"Ошибка при установке вебхука: {e}")
        return f"Ошибка при установке вебхука: {e}"

# Обработчик вебхуков от Telegram
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        logger.info("Получен вебхук от Telegram")
        # Получаем данные запроса
        update_json = request.get_json()
        logger.info(f"Данные вебхука: {update_json}")
        
        # Создаем объект Update
        update = Update.de_json(update_json, bot.bot)
        
        # Запускаем асинхронную обработку в отдельном потоке
        asyncio.run(bot.process_update(update))
        return "OK"
    except Exception as e:
        logger.error(f"Ошибка при обработке вебхука: {e}")
        return f"Ошибка: {e}", 500

# ================== Запуск ==================

if __name__ == "__main__":
    if os.environ.get('RENDER'):
        # На Render запускаем Flask-сервер
        logger.info("Запуск бота в режиме вебхука на Render")
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port)
    else:
        # Локальный запуск в режиме поллинга
        logger.info("Запуск бота в режиме поллинга (локально)")
        bot.run_polling()