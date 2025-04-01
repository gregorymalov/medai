from fastapi import APIRouter, HTTPException, status, Request, BackgroundTasks, Response, Depends
from typing import Dict, Any, Optional, List
import logging
import json
import requests

from ..models.clinic import ClinicRegistrationRequest, ClinicResponse, AdministratorResponse, ApiResponse
from ..models.amocrm import AmoCRMAuthRequest, AmoCRMCredentials
from ..services.clinic_service import ClinicService
from ..services.limits_service import LimitsService
# from ..services.amocrm_service import AsyncAmoCRMClient
from mlab_amo_async.amocrm_client import AsyncAmoCRMClient
from motor.motor_asyncio import AsyncIOMotorClient


# Настройка логирования
logger = logging.getLogger(__name__)

# Глобальные константы
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "medai"

# Создаем роутер
router = APIRouter(tags=["admin"])

# Зависимости для сервисов
def get_clinic_service():
    return ClinicService()

def get_limits_service():
    return LimitsService()

@router.post("/api/admin/clinics", response_model=ApiResponse)
async def register_clinic(
    request: ClinicRegistrationRequest,
    clinic_service: ClinicService = Depends(get_clinic_service)
):
    try:
        # Регистрируем клинику и создаем администраторов
        # (инициализация токена происходит внутри сервиса)
        result = await clinic_service.register_clinic(request.dict())
        
        return ApiResponse(
            success=True,
            message=f"Клиника {request.name} успешно зарегистрирована с авторизацией в AmoCRM",
            data=result
        )
    except Exception as e:
        logger.error(f"Ошибка при регистрации клиники: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("/api/admin/clinics/{clinic_id}/refresh-token", response_model=ApiResponse)
async def refresh_amocrm_token(
    clinic_id: str,
    client_secret: Optional[str] = None,
    redirect_url: Optional[str] = None,
    clinic_service: ClinicService = Depends(get_clinic_service)
):
    """
    Обновляет токен для конкретной клиники.
    Адаптация существующего эндпоинта /api/amocrm/refresh-token.
    """
    try:
        logger.info(f"Запрос на диагностику/обновление токена для клиники ID={clinic_id}")
        
        # Получаем информацию о клинике
        clinic = await clinic_service.get_clinic_by_id(clinic_id)
        
        if not clinic:
            return ApiResponse(
                success=False,
                message=f"Клиника с ID {clinic_id} не найдена",
                data=None
            )
        
        # Получаем token_data из MongoDB
        mongo_client = AsyncIOMotorClient(MONGO_URI)
        db = mongo_client[DB_NAME]
        collection = db["tokens"]
        
        token_data = await collection.find_one({"client_id": clinic["client_id"]})
        
        if not token_data:
            return ApiResponse(
                success=False,
                message=f"Токен для клиники ID={clinic_id} (client_id={clinic['client_id']}) не найден в базе данных",
                data={
                    "suggestion": "Необходимо выполнить первичную авторизацию через /api/admin/clinics"
                }
            )
        
        # Выводим информацию о токене для диагностики
        token_info = {
            "client_id": clinic["client_id"],
            "has_access_token": "access_token" in token_data,
            "has_refresh_token": "refresh_token" in token_data,
            "has_subdomain": "subdomain" in token_data,
            "updated_at": token_data.get("updated_at", "Неизвестно")
        }
        
        # Создаем экземпляр клиента AmoCRM
        client = AsyncAmoCRMClient(
            client_id=clinic["client_id"],
            client_secret=client_secret or clinic["client_secret"],
            subdomain=clinic["amocrm_subdomain"],
            redirect_url=redirect_url or clinic["redirect_url"],
            mongo_uri=MONGO_URI,
            db_name=DB_NAME
        )
        
        # Проверяем правильность хранимого токена
        try:
            # Пытаемся получить токен (это вызовет обновление, если он истек)
            access_token = await client.token_manager.get_access_token()
            
            # Если мы дошли сюда, то токен либо действителен, либо успешно обновлен
            return ApiResponse(
                success=True,
                message="Токен действителен или успешно обновлен",
                data={
                    "token_info": token_info,
                    "access_token_preview": access_token[:10] + "..." if access_token else None,
                    "clinic_id": clinic_id
                }
            )
        except Exception as token_error:
            # Если возникла ошибка, попробуем принудительно обновить токен
            logger.error(f"Ошибка при проверке токена: {token_error}")
            
            try:
                # Явно указываем нужные параметры
                client.token_manager.subdomain = clinic["amocrm_subdomain"]
                
                # Принудительно пытаемся обновить токен
                refresh_token = await client.token_manager._storage.get_refresh_token(clinic["client_id"])
                
                if not refresh_token:
                    return ApiResponse(
                        success=False,
                        message="Refresh token отсутствует в базе данных",
                        data={
                            "token_info": token_info,
                            "error": str(token_error),
                            "suggestion": "Необходимо выполнить первичную авторизацию через /api/admin/clinics"
                        }
                    )
                
                # Формируем запрос на обновление токена
                body = {
                    "client_id": clinic["client_id"],
                    "client_secret": client_secret or clinic["client_secret"],
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "redirect_uri": redirect_url or clinic["redirect_url"],
                }
                
                logger.info(f"Попытка принудительно обновить токен: {json.dumps(body, default=str)}")
                
                response = requests.post(f"https://{clinic['amocrm_subdomain']}.amocrm.ru/oauth2/access_token", json=body)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Сохраняем новые токены
                    await client.token_manager._storage.save_tokens(
                        clinic["client_id"], 
                        data["access_token"], 
                        data["refresh_token"], 
                        clinic["amocrm_subdomain"]
                    )
                    
                    return ApiResponse(
                        success=True,
                        message="Токен успешно обновлен принудительно",
                        data={
                            "old_token_info": token_info,
                            "access_token_preview": data["access_token"][:10] + "...",
                            "clinic_id": clinic_id
                        }
                    )
                else:
                    return ApiResponse(
                        success=False,
                        message=f"Ошибка при принудительном обновлении токена: HTTP {response.status_code}",
                        data={
                            "token_info": token_info,
                            "response": response.text,
                            "suggestion": "Возможно, интеграция была отключена или удалена в AmoCRM"
                        }
                    )
                    
            except Exception as forced_refresh_error:
                return ApiResponse(
                    success=False,
                    message=f"Ошибка при принудительном обновлении токена: {str(forced_refresh_error)}",
                    data={
                        "token_info": token_info,
                        "original_error": str(token_error),
                        "clinic_id": clinic_id
                    }
                )
    except Exception as e:
        error_msg = f"Ошибка при диагностике/обновлении токена: {str(e)}"
        logger.error(error_msg)
        
        return ApiResponse(
            success=False,
            message=error_msg,
            data=None
        )
    
@router.get("/api/admin/test-mongodb")
async def test_mongodb(clinic_service: ClinicService = Depends(get_clinic_service)):
    """
    Тестирует подключение к MongoDB
    """
    result = await clinic_service.test_mongodb_connection()
    return result