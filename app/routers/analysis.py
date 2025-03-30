from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from typing import Dict, Any, Optional
import logging
import os

from ..models.call_analysis import CallAnalysisRequest, CallAnalysisResponse
from ..services.call_analysis_service import call_analysis_service
from ..settings.paths import TRANSCRIPTION_DIR

router = APIRouter(tags=["analysis"])
logger = logging.getLogger(__name__)

@router.post("/api/call/analyze", response_model=CallAnalysisResponse)
async def analyze_call(request: CallAnalysisRequest, background_tasks: BackgroundTasks):
    """
    Анализирует звонок с помощью LLM и формирует отчет.
    Можно передать либо имя файла транскрипции, либо текст транскрипции напрямую.
    """
    try:
        # Проверяем, что передан хотя бы один из параметров для анализа
        if not request.transcription_filename and not request.transcription_text:
            return CallAnalysisResponse(
                success=False,
                message="Необходимо указать имя файла транскрипции или текст транскрипции",
                data=None
            )
        
        # Получаем текст для анализа
        dialogue_text = ""
        if request.transcription_filename:
            file_path = os.path.join(TRANSCRIPTION_DIR, request.transcription_filename)
            if not os.path.exists(file_path):
                return CallAnalysisResponse(
                    success=False,
                    message=f"Файл транскрипции {request.transcription_filename} не найден",
                    data=None
                )
            dialogue_text = call_analysis_service.load_transcription(file_path)
        else:
            dialogue_text = request.transcription_text
        
        # Собираем метаданные
        meta_info = request.meta_info or {}
        if request.note_id:
            meta_info["note_id"] = request.note_id
        if request.contact_id:
            meta_info["contact_id"] = request.contact_id
        if request.lead_id:
            meta_info["lead_id"] = request.lead_id
            
        # Выполняем анализ
        logger.info("Запуск анализа звонка")
        analysis_result = call_analysis_service.full_call_analysis(dialogue_text, meta_info)
        
        # Сохраняем результат в файл
        output_filename = None
        if request.transcription_filename:
            # Используем схожее имя для файла анализа
            base_name = os.path.splitext(request.transcription_filename)[0]
            output_filename = f"{base_name}_analysis.txt"
        
        # Сохраняем анализ в фоновом режиме
        background_tasks.add_task(
            call_analysis_service.save_analysis,
            analysis_result,
            output_filename
        )
        
        # Формируем и возвращаем ответ
        return CallAnalysisResponse(
            success=True,
            message="Анализ звонка успешно выполнен",
            data={
                "classification": analysis_result["classification"],
                "analysis": analysis_result["analysis"],
                "output_filename": output_filename,
                "timestamp": analysis_result["timestamp"]
            }
        )
        
    except Exception as e:
        logger.error(f"Ошибка при анализе звонка: {str(e)}")
        return CallAnalysisResponse(
            success=False,
            message=f"Ошибка при анализе звонка: {str(e)}",
            data=None
        )