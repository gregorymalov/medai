Структура проекта:

app/
├── main.py # Основной файл приложения FastAPI
├── models/ # Модели Pydantic
│ ├── **init**.py
│ ├── amocrm.py # Модели для AmoCRM
│ └── transcription.py # Модели для транскрибации
├── routers/ # Маршруты API
│ ├── **init**.py
│ ├── admin.py # Административные маршруты
│ ├── amocrm.py # Маршруты для AmoCRM
│ └── transcription.py # Маршруты для транскрибации
├── services/ # Бизнес-логика
│ ├── **init**.py
│ ├── amocrm_service.py # Логика для AmoCRM
│ └── transcription_service.py # Логика транскрибации
└── utils/ # Вспомогательные функции
├── **init**.py
└── helpers.py
