# Telegram Bot - Сканер чеков

Бот для распознавания чеков и SMS с автоматической категоризацией расходов через AI.

## Возможности:
- 📸 Распознавание фото чеков через Gemini AI
- 💬 Парсинг SMS от банков через OpenRouter (бесплатно)
- ✅ Inline-кнопки для подтверждения данных
- ✏️ Редактирование распознанных данных
- 📊 Автоматическое сохранение в Google Sheets
- 🔍 Поиск по брендам, юр.лицам, категориям

## AI Модели:
- **Фото чеков**: Gemini 2.5 Flash (vision)
- **SMS текст**: OpenRouter `google/gemini-2.0-flash-exp:free`

## Файлы проекта:
- `bot.py` - основной код бота (включает Flask webhook и настройку)
- `mapping_service.py` - сервис для работы со справочником компаний
- `requirements.txt` - зависимости Python
- `render.yaml` - конфигурация для Render.com
- `RENDER_DEPLOY.md` - инструкция по деплою
- `.env` - переменные окружения (не в git)
- `credentials.json` - Google Service Account (не в git)

## Деплой:
- **Render.com** (рекомендуется) - см. `RENDER_DEPLOY.md`
- **PythonAnywhere** (legacy) - ограничения на внешние API

## Команды бота:
- `/start` - Главное меню
- `/reload` - Обновить базу брендов из Google Sheets

## Версия:
2.1.0-openrouter

