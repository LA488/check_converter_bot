# Быстрый старт на PythonAnywhere

## 1. Загрузите файлы через Files в PA:
```
/home/la488/Tg-bot-Check-Converter/
├── bot.py
├── mapping_service.py
├── .env
├── credentials.json
└── requirements.txt
```

## 2. Откройте Bash консоль и выполните:
```bash
cd ~/Tg-bot-Check-Converter
pip3.10 install --user -r requirements.txt
```

## 3. Настройте Web App:
- Перейдите в раздел "Web"
- Нажмите "Add a new web app"
- Выберите "Manual configuration"
- Python version: 3.10

## 4. Настройте WSGI файл:
Откройте `/var/www/la488_pythonanywhere_com_wsgi.py` и замените содержимое на:

```python
import sys
import os

project_home = '/home/la488/Tg-bot-Check-Converter'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.environ['PYTHONANYWHERE_DOMAIN'] = 'la488.pythonanywhere.com'

from bot import app as application
```

## 5. Установите webhook:
В Bash консоли выполните:
```bash
cd ~/Tg-bot-Check-Converter
python3.10 -c "import asyncio; from bot import on_startup; asyncio.run(on_startup())"
```

## 6. Reload веб-приложение
Нажмите зеленую кнопку "Reload" в разделе Web

## Готово! 
Проверьте бота в Telegram - отправьте `/start`

## Если не работает:
1. Проверьте error log: `/var/log/la488.pythonanywhere.com.error.log`
2. Убедитесь что credentials.json загружен
3. Проверьте что сервисный аккаунт имеет доступ к Google Sheets
