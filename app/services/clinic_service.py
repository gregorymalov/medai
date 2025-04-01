from motor.motor_asyncio import AsyncIOMotorClient
from bson.objectid import ObjectId
from datetime import datetime
import logging
from typing import List, Dict, Any, Optional

from ..models.clinic import ClinicResponse, AdministratorResponse
from mlab_amo_async.amocrm_client import AsyncAmoCRMClient

logger = logging.getLogger(__name__)

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "medai"

class ClinicService:
    def __init__(self):
        self.client = AsyncIOMotorClient(MONGO_URI)
        self.db = self.client[DB_NAME]
        
    async def register_clinic(self, clinic_data):
        """
        Регистрирует новую клинику и создает администраторов из AmoCRM.
        Предотвращает создание дубликатов по client_id.
        """
        try:
            # Логируем входные данные
            logger.info(f"Начинаем регистрацию клиники: {clinic_data.get('name', 'Unknown')}")
            
            # Проверяем, существует ли уже клиника с таким client_id
            existing_clinic = await self.db.clinics.find_one({"client_id": clinic_data["client_id"]})
            
            now = datetime.now().isoformat()
            
            if existing_clinic:
                # Клиника уже существует - обновляем её данные
                clinic_id = str(existing_clinic["_id"])
                logger.info(f"Клиника с client_id {clinic_data['client_id']} уже существует (ID: {clinic_id})")
                
                # Обновляем данные клиники
                await self.db.clinics.update_one(
                    {"_id": ObjectId(clinic_id)},
                    {"$set": {
                        "name": clinic_data["name"],
                        "amocrm_subdomain": clinic_data["amocrm_subdomain"],
                        "client_secret": clinic_data["client_secret"],
                        "redirect_url": clinic_data["redirect_url"],
                        "amocrm_pipeline_id": clinic_data.get("amocrm_pipeline_id"),
                        "monthly_limit": clinic_data.get("monthly_limit", 100),
                        "updated_at": now
                    }}
                )
                logger.info(f"Данные клиники {clinic_id} обновлены")
            else:
                # Новая клиника - создаем
                clinic_doc = {
                    "name": clinic_data["name"],
                    "amocrm_subdomain": clinic_data["amocrm_subdomain"],
                    "client_id": clinic_data["client_id"],
                    "client_secret": clinic_data["client_secret"],
                    "redirect_url": clinic_data["redirect_url"],
                    "amocrm_pipeline_id": clinic_data.get("amocrm_pipeline_id"),
                    "monthly_limit": clinic_data.get("monthly_limit", 100),
                    "current_month_usage": 0,
                    "last_reset_date": now,
                    "created_at": now,
                    "updated_at": now
                }
                
                # Вставляем клинику в базу данных
                result = await self.db.clinics.insert_one(clinic_doc)
                clinic_id = str(result.inserted_id)
                logger.info(f"Новая клиника создана с ID: {clinic_id}")
            
            # Создаем клиент AmoCRM для получения пользователей
            amocrm_client = AsyncAmoCRMClient(
                client_id=clinic_data["client_id"],
                client_secret=clinic_data["client_secret"],
                subdomain=clinic_data["amocrm_subdomain"],
                redirect_url=clinic_data["redirect_url"],
                mongo_uri=MONGO_URI,
                db_name=DB_NAME
            )
            
            # Инициализируем токен с кодом авторизации
            await amocrm_client.init_token(clinic_data["auth_code"])
            logger.info("Токен AmoCRM инициализирован успешно")
            
            # Получаем пользователей из AmoCRM
            users = await self.get_amocrm_users(amocrm_client)
            logger.info(f"Получено {len(users) if users else 0} пользователей из AmoCRM")
            
            if not users:
                # Если не удалось получить пользователей, создадим хотя бы одного админа вручную
                logger.warning("Не удалось получить пользователей из AmoCRM, создаем базового админа")
                
                # Проверяем, существует ли уже базовый администратор
                existing_admin = await self.db.administrators.find_one({
                    "clinic_id": ObjectId(clinic_id),
                    "amocrm_user_id": "default_admin"
                })
                
                if existing_admin:
                    admin_ids = [str(existing_admin["_id"])]
                    logger.info("Базовый администратор уже существует")
                else:
                    admin_doc = {
                        "clinic_id": ObjectId(clinic_id),
                        "name": "Администратор по умолчанию",
                        "amocrm_user_id": "default_admin",
                        "email": None,
                        "monthly_limit": None,
                        "current_month_usage": 0,
                        "created_at": now,
                        "updated_at": now
                    }
                    admin_result = await self.db.administrators.insert_one(admin_doc)
                    admin_ids = [str(admin_result.inserted_id)]
                    logger.info("Создан базовый администратор")
            else:
                # Создаем администраторов в базе данных
                admin_ids = await self.create_administrators(users, clinic_id)
                
            logger.info(f"Всего администраторов: {len(admin_ids)}")
            
            # Обновляем клинику с добавлением ID администраторов
            await self.db.clinics.update_one(
                {"_id": ObjectId(clinic_id)},
                {"$set": {"administrator_ids": admin_ids}}
            )
            logger.info("Клиника обновлена с ID администраторов")
            
            # Возвращаем информацию о созданной/обновленной клинике
            return {
                "clinic_id": clinic_id,
                "name": clinic_data["name"],
                "administrator_count": len(admin_ids),
                "is_new": not existing_clinic
            }
            
        except Exception as e:
            logger.error(f"Ошибка при регистрации клиники: {e}")
            import traceback
            logger.error(f"Трассировка: {traceback.format_exc()}")
            raise
            
    async def get_amocrm_users(self, amocrm_client):
        """
        Получает пользователей из AmoCRM
        """
        try:
            logger.info("Запрашиваем пользователей из AmoCRM")
            response, status_code = await amocrm_client.contacts.request(
                "get", 
                "users"
            )
            
            logger.info(f"Получен ответ от AmoCRM: статус {status_code}")
            
            if status_code != 200:
                logger.error(f"Ошибка при получении пользователей AmoCRM: статус {status_code}")
                return []
                
            if "_embedded" not in response:
                logger.error(f"В ответе AmoCRM отсутствует ключ '_embedded': {response}")
                return []
                
            if "users" not in response["_embedded"]:
                logger.error(f"В ответе AmoCRM отсутствует ключ 'users': {response['_embedded']}")
                return []
                
            users = response["_embedded"]["users"]
            logger.info(f"Получено {len(users)} пользователей из AmoCRM")
            return users
            
        except Exception as e:
            logger.error(f"Исключение при получении пользователей AmoCRM: {e}")
            import traceback
            logger.error(f"Трассировка: {traceback.format_exc()}")
            return []
            
    async def create_administrators(self, amocrm_users, clinic_id):
        """
        Создает администраторов на основе пользователей AmoCRM.
        Предотвращает создание дубликатов.
        """
        admin_ids = []
        
        for user in amocrm_users:
            try:
                user_id = str(user["id"])
                # Проверяем, существует ли уже такой администратор
                existing_admin = await self.db.administrators.find_one({
                    "amocrm_user_id": user_id,
                    "clinic_id": ObjectId(clinic_id)
                })
                
                now = datetime.now().isoformat()
                
                if existing_admin:
                    # Обновляем существующего администратора
                    await self.db.administrators.update_one(
                        {"_id": existing_admin["_id"]},
                        {"$set": {
                            "name": user.get("name", "Неизвестный администратор"),
                            "email": user.get("email"),
                            "updated_at": now
                        }}
                    )
                    admin_ids.append(str(existing_admin["_id"]))
                    logger.info(f"Обновлен администратор: {user.get('name')} (ID: {str(existing_admin['_id'])})")
                else:
                    # Создаем нового администратора
                    admin_doc = {
                        "clinic_id": ObjectId(clinic_id),
                        "name": user.get("name", "Неизвестный администратор"),
                        "amocrm_user_id": user_id,
                        "email": user.get("email"),
                        "monthly_limit": None,  # Используется лимит клиники
                        "current_month_usage": 0,
                        "created_at": now,
                        "updated_at": now
                    }
                    
                    result = await self.db.administrators.insert_one(admin_doc)
                    admin_ids.append(str(result.inserted_id))
                    logger.info(f"Создан новый администратор: {user.get('name')} (ID: {str(result.inserted_id)})")
            except Exception as e:
                logger.error(f"Ошибка при создании/обновлении администратора: {e}")
                continue
                
        return admin_ids
    async def get_clinic_by_id(self, clinic_id: str) -> Optional[Dict[str, Any]]:
        """
        Получает информацию о клинике по ID
        """
        try:
            clinic = await self.db.clinics.find_one({"_id": ObjectId(clinic_id)})
            
            if not clinic:
                return None
                
            # Получаем администраторов клиники
            administrators = []
            admin_cursor = self.db.administrators.find({"clinic_id": ObjectId(clinic_id)})
            
            async for admin in admin_cursor:
                administrators.append({
                    "id": str(admin["_id"]),
                    "name": admin["name"],
                    "email": admin.get("email"),
                    "amocrm_user_id": admin["amocrm_user_id"],
                    "monthly_limit": admin.get("monthly_limit"),
                    "current_month_usage": admin.get("current_month_usage", 0)
                })
                
            # Форматируем данные клиники
            clinic_data = {
                "id": str(clinic["_id"]),
                "name": clinic["name"],
                "amocrm_subdomain": clinic["amocrm_subdomain"],
                "amocrm_pipeline_id": clinic.get("amocrm_pipeline_id"),
                "monthly_limit": clinic.get("monthly_limit", 100),
                "current_month_usage": clinic.get("current_month_usage", 0),
                "last_reset_date": clinic.get("last_reset_date"),
                "administrators": administrators
            }
            
            return clinic_data
            
        except Exception as e:
            logger.error(f"Ошибка при получении информации о клинике: {e}")
            return None
    
    async def sync_administrators(self, clinic_id: str):
        """
        Синхронизирует администраторов клиники с AmoCRM
        """
        try:
            # Получаем информацию о клинике
            clinic = await self.db.clinics.find_one({"_id": ObjectId(clinic_id)})
            
            if not clinic:
                raise ValueError(f"Клиника с ID {clinic_id} не найдена")
                
            # Создаем клиент AmoCRM
            amocrm_client = AsyncAmoCRMClient(
                client_id=clinic["client_id"],
                client_secret=clinic["client_secret"],
                subdomain=clinic["amocrm_subdomain"],
                redirect_url=clinic["redirect_url"],
                mongo_uri=MONGO_URI,
                db_name=DB_NAME
            )
            
            # Получаем пользователей из AmoCRM
            users = await self.get_amocrm_users(amocrm_client)
            
            # Получаем существующих администраторов
            existing_admins = {}
            admin_cursor = self.db.administrators.find({"clinic_id": ObjectId(clinic_id)})
            
            async for admin in admin_cursor:
                existing_admins[admin["amocrm_user_id"]] = admin
                
            # Обновляем/создаем администраторов
            added = 0
            updated = 0
            
            for user in users:
                user_id = str(user["id"])
                
                if user_id in existing_admins:
                    # Обновляем существующего администратора
                    await self.db.administrators.update_one(
                        {"_id": existing_admins[user_id]["_id"]},
                        {"$set": {
                            "name": user.get("name", "Неизвестный администратор"),
                            "email": user.get("email"),
                            "updated_at": datetime.now().isoformat()
                        }}
                    )
                    updated += 1
                else:
                    # Создаем нового администратора
                    now = datetime.now().isoformat()
                    admin_doc = {
                        "clinic_id": ObjectId(clinic_id),
                        "name": user.get("name", "Неизвестный администратор"),
                        "amocrm_user_id": user_id,
                        "email": user.get("email"),
                        "monthly_limit": None,  # Используется лимит клиники
                        "current_month_usage": 0,
                        "created_at": now,
                        "updated_at": now
                    }
                    
                    await self.db.administrators.insert_one(admin_doc)
                    added += 1
                    
            return {
                "added_administrators": added,
                "updated_administrators": updated,
                "total_administrators": len(users)
            }
                
        except Exception as e:
            logger.error(f"Ошибка при синхронизации администраторов: {e}")
            raise
    
    async def update_administrator(self, administrator_id: str, data: Dict[str, Any]):
        """
        Обновляет информацию об администраторе
        """
        try:
            # Проверяем, существует ли администратор
            admin = await self.db.administrators.find_one({"_id": ObjectId(administrator_id)})
            
            if not admin:
                raise ValueError(f"Администратор с ID {administrator_id} не найден")
                
            # Обновляем данные администратора
            update_data = {
                "updated_at": datetime.now().isoformat()
            }
            
            # Добавляем поля, которые нужно обновить
            valid_fields = ["name", "email", "monthly_limit"]
            for field in valid_fields:
                if field in data:
                    update_data[field] = data[field]
                    
            await self.db.administrators.update_one(
                {"_id": ObjectId(administrator_id)},
                {"$set": update_data}
            )
            
            # Получаем обновленного администратора
            updated_admin = await self.db.administrators.find_one({"_id": ObjectId(administrator_id)})
            
            return {
                "id": str(updated_admin["_id"]),
                "name": updated_admin["name"],
                "email": updated_admin.get("email"),
                "amocrm_user_id": updated_admin["amocrm_user_id"],
                "monthly_limit": updated_admin.get("monthly_limit"),
                "current_month_usage": updated_admin.get("current_month_usage", 0),
                "clinic_id": str(updated_admin["clinic_id"])
            }
                
        except Exception as e:
            logger.error(f"Ошибка при обновлении администратора: {e}")
            raise
    
    async def reset_monthly_limits(self):
        """
        Сбрасывает месячные счетчики использования
        """
        try:
            now = datetime.now().isoformat()
            
            # Сбрасываем счетчики для клиник
            clinics_result = await self.db.clinics.update_many(
                {},
                {"$set": {
                    "current_month_usage": 0,
                    "last_reset_date": now
                }}
            )
            
            # Сбрасываем счетчики для администраторов
            admins_result = await self.db.administrators.update_many(
                {},
                {"$set": {"current_month_usage": 0}}
            )
            
            return {
                "reset_clinics": clinics_result.modified_count,
                "reset_administrators": admins_result.modified_count,
                "reset_date": now
            }
                
        except Exception as e:
            logger.error(f"Ошибка при сбросе месячных счетчиков: {e}")
            raise

    async def find_clinic_by_client_id(self, client_id: str):
        """
        Находит клинику по client_id
        """
        try:
            clinic = await self.db.clinics.find_one({"client_id": client_id})
            
            if not clinic:
                return None
                
            return {
                "id": str(clinic["_id"]),
                "name": clinic["name"],
                "client_id": clinic["client_id"],
                "client_secret": clinic["client_secret"],
                "amocrm_subdomain": clinic["amocrm_subdomain"],
                "redirect_url": clinic["redirect_url"],
                "amocrm_pipeline_id": clinic.get("amocrm_pipeline_id")
            }
        except Exception as e:
            logger.error(f"Ошибка при поиске клиники по client_id: {e}")
            return None
        
    async def test_mongodb_connection(self):
        """Тестирует подключение к MongoDB и возможность записи данных"""
        try:
            # Проверка подключения
            await self.client.admin.command('ping')
            
            # Тестовая запись
            test_doc = {"test": "connection", "timestamp": datetime.now().isoformat()}
            result = await self.db.test_collection.insert_one(test_doc)
            test_id = result.inserted_id
            
            # Проверка чтения
            read_doc = await self.db.test_collection.find_one({"_id": test_id})
            
            return {
                "success": True,
                "inserted_id": str(test_id),
                "read_back": bool(read_doc),
                "database": DB_NAME,
                "collections": {
                    "clinics": await self.db.clinics.count_documents({}),
                    "administrators": await self.db.administrators.count_documents({}),
                    "tokens": await self.db.tokens.count_documents({})
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }