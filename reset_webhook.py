import asyncio
import os
from dotenv import load_dotenv
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

load_dotenv('.env')

BOT_TOKEN = os.getenv("BOT_TOKEN")
PA_USERNAME = os.getenv("PYTHONANYWHERE_USERNAME")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
WEBHOOK_URL = f"https://{PA_USERNAME}.pythonanywhere.com/{WEBHOOK_SECRET}"
PROXY_URL = "http://proxy.server:3128"

async def reset_webhook():
    session = AiohttpSession(proxy=PROXY_URL)
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML), session=session)

    await bot.delete_webhook(drop_pending_updates=True)
    print("Old webhook deleted")

    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True, allowed_updates=["message", "callback_query"])
    print(f"New webhook set: {WEBHOOK_URL}")

    info = await bot.get_webhook_info()
    print(f"Webhook URL: {info.url}")
    print(f"Allowed updates: {info.allowed_updates}")

    await bot.session.close()

asyncio.run(reset_webhook())
