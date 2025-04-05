import json
from fastapi import APIRouter, HTTPException, status
from typing import Optional
from ..models.amocrm import AmoCRMAuthRequest, APIResponse
from mlab_amo_async.amocrm_client import AsyncAmoCRMClient
import logging

# Настраиваем логирование
logger = logging.getLogger(__name__)

# Создаем роутер для административных функций
router = APIRouter(prefix="/api/amocrm", tags=["admin"])

# Глобальные константы
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "medai"

@router.post("/auth", response_model=APIResponse)
async def authenticate_amocrm(request: AmoCRMAuthRequest):
    """
    Регистрация пользователя и получение access/refresh токенов AmoCRM.
    Сохраняет токены в MongoDB для последующего использования.
    """
    try:
        logger.info(f"Авторизация в AmoCRM: client_id={request.client_id}, subdomain={request.subdomain}")
        
        # Создаем экземпляр клиента
        client = AsyncAmoCRMClient(
            client_id=request.client_id,
            client_secret=request.client_secret,
            subdomain=request.subdomain,
            redirect_url=request.redirect_url,
            mongo_uri=MONGO_URI,
            db_name=DB_NAME
        )
        
        # Инициализируем токены
        await client.init_token(request.auth_code)
        
        logger.info(f"Успешная авторизация в AmoCRM для client_id={request.client_id}")
        
        return APIResponse(
            success=True,
            message="Авторизация в AmoCRM успешно выполнена. Токены сохранены в MongoDB.",
            data={"client_id": request.client_id}
        )
    except Exception as e:
        error_msg = f"Ошибка при авторизации в AmoCRM: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
    finally:
        if 'client' in locals():
            await client.close()

@router.post("/refresh-token")
async def refresh_amocrm_token(
    client_id: str, 
    client_secret: Optional[str] = None,
    redirect_url: Optional[str] = None,
    subdomain: Optional[str] = None
):
    """
    Диагностика и принудительное обновление токена AmoCRM.
    
    Если client_secret, redirect_url и subdomain не указаны, 
    используются значения из MongoDB (если они там есть).
    """
    try:
        logger.info(f"Запрос на диагностику/обновление токена для client_id={client_id}")
        
        # Проверяем, есть ли токен в MongoDB
        from motor.motor_asyncio import AsyncIOMotorClient
        
        mongo_client = AsyncIOMotorClient(MONGO_URI)
        db = mongo_client[DB_NAME]
        collection = db["tokens"]
        
        token_data = await collection.find_one({"client_id": client_id})
        
        if not token_data:
            return {
                "success": False,
                "message": f"Токен для client_id={client_id} не найден в базе данных",
                "data": {
                    "suggestion": "Необходимо выполнить первичную авторизацию через /api/amocrm/auth"
                }
            }
        
        # Выводим информацию о токене для диагностики
        token_info = {
            "client_id": client_id,
            "has_access_token": "access_token" in token_data,
            "has_refresh_token": "refresh_token" in token_data,
            "has_subdomain": "subdomain" in token_data,
            "updated_at": token_data.get("updated_at", "Неизвестно")
        }
        
        # Создаем экземпляр клиента AmoCRM
        # Если указаны client_secret, redirect_url и subdomain, используем их,
        # иначе - значения из базы данных
        client = AsyncAmoCRMClient(
            client_id=client_id,
            client_secret=client_secret or "",  
            subdomain=subdomain or token_data.get("subdomain", ""),
            redirect_url=redirect_url or "",   
            mongo_uri=MONGO_URI,
            db_name=DB_NAME
        )
        
        # Проверяем правильность хранимого токена
        try:
            # Пытаемся получить токен (это вызовет обновление, если он истек)
            access_token = await client.token_manager.get_access_token()
            
            # Если мы дошли сюда, то токен либо действителен, либо успешно обновлен
            return {
                "success": True,
                "message": "Токен действителен или успешно обновлен",
                "data": {
                    "token_info": token_info,
                    "access_token_preview": access_token[:10] + "..." if access_token else None
                }
            }
        except Exception as token_error:
            # Если возникла ошибка, попробуем принудительно обновить токен
            logger.error(f"Ошибка при проверке токена: {token_error}")
            
            if client_secret and redirect_url and subdomain:
                try:
                    # Явно указываем нужные параметры
                    client.token_manager.subdomain = subdomain
                    
                    # Принудительно пытаемся обновить токен
                    refresh_token = await client.token_manager._storage.get_refresh_token(client_id)
                    
                    if not refresh_token:
                        return {
                            "success": False,
                            "message": "Refresh token отсутствует в базе данных",
                            "data": {
                                "token_info": token_info,
                                "error": str(token_error),
                                "suggestion": "Необходимо выполнить первичную авторизацию через /api/amocrm/auth"
                            }
                        }
                    
                    # Формируем запрос на обновление токена
                    body = {
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "redirect_uri": redirect_url,
                    }
                    
                    logger.info(f"Попытка принудительно обновить токен: {json.dumps(body, default=str)}")
                    
                    import requests
                    response = requests.post(f"https://{subdomain}.amocrm.ru/oauth2/access_token", json=body)
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Сохраняем новые токены
                        await client.token_manager._storage.save_tokens(
                            client_id, 
                            data["access_token"], 
                            data["refresh_token"], 
                            subdomain
                        )
                        
                        return {
                            "success": True,
                            "message": "Токен успешно обновлен принудительно",
                            "data": {
                                "old_token_info": token_info,
                                "access_token_preview": data["access_token"][:10] + "..."
                            }
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"Ошибка при принудительном обновлении токена: HTTP {response.status_code}",
                            "data": {
                                "token_info": token_info,
                                "response": response.text,
                                "suggestion": "Возможно, интеграция была отключена или удалена в AmoCRM"
                            }
                        }
                        
                except Exception as forced_refresh_error:
                    return {
                        "success": False,
                        "message": f"Ошибка при принудительном обновлении токена: {str(forced_refresh_error)}",
                        "data": {
                            "token_info": token_info,
                            "original_error": str(token_error)
                        }
                    }
            else:
                return {
                    "success": False,
                    "message": "Токен недействителен, для обновления необходимо указать client_secret, redirect_url и subdomain",
                    "data": {
                        "token_info": token_info,
                        "error": str(token_error)
                    }
                }
    except Exception as e:
        error_msg = f"Ошибка при диагностике/обновлении токена: {str(e)}"
        logger.error(error_msg)
        
        return {
            "success": False,
            "message": error_msg,
            "data": None
        }
    finally:
        if 'client' in locals():
            await client.close()
