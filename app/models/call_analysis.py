from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime

class CallAnalysisRequest(BaseModel):
    transcription_filename: Optional[str] = Field(None, description="Имя файла транскрипции в директории transcription")
    transcription_text: Optional[str] = Field(None, description="Текст транскрипции для анализа")
    note_id: Optional[int] = Field(None, description="ID заметки для связи с записью звонка")
    contact_id: Optional[int] = Field(None, description="ID контакта для связи")
    lead_id: Optional[int] = Field(None, description="ID сделки для связи")
    meta_info: Optional[Dict[str, Any]] = Field(None, description="Дополнительная информация о звонке")

class CallAnalysisResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None