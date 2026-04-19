# Деплой на Render.com

## Преимущества Render.com
- ✅ Бесплатный tier без ограничений на внешние API
- ✅ Поддержка OpenRouter и других AI сервисов
- ✅ Автоматический деплой из GitHub
- ✅ HTTPS из коробки
- ✅ Простая настройка переменных окружения

## Шаг 1: Подготовка репозитория

1. Убедитесь, что все изменения закоммичены в git:
```bash
git add .
git commit -m "Добавлена поддержка Render.com и OpenRouter"
git push origin main
```

2. Файлы для деплоя уже готовы:
   - `render.yaml` - конфигурация сервиса
   - `requirements.txt` - зависимости Python
   - `bot.py` - основной код с поддержкой webhook

## Шаг 2: Создание аккаунта на Render.com

1. Перейдите на https://render.com
2. Зарегистрируйтесь через GitHub (рекомендуется)
3. Подтвердите email

## Шаг 3: Создание Web Service

1. На dashboard нажмите **"New +"** → **"Web Service"**
2. Подключите ваш GitHub репозиторий
3. Render автоматически обнаружит `render.yaml`
4. Нажмите **"Apply"**

## Шаг 4: Настройка переменных окружения

В разделе **Environment** добавьте переменные:

```
BOT_TOKEN=ваш_токен_от_BotFather
OPENROUTER_API_KEY=ваш_ключ_OpenRouter
GOOGLE_AI_STUDIO_KEY=ваш_ключ_Gemini (для фото чеков)
GOOGLE_SHEET_URL=ссылка_на_таблицу
GOOGLE_SERVICE_ACCOUNT_FILE=credentials.json
RENDER_DOMAIN=ваш-сервис.onrender.com
WEBHOOK_SECRET=случайная_строка_32_символа
```

**Важно:** `RENDER_DOMAIN` будет доступен после первого деплоя (например: `tg-bot-check-converter.onrender.com`)

## Шаг 5: Загрузка credentials.json

Render не поддерживает загрузку файлов через UI, поэтому есть 2 варианта:

### Вариант A: Через Secret Files (рекомендуется)
1. В настройках сервиса → **Secret Files**
2. Добавьте файл `credentials.json`
3. Вставьте содержимое вашего credentials.json

### Вариант B: Через переменную окружения
1. Конвертируйте credentials.json в base64:
```bash
cat credentials.json | base64
```
2. Добавьте переменную `GOOGLE_CREDENTIALS_BASE64`
3. В bot.py добавьте декодирование при старте

## Шаг 6: Первый деплой

1. Нажмите **"Manual Deploy"** → **"Deploy latest commit"**
2. Дождитесь завершения (3-5 минут)
3. Скопируйте URL сервиса (например: `https://tg-bot-check-converter.onrender.com`)
4. Обновите переменную `RENDER_DOMAIN` (без https://)
5. Сделайте **"Manual Deploy"** еще раз

## Шаг 7: Проверка работы

1. Откройте логи в Render dashboard
2. Должны увидеть:
```
🤖 Bot version: 2.0.0-inline-buttons
🤖 AI Provider: OpenRouter
Running in WEBHOOK mode on Render
✅ Webhook and Menu set successfully!
```

3. Проверьте бота в Telegram:
   - Отправьте `/start`
   - Отправьте фото чека (будет использован Gemini)
   - Отправьте SMS текст (будет использован OpenRouter)

## Модели AI

### Для фото чеков (vision)
- **Gemini 2.5 Flash** - бесплатные модели OpenRouter не поддерживают vision
- Требуется `GOOGLE_AI_STUDIO_KEY`

### Для SMS текста
- **OpenRouter**: `google/gemini-2.0-flash-exp:free`
- Бесплатно, без ограничений PythonAnywhere
- Альтернативы: `meta-llama/llama-3.2-3b-instruct:free`, `mistralai/mistral-7b-instruct:free`

## Бесплатный tier Render.com

- ✅ 750 часов в месяц (достаточно для 1 сервиса 24/7)
- ✅ Автоматический sleep после 15 минут неактивности
- ✅ Автоматический wake-up при входящем запросе
- ⚠️ Cold start ~30 секунд (первый запрос после sleep)

## Автоматический деплой

После настройки каждый `git push` в main ветку автоматически задеплоит изменения.

Отключить: Settings → Build & Deploy → Auto-Deploy: Off

## Мониторинг

- **Логи**: Dashboard → Logs (real-time)
- **Метрики**: Dashboard → Metrics (CPU, Memory, Requests)
- **Alerts**: Settings → Notifications

## Troubleshooting

### Бот не отвечает
1. Проверьте логи на ошибки
2. Убедитесь, что `RENDER_DOMAIN` указан правильно
3. Проверьте webhook: `https://api.telegram.org/bot<TOKEN>/getWebhookInfo`

### Ошибка "credentials.json not found"
1. Проверьте Secret Files в настройках
2. Убедитесь, что путь `credentials.json` (без слэшей)

### OpenRouter не работает
1. Проверьте баланс на https://openrouter.ai/credits
2. Убедитесь, что `OPENROUTER_API_KEY` указан правильно
3. Проверьте логи на ошибки API

### Cold start слишком долгий
- Бесплатный tier засыпает после 15 минут
- Платный план ($7/мес) держит сервис всегда активным
- Или используйте внешний ping сервис (UptimeRobot)

## Миграция с PythonAnywhere

1. Остановите бота на PythonAnywhere
2. Удалите webhook: `https://api.telegram.org/bot<TOKEN>/deleteWebhook`
3. Задеплойте на Render (шаги выше)
4. Новый webhook установится автоматически

## Стоимость

- **Free tier**: $0/мес (750 часов, sleep после 15 мин)
- **Starter**: $7/мес (всегда активен, больше ресурсов)

Для личного бота Free tier более чем достаточно.

## Полезные ссылки

- Render Dashboard: https://dashboard.render.com
- Render Docs: https://render.com/docs
- OpenRouter: https://openrouter.ai
- Gemini API: https://aistudio.google.com
