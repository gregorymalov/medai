import re
from typing import Dict, Any, Optional
from datetime import datetime
import os
import json
# import re
import time
import logging
# import asyncio
# import aiofiles
from motor.motor_asyncio import AsyncIOMotorClient
from ..settings.paths import AUDIO_DIR, TRANSCRIPTION_DIR
from ..settings.auth import evenlabs
from ..services.limits_service import LimitsService


logger = logging.getLogger(__name__)

# Глобальные константы
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "medai"

def detect_speaker_roles(dialogue, manager_name=None, client_name=None):
    """
    Определяет, кто из говорящих является менеджером, а кто клиентом,
    используя эвристики и анализ текста.
    
    :param dialogue: список словарей с репликами (speaker, text)
    :param manager_name: имя менеджера, если известно
    :param client_name: имя клиента, если известно
    :returns: (manager_speaker, client_speaker) - идентификаторы говорящих
    """
    # Фразы, типичные для менеджера
    manager_phrases = [
        "клиника", "стоматология", 
        "запись", "администратор", "как могу к вам обращаться",
        "врач", "прием", "доктор", "стоматологическая клиника", "приглашаем",
        "как вас зовут", "специалист", "услуги", "мы работаем",
        "рассрочка", "помочь", "подобрать", "предложить",
        "консультация", "спасибо за звонок", 
        "всего доброго"
    ]
    
    # Фразы, типичные для клиента
    client_phrases = [
        "сколько стоит", "цена", "дорого", "у меня проблема",
        "больно", "болит зуб", "когда можно", "хочу", 
        "у меня проблема", "подскажите", "я хотел", "мне нужно", "мне надо", "сколько будет",
        "как попасть", "как записаться", "хочу записаться"
    ]
    
    # Специальные маркеры сильного индикатора менеджера
    strong_manager_markers = [
        "администратор", "клиника", "стоматология", "я вас слушаю",
        "чем могу помочь", "стоматологическая клиника", "медицинский центр"
    ]
    
    # Специальные маркеры сильного индикатора клиента
    strong_client_markers = [
        "хочу записаться", "меня беспокоит", "мне нужно", "у меня болит",
        "подскажите пожалуйста", "сколько будет стоить"
    ]
    
    # Инициализируем счетчики для разных говорящих
    speakers = {}
    
    # Начальный анализ - собираем данные по всем говорящим
    for line in dialogue:
        speaker = line["speaker"]
        text = line["text"].lower()
        
        # Инициализируем счетчики для нового говорящего
        if speaker not in speakers:
            speakers[speaker] = {
                "manager_score": 0, 
                "client_score": 0, 
                "greeting_first": False,
                "lines_count": 0,
                "words_count": 0
            }
        
        # Увеличиваем счетчик реплик
        speakers[speaker]["lines_count"] += 1
        # Считаем примерное количество слов
        speakers[speaker]["words_count"] += len(text.split())
        
        # Проверяем, кто первым поздоровался
        if "добрый день" in text.lower() or "здравствуйте" in text.lower() or "добрый" in text.lower() or "алло" in text.lower():
            if not any(s["greeting_first"] for s in speakers.values()):
                speakers[speaker]["greeting_first"] = True
                # Первое приветствие обычно от менеджера
                speakers[speaker]["manager_score"] += 3
        
        # Проверяем фразы менеджера
        for phrase in manager_phrases:
            if phrase in text.lower():
                speakers[speaker]["manager_score"] += 1
        
        # Проверяем фразы клиента
        for phrase in client_phrases:
            if phrase in text.lower():
                speakers[speaker]["client_score"] += 1
        
        # Проверяем сильные индикаторы менеджера
        for marker in strong_manager_markers:
            if marker in text.lower():
                speakers[speaker]["manager_score"] += 5
        
        # Проверяем сильные индикаторы клиента
        for marker in strong_client_markers:
            if marker in text.lower():
                speakers[speaker]["client_score"] += 5
                
        # Особые эвристики для распознавания ролей
        
        # 1. Представление клиники - явный признак менеджера
        if re.search(r'(это|здравствуйте|приветствую).*клиника', text.lower()) or re.search(r'клиника.*слушает', text.lower()):
            speakers[speaker]["manager_score"] += 10
            
        # 2. Представление по имени - обычно это делает менеджер
        if "меня зовут" in text.lower() or "меня" in text.lower() and any(name in text.lower() for name in ["мария", "елена", "ольга", "анна", "екатерина"]):
            speakers[speaker]["manager_score"] += 7
        
        # 3. Вопрос о имени клиента - явный признак менеджера
        if "как я могу к вам обращаться" in text.lower() or "как вас зовут" in text.lower() or "как могу обращаться" in text.lower():
            speakers[speaker]["manager_score"] += 8
            
        # 4. Проверка на типичные названия клиник
        if any(clinic in text.lower() for clinic in ["дентал", "смайл", "стома", "эли", "дент", "медикал"]):
            speakers[speaker]["manager_score"] += 6
        
        # Если говорящий упоминает имя менеджера
        if manager_name and manager_name.lower() in text.lower():
            # Если говорящий говорит о себе в третьем лице
            if "администратор" in text.lower() or "меня зовут" in text.lower():
                speakers[speaker]["manager_score"] += 8
            else:
                speakers[speaker]["client_score"] += 2
        
        # Если говорящий упоминает имя клиента
        if client_name and client_name.lower() in text.lower():
            # Если говорящий обращается к клиенту по имени
            if "вас" in text.lower() or "вам" in text.lower():
                speakers[speaker]["manager_score"] += 3
            else:
                speakers[speaker]["client_score"] += 5
    
    # Если у нас только один говорящий, не можем определить роли
    if len(speakers) < 2:
        return None, None
    
    # Вторичный анализ - учитываем особенности диалогов
    
    # 1. Подсчитываем количество реплик и слов каждого говорящего
    total_lines = sum(s["lines_count"] for s in speakers.values())
    total_words = sum(s["words_count"] for s in speakers.values())
    
    # Обычно менеджер говорит больше
    for speaker, stats in speakers.items():
        lines_ratio = stats["lines_count"] / total_lines
        words_ratio = stats["words_count"] / total_words
        
        # Если говорящий произнес больше 60% всех слов, это скорее менеджер
        if words_ratio > 0.6:
            stats["manager_score"] += 3
        
        # Если говорящий произнес меньше 30% всех слов, это скорее клиент
        if words_ratio < 0.3:
            stats["client_score"] += 2
    
    # 2. Определяем, кто начал разговор
    if len(dialogue) > 0:
        first_speaker = dialogue[0]["speaker"]
        # Обычно менеджер начинает разговор
        speakers[first_speaker]["manager_score"] += 2
    
    # 3. Определяем, кто завершил разговор
    if len(dialogue) > 0:
        last_speaker = dialogue[-1]["speaker"]
        last_text = dialogue[-1]["text"].lower()
        
        # Если последняя реплика содержит прощание, скорее всего это менеджер
        if "всего доброго" in last_text or "до свидания" in last_text or "до свидан" in last_text:
            speakers[last_speaker]["manager_score"] += 2
    
    # Определяем роли на основе собранных данных
    speaker_items = list(speakers.items())
    
    # Сортируем по разнице между счетчиками (manager_score - client_score)
    speaker_items.sort(key=lambda x: x[1]["manager_score"] - x[1]["client_score"], reverse=True)
    
    # Логируем анализ для отладки
    logger.info(f"Результаты анализа ролей: {speaker_items}")
    
    # Первый говорящий с наибольшей разницей будет менеджером
    manager_speaker = speaker_items[0][0]
    
    # Если есть только один говорящий, клиента нет
    if len(speaker_items) < 2:
        client_speaker = None
    else:
        # Второй говорящий (с наименьшей разницей) будет клиентом
        client_speaker = speaker_items[1][0]
    
    return manager_speaker, client_speaker

# async def transcribe_and_save(
#     audio_path: str,
#     output_path: str,
#     num_speakers: int = 2,
#     diarize: bool = True,
#     phone: Optional[str] = None,
#     manager_name: Optional[str] = None,
#     client_name: Optional[str] = None,
#     is_first_contact: bool = False,
#     note_data: Optional[Dict[str, Any]] = None,
#     administrator_id: Optional[str] = None  # Добавляем параметр ID администратора
# ):
#     """
#     Выполняет транскрибацию аудиофайла и сохраняет результат в текстовый файл.
    
#     :param audio_path: Путь к аудиофайлу
#     :param output_path: Путь для сохранения результата
#     :param num_speakers: Количество говорящих
#     :param diarize: Включить разделение по говорящим
#     :param phone: Номер телефона клиента
#     :param manager_name: Имя менеджера/ответственного
#     :param client_name: Имя клиента
#     :param is_first_contact: Флаг первичного обращения
#     :param note_data: Дополнительные данные о заметке
#     :param administrator_id: ID администратора для обновления лимитов
#     """
#     try:
#         logger.info(f"Начало фоновой транскрибации файла: {audio_path}")
#         start_time = time.time()
        
#         # Инициализируем клиент EvenLabs
#         client = evenlabs()
        
#         # Открываем файл и отправляем его на транскрибацию
#         with open(audio_path, "rb") as audio_file:
#             response = client.speech_to_text.convert(
#                 file=audio_file, 
#                 model_id="scribe_v1",
#                 diarize=diarize,
#                 num_speakers=num_speakers
#             )
        
#         # Преобразуем ответ в словарь
#         response_dict = response.dict()
        
#         # Сохраняем полный ответ API для отладки
#         debug_file_path = output_path + ".debug.json"
#         with open(debug_file_path, "w", encoding="utf-8") as debug_file:
#             json.dump(response_dict, debug_file, ensure_ascii=False, indent=2)
#         logger.info(f"Сохранен отладочный файл с полным ответом API: {debug_file_path}")
        
#         # Настройка отображаемых имен
#         manager_display = "Менеджер"
#         if manager_name:
#             manager_display = f"Менеджер ({manager_name})"
        
#         client_display = "Клиент"
#         if client_name:
#             if is_first_contact:
#                 client_display = f"Клиент ({client_name})"
#             else:
#                 client_display = client_name
#         elif is_first_contact:
#             client_display = "Клиент (первичный)"
        
#         # Создаем универсальную карту спикеров
#         speaker_mapping = {}
#         for i in range(num_speakers):
#             # Основное имя спикера
#             display_name = f"Участник {i+1}"
#             if i == 0:
#                 display_name = manager_display
#             elif i == 1:
#                 display_name = client_display
            
#             # Маппинг для разных форматов идентификаторов
#             speaker_mapping[f"speaker_{i}"] = display_name
#             speaker_mapping[i] = display_name
#             speaker_mapping[str(i)] = display_name
        
#         # НОВЫЙ ПОДХОД: будем анализировать не только speaker_id, но и паузы в речи
#         # Это помогает, если API не правильно определяет смену говорящих
        
#         words = response_dict.get("words", [])
        
#         # Собираем слова в предложения, основываясь на паузах между словами
#         sentences = []
#         current_sentence = []
#         current_speaker = None
#         current_start = 0
        
#         # Параметры для определения пауз между предложениями
#         PAUSE_THRESHOLD = 0.7  # Порог паузы в секундах для разделения предложений
#         MAX_SENTENCE_DURATION = 10.0  # Максимальная длительность одного предложения в секундах
        
#         for i, word in enumerate(words):
#             # Пропускаем пробелы
#             if word.get("type") == "spacing":
#                 continue
            
#             # Получаем текущее слово
#             word_text = word.get("text", "")
#             word_start = word.get("start", 0)
#             word_end = word.get("end", 0)
#             word_speaker = word.get("speaker_id", "Unknown")
            
#             # Определяем, является ли это начало новой реплики
#             is_new_sentence = False
            
#             # Если это первое слово
#             if not current_sentence:
#                 is_new_sentence = True
#                 current_speaker = word_speaker
#             else:
#                 # Если сменился говорящий
#                 if word_speaker != current_speaker:
#                     is_new_sentence = True
#                 # Если длинная пауза между словами
#                 elif i > 0 and (word_start - words[i-1].get("end", 0)) > PAUSE_THRESHOLD:
#                     is_new_sentence = True
#                 # Если предложение слишком длинное
#                 elif word_end - current_start > MAX_SENTENCE_DURATION:
#                     is_new_sentence = True
#                 # Если в слове есть знак конца предложения и следующее слово начинается с большой буквы
#                 elif (word_text.endswith('.') or word_text.endswith('?') or word_text.endswith('!')) and i < len(words)-1:
#                     next_word = words[i+1].get("text", "")
#                     if next_word and next_word[0].isupper():
#                         is_new_sentence = True
            
#             # Если это новое предложение, сохраняем предыдущее и начинаем новое
#             if is_new_sentence and current_sentence:
#                 # Формируем текст из слов
#                 text = " ".join([w.get("text", "") for w in current_sentence])
#                 # Время начала и конца предложения
#                 start_time = current_sentence[0].get("start", 0)
#                 end_time = current_sentence[-1].get("end", 0)
#                 # Определяем говорящего (берем наиболее частый speaker_id)
#                 speaker_counts = {}
#                 for w in current_sentence:
#                     sp = w.get("speaker_id", "Unknown")
#                     speaker_counts[sp] = speaker_counts.get(sp, 0) + 1
#                 most_common_speaker = max(speaker_counts.items(), key=lambda x: x[1])[0]
                
#                 # Добавляем предложение в список
#                 sentences.append({
#                     "speaker_id": most_common_speaker,
#                     "text": text,
#                     "start_time": start_time,
#                     "end_time": end_time
#                 })
                
#                 # Начинаем новое предложение
#                 current_sentence = [word]
#                 current_speaker = word_speaker
#                 current_start = word_start
#             else:
#                 # Продолжаем текущее предложение
#                 current_sentence.append(word)
        
#         # Добавляем последнее предложение
#         if current_sentence:
#             text = " ".join([w.get("text", "") for w in current_sentence])
#             start_time = current_sentence[0].get("start", 0)
#             end_time = current_sentence[-1].get("end", 0)
#             speaker_counts = {}
#             for w in current_sentence:
#                 sp = w.get("speaker_id", "Unknown")
#                 speaker_counts[sp] = speaker_counts.get(sp, 0) + 1
#             most_common_speaker = max(speaker_counts.items(), key=lambda x: x[1])[0]
            
#             sentences.append({
#                 "speaker_id": most_common_speaker,
#                 "text": text,
#                 "start_time": start_time,
#                 "end_time": end_time
#             })
        
#         # Если у нас всего одно предложение для 2+ спикеров, разделим его по очереди
#         if len(sentences) == 1 and num_speakers >= 2:
#             logger.warning("Обнаружено только одно предложение для нескольких говорящих. Применяем эвристическое разделение.")
#             text = sentences[0]["text"]
#             # Разделяем по знакам препинания, затем объединяем в предполагаемые реплики
#             import re
#             parts = re.split(r'([.!?])\s+', text)
#             new_sentences = []
            
#             current_speaker_idx = 0
#             current_text_parts = []
#             current_start = sentences[0]["start_time"]
#             total_duration = sentences[0]["end_time"] - sentences[0]["start_time"]
#             part_duration = total_duration / len(parts) if len(parts) > 0 else total_duration
            
#             for i, part in enumerate(parts):
#                 if not part:
#                     continue
                
#                 # Добавляем часть к текущему предложению
#                 current_text_parts.append(part)
                
#                 # Если это знак препинания, завершаем предложение
#                 if part in ['.', '!', '?'] or i == len(parts) - 1:
#                     if current_text_parts:
#                         combined_text = ''.join(current_text_parts).strip()
#                         if combined_text:
#                             part_start = current_start
#                             part_end = part_start + part_duration * len(current_text_parts)
                            
#                             new_sentences.append({
#                                 "speaker_id": current_speaker_idx % num_speakers,
#                                 "text": combined_text,
#                                 "start_time": part_start,
#                                 "end_time": part_end
#                             })
                            
#                             current_start = part_end
#                             current_speaker_idx += 1
#                             current_text_parts = []
            
#             if new_sentences:
#                 sentences = new_sentences
#                 logger.info(f"Разделили аудио на {len(sentences)} предложений с помощью эвристики")
        
#         # Финальная обработка предложений в диалог
#         dialogue = []
#         for sentence in sentences:
#             speaker_id = sentence["speaker_id"]
#             # Используем маппинг для определения отображаемого имени спикера
#             display_name = speaker_mapping.get(speaker_id, "Участник")
            
#             # Если не смогли определить по маппингу, используем чередование
#             if display_name == "Участник":
#                 display_name = manager_display if len(dialogue) % 2 == 0 else client_display
            
#             dialogue.append({
#                 "speaker": display_name,
#                 "text": sentence["text"],
#                 "start_time": sentence["start_time"],
#                 "end_time": sentence["end_time"]
#             })
        
#         # Если после всего у нас только одна реплика, попробуем разделить по вопросам и ответам
#         if len(dialogue) <= 1 and num_speakers >= 2:
#             logger.warning("Обнаружена только одна реплика. Применяем разделение по вопросам и ответам.")
#             text = dialogue[0]["text"] if dialogue else ""
            
#             # Разделяем текст по вопросительным знакам
#             qa_parts = text.split("?")
#             new_dialogue = []
            
#             for i, part in enumerate(qa_parts):
#                 if not part.strip():
#                     continue
                
#                 # Добавляем вопросительный знак обратно (кроме последней части)
#                 if i < len(qa_parts) - 1:
#                     part += "?"
                
#                 # Определяем говорящего (чередуем)
#                 speaker = manager_display if i % 2 == 0 else client_display
                
#                 # Расчетное время (приблизительно)
#                 start_time = i * (dialogue[0]["end_time"] / len(qa_parts)) if dialogue else i
#                 end_time = (i + 1) * (dialogue[0]["end_time"] / len(qa_parts)) if dialogue else i + 1
                
#                 new_dialogue.append({
#                     "speaker": speaker,
#                     "text": part.strip(),
#                     "start_time": start_time,
#                     "end_time": end_time
#                 })
            
#             if new_dialogue:
#                 dialogue = new_dialogue
#                 logger.info(f"Разделили диалог на {len(dialogue)} реплик с помощью эвристики вопросов-ответов")
        
#         # Записываем диалог в файл
#         with open(output_path, "w", encoding="utf-8") as file:
#             # Добавляем заголовок с информацией о звонке
#             file.write(f"Транскрипция звонка\n")
#             file.write(f"Дата и время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            
#             if phone:
#                 file.write(f"Телефон: {phone}\n")
            
#             if client_name:
#                 file.write(f"Клиент: {client_name}\n")
                
#             if manager_name:
#                 file.write(f"Менеджер: {manager_name}\n")
                
#             if is_first_contact:
#                 file.write("Тип: Первичное обращение\n")
                
#             file.write(f"Файл: {os.path.basename(audio_path)}\n")
            
#             # Добавляем информацию о длительности
#             duration = response_dict.get("duration", 0)
#             minutes = int(duration) // 60
#             seconds = int(duration) % 60
#             file.write(f"Длительность: {minutes}:{seconds:02d}\n\n")
            
#             # Записываем диалог
#             for line in dialogue:
#                 # Форматируем время в формате [MM:SS]
#                 start_min = int(line["start_time"]) // 60
#                 start_sec = int(line["start_time"]) % 60
#                 time_str = f"[{start_min:02d}:{start_sec:02d}]"
                
#                 file.write(f"{time_str} {line['speaker']}: {line['text']}\n\n")
                
#         process_time = time.time() - start_time
#         logger.info(f"Транскрипция завершена и сохранена в {output_path} (заняло {process_time:.2f} сек.)")
        
#         # Сохраняем информацию о транскрипции в базу данных, если есть данные заметки
#         if note_data:
#             try:
#                 output_filename = os.path.basename(output_path)
#                 audio_filename = os.path.basename(audio_path)  # Получаем имя аудиофайла
                
#                 await save_transcription_info(
#                     filename=output_filename,
#                     note_id=note_data.get("note_id"),
#                     lead_id=note_data.get("lead_id"),
#                     contact_id=note_data.get("contact_id"),
#                     client_id=note_data.get("client_id"),
#                     manager=manager_name,
#                     phone=phone,
#                     filename_audio=audio_filename,  # Передаем имя аудиофайла
#                     administrator_id=administrator_id  # Передаем ID администратора
#                 )
#             except Exception as db_error:
#                 logger.error(f"Ошибка при сохранении информации о транскрипции в базу данных: {db_error}")
        
#     except Exception as e:
#         logger.error(f"Ошибка при фоновой транскрибации: {str(e)}")
#         import traceback
#         logger.error(f"Стек трейс: {traceback.format_exc()}")
        
#         # Записываем информацию об ошибке в файл результата
#         try:
#             with open(output_path, "w", encoding="utf-8") as file:
#                 file.write(f"Ошибка при транскрибации файла {audio_path}:\n\n{str(e)}")
#         except:
#             logger.error(f"Не удалось записать информацию об ошибке в файл {output_path}")

async def transcribe_and_save(
        audio_path: str,
        output_path: str,
        num_speakers: int = 2,
        diarize: bool = True,
        phone: Optional[str] = None,
        manager_name: Optional[str] = None,
        client_name: Optional[str] = None,
        is_first_contact: bool = False,
        note_data: Optional[Dict[str, Any]] = None,
        administrator_id: Optional[str] = None
    ):
        """
        Выполняет транскрибацию аудиофайла и сохраняет результат в текстовый файл.
        
        :param audio_path: Путь к аудиофайлу
        :param output_path: Путь для сохранения результата
        :param num_speakers: Количество говорящих
        :param diarize: Включить разделение по говорящим
        :param phone: Номер телефона клиента
        :param manager_name: Имя менеджера/ответственного
        :param client_name: Имя клиента
        :param is_first_contact: Флаг первичного обращения
        :param note_data: Дополнительные данные о заметке
        :param administrator_id: ID администратора для обновления лимитов
        """
        try:
            logger.info(f"Начало фоновой транскрибации файла: {audio_path}")
            start_time = time.time()
            
            # Инициализируем клиент EvenLabs
            client = evenlabs()
            
            # Открываем файл и отправляем его на транскрибацию
            with open(audio_path, "rb") as audio_file:
                response = client.speech_to_text.convert(
                    file=audio_file, 
                    model_id="scribe_v1",
                    diarize=diarize,
                    num_speakers=num_speakers
                )
            
            # Преобразуем ответ в словарь
            response_dict = response.dict()
            
            # Сохраняем полный ответ API для отладки
            debug_file_path = output_path + ".debug.json"
            with open(debug_file_path, "w", encoding="utf-8") as debug_file:
                json.dump(response_dict, debug_file, ensure_ascii=False, indent=2)
            logger.info(f"Сохранен отладочный файл с полным ответом API: {debug_file_path}")
            
            # Создаем нейтральные метки говорящих для начального анализа
            speaker_mapping = {}
            for i in range(num_speakers):
                # Нейтральные метки для начального распознавания
                neutral_name = f"Speaker {i+1}"
                speaker_mapping[f"speaker_{i}"] = neutral_name
                speaker_mapping[i] = neutral_name
                speaker_mapping[str(i)] = neutral_name
            
            # Получаем слова из ответа API
            words = response_dict.get("words", [])
            
            # Собираем слова в предложения, основываясь на паузах между словами
            sentences = []
            current_sentence = []
            current_speaker = None
            current_start = 0
            
            # Параметры для определения пауз между предложениями
            PAUSE_THRESHOLD = 0.7  # Порог паузы в секундах для разделения предложений
            MAX_SENTENCE_DURATION = 10.0  # Максимальная длительность одного предложения в секундах
            
            for i, word in enumerate(words):
                # Пропускаем пробелы
                if word.get("type") == "spacing":
                    continue
                
                # Получаем текущее слово
                word_text = word.get("text", "")
                word_start = word.get("start", 0)
                word_end = word.get("end", 0)
                word_speaker = word.get("speaker_id", "Unknown")
                
                # Определяем, является ли это начало новой реплики
                is_new_sentence = False
                
                # Если это первое слово
                if not current_sentence:
                    is_new_sentence = True
                    current_speaker = word_speaker
                else:
                    # Если сменился говорящий
                    if word_speaker != current_speaker:
                        is_new_sentence = True
                    # Если длинная пауза между словами
                    elif i > 0 and (word_start - words[i-1].get("end", 0)) > PAUSE_THRESHOLD:
                        is_new_sentence = True
                    # Если предложение слишком длинное
                    elif word_end - current_start > MAX_SENTENCE_DURATION:
                        is_new_sentence = True
                    # Если в слове есть знак конца предложения и следующее слово начинается с большой буквы
                    elif (word_text.endswith('.') or word_text.endswith('?') or word_text.endswith('!')) and i < len(words)-1:
                        next_word = words[i+1].get("text", "")
                        if next_word and next_word[0].isupper():
                            is_new_sentence = True
                
                # Если это новое предложение, сохраняем предыдущее и начинаем новое
                if is_new_sentence and current_sentence:
                    # Формируем текст из слов
                    text = " ".join([w.get("text", "") for w in current_sentence])
                    # Время начала и конца предложения
                    start_time = current_sentence[0].get("start", 0)
                    end_time = current_sentence[-1].get("end", 0)
                    # Определяем говорящего (берем наиболее частый speaker_id)
                    speaker_counts = {}
                    for w in current_sentence:
                        sp = w.get("speaker_id", "Unknown")
                        speaker_counts[sp] = speaker_counts.get(sp, 0) + 1
                    most_common_speaker = max(speaker_counts.items(), key=lambda x: x[1])[0]
                    
                    # Добавляем предложение в список
                    sentences.append({
                        "speaker_id": most_common_speaker,
                        "text": text,
                        "start_time": start_time,
                        "end_time": end_time
                    })
                    
                    # Начинаем новое предложение
                    current_sentence = [word]
                    current_speaker = word_speaker
                    current_start = word_start
                else:
                    # Продолжаем текущее предложение
                    current_sentence.append(word)
            
            # Добавляем последнее предложение
            if current_sentence:
                text = " ".join([w.get("text", "") for w in current_sentence])
                start_time = current_sentence[0].get("start", 0)
                end_time = current_sentence[-1].get("end", 0)
                speaker_counts = {}
                for w in current_sentence:
                    sp = w.get("speaker_id", "Unknown")
                    speaker_counts[sp] = speaker_counts.get(sp, 0) + 1
                most_common_speaker = max(speaker_counts.items(), key=lambda x: x[1])[0]
                
                sentences.append({
                    "speaker_id": most_common_speaker,
                    "text": text,
                    "start_time": start_time,
                    "end_time": end_time
                })
            
            # Обработка для случая одного предложения и других специальных случаев...
            # (код из оригинальной функции для обработки различных особых случаев)
            
            # Если у нас всего одно предложение для 2+ спикеров, разделим его по очереди
            if len(sentences) == 1 and num_speakers >= 2:
                logger.warning("Обнаружено только одно предложение для нескольких говорящих. Применяем эвристическое разделение.")
                text = sentences[0]["text"]
                # Разделяем по знакам препинания, затем объединяем в предполагаемые реплики
                import re
                parts = re.split(r'([.!?])\s+', text)
                new_sentences = []
                
                current_speaker_idx = 0
                current_text_parts = []
                current_start = sentences[0]["start_time"]
                total_duration = sentences[0]["end_time"] - sentences[0]["start_time"]
                part_duration = total_duration / len(parts) if len(parts) > 0 else total_duration
                
                for i, part in enumerate(parts):
                    if not part:
                        continue
                    
                    # Добавляем часть к текущему предложению
                    current_text_parts.append(part)
                    
                    # Если это знак препинания, завершаем предложение
                    if part in ['.', '!', '?'] or i == len(parts) - 1:
                        if current_text_parts:
                            combined_text = ''.join(current_text_parts).strip()
                            if combined_text:
                                part_start = current_start
                                part_end = part_start + part_duration * len(current_text_parts)
                                
                                new_sentences.append({
                                    "speaker_id": current_speaker_idx % num_speakers,
                                    "text": combined_text,
                                    "start_time": part_start,
                                    "end_time": part_end
                                })
                                
                                current_start = part_end
                                current_speaker_idx += 1
                                current_text_parts = []
                
                if new_sentences:
                    sentences = new_sentences
                    logger.info(f"Разделили аудио на {len(sentences)} предложений с помощью эвристики")
            
            # Финальная обработка предложений в диалог с нейтральными метками
            initial_dialogue = []
            for sentence in sentences:
                speaker_id = sentence["speaker_id"]
                # Используем нейтральные метки для начального анализа
                display_name = speaker_mapping.get(speaker_id, f"Speaker Unknown")
                
                initial_dialogue.append({
                    "speaker": display_name,
                    "text": sentence["text"],
                    "start_time": sentence["start_time"],
                    "end_time": sentence["end_time"],
                    "original_speaker_id": speaker_id
                })
            
            # Применяем эвристики для определения ролей (менеджер vs клиент)
            manager_speaker, client_speaker = detect_speaker_roles(initial_dialogue, manager_name, client_name)
            
            logger.info(f"Определены роли: Менеджер = {manager_speaker}, Клиент = {client_speaker}")
            
            # Создаем финальные метки для вывода
            manager_display = f"Менеджер{' (' + manager_name + ')' if manager_name else ''}"
            client_display = f"Клиент{' (' + client_name + ')' if client_name else ''}"
            
            # Переформатируем диалог с определенными ролями
            dialogue = []
            for line in initial_dialogue:
                original_speaker = line["speaker"]
                if original_speaker == manager_speaker:
                    display_name = manager_display
                elif original_speaker == client_speaker:
                    display_name = client_display
                else:
                    display_name = f"Участник ({original_speaker})"
                    
                dialogue.append({
                    "speaker": display_name,
                    "text": line["text"],
                    "start_time": line["start_time"],
                    "end_time": line["end_time"]
                })
            
            # Записываем диалог в файл
            with open(output_path, "w", encoding="utf-8") as file:
                # Добавляем заголовок с информацией о звонке
                file.write(f"Транскрипция звонка\n")
                file.write(f"Дата и время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                
                if phone:
                    file.write(f"Телефон: {phone}\n")
                
                if client_name:
                    file.write(f"Клиент: {client_name}\n")
                    
                if manager_name:
                    file.write(f"Менеджер: {manager_name}\n")
                    
                if is_first_contact:
                    file.write("Тип: Первичное обращение\n")
                    
                file.write(f"Файл: {os.path.basename(audio_path)}\n")
                
                # Добавляем информацию о длительности
                duration = response_dict.get("duration", 0)
                minutes = int(duration) // 60
                seconds = int(duration) % 60
                file.write(f"Длительность: {minutes}:{seconds:02d}\n\n")
                
                # Записываем диалог
                for line in dialogue:
                    # Форматируем время в формате [MM:SS]
                    start_min = int(line["start_time"]) // 60
                    start_sec = int(line["start_time"]) % 60
                    time_str = f"[{start_min:02d}:{start_sec:02d}]"
                    
                    file.write(f"{time_str} {line['speaker']}: {line['text']}\n\n")
                    
            process_time = time.time() - start_time
            logger.info(f"Транскрипция завершена и сохранена в {output_path} (заняло {process_time:.2f} сек.)")
            
            # Сохраняем информацию о транскрипции в базу данных, если есть данные заметки
            if note_data:
                try:
                    output_filename = os.path.basename(output_path)
                    audio_filename = os.path.basename(audio_path)  # Получаем имя аудиофайла
                    
                    await save_transcription_info(
                        filename=output_filename,
                        note_id=note_data.get("note_id"),
                        lead_id=note_data.get("lead_id"),
                        contact_id=note_data.get("contact_id"),
                        client_id=note_data.get("client_id"),
                        manager=manager_name,
                        phone=phone,
                        filename_audio=audio_filename,  # Передаем имя аудиофайла
                        administrator_id=administrator_id  # Передаем ID администратора
                    )
                except Exception as db_error:
                    logger.error(f"Ошибка при сохранении информации о транскрипции в базу данных: {db_error}")
            
        except Exception as e:
            logger.error(f"Ошибка при фоновой транскрибации: {str(e)}")
            import traceback
            logger.error(f"Стек трейс: {traceback.format_exc()}")
            
            # Записываем информацию об ошибке в файл результата
            try:
                with open(output_path, "w", encoding="utf-8") as file:
                    file.write(f"Ошибка при транскрибации файла {audio_path}:\n\n{str(e)}")
            except:
                logger.error(f"Не удалось записать информацию об ошибке в файл {output_path}")    


async def save_transcription_info(
    filename: str,
    note_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    client_id: Optional[str] = None,
    manager: Optional[str] = None,
    phone: Optional[str] = None,
    filename_audio: Optional[str] = None,
    administrator_id: Optional[str] = None
):
    """
    Сохраняет информацию о транскрипции в MongoDB для последующего поиска.
    Предотвращает создание дубликатов.
    """
    try:
        mongo_client = AsyncIOMotorClient(MONGO_URI)
        db = mongo_client[DB_NAME]
        collection = db["transcriptions"]
        
        # Проверяем, существует ли уже запись для этого файла
        existing_record = await collection.find_one({
            "filename": filename
        })
        
        if existing_record:
            # Обновляем существующую запись
            await collection.update_one(
                {"_id": existing_record["_id"]},
                {"$set": {
                    "lead_id": lead_id,
                    "contact_id": contact_id,
                    "note_id": note_id,
                    "client_id": client_id,
                    "manager": manager,
                    "phone": phone,
                    "filename_audio": filename_audio,
                    "updated_at": datetime.now().isoformat()
                }}
            )
            logger.info(f"Обновлена информация о транскрипции: {filename}")
        else:
            # Создаем новую запись
            record = {
                "lead_id": lead_id,
                "contact_id": contact_id,
                "note_id": note_id,
                "client_id": client_id,
                "manager": manager,
                "phone": phone,
                "filename": filename,
                "filename_audio": filename_audio,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            # Сохраняем в базу
            await collection.insert_one(record)
            logger.info(f"Сохранена информация о транскрипции в базу данных: {filename}")
        
        # Обновляем лимиты, если указан ID администратора
        if administrator_id and client_id:
            # Обновляем счетчики использования
            limits_service = LimitsService()
            increment_result = await limits_service.increment_usage(administrator_id)
            
            if increment_result:
                logger.info(f"Обновлены лимиты использования для администратора {administrator_id}")
            else:
                logger.warning(f"Не удалось обновить лимиты для администратора {administrator_id}")
        
        return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении информации о транскрипции в базу данных: {e}")
        return False
    
async def find_transcription_file(
    note_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    phone: Optional[str] = None
):
    """
    Ищет файл транскрипции в базе данных по указанным параметрам.
    Возвращает имя файла, если найдено.
    """
    try:
        mongo_client = AsyncIOMotorClient(MONGO_URI)
        db = mongo_client[DB_NAME]
        collection = db["transcriptions"]
        
        # Создаем фильтр
        filter_query = {}
        if note_id:
            filter_query["note_id"] = note_id
        if lead_id:
            filter_query["lead_id"] = lead_id
        if contact_id:
            filter_query["contact_id"] = contact_id
        if phone:
            filter_query["phone"] = phone
            
        # Если фильтр пустой, возвращаем None
        if not filter_query:
            logger.warning("Не указаны параметры для поиска транскрипции")
            return None
        
        # Ищем запись
        record = await collection.find_one(filter_query, sort=[("created_at", -1)])
        
        if record and "filename" in record:
            logger.info(f"Найдена запись о транскрипции: {record['filename']}")
            return record["filename"]
        else:
            logger.warning(f"Запись о транскрипции не найдена для параметров: {filter_query}")
            return None
    except Exception as e:
        logger.error(f"Ошибка при поиске записи о транскрипции: {e}")
        return None