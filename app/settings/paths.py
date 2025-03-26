import os

# Определяем базовую директорию проекта 
# (app - директория с кодом приложения)
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Корневая директория проекта (на уровень выше app)
ROOT_DIR = os.path.dirname(APP_DIR)

# Директория для хранения данных
DATA_DIR = os.path.join(APP_DIR, "data")

# Директории для хранения аудиофайлов и транскрипций
AUDIO_DIR = os.path.join(DATA_DIR, "audio")
TRANSCRIPTION_DIR = os.path.join(DATA_DIR, "transcription")

# Создаем директории, если они не существуют
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(TRANSCRIPTION_DIR, exist_ok=True)

# Удобная функция для логирования путей
def print_paths():
    print(f"Директория приложения: {APP_DIR}")
    print(f"Аудиофайлы: {AUDIO_DIR}")
    print(f"Транскрипции: {TRANSCRIPTION_DIR}")