import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from motor.motor_asyncio import AsyncIOMotorClient
from bson.objectid import ObjectId

from ..models.metrics import CallMetricsRecord

logger = logging.getLogger(__name__)

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "medai"

class CallMetricsService:
    def __init__(self):
        """Инициализация сервиса для работы с метриками звонков"""
        self.client = AsyncIOMotorClient(MONGO_URI)
        self.db = self.client[DB_NAME]
        self.metrics_collection = self.db["call_metrics"]

    def extract_metrics_from_analysis(analysis_text: str) -> Dict[str, Any]:
        """
        Извлекает числовые оценки и категориальные переменные из текста анализа
        Расширенная версия с поддержкой дополнительных метрик
        """
        try:
            metrics = {}
            subcriteria = {}
            
            # Извлекаем числовые оценки
            greeting_match = re.search(r'Приветствие[^(]*\((\d+)/10\)', analysis_text)
            if greeting_match:
                metrics["greeting"] = float(greeting_match.group(1))
            
            needs_match = re.search(r'Выявление потребностей[^(]*\((\d+)/10\)', analysis_text)
            if needs_match:
                metrics["needs_identification"] = float(needs_match.group(1))
            
            solution_match = re.search(r'Предложение решения[^(]*\((\d+)/10\)', analysis_text)
            if solution_match:
                metrics["solution_proposal"] = float(solution_match.group(1))
            
            objection_match = re.search(r'Работа с возражениями[^(]*\((\d+)/10\)', analysis_text)
            if objection_match:
                metrics["objection_handling"] = float(objection_match.group(1))
            
            closing_match = re.search(r'Завершение разговора[^(]*\((\d+)/10\)', analysis_text)
            if closing_match:
                metrics["call_closing"] = float(closing_match.group(1))
            
            overall_match = re.search(r'Общая оценка[^(]*\((\d+)/10\)', analysis_text)
            if overall_match:
                metrics["overall_score"] = float(overall_match.group(1))
            
            # Извлекаем тональность разговора
            tone_match = re.search(r'Тональность разговора[^(]*(позитивн|нейтральн|негативн)', analysis_text, re.IGNORECASE)
            if tone_match:
                tone_text = tone_match.group(1).lower()
                if "позитивн" in tone_text:
                    metrics["tone"] = "positive"
                elif "негативн" in tone_text:
                    metrics["tone"] = "negative"
                else:
                    metrics["tone"] = "neutral"
            
            # Извлекаем удовлетворенность клиента
            satisfaction_match = re.search(r'Удовлетворенность клиента[^(]*(высок|средн|низк)', analysis_text, re.IGNORECASE)
            if satisfaction_match:
                satisfaction_text = satisfaction_match.group(1).lower()
                if "высок" in satisfaction_text:
                    metrics["customer_satisfaction"] = "high"
                elif "низк" in satisfaction_text:
                    metrics["customer_satisfaction"] = "low"
                else:
                    metrics["customer_satisfaction"] = "medium"
            
            # Пытаемся извлечь FG% (процент выполнения критериев)
            fg_match = re.search(r'выполнен(?:ие|о)(?:\s+критериев)?(?:\s*[-:])?\s*(\d+)%', analysis_text, re.IGNORECASE)
            if fg_match:
                metrics["fg_percent"] = float(fg_match.group(1))
            else:
                # Если не найдено явное указание FG%, рассчитаем его из средних оценок
                if "overall_score" in metrics:
                    metrics["fg_percent"] = metrics["overall_score"] * 10  # Преобразуем оценку 0-10 в проценты 0-100
            
            # Извлекаем информацию о конверсии
            conversion_match = re.search(r'конверсия[^:]*:[^a-zа-я]*(да|нет|успешн|неуспешн)', analysis_text, re.IGNORECASE)
            if conversion_match:
                conversion_text = conversion_match.group(1).lower()
                if "да" in conversion_text or "успешн" in conversion_text:
                    metrics["conversion"] = True
                else:
                    metrics["conversion"] = False
            
            # Извлекаем тип звонка (входящий/исходящий)
            call_type_match = re.search(r'тип звонка[^:]*:[^a-zа-я]*(входящ|исходящ)', analysis_text, re.IGNORECASE)
            if call_type_match:
                call_type_text = call_type_match.group(1).lower()
                if "входящ" in call_type_text:
                    metrics["call_type"] = "входящий"
                else:
                    metrics["call_type"] = "исходящий"
            
            # Категория звонка (первичка_1/первичка_перезвон/подтверждение/вторичка)
            call_category_match = re.search(r'категория[^:]*:[^a-zа-я]*(первичка\s*1|первичка\s*перезвон|подтвержден|вторичк)', analysis_text, re.IGNORECASE)
            if call_category_match:
                category_text = call_category_match.group(1).lower()
                if "первичка 1" in category_text or "первичка1" in category_text:
                    metrics["call_category"] = "первичка_1"
                elif "перезвон" in category_text:
                    metrics["call_category"] = "первичка_перезвон"
                elif "подтвержден" in category_text:
                    metrics["call_category"] = "подтверждение"
                elif "вторичк" in category_text:
                    metrics["call_category"] = "вторичка"
            
            # Извлекаем источник трафика
            source_match = re.search(r'источник[^:]*:[^a-zа-я]*([a-zа-я0-9\s]+)', analysis_text, re.IGNORECASE)
            if source_match:
                metrics["traffic_source"] = source_match.group(1).strip()
            
            # Извлекаем потребность клиента
            need_match = re.search(r'потребность[^:]*:[^a-zа-я]*([^\n.]+)', analysis_text, re.IGNORECASE)
            if need_match:
                metrics["client_request"] = need_match.group(1).strip()
            
            # Извлекаем детальные критерии оценки для подкритериев
            # Ищем последовательность символов ✅, !, ± в тексте
            criteria_match = re.search(r'критерии[^:]*:[^a-zа-я]*([✅!±\s]+)', analysis_text, re.IGNORECASE)
            if criteria_match:
                criteria_string = criteria_match.group(1).strip()
                # Преобразуем строку символов в массив для сохранения в subcriteria
                subcriteria["criteria_symbols"] = list(criteria_string.replace(" ", ""))
            
            # Извлекаем подкритерии для разных типов звонков
            # Приветствие
            greeting_criteria = re.search(r'приветствие[^:]*:[^a-zа-я]*(✅|!|±)', analysis_text, re.IGNORECASE)
            if greeting_criteria:
                subcriteria["greeting"] = greeting_criteria.group(1)
            
            # Имя пациента
            name_criteria = re.search(r'имя пациента[^:]*:[^a-zа-я]*(✅|!|±)', analysis_text, re.IGNORECASE)
            if name_criteria:
                subcriteria["patient_name"] = name_criteria.group(1)
            
            # Выявление потребностей
            need_criteria = re.search(r'выявление потребностей[^:]*:[^a-zа-я]*(✅|!|±)', analysis_text, re.IGNORECASE)
            if need_criteria:
                subcriteria["need_identification"] = need_criteria.group(1)
            
            # Презентация клиники
            clinic_criteria = re.search(r'презентация клиники[^:]*:[^a-zа-я]*(✅|!|±)', analysis_text, re.IGNORECASE)
            if clinic_criteria:
                subcriteria["clinic_presentation"] = clinic_criteria.group(1)
            
            # Презентация услуг
            service_criteria = re.search(r'презентация услуг[^:]*:[^a-zа-я]*(✅|!|±)', analysis_text, re.IGNORECASE)
            if service_criteria:
                subcriteria["service_presentation"] = service_criteria.group(1)
            
            # Презентация врачей
            doctor_criteria = re.search(r'презентация врачей[^:]*:[^a-zа-я]*(✅|!|±)', analysis_text, re.IGNORECASE)
            if doctor_criteria:
                subcriteria["doctor_presentation"] = doctor_criteria.group(1)
            
            # Запись на приём
            appointment_criteria = re.search(r'запись[^:]*:[^a-zа-я]*(✅|!|±)', analysis_text, re.IGNORECASE)
            if appointment_criteria:
                subcriteria["appointment"] = appointment_criteria.group(1)
            
            # Цена
            price_criteria = re.search(r'цена[^:]*:[^a-zа-я]*(✅|!|±)', analysis_text, re.IGNORECASE)
            if price_criteria:
                subcriteria["price"] = price_criteria.group(1)
            
            # Адрес
            address_criteria = re.search(r'адрес[^:]*:[^a-zа-я]*(✅|!|±)', analysis_text, re.IGNORECASE)
            if address_criteria:
                subcriteria["address"] = address_criteria.group(1)
            
            # Паспорт
            passport_criteria = re.search(r'паспорт[^:]*:[^a-zа-я]*(✅|!|±)', analysis_text, re.IGNORECASE)
            if passport_criteria:
                subcriteria["passport"] = passport_criteria.group(1)
            
            # Работа с возражениями
            objection_criteria = re.search(r'работа с возражениями[^:]*:[^a-zа-я]*(✅|!|±)', analysis_text, re.IGNORECASE)
            if objection_criteria:
                subcriteria["objection_handling"] = objection_criteria.group(1)
            
            # Следующий шаг
            next_step_criteria = re.search(r'следующий шаг[^:]*:[^a-zа-я]*(✅|!|±)', analysis_text, re.IGNORECASE)
            if next_step_criteria:
                subcriteria["next_step"] = next_step_criteria.group(1)
            
            # Качество речи
            speech_criteria = re.search(r'речь[^:]*:[^a-zа-я]*(✅|!|±)', analysis_text, re.IGNORECASE)
            if speech_criteria:
                subcriteria["speech_quality"] = speech_criteria.group(1)
            
            # Проявление инициативы
            initiative_criteria = re.search(r'инициатива[^:]*:[^a-zа-я]*(✅|!|±)', analysis_text, re.IGNORECASE)
            if initiative_criteria:
                subcriteria["initiative"] = initiative_criteria.group(1)
            
            # Апелляция (для перезвона и подтверждения)
            appeal_criteria = re.search(r'апелляция[^:]*:[^a-zа-я]*(✅|!|±)', analysis_text, re.IGNORECASE)
            if appeal_criteria:
                subcriteria["recall_appeal"] = appeal_criteria.group(1)
            
            # Уточнение вопроса (для вторички)
            clarification_criteria = re.search(r'уточнение[^:]*:[^a-zа-я]*(✅|!|±)', analysis_text, re.IGNORECASE)
            if clarification_criteria:
                subcriteria["clarification"] = clarification_criteria.group(1)
            
            # Если есть подкритерии, добавляем их в метрики
            if subcriteria:
                metrics["subcriteria"] = subcriteria
            
            # Проверяем, что извлечены все необходимые метрики
            required_keys = [
                "greeting", "needs_identification", "solution_proposal", 
                "objection_handling", "call_closing", "tone", 
                "customer_satisfaction", "overall_score"
            ]
            
            # Если не хватает какой-то метрики, заполняем значениями по умолчанию
            for key in required_keys:
                if key not in metrics:
                    if key in ["tone"]:
                        metrics[key] = "neutral"
                    elif key in ["customer_satisfaction"]:
                        metrics[key] = "medium"
                    else:
                        metrics[key] = 0.0
            
            return metrics
        except Exception as e:
            logger.error(f"Ошибка при извлечении метрик из анализа: {e}")
            return None
        
    # async def save_call_metrics(self, metrics_data: Dict[str, Any]) -> str:
    #     """
    #     Сохраняет метрики звонка в базу данных
    #     Возвращает ID созданной записи
    #     """
    #     try:
    #         # Проверяем, существует ли уже метрика для этого звонка
    #         query = {}
    #         if metrics_data.get("call_id"):
    #             query["call_id"] = metrics_data["call_id"]
    #         elif metrics_data.get("note_id"):
    #             query["note_id"] = metrics_data["note_id"]
                
    #         if query and await self.metrics_collection.find_one(query):
    #             # Обновляем существующую запись
    #             result = await self.metrics_collection.update_one(
    #                 query,
    #                 {"$set": {
    #                     "metrics": metrics_data["metrics"],
    #                     "comments": metrics_data.get("comments"),
    #                     "recommendations": metrics_data.get("recommendations"),
    #                     "call_classification": metrics_data["call_classification"],
    #                     "updated_at": datetime.now().isoformat()
    #                 }}
    #             )
                
    #             if result.modified_count > 0:
    #                 existing_record = await self.metrics_collection.find_one(query)
    #                 if existing_record:
    #                     return str(existing_record["_id"])
    #                 return "updated"
            
    #         # Создаем новую запись
    #         metrics_data["created_at"] = datetime.now().isoformat()
            
    #         # Преобразуем строковую дату из timestamp, если она предоставлена
    #         if "timestamp" in metrics_data and not metrics_data.get("date"):
    #             try:
    #                 date_obj = datetime.fromtimestamp(metrics_data["timestamp"])
    #                 metrics_data["date"] = date_obj.strftime("%Y-%m-%d")
    #             except:
    #                 metrics_data["date"] = datetime.now().strftime("%Y-%m-%d")
            
    #         # Если дата не указана, используем текущую
    #         if not metrics_data.get("date"):
    #             metrics_data["date"] = datetime.now().strftime("%Y-%m-%d")
                
    #         result = await self.metrics_collection.insert_one(metrics_data)
    #         return str(result.inserted_id)
        
    #     except Exception as e:
    #         logger.error(f"Ошибка при сохранении метрик звонка: {e}")
    #         raise

    async def save_call_metrics(
        request: CallAnalysisRequest,
        analysis_result: Dict[str, Any],
        metrics: Dict[str, Any],
        background_tasks: BackgroundTasks,
        clinic_service: ClinicService
    ):
        """
        Сохраняет расширенные метрики звонка в базу данных
        """
        try:
            # Получаем информацию об администраторе и клинике
            clinic_data = await clinic_service.get_clinic_by_id(request.clinic_id)
            
            if not clinic_data:
                logger.warning(f"Клиника не найдена: {request.clinic_id}, не сохраняем метрики")
                return
                
            # Ищем администратора по ID
            administrator_name = "Неизвестный администратор"
            for admin in clinic_data.get("administrators", []):
                if admin["id"] == request.administrator_id:
                    administrator_name = admin["name"]
                    break
            
            # Получаем текущую дату и время
            now = datetime.now()
            current_date = now.strftime("%Y-%m-%d")
            current_time = now.strftime("%H:%M:%S")
            
            # Формируем расширенную метрику для сохранения
            metrics_data = {
                "administrator_id": request.administrator_id,
                "administrator_name": administrator_name,
                "clinic_id": request.clinic_id,
                "date": current_date,
                "time": current_time,
                "call_id": request.call_id,
                "note_id": request.note_id,
                "contact_id": request.contact_id,
                "lead_id": request.lead_id,
                "metrics": metrics,
                "call_classification": analysis_result["classification"],
                "comments": "",
                "recommendations": extract_recommendations(analysis_result["analysis"]),
                "created_at": now.isoformat()
            }
            
            # Дополнительные поля из расширенных метрик
            if "call_type" in metrics:
                metrics_data["call_type"] = metrics["call_type"]
                
            if "call_category" in metrics:
                metrics_data["call_category"] = metrics["call_category"]
                
            if "traffic_source" in metrics:
                metrics_data["traffic_source"] = metrics["traffic_source"]
                
            if "client_request" in metrics:
                metrics_data["client_request"] = metrics["client_request"]
                
            if "conversion" in metrics:
                metrics_data["conversion"] = metrics["conversion"]
            
            # Формируем ссылки на CRM и транскрибацию
            # Ссылка на CRM (предполагаем, что может быть в meta_info)
            if request.meta_info and "crm_link" in request.meta_info:
                metrics_data["crm_link"] = request.meta_info["crm_link"]
            elif request.lead_id:
                # Формируем ссылку на сделку в AmoCRM
                metrics_data["crm_link"] = f"https://{clinic_data.get('amocrm_subdomain', 'amocrm')}.amocrm.ru/leads/detail/{request.lead_id}"
            elif request.contact_id:
                # Формируем ссылку на контакт в AmoCRM
                metrics_data["crm_link"] = f"https://{clinic_data.get('amocrm_subdomain', 'amocrm')}.amocrm.ru/contacts/detail/{request.contact_id}"
            
            # Формируем ссылку на транскрибацию
            if request.transcription_filename:
                metrics_data["transcription_link"] = f"/api/transcriptions/{request.transcription_filename}/download"
            
            # Сохраняем метрики в фоновом режиме
            background_tasks.add_task(
                save_metrics_background,
                metrics_data
            )
            
            logger.info(f"Задача на сохранение расширенных метрик звонка добавлена в фон: администратор {administrator_name}")
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении метрик звонка: {e}")
            import traceback
            logger.error(f"Стек-трейс: {traceback.format_exc()}")

    async def save_metrics_background(metrics_data: Dict[str, Any]):
        """
        Фоновая задача для сохранения расширенных метрик звонка
        """
        try:
            # Сохраняем метрики в базу данных
            metric_id = await call_metrics_service.save_call_metrics(metrics_data)
            logger.info(f"Расширенные метрики звонка сохранены с ID: {metric_id}")
            
            # Обновляем счетчики использования для администратора и клиники
            try:
                # Увеличиваем счетчик оцененных звонков администратора
                admin_result = await call_metrics_service.db.administrators.update_one(
                    {"_id": metrics_data["administrator_id"]},
                    {"$inc": {"current_month_usage": 1}}
                )
                
                # Если администратор не найден по _id, попробуем поискать по id
                if admin_result.modified_count == 0:
                    await call_metrics_service.db.administrators.update_one(
                        {"id": metrics_data["administrator_id"]},
                        {"$inc": {"current_month_usage": 1}}
                    )
                    
                # Увеличиваем счетчик оцененных звонков клиники
                clinic_result = await call_metrics_service.db.clinics.update_one(
                    {"_id": metrics_data["clinic_id"]},
                    {"$inc": {"current_month_usage": 1}}
                )
                
                # Если клиника не найдена по _id, попробуем поискать по id
                if clinic_result.modified_count == 0:
                    await call_metrics_service.db.clinics.update_one(
                        {"id": metrics_data["clinic_id"]},
                        {"$inc": {"current_month_usage": 1}}
                    )
                    
                logger.info(f"Счетчики использования обновлены для администратора {metrics_data['administrator_id']} и клиники {metrics_data['clinic_id']}")
                
            except Exception as counter_error:
                logger.error(f"Ошибка при обновлении счетчиков использования: {counter_error}")
            
        except Exception as e:
            logger.error(f"Ошибка при фоновом сохранении метрик звонка: {e}")
            import traceback
            logger.error(f"Стек-трейс: {traceback.format_exc()}")
    
    # async def get_call_metrics(self, 
    #                           start_date: str, 
    #                           end_date: str, 
    #                           clinic_id: Optional[str] = None,
    #                           administrator_ids: Optional[List[str]] = None,
    #                           call_classification: Optional[int] = None) -> List[Dict[str, Any]]:
    #     """
    #     Получает метрики звонков за указанный период с возможностью фильтрации
    #     """
    #     try:
    #         # Создаем фильтр для запроса
    #         query = {
    #             "date": {
    #                 "$gte": start_date,
    #                 "$lte": end_date
    #             }
    #         }
            
    #         if clinic_id:
    #             query["clinic_id"] = clinic_id
            
    #         if administrator_ids:
    #             query["administrator_id"] = {"$in": administrator_ids}
                
    #         if call_classification:
    #             query["call_classification"] = call_classification
                
    #         # Выполняем запрос и получаем результаты
    #         cursor = self.metrics_collection.find(query)
    #         metrics = await cursor.to_list(length=None)
            
    #         # Преобразуем _id в строку для сериализации
    #         for metric in metrics:
    #             if "_id" in metric and not isinstance(metric["_id"], str):
    #                 metric["_id"] = str(metric["_id"])
            
    #         return metrics
            
    #     except Exception as e:
    #         logger.error(f"Ошибка при получении метрик звонков: {e}")
    #         raise

    async def get_call_metrics(self, 
                              start_date: str, 
                              end_date: str, 
                              clinic_id: Optional[str] = None,
                              administrator_ids: Optional[List[str]] = None,
                              call_classification: Optional[int] = None,
                              call_type: Optional[str] = None,
                              call_category: Optional[str] = None,
                              traffic_source: Optional[str] = None,
                              conversion: Optional[bool] = None) -> List[Dict[str, Any]]:
        """
        Получает метрики звонков за указанный период с расширенными возможностями фильтрации
        """
        try:
            # Создаем фильтр для запроса
            query = {
                "date": {
                    "$gte": start_date,
                    "$lte": end_date
                }
            }
            
            if clinic_id:
                query["clinic_id"] = clinic_id
            
            if administrator_ids:
                query["administrator_id"] = {"$in": administrator_ids}
                    
            if call_classification:
                query["call_classification"] = call_classification
                
            if call_type:
                query["call_type"] = call_type
                
            if call_category:
                query["call_category"] = call_category
                
            if traffic_source:
                query["traffic_source"] = traffic_source
                
            if conversion is not None:
                query["conversion"] = conversion
                    
            # Выполняем запрос и получаем результаты
            cursor = self.metrics_collection.find(query)
            metrics = await cursor.to_list(length=None)
            
            # Преобразуем _id в строку для сериализации
            for metric in metrics:
                if "_id" in metric and not isinstance(metric["_id"], str):
                    metric["_id"] = str(metric["_id"])
            
            return metrics
                
        except Exception as e:
            logger.error(f"Ошибка при получении метрик звонков: {e}")
            raise
    
    async def get_administrator_metrics(self, administrator_id: str, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        Получает агрегированные метрики для конкретного администратора
        """
        try:
            # Получаем все метрики для администратора
            metrics = await self.get_call_metrics(start_date, end_date, administrator_ids=[administrator_id])
            
            if not metrics:
                return {
                    "administrator_id": administrator_id,
                    "call_count": 0,
                    "average_scores": {
                        "greeting": 0,
                        "needs_identification": 0,
                        "solution_proposal": 0,
                        "objection_handling": 0,
                        "call_closing": 0,
                        "overall_score": 0
                    },
                    "tone_stats": {"positive": 0, "neutral": 0, "negative": 0},
                    "satisfaction_stats": {"high": 0, "medium": 0, "low": 0},
                    "call_types": {}
                }
            
            # Агрегируем метрики
            call_count = len(metrics)
            
            # Подсчитываем средние оценки
            total_greeting = sum(m["metrics"]["greeting"] for m in metrics)
            total_needs = sum(m["metrics"]["needs_identification"] for m in metrics)
            total_solution = sum(m["metrics"]["solution_proposal"] for m in metrics)
            total_objection = sum(m["metrics"]["objection_handling"] for m in metrics)
            total_closing = sum(m["metrics"]["call_closing"] for m in metrics)
            total_overall = sum(m["metrics"]["overall_score"] for m in metrics)
            
            # Подсчитываем статистику по тональности
            tone_stats = {"positive": 0, "neutral": 0, "negative": 0}
            satisfaction_stats = {"high": 0, "medium": 0, "low": 0}
            call_types = {}
            
            for m in metrics:
                # Тональность
                tone = m["metrics"]["tone"]
                tone_stats[tone] = tone_stats.get(tone, 0) + 1
                
                # Удовлетворенность
                satisfaction = m["metrics"]["customer_satisfaction"]
                satisfaction_stats[satisfaction] = satisfaction_stats.get(satisfaction, 0) + 1
                
                # Типы звонков
                call_type = m["call_classification"]
                call_types[call_type] = call_types.get(call_type, 0) + 1
            
            return {
                "administrator_id": administrator_id,
                "administrator_name": metrics[0]["administrator_name"] if metrics else "",
                "call_count": call_count,
                "average_scores": {
                    "greeting": total_greeting / call_count if call_count > 0 else 0,
                    "needs_identification": total_needs / call_count if call_count > 0 else 0,
                    "solution_proposal": total_solution / call_count if call_count > 0 else 0,
                    "objection_handling": total_objection / call_count if call_count > 0 else 0,
                    "call_closing": total_closing / call_count if call_count > 0 else 0,
                    "overall_score": total_overall / call_count if call_count > 0 else 0
                },
                "tone_stats": tone_stats,
                "satisfaction_stats": satisfaction_stats,
                "call_types": call_types
            }
            
        except Exception as e:
            logger.error(f"Ошибка при получении агрегированных метрик для администратора: {e}")
            raise
    
    async def get_clinic_metrics(self, clinic_id: str, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        Получает агрегированные метрики для клиники
        """
        try:
            # Получаем все метрики для клиники
            metrics = await self.get_call_metrics(start_date, end_date, clinic_id=clinic_id)
            
            if not metrics:
                return {
                    "clinic_id": clinic_id,
                    "call_count": 0,
                    "administrators": {},
                    "average_scores": {
                        "greeting": 0,
                        "needs_identification": 0,
                        "solution_proposal": 0,
                        "objection_handling": 0,
                        "call_closing": 0,
                        "overall_score": 0
                    },
                    "tone_stats": {"positive": 0, "neutral": 0, "negative": 0},
                    "satisfaction_stats": {"high": 0, "medium": 0, "low": 0},
                    "call_types": {}
                }
            
            # Группируем метрики по администраторам
            admin_metrics = {}
            for metric in metrics:
                admin_id = metric["administrator_id"]
                if admin_id not in admin_metrics:
                    admin_metrics[admin_id] = {
                        "name": metric["administrator_name"],
                        "call_count": 0,
                        "metrics": []
                    }
                admin_metrics[admin_id]["call_count"] += 1
                admin_metrics[admin_id]["metrics"].append(metric)
            
            # Агрегируем общие метрики
            call_count = len(metrics)
            
            # Подсчитываем средние оценки
            total_greeting = sum(m["metrics"]["greeting"] for m in metrics)
            total_needs = sum(m["metrics"]["needs_identification"] for m in metrics)
            total_solution = sum(m["metrics"]["solution_proposal"] for m in metrics)
            total_objection = sum(m["metrics"]["objection_handling"] for m in metrics)
            total_closing = sum(m["metrics"]["call_closing"] for m in metrics)
            total_overall = sum(m["metrics"]["overall_score"] for m in metrics)
            
            # Подсчитываем статистику по тональности и удовлетворенности
            tone_stats = {"positive": 0, "neutral": 0, "negative": 0}
            satisfaction_stats = {"high": 0, "medium": 0, "low": 0}
            call_types = {}
            
            for m in metrics:
                # Тональность
                tone = m["metrics"]["tone"]
                tone_stats[tone] = tone_stats.get(tone, 0) + 1
                
                # Удовлетворенность
                satisfaction = m["metrics"]["customer_satisfaction"]
                satisfaction_stats[satisfaction] = satisfaction_stats.get(satisfaction, 0) + 1
                
                # Типы звонков
                call_type = m["call_classification"]
                call_types[call_type] = call_types.get(call_type, 0) + 1
            
            return {
                "clinic_id": clinic_id,
                "call_count": call_count,
                "administrators": admin_metrics,
                "average_scores": {
                    "greeting": total_greeting / call_count if call_count > 0 else 0,
                    "needs_identification": total_needs / call_count if call_count > 0 else 0,
                    "solution_proposal": total_solution / call_count if call_count > 0 else 0,
                    "objection_handling": total_objection / call_count if call_count > 0 else 0,
                    "call_closing": total_closing / call_count if call_count > 0 else 0,
                    "overall_score": total_overall / call_count if call_count > 0 else 0
                },
                "tone_stats": tone_stats,
                "satisfaction_stats": satisfaction_stats,
                "call_types": call_types
            }
            
        except Exception as e:
            logger.error(f"Ошибка при получении агрегированных метрик для клиники: {e}")
            raise
            
    async def get_metrics_summary(self, metrics_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Создает сводный отчет на основе метрик звонков
        """
        if not metrics_data:
            return {
                "call_count": 0,
                "average_scores": {
                    "greeting": 0,
                    "needs_identification": 0,
                    "solution_proposal": 0,
                    "objection_handling": 0,
                    "call_closing": 0,
                    "overall_score": 0
                },
                "tone_stats": {"positive": 0, "neutral": 0, "negative": 0},
                "satisfaction_stats": {"high": 0, "medium": 0, "low": 0},
                "call_types": {}
            }
            
        # Агрегируем общие метрики
        call_count = len(metrics_data)
        
        # Подсчитываем средние оценки
        total_greeting = sum(m["metrics"]["greeting"] for m in metrics_data)
        total_needs = sum(m["metrics"]["needs_identification"] for m in metrics_data)
        total_solution = sum(m["metrics"]["solution_proposal"] for m in metrics_data)
        total_objection = sum(m["metrics"]["objection_handling"] for m in metrics_data)
        total_closing = sum(m["metrics"]["call_closing"] for m in metrics_data)
        total_overall = sum(m["metrics"]["overall_score"] for m in metrics_data)
        
        # Подсчитываем статистику по тональности и удовлетворенности
        tone_stats = {"positive": 0, "neutral": 0, "negative": 0}
        satisfaction_stats = {"high": 0, "medium": 0, "low": 0}
        call_types = {}
        
        for m in metrics_data:
            # Тональность
            tone = m["metrics"]["tone"]
            tone_stats[tone] = tone_stats.get(tone, 0) + 1
            
            # Удовлетворенность
            satisfaction = m["metrics"]["customer_satisfaction"]
            satisfaction_stats[satisfaction] = satisfaction_stats.get(satisfaction, 0) + 1
            
            # Типы звонков
            call_type = m["call_classification"]
            call_types[call_type] = call_types.get(call_type, 0) + 1
        
        return {
            "call_count": call_count,
            "average_scores": {
                "greeting": total_greeting / call_count if call_count > 0 else 0,
                "needs_identification": total_needs / call_count if call_count > 0 else 0,
                "solution_proposal": total_solution / call_count if call_count > 0 else 0,
                "objection_handling": total_objection / call_count if call_count > 0 else 0,
                "call_closing": total_closing / call_count if call_count > 0 else 0,
                "overall_score": total_overall / call_count if call_count > 0 else 0
            },
            "tone_stats": tone_stats,
            "satisfaction_stats": satisfaction_stats,
            "call_types": call_types
        }

# Создаем экземпляр сервиса для использования в других модулях
call_metrics_service = CallMetricsService()