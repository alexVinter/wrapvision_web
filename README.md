Инструкция по запуску проекта WrapVision

1. Установить Python 3.10 или 3.11.

2. Распаковать архив проекта в удобную папку.

3. Открыть командную строку в папке проекта.

4. Создать виртуальное окружение:

python -m venv .venv

5. Активировать виртуальное окружение:

Windows:
.venv\Scripts\activate

6. Установить зависимости:

python -m pip install --upgrade pip
pip install -r requirements.txt

7. Создать файл .env на основе .env.example:

copy .env.example .env

8. При необходимости указать API-ключи в файле .env:

ZVENO_API_KEY=
GOOGLE_MAPS_API_KEY=

Если ключи не указаны, приложение запустится, но генерация через внешний сервис и карта могут работать ограниченно.

9. Инициализировать базу данных:

python -m app.db.init_db

10. Запустить приложение:

python -m uvicorn app.main:app --reload

11. Открыть сайт в браузере:

http://127.0.0.1:8000
