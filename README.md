# Умный сканер чеков (Gemini AI Edition)

Этот бот автоматически извлекает данные из фотографий чеков с помощью **Google Gemini 1.5 Flash** и записывает их в Google Таблицу.

## 🚀 Быстрый старт

### 1. Подготовка окружения
Убедитесь, что у вас установлен Python 3.8+.
```bash
pip install -r requirements.txt
```

### 2. Настройка API
Создайте файл `.env` (он уже должен быть создан автоматически) и заполните следующие поля:

#### **Google Gemini API**
1. Перейдите в [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Нажмите **"Create API key"**.
3. Вставьте полученный ключ в поле `GOOGLE_AI_STUDIO_KEY` в файле `.env`.
*Для личного использования API Gemini бесплатно.*

#### **Google Sheets (Google Cloud)**
1. Перейдите в [Google Cloud Console](https://console.cloud.google.com/).
2. Создайте новый проект.
3. Включите **Google Sheets API** и **Google Drive API**.
4. Создайте **Service Account** (Credentials -> Create Credentials).
5. Создайте **Key** (JSON) для этого аккаунта и скачайте его.
6. Переименуйте файл в `credentials.json` и положите в папку с ботом.
7. **ВАЖНО:** Скопируйте `client_email` из JSON-файла и поделитесь (Share) вашей Google Таблицей с этим адресом (права Редактора).

### 3. Запуск
```bash
python bot.py
```

## 🛠 Как это работает
1. Вы отправляете фото боту.
2. Бот отправляет фото в **Gemini 1.5 Flash**.
3. AI находит: Название магазина, Сумму, Категорию и Дату.
4. Данные добавляются новой строкой в вашу таблицу.

## 👨‍💻 Структура проекта
- `bot.py` — основной код бота.
- `requirements.txt` — зависимости.
- `.env` — ваши ключи и настройки.
- `credentials.json` — ключи доступа к Google Таблицам.
