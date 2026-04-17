import asyncio
import os
import json
import re
import traceback

from io import BytesIO
from datetime import datetime, timezone, timedelta
from typing import Optional

import gspread
from google import genai
from PIL import Image
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from flask import Flask, request

from mapping_service import MappingService

# Bot version for tracking deployments
BOT_VERSION = "2.0.0-inline-buttons"
print(f"🤖 Bot version: {BOT_VERSION}")

# Timezone for Uzbekistan (UTC+5)
UZ_TIMEZONE = timezone(timedelta(hours=5))

def get_uz_time():
    """Returns current time in Uzbekistan timezone (UTC+5)."""
    return datetime.now(UZ_TIMEZONE).strftime("%Y-%m-%d %H:%M")

# Load environment variables explicitly by absolute path
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_AI_STUDIO_KEY = os.getenv("GOOGLE_AI_STUDIO_KEY")
GOOGLE_SHEET_URL = os.getenv("GOOGLE_SHEET_URL")
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
PA_USERNAME = os.getenv("PYTHONANYWHERE_USERNAME")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
PROXY_URL = "proxy.server:3128"

# Resolve credentials file path to absolute path safely
BASE_DIR = os.path.dirname(__file__)
if GOOGLE_SERVICE_ACCOUNT_FILE and not os.path.isabs(GOOGLE_SERVICE_ACCOUNT_FILE):
    GOOGLE_SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, GOOGLE_SERVICE_ACCOUNT_FILE)

# Construct Webhook URL
WEBHOOK_URL = f"https://{PA_USERNAME}.pythonanywhere.com/{WEBHOOK_SECRET}"

# Bot and Dispatcher setup
# We will initialize Bot with a proxy session if on PythonAnywhere to avoid global loop issues
def get_bot():
    if os.environ.get('PYTHONANYWHERE_DOMAIN'):
        session = AiohttpSession(proxy=f"http://{PROXY_URL}")
        return Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML), session=session)
    return Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

bot = get_bot()
dp = Dispatcher(storage=MemoryStorage())
app = Flask(__name__)

# Initialize Gemini Client
# The SDK automatically uses HTTP_PROXY/HTTPS_PROXY environment variables
gemini_client = genai.Client(api_key=GOOGLE_AI_STUDIO_KEY)

# Initialize Mapping Service
mapping_service = MappingService(GOOGLE_SHEET_URL, GOOGLE_SERVICE_ACCOUNT_FILE)

# Track last save operations per user to prevent duplicates
last_save_tracker = {}  # {user_id: {'data': {...}, 'timestamp': datetime}}

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
    """Sends image to Google Gemini for data extraction with quota handling."""
    model_name = 'gemini-2.5-flash' # Correct version for 2026
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
            model=model_name,
            contents=[img, prompt],
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=ReceiptData.model_json_schema()
            )
        )
        
        raw_text = response.text.strip()
        data_dict = json.loads(raw_text)
        validated_data = ReceiptData(**data_dict)
        return validated_data.model_dump()
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "quota" in error_msg.lower():
            print(f"CRITICAL: Quota exceeded for {model_name}")
            return "QUOTA_EXCEEDED"
        print(f"Gemini Extraction Error: {e}")
        return None

async def extract_text_data(text: str):
    """Parses text (e.g. bank SMS) using Gemini to extract merchant data."""
    model_name = 'gemini-2.5-flash'
    try:

        prompt = f"""
        Extract receipt data from this text (it might be a bank SMS or notification):
        "{text}"

        Return JSON with:
        - alpha_name: Legal merchant name (if found).
        - brand_name: Clean brand name.
        - category: Business category in Russian.
        - subcategory: Business subcategory in Russian.
        """

        response = await gemini_client.aio.models.generate_content(
            model=model_name,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=ReceiptData.model_json_schema()
            )
        )
        
        raw_text = response.text.strip()
        data_dict = json.loads(raw_text)
        validated_data = ReceiptData(**data_dict)
        return validated_data.model_dump()
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "quota" in error_msg.lower():
            return "QUOTA_EXCEEDED"
        print(f"Gemini Text Extraction Error: {e}")
        return None


async def save_to_sheet(data: dict):
    """Appends extracted data to Google Sheets (Worksheet 0) with duplicate check."""
    client = get_sheets_client()
    if not client:
        return False

    try:
        sh = client.open_by_url(GOOGLE_SHEET_URL)
        sheet = sh.get_worksheet(0)

        # Prepare the row to save
        brand_name = data.get('brand_name', '')
        alpha_name = data.get('alpha_name', '')
        category = data.get('category', '')
        subcategory = data.get('subcategory', '')
        timestamp = get_uz_time()

        row = [brand_name, alpha_name, category, subcategory, timestamp]

        # Check for duplicates in last 10 rows (recent entries)
        all_values = sheet.get_all_values()
        if len(all_values) > 1:  # Skip header row
            recent_rows = all_values[-10:] if len(all_values) > 10 else all_values[1:]

            for existing_row in recent_rows:
                if len(existing_row) >= 4:
                    # Check if brand, alpha_name, category, subcategory match
                    if (existing_row[0] == brand_name and
                        existing_row[1] == alpha_name and
                        existing_row[2] == category and
                        existing_row[3] == subcategory):

                        # Check timestamp - if within last 2 minutes, it's a duplicate
                        if len(existing_row) >= 5:
                            existing_time = existing_row[4]
                            print(f"[DUPLICATE CHECK] Found similar entry at {existing_time}, current time {timestamp}")

                            # Parse timestamps and compare
                            try:
                                from datetime import datetime
                                existing_dt = datetime.strptime(existing_time, "%Y-%m-%d %H:%M")
                                current_dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M")
                                time_diff = abs((current_dt - existing_dt).total_seconds())

                                if time_diff < 120:  # Less than 2 minutes
                                    print(f"[DUPLICATE DETECTED] Skipping save - duplicate found within {time_diff} seconds")
                                    return "DUPLICATE"
                            except:
                                pass

        sheet.append_row(row)
        print(f"[SAVE] Expense saved to worksheet 0 at {timestamp}")
        return True
    except Exception as e:
        print(f"[ERROR] Sheets Error: {e}")
        return False

# --- State Management ---
class SearchState(StatesGroup):
    waiting_for_brand = State()
    waiting_for_legal = State()
    waiting_for_category = State()
    waiting_for_subcategory = State()

class ConfirmState(StatesGroup):
    waiting_confirmation = State()

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

def get_confirmation_keyboard():
    buttons = [
        [InlineKeyboardButton(text="✅ Все верно", callback_data="confirm_save")],
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data="confirm_edit")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="confirm_cancel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()

    welcome_text = (
        "👋 <b>Умный учет расходов</b>\n\n"
        "📸 Отправьте фото чека или текст SMS\n"
        "🤖 Я распознаю данные через AI\n"
        "📊 Сохраню в Google Таблицу\n\n"
        "Используйте кнопки ниже для поиска в базе."
    )

    await message.answer(welcome_text, reply_markup=get_main_keyboard())

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
async def handle_photo(message: types.Message, state: FSMContext):
    status_msg = await message.answer("🚀 Анализируем чек...")

    try:
        photo = message.photo[-1]
        file_info = await bot.get_file(photo.file_id)
        photo_bytes = await bot.download_file(file_info.file_path)
        img_data = photo_bytes.read()

        await status_msg.edit_text("🔍 Извлекаем данные...")
        extracted_data = await extract_receipt_data(img_data)

        if extracted_data == "QUOTA_EXCEEDED":
            await status_msg.edit_text(
                "⚠️ <b>Превышен лимит запросов к AI-модели</b>\n\n"
                "Бесплатная квота Gemini API исчерпана. Лимиты обновляются ежедневно в полночь по тихоокеанскому времени (Pacific Time).\n\n"
                "Пожалуйста, попробуйте позже или обратитесь к администратору для увеличения квоты."
            )
            return

        if not extracted_data or not extracted_data.get('alpha_name'):
            await status_msg.edit_text("❌ Не удалось распознать данные на этом чеке. Попробуйте еще раз или пришлите текст СМС.")
            return

        alpha_name = extracted_data.get('alpha_name', '')
        brand_name = extracted_data.get('brand_name', '')
        category = extracted_data.get('category', '')
        subcategory = extracted_data.get('subcategory', '')

        # Check if mapping exists
        mapping = mapping_service.find_mapping_by_legal_name(alpha_name)
        if mapping:
            # Use existing mapping
            brand_name = mapping.get('ИМЯ', brand_name)
            category = mapping.get('КАТЕГОРИЯ', category)
            subcategory = mapping.get('ПОДКАТЕГОРИЯ', subcategory)

        # Store data for confirmation
        await state.update_data(
            alpha_name=alpha_name,
            brand_name=brand_name,
            category=category,
            subcategory=subcategory,
            is_new_mapping=not mapping
        )

        confirm_msg = f"✅ Распознано:\n\n"
        confirm_msg += f"🏢 Юр. лицо: {alpha_name}\n"
        confirm_msg += f"🏷 Бренд: {brand_name}\n"
        confirm_msg += f"📁 Категория: {category}\n"
        if subcategory:
            confirm_msg += f"🔹 Подкатегория: {subcategory}\n"

        if not mapping:
            confirm_msg += f"\n⚠️ Новая компания (будет добавлена в справочник)\n"

        confirm_msg += f"\nВсе верно?"

        await status_msg.edit_text(confirm_msg, reply_markup=get_confirmation_keyboard())
        await state.set_state(ConfirmState.waiting_confirmation)

    except Exception as e:
        await status_msg.edit_text(f"🔴 Ошибка: {str(e)}")
        await state.clear()

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

@dp.callback_query(F.data == "confirm_save")
async def handle_confirm_save(callback: types.CallbackQuery, state: FSMContext):
    """Handle save confirmation button."""
    user_id = callback.from_user.id
    print(f"[CALLBACK] confirm_save triggered by user {user_id}")

    # Immediately answer callback to prevent double-click
    await callback.answer()

    # Check if already processing
    data = await state.get_data()
    print(f"[CALLBACK] Current state data: processing={data.get('processing')}, is_new_mapping={data.get('is_new_mapping')}")

    if data.get('processing'):
        print(f"[CALLBACK] Already processing, ignoring duplicate click")
        return

    # Check if this exact data was just saved by this user
    if user_id in last_save_tracker:
        last_save = last_save_tracker[user_id]
        last_data = last_save['data']
        last_time = last_save['timestamp']
        time_diff = (datetime.now(UZ_TIMEZONE) - last_time).total_seconds()

        # Check if same data within last 10 seconds
        if (time_diff < 10 and
            last_data.get('brand_name') == data.get('brand_name') and
            last_data.get('alpha_name') == data.get('alpha_name') and
            last_data.get('category') == data.get('category') and
            last_data.get('subcategory') == data.get('subcategory')):
            print(f"[DUPLICATE BLOCKED] User {user_id} tried to save same data within {time_diff} seconds")
            await callback.message.edit_text("⚠️ Эта запись уже была сохранена только что!")
            await callback.message.answer("Главное меню:", reply_markup=get_main_keyboard())
            await state.clear()
            return

    # Mark as processing
    await state.update_data(processing=True)
    print(f"[CALLBACK] Set processing=True, starting save operation")

    await callback.message.edit_text("📝 Сохраняю в таблицу...")

    # If new mapping, add to mapping sheet (Sheet1)
    if data.get('is_new_mapping'):
        try:
            print(f"[SAVE] Adding new mapping to Sheet1...")
            client = get_sheets_client()
            if client:
                sh = client.open_by_url(GOOGLE_SHEET_URL)
                mapping_sheet = sh.worksheet("Sheet1")  # Mapping sheet
                mapping_row = [
                    data.get('brand_name', ''),
                    data.get('alpha_name', ''),
                    data.get('category', ''),
                    data.get('subcategory', ''),
                    get_uz_time()  # Use UTC+5 time
                ]
                mapping_sheet.append_row(mapping_row)
                mapping_service._load_data()
                print(f"[SAVE] New mapping added to Sheet1 at {get_uz_time()}")
        except Exception as e:
            print(f"[ERROR] Error adding to mapping: {e}")

    # Always save expense to worksheet 0
    print(f"[SAVE] Saving expense to worksheet 0...")
    success = await save_to_sheet(data)
    print(f"[SAVE] Save result: {success}")

    # Track this save operation
    last_save_tracker[user_id] = {
        'data': data.copy(),
        'timestamp': datetime.now(UZ_TIMEZONE)
    }
    print(f"[TRACKER] Saved operation for user {user_id}")

    if success == "DUPLICATE":
        await callback.message.edit_text("⚠️ Эта запись уже была сохранена недавно (обнаружен дубликат).")
        await callback.message.answer("Главное меню:", reply_markup=get_main_keyboard())
    elif success:
        await callback.message.edit_text("✨ Запись добавлена!")
        await callback.message.answer("Главное меню:", reply_markup=get_main_keyboard())
    else:
        await callback.message.edit_text("⚠️ Ошибка при записи в таблицу.")
        await callback.message.answer("Главное меню:", reply_markup=get_main_keyboard())

    print(f"[CALLBACK] Clearing state for user {user_id}")
    await state.clear()

@dp.callback_query(F.data == "confirm_cancel")
async def handle_confirm_cancel(callback: types.CallbackQuery, state: FSMContext):
    """Handle cancel button."""
    print(f"[CALLBACK] confirm_cancel triggered by user {callback.from_user.id}")
    await callback.message.edit_text("❌ Отменено")
    await callback.message.answer("Главное меню:", reply_markup=get_main_keyboard())
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "confirm_edit")
async def handle_confirm_edit(callback: types.CallbackQuery, state: FSMContext):
    """Handle edit button - allow user to edit the recognized data."""
    print(f"[CALLBACK] confirm_edit triggered by user {callback.from_user.id}")
    data = await state.get_data()

    edit_msg = "✏️ Редактирование данных\n\n"
    edit_msg += "Отправьте исправленные данные в формате:\n\n"
    edit_msg += f"Бренд: {data.get('brand_name', '')}\n"
    edit_msg += f"Юр.лицо: {data.get('alpha_name', '')}\n"
    edit_msg += f"Категория: {data.get('category', '')}\n"
    edit_msg += f"Подкатегория: {data.get('subcategory', '')}\n\n"
    edit_msg += "Скопируйте, отредактируйте и отправьте обратно"

    await callback.message.edit_text(edit_msg)
    await state.set_state(ConfirmState.waiting_confirmation)  # Keep state for manual edit
    await callback.answer()

@dp.message(ConfirmState.waiting_confirmation)
async def handle_manual_edit(message: types.Message, state: FSMContext):
    """Handle manually edited data from user."""
    text = message.text.strip()

    # Parse the edited data
    lines = text.split('\n')
    edited_data = {}

    for line in lines:
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip().lower()
            value = value.strip()

            if 'бренд' in key:
                edited_data['brand_name'] = value
            elif 'юр' in key or 'лицо' in key:
                edited_data['alpha_name'] = value
            elif 'категор' in key and 'под' not in key:
                edited_data['category'] = value
            elif 'подкатегор' in key:
                edited_data['subcategory'] = value

    # Update state with edited data
    old_data = await state.get_data()
    old_data.update(edited_data)

    # Reset processing flag to allow new save
    old_data['processing'] = False
    await state.update_data(**old_data)

    print(f"[EDIT] User {message.from_user.id} edited data, showing confirmation again")

    # Show confirmation again
    confirm_msg = "✅ Обновленные данные:\n\n"
    confirm_msg += f"🏢 Юр. лицо: {old_data.get('alpha_name', '')}\n"
    confirm_msg += f"🏷 Бренд: {old_data.get('brand_name', '')}\n"
    confirm_msg += f"📁 Категория: {old_data.get('category', '')}\n"
    if old_data.get('subcategory'):
        confirm_msg += f"🔹 Подкатегория: {old_data.get('subcategory', '')}\n"
    confirm_msg += f"\nВсе верно?"

    await message.answer(confirm_msg, reply_markup=get_confirmation_keyboard())

@dp.message(F.text & ~F.starts_with("/"))
async def handle_text_logic(message: types.Message, state: FSMContext):
    """Processes search queries or parses SMS text as receipts."""
    query = message.text.strip()

    # 1. First, try simple brand lookup
    results = mapping_service.search_by_brand_name(query)
    if results:
        response = f"🔍 **Найдено в базе:**\n\n"
        for row in results:
            response += (
                f"🏷 **Бренд:** {row.get('ИМЯ')}\n"
                f"🏢 **Юр. лицо:** {row.get('АЛЬФА ИМЯ')}\n"
                f"📁 **Категория:** {row.get('КАТЕГОРИЯ')}\n"
                f"-------------------\n"
            )
        await message.answer(response, parse_mode="Markdown", reply_markup=get_main_keyboard())
        return

    # 2. If length > 20, assume it's an SMS/Notification and try AI parsing
    if len(query) > 20:
        status_msg = await message.answer("🤖 Текст не найден в базе. Пробую распознать как СМС...")
        extracted_data = await extract_text_data(query)

        if extracted_data == "QUOTA_EXCEEDED":
            await status_msg.edit_text(
                "⚠️ <b>Превышен лимит запросов к AI-модели</b>\n\n"
                "Бесплатная квота Gemini API исчерпана. Лимиты обновляются ежедневно в полночь по тихоокеанскому времени (Pacific Time).\n\n"
                "Поиск в базе данных результатов не дал. Попробуйте позже или обратитесь к администратору."
            )
            return

        if extracted_data and extracted_data.get('alpha_name'):
            alpha_name = extracted_data.get('alpha_name')
            brand_name = extracted_data.get('brand_name')
            category = extracted_data.get('category')
            subcategory = extracted_data.get('subcategory', '')

            # Check if mapping exists
            mapping = mapping_service.find_mapping_by_legal_name(alpha_name)
            if mapping:
                brand_name = mapping.get('ИМЯ', brand_name)
                category = mapping.get('КАТЕГОРИЯ', category)
                subcategory = mapping.get('ПОДКАТЕГОРИЯ', subcategory)

            # Store for confirmation
            await state.update_data(
                alpha_name=alpha_name,
                brand_name=brand_name,
                category=category,
                subcategory=subcategory,
                is_new_mapping=not mapping
            )

            confirm_msg = f"✨ СМС распознано:\n\n"
            confirm_msg += f"🏢 Юр.лицо: {alpha_name}\n"
            confirm_msg += f"🏷 Бренд: {brand_name}\n"
            confirm_msg += f"📁 Категория: {category}\n"
            if subcategory:
                confirm_msg += f"🔹 Подкатегория: {subcategory}\n"

            if not mapping:
                confirm_msg += f"\n⚠️ Новая компания (будет добавлена в справочник)\n"

            confirm_msg += f"\nВсе верно?"

            await status_msg.edit_text(confirm_msg, reply_markup=get_confirmation_keyboard())
            await state.set_state(ConfirmState.waiting_confirmation)
            return

    # 3. Fallback
    await message.answer("🔍 Ничего не найдено. Выберите режим поиска кнопками ниже:", reply_markup=get_main_keyboard())


@dp.callback_query()
async def handle_any_callback(callback: types.CallbackQuery):
    """Fallback handler for unhandled callbacks - for debugging."""
    print(f"[UNHANDLED CALLBACK] data={callback.data}, user={callback.from_user.id}")
    await callback.answer("⚠️ Callback получен, но handler не найден. Проверьте версию бота на сервере!")


@app.route(f"/{WEBHOOK_SECRET}", methods=["POST"])
def telegram_webhook():
    """Handle incoming updates from Telegram via Webhook."""
    try:
        async def process_update():
            # Create a fresh session and bot for this request to avoid "loop closed" errors
            if os.environ.get('PYTHONANYWHERE_DOMAIN'):
                # Explicitly use the proxy URL for stable networking on PA
                async with AiohttpSession(proxy=f"http://{PROXY_URL}") as session:
                    async with Bot(
                        token=BOT_TOKEN,
                        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
                        session=session
                    ) as temp_bot:
                        update = types.Update.model_validate(request.json, context={"bot": temp_bot})
                        await dp.feed_update(temp_bot, update)
            else:
                # Local or non-PA environment
                async with Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)) as temp_bot:
                    update = types.Update.model_validate(request.json, context={"bot": temp_bot})
                    await dp.feed_update(temp_bot, update)

        # Use get_event_loop or create new one if closed
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        loop.run_until_complete(process_update())
    except Exception as e:
        error_trace = traceback.format_exc()
        app.logger.error(f"Webhook error: {e}\n{error_trace}")
        print(f"Webhook error: {e}\n{error_trace}")
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
    # Log registered handlers count
    print(f"📊 Registered message handlers: {len([h for h in dp.message.handlers if h])}")
    print(f"📊 Registered callback handlers: {len([h for h in dp.callback_query.handlers if h])}")

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
