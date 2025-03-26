from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime

class AmoCRMCredentials(BaseModel):
    client_id: str = Field(..., description="Client ID из интеграции AmoCRM")
    client_secret: str = Field(..., description="Client Secret из интеграции AmoCRM")
    subdomain: str = Field(..., description="Поддомен вашей AmoCRM (example в example.amocrm.ru)")
    redirect_url: str = Field(..., description="URL перенаправления из настроек интеграции")

class AmoCRMAuthRequest(AmoCRMCredentials):
    auth_code: str = Field(..., description="Код авторизации, полученный после редиректа")

class LeadRequest(BaseModel):
    client_id: str = Field(..., description="Client ID из интеграции AmoCRM")
    lead_id: int = Field(..., description="ID сделки в AmoCRM")

class ContactRequest(BaseModel):
    client_id: str = Field(..., description="Client ID из интеграции AmoCRM")
    contact_id: int = Field(..., description="ID контакта в AmoCRM")

class LeadsByDateRequest(BaseModel):
    client_id: str = Field(..., description="Client ID из интеграции AmoCRM")
    date: str = Field(..., description="Дата в формате ДД.ММ.ГГГГ (например, 13.03.2025)")

class APIResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None

class ContactResponse(BaseModel):
    id: int
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None

class CallResponse(BaseModel):
    contact_id: int
    call_link: Optional[str] = None
    download_url: Optional[str] = None
    local_path: Optional[str] = None