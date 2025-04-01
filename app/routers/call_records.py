from fastapi import APIRouter, HTTPException, status, Request, Depends
from typing import List, Optional
import logging
from datetime import datetime

from ..models.clinic import ApiResponse
from ..services.call_record_service import CallRecordService
from ..services.limits_service import LimitsService

# Настройка логирования
logger = logging.getLogger(__name__)

# Создаем роутер
router = APIRouter(prefix="/api", tags=["call_records"])

# Зависимости для сервисов
def get_call_record_service():
    return CallRecordService()

def get_limits_service():
    return LimitsService()

@router.post("/call-records", response_model=ApiResponse)
async def create_call_record(
    data: dict,
    call_record_service: CallRecordService = Depends(get_call_record_service),
    limits_service: LimitsService = Depends(get_limits_service)
):
    """
    Сохраняет запись о звонке, проверяя лимиты
    """
    try:
        # Проверяем лимиты для администратора
        allowed, reason, remaining = await limits_service.check_limits(data["administrator_id"])
        
        if not allowed:
            return ApiResponse(
                success=False,
                message=reason,
                data={"remaining": 0}
            )
            
        # Сохраняем запись о звонке
        result = await call_record_service.save_call_record(data)
        
        # Увеличиваем счетчик использования
        await limits_service.increment_usage(data["administrator_id"])
        
        return ApiResponse(
            success=True,
            message="Запись о звонке успешно сохранена",
            data={
                "record_id": result["record_id"],
                "remaining": remaining - 1  # Оставшееся количество звонков
            }
        )
    except Exception as e:
        logger.error(f"Ошибка при сохранении записи о звонке: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/call-records", response_model=ApiResponse)
async def get_call_records(
    clinic_id: Optional[str] = None,
    administrator_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    call_record_service: CallRecordService = Depends(get_call_record_service)
):
    """
    Получает записи о звонках с возможностью фильтрации
    """
    try:
        records = await call_record_service.get_call_records(
            clinic_id,
            administrator_id,
            start_date,
            end_date
        )
        
        return ApiResponse(
            success=True,
            message=f"Найдено {len(records)} записей",
            data={"records": records}
        )
    except Exception as e:
        logger.error(f"Ошибка при получении записей о звонках: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )