from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import logging
import os
from app.routers import admin, amocrm, transcription, analysis, reports

from app.settings.paths import print_paths
# Выводим информацию о путях при запуске
print_paths()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Создаем FastAPI приложение
app = FastAPI(
    title="AmoCRM API Integration",
    description="API для работы с AmoCRM через MongoDB",
    version="1.0.0"
)

# Добавляем CORS middleware для фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене замените на конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware для логирования запросов
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Запрос: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Ответ: {response.status_code}")
    return response

# Глобальные константы
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "medai"
AUDIO_DIR = "audio"  # Директория для сохранения аудиофайлов

# Создаем директорию для аудио, если она не существует
os.makedirs(AUDIO_DIR, exist_ok=True)

# Подключаем роутеры к приложению
app.include_router(admin.router)
app.include_router(amocrm.router)
app.include_router(transcription.router)
app.include_router(analysis.router)
app.include_router(reports.router)

# Эндпоинт для проверки статуса API
@app.get("/api/status")
async def get_status():
    return {
        "success": True,
        "message": "API работает нормально",
        "data": {"version": "1.0.0"}
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("run:app", host="127.0.0.1", port=8000)