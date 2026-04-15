import asyncio
import os
import json
import re
from io import BytesIO
from datetime import datetime
from typing import Optional

import gspread
from google import genai
from PIL import Image
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from flask import Flask, request

from mapping_service import MappingService

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_AI_STUDIO_KEY = os.getenv("GOOGLE_AI_STUDIO_KEY")
GOOGLE_SHEET_URL = os.getenv("GOOGLE_SHEET_URL")
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
PA_USERNAME = os.getenv("PYTHONANYWHERE_USERNAME")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
PROXY_URL = "proxy.server:3128"

# Construct Webhook URL
WEBHOOK_URL = f"https://{PA_USERNAME}.pythonanywhere.com/{WEBHOOK_SECRET}"

# Bot and Dispatcher setup
# We will initialize them without a global session to avoid loop conflicts on PythonAnywhere
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher(storage=MemoryStorage())
app = Flask(__name__)

# Initialize Gemini Client
# The SDK automatically uses HTTP_PROXY/HTTPS_PROXY environment variables
gemini_client = genai.Client(api_key=GOOGLE_AI_STUDIO_KEY)

# Initialize Mapping Service
mapping_service = MappingService(GOOGLE_SHEET_URL, GOOGLE_SERVICE_ACCOUNT_FILE)

class ReceiptData(BaseModel):
    alpha_name: Optional[str] = Field(None, description="The EXACT legal name of the merchant as written on the receipt (e.g. 'PROWEB MCHJ', 'OOO HITECH MED LAB').")
    brand_name: Optional[str] = Field(None, description="The commercial short brand name (e.g. 'Proweb' for 'PROWEB MCHJ', 'Yandex Go' for 'YANDEXGO UB SCOOTER').")
    category: Optional[str] = Field(None, description="Main category of the business (e.g. Учебный центр, Аптека, Кофе, Фаст-Фуд). Invent a fitting one in Russian.")
    subcategory: Optional[str] = Field(None, description="Subcategory of the business (e.g. ИТ-курсы, Пицца, Женская одежда). Invent a fitting one in Russian.")

def get_sheets_client():
    """Authenticates and returns the Google Sheets client."""
    try:
        if not os.path.exists(GOOGLE_SERVICE_ACCOUNT_FILE):
            print(f"Error: Credentials file {GOOGLE_SERVICE_ACCOUNT_FILE} not found!")
            return None
        return gspread.service_account(filename=GOOGLE_SERVICE_ACCOUNT_FILE)
    except Exception as e:
        print(f"Error connecting to Google Sheets: {e}")
        return None

async def extract_receipt_data(image_bytes: bytes):
    """Sends image to Google Gemini 1.5 Flash for data extraction."""
    try:
        img = Image.open(BytesIO(image_bytes))
        
        prompt = """
        Analyze this receipt. Extract the following information:
        - alpha_name: The EXACT legal name of the merchant (found at top or bottom, often contains MCHJ, OOO, etc.).
        - brand_name: A short, clean commercial brand name derived from the receipt (e.g. "Proweb", "Korzinka").
        - category: A suitable business category in Russian (e.g. "Учебный центр").
        - subcategory: A suitable business subcategory in Russian (e.g. "ИТ-курсы").
        """

        response = await gemini_client.aio.models.generate_content(
            model='gemini-2.5-flash',
            contents=[img, prompt],
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=ReceiptData.model_json_schema()
            )
        )
        
        raw_text = response.text.strip()
        print(f"DEBUG: Raw AI Response: {raw_text}")
        
        data_dict = json.loads(raw_text)
        validated_data = ReceiptData(**data_dict)
        return validated_data.model_dump()
    except Exception as e:
        print(f"Gemini Extraction Error: {e}")
        return None

async def save_to_sheet(data: dict):
    """Appends extracted data to Google Sheets (Worksheet 0)."""
    client = get_sheets_client()
    if not client:
        return False
    
    try:
        sh = client.open_by_url(GOOGLE_SHEET_URL)
        # We assume expenses go to a different sheet than mapping if possible, 
        # but for now we'll use the first sheet as per previous setup.
        sheet = sh.get_worksheet(0) 
        
        row = [
            data.get('brand_name', ''),
            data.get('alpha_name', ''),
            data.get('category', ''),
            data.get('subcategory', ''),
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ]
        sheet.append_row(row)
        return True
    except Exception as e:
        print(f"Sheets Error: {e}")
        return False

# --- State Management ---
class SearchState(StatesGroup):
    waiting_for_brand = State()
    waiting_for_legal = State()
    waiting_for_category = State()
    waiting_for_subcategory = State()

# --- Keyboards ---
def get_main_keyboard():
    buttons = [
        [KeyboardButton(text="🔍 По бренду"), KeyboardButton(text="🏢 По юр. лицу")],
        [KeyboardButton(text="📂 По категории"), KeyboardButton(text="🔹 По подкатегории")],
        [KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(
        keyboard=buttons, 
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите режим поиска..."
    )

def get_cancel_keyboard():
    buttons = [[KeyboardButton(text="❌ Отмена")]]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Привет! Я умный сканер чеков с базой брендов.\n\n"
        "1. **Пришли фото чека** — я автоматически определю категорию по юр. лицу.\n"
        "2. **Выбери режим поиска** ниже, чтобы найти информацию вручную.",
        reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "❌ Отмена")
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено. Выберите режим поиска:", reply_markup=get_main_keyboard())

@dp.message(F.text == "🔍 По бренду")
async def search_brand_mode(message: types.Message, state: FSMContext):
    await state.set_state(SearchState.waiting_for_brand)
    await message.answer("Введите название бренда для поиска:", reply_markup=get_cancel_keyboard())

@dp.message(F.text == "🏢 По юр. лицу")
async def search_legal_mode(message: types.Message, state: FSMContext):
    await state.set_state(SearchState.waiting_for_legal)
    await message.answer("Введите юридическое название (ООО, МЧЖ и т.д.):", reply_markup=get_cancel_keyboard())

@dp.message(F.text == "📂 По категории")
async def search_category_mode(message: types.Message, state: FSMContext):
    await state.set_state(SearchState.waiting_for_category)
    await message.answer("Введите категорию (например, 'Аптека' или 'Супермаркет'):", reply_markup=get_cancel_keyboard())

@dp.message(F.text == "🔹 По подкатегории")
async def search_subcategory_mode(message: types.Message, state: FSMContext):
    await state.set_state(SearchState.waiting_for_subcategory)
    await message.answer("Введите подкатегорию (например, 'ИТ-курсы' или 'Кофе'):", reply_markup=get_cancel_keyboard())

@dp.message(Command("reload"))
async def cmd_reload(message: types.Message):
    """Reloads the mapping database from Google Sheets."""
    mapping_service._load_data()
    await message.answer("🔄 База брендов успешно обновлена!")

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    status_msg = await message.answer("🚀 Анализируем чек...")
    
    try:
        photo = message.photo[-1]
        file_info = await bot.get_file(photo.file_id)
        photo_bytes = await bot.download_file(file_info.file_path)
        img_data = photo_bytes.read()

        await status_msg.edit_text("🔍 Извлекаем данные...")
        extracted_data = await extract_receipt_data(img_data)
        
        if not extracted_data or not extracted_data.get('alpha_name'):
            await status_msg.edit_text("❌ Не удалось распознать данные о компании.")
            return

        alpha_name = extracted_data.get('alpha_name', '')
        
        # Check if already exists in sheets
        mapping = mapping_service.find_mapping_by_legal_name(alpha_name)
        if mapping:
            await status_msg.edit_text("Такая компания уже имеется в таблице")
            return
            
        brand_name = extracted_data.get('brand_name', '')
        category = extracted_data.get('category', '')
        subcategory = extracted_data.get('subcategory', '')
        date_added = datetime.now().strftime("%Y-%m-%d %H:%M")

        save_msg = f"✅ Распознано:\n"
        save_msg += f"🏢 Компания: {alpha_name}\n"
        save_msg += f"📁 Категория: {category}\n"
        if subcategory:
            save_msg += f"Подкатегория: {subcategory}\n"
        save_msg += f"Дата добавления: {date_added}\n\n"
        save_msg += "📝 Записываю в таблицу..."
        
        await status_msg.edit_text(save_msg)
        
        success = await save_to_sheet(extracted_data)
        if success:
            await status_msg.answer("✨ Запись добавлена!")
            mapping_service._load_data() # Reload cache after successful insert
        else:
            await status_msg.answer("⚠️ Ошибка при записи в таблицу.")

    except Exception as e:
        await status_msg.edit_text(f"🔴 Ошибка: {str(e)}")

@dp.message(SearchState.waiting_for_brand)
@dp.message(SearchState.waiting_for_legal)
@dp.message(SearchState.waiting_for_category)
@dp.message(SearchState.waiting_for_subcategory)
async def handle_search_query(message: types.Message, state: FSMContext):
    """Processes search queries based on the selected mode."""
    query = message.text.strip()
    current_state = await state.get_state()
    
    if current_state == SearchState.waiting_for_brand:
        field = "ИМЯ"
        field_label = "бренд"
    elif current_state == SearchState.waiting_for_legal:
        field = "АЛЬФА ИМЯ"
        field_label = "юр. лицо"
    elif current_state == SearchState.waiting_for_category:
        field = "КАТЕГОРИЯ"
        field_label = "категория"
    else:
        field = "ПОДКАТЕГОРИЯ"
        field_label = "подкатегория"

    results = mapping_service.search_by_field(field, query)
    
    if not results:
        await message.answer(f"🔍 По запросу '{query}' ({field_label}) ничего не найдено.")
        return
    
    response = f"🔍 **Результаты поиска для '{query}':**\n\n"
    for row in results:
        response += (
            f"🏷 **Бренд:** {row.get('ИМЯ')}\n"
            f"🏢 **Юр. лицо:** {row.get('АЛЬФА ИМЯ')}\n"
            f"📁 **Категория:** {row.get('КАТЕГОРИЯ')}\n"
            f"🔹 **Подкатегория:** {row.get('ПОДКАТЕГОРИЯ') or '-'}\n"
            f"-------------------\n"
        )
    
    await message.answer(response, parse_mode="Markdown", reply_markup=get_main_keyboard())
    await state.clear()

@dp.message(F.text & ~F.starts_with("/"))
async def handle_legacy_text_lookup(message: types.Message):
    """Fallback for direct text input (defaults to brand search)."""
    query = message.text.strip()
    results = mapping_service.search_by_brand_name(query)
    # ... (same logic as above or just redirect)
    if results:
        response = f"🔍 **Найдено по названию:**\n\n"
        for row in results:
            response += (
                f"🏷 **Бренд:** {row.get('ИМЯ')}\n"
                f"🏢 **Юр. лицо:** {row.get('АЛЬФА ИМЯ')}\n"
                f"📁 **Категория:** {row.get('КАТЕГОРИЯ')}\n"
                f"-------------------\n"
            )
        await message.answer(response, parse_mode="Markdown", reply_markup=get_main_keyboard())
    else:
        await message.answer("Выберите режим поиска кнопками ниже:", reply_markup=get_main_keyboard())

@app.route(f"/{WEBHOOK_SECRET}", methods=["POST"])
def telegram_webhook():
    """Handle incoming updates from Telegram via Webhook."""
    try:
        # Create a temporary session with proxy for this specific loop
        if os.environ.get('PYTHONANYWHERE_DOMAIN'):
            proxy_session = AiohttpSession(proxy=f"http://{PROXY_URL}")
            temp_bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN), session=proxy_session)
        else:
            temp_bot = bot

        update = types.Update.model_validate(request.json, context={"bot": temp_bot})
        
        # Run the update in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(dp.feed_update(temp_bot, update))
        finally:
            # Clean up session and loop
            if os.environ.get('PYTHONANYWHERE_DOMAIN'):
                loop.run_until_complete(proxy_session.close())
            loop.close()
            
    except Exception as e:
        app.logger.error(f"Webhook error: {e}")
    return "OK", 200

async def on_startup():
    """Set webhook and bot menu with retries to handle proxy instability."""
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Attempt {attempt}/{max_retries}: Setting up bot menu and webhook...")
            # Set command menu
            commands = [
                types.BotCommand(command="start", description="🏠 Главное меню / Начать поиск"),
                types.BotCommand(command="help", description="❓ Как пользоваться"),
                types.BotCommand(command="cancel", description="❌ Отменить поиск")
            ]
            await bot.set_my_commands(commands)
            
            print(f"Setting webhook to: {WEBHOOK_URL}")
            await asyncio.sleep(2) # Increased delay for stability
            await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
            print("✅ Webhook and Menu set successfully!")
            return # Success! Exit the function
        except Exception as e:
            print(f"⚠️ Attempt {attempt} failed: {e}")
            if attempt < max_retries:
                wait_time = attempt * 5 # Exponential backoff
                print(f"Waiting {wait_time} seconds before next attempt...")
                await asyncio.sleep(wait_time)
            else:
                print("❌ All attempts failed. Please try again in 10-15 minutes.")

async def on_shutdown():
    """Remove webhook when the bot stops."""
    print("Removing webhook...")
    await bot.delete_webhook()

async def start_polling():
    """Standard polling for local development."""
    print("Starting in POLLING mode...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Check if we are running on PythonAnywhere
    if os.environ.get('PYTHONANYWHERE_DOMAIN'):
        # On PythonAnywhere, we don't 'run' the app here. 
        # PythonAnywhere's WSGI server will import 'app' and run it.
        # But we need to ensure the webhook is set.
        print("Running on PythonAnywhere (Webhook mode enabled).")
        asyncio.run(on_startup())
    else:
        # Local run (Polling)
        try:
            asyncio.run(start_polling())
        except KeyboardInterrupt:
            print("Bot stopped.")
