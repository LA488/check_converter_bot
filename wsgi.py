import sys
import os

# Добавьте путь к вашему проекту
project_home = '/home/la488/Tg-bot-Check-Converter'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Установите переменную окружения для определения PA
os.environ['PYTHONANYWHERE_DOMAIN'] = 'la488.pythonanywhere.com'

# Импортируйте Flask app
from bot import app as application
