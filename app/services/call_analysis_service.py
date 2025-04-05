import os
from datetime import datetime
from ..settings.auth import get_langchain_token
from ..settings.paths import DATA_DIR, TRANSCRIPTION_DIR
from langchain.prompts import PromptTemplate

class CallAnalysisService:
    def __init__(self):
        self.llm = get_langchain_token()
        self.prompts_path = os.path.join(DATA_DIR, "prompts.txt")
        
        # Создаем директорию для результатов анализа
        self.analysis_dir = os.path.join(DATA_DIR, "analysis")
        os.makedirs(self.analysis_dir, exist_ok=True)
    
    def load_transcription(self, file_path):
        """Загружает транскрипцию звонка из файла"""
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    
    def load_prompt(self, prompt_type):
        """Загружает нужный промпт из файла prompts.txt"""
        if not os.path.exists(self.prompts_path):
            raise FileNotFoundError(f"Файл промптов не найден: {self.prompts_path}")
        
        with open(self.prompts_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        prompts = {}
        sections = content.split("[")
        for section in sections:
            if "]" in section:
                key, text = section.split("]", 1)
                prompts[key.strip()] = text.strip()
        
        return prompts.get(prompt_type, "")
    
    # def classify_call(self, dialogue):
    #     """Определяет тип звонка"""
    #     prompt_template = PromptTemplate(
    #         input_variables=["dialogue"],
    #         template=self.load_prompt("classification")
    #     )
        
    #     query = prompt_template.format(dialogue=dialogue)
    #     response = self.llm.invoke(query)
    #     try:
    #         call_type = int(response.content.strip())
    #     except ValueError:
    #         call_type = 0  # Неопределенный тип звонка
    #     return call_type

    # Исправленная версия метода classify_call в файле call_analysis_service.py

    # def classify_call(self, dialogue):
    #     """Определяет тип звонка"""
    #     prompt_template = PromptTemplate(
    #         input_variables=["dialogue"],
    #         template=self.load_prompt("classification")
    #     )
        
    #     query = prompt_template.format(dialogue=dialogue)
    #     response = self.llm.invoke(query)
        
    #     # Создаем словарь для сопоставления имен категорий с кодами
    #     categories = {
    #         "Первичное обращение": 1,
    #         "Запись на приём": 2,
    #         "Запрос информации": 3,
    #         "Проблема или жалоба": 4,
    #         "Изменение или отмена встречи": 5,
    #         "Повторная консультация": 6,
    #         "Запрос результатов анализов": 7,
    #         "Другое": 8
    #     }
        
    #     # Получаем текст ответа от LLM
    #     response_text = response.content.strip()
        
    #     # Пытаемся сначала определить категорию по тексту
    #     for category_name, category_code in categories.items():
    #         if category_name.lower() in response_text.lower():
    #             return category_code
        
    #     # Если не нашли по названию, пробуем найти число в ответе
    #     try:
    #         # Пытаемся извлечь число из ответа
    #         import re
    #         numbers = re.findall(r'\d+', response_text)
    #         if numbers:
    #             call_type = int(numbers[0])
    #             if 1 <= call_type <= 8:  # Проверяем, что число в допустимом диапазоне
    #                 return call_type
    #     except ValueError:
    #         pass
        
    #     # Если ничего не удалось определить, устанавливаем значение по умолчанию
    #     return 1  # По умолчанию "Первичное обращение" как наиболее вероятное
        
    def classify_call(self, dialogue):
        """Определяет тип звонка и возвращает текстовое название категории"""
        prompt_template = PromptTemplate(
            input_variables=["dialogue"],
            template=self.load_prompt("classification")
        )
        
        query = prompt_template.format(dialogue=dialogue)
        response = self.llm.invoke(query)
        
        # Получаем текст ответа от LLM
        response_text = response.content.strip()
        
        # Словарь для точного соответствия категорий из промпта
        category_keywords = {
            "первичное обращение": "Первичное обращение (новый клиент)",
            "запись на приём": "Запись на приём",
            "запрос информации": "Запрос информации (цены, услуги и т.д.)",
            "проблема или жалоба": "Проблема или жалоба",
            "изменение или отмена встречи": "Изменение или отмена встречи",
            "повторная консультация": "Повторная консультация", 
            "запрос результатов анализов": "Запрос результатов анализов",
            "другое": "Другое"
        }
        
        # Проверяем точное совпадение полного названия категории
        response_lower = response_text.lower()
        for keyword, full_name in category_keywords.items():
            if keyword in response_lower:
                return full_name
        
        # Если в ответе есть числа от 1 до 8, преобразуем их в названия категорий
        import re
        numbers = re.findall(r'\d+', response_text)
        if numbers:
            for num in numbers:
                try:
                    category_number = int(num)
                    if 1 <= category_number <= 8:
                        # Сопоставляем числовой код с полным названием
                        category_map = {
                            1: "Первичное обращение (новый клиент)",
                            2: "Запись на приём",
                            3: "Запрос информации (цены, услуги и т.д.)",
                            4: "Проблема или жалоба",
                            5: "Изменение или отмена встречи",
                            6: "Повторная консультация", 
                            7: "Запрос результатов анализов",
                            8: "Другое"
                        }
                        return category_map[category_number]
                except ValueError:
                    continue
        
        # Если не удалось определить категорию из ответа, анализируем диалог эвристически
        dialogue_lower = dialogue.lower()
        
        # Ищем ключевые слова, характерные для каждой категории
        if "запис" in dialogue_lower and ("на прием" in dialogue_lower or "к врачу" in dialogue_lower):
            return "Запись на приём"
        elif "первый раз" in dialogue_lower or "впервые" in dialogue_lower:
            return "Первичное обращение (новый клиент)"
        elif "сколько стоит" in dialogue_lower or "цена" in dialogue_lower or "цены" in dialogue_lower:
            return "Запрос информации (цены, услуги и т.д.)"
        elif "проблем" in dialogue_lower or "жалоб" in dialogue_lower or "болит" in dialogue_lower:
            return "Проблема или жалоба"
        elif "перенести" in dialogue_lower or "отмен" in dialogue_lower:
            return "Изменение или отмена встречи"
        elif "повторн" in dialogue_lower or "контрольный" in dialogue_lower:
            return "Повторная консультация"
        elif "результат" in dialogue_lower or "анализ" in dialogue_lower:
            return "Запрос результатов анализов"
        
        # Если все методы не дали результат, возвращаем наиболее вероятное
        # По контексту - в стоматологиях это обычно "Запись на приём"
        return "Запись на приём"

    # def classify_call(self, dialogue):
    #     """Определяет тип звонка и возвращает текстовое название категории"""
    #     prompt_template = PromptTemplate(
    #         input_variables=["dialogue"],
    #         template=self.load_prompt("classification")
    #     )
        
    #     query = prompt_template.format(dialogue=dialogue)
    #     response = self.llm.invoke(query)
        
    #     # Получаем текст ответа от LLM
    #     response_text = response.content.strip()
        
    #     # Словарь для сопоставления текстовых названий категорий с их полными названиями
    #     category_map = {
    #         "первичное обращение": "Первичное обращение (новый клиент)",
    #         "запись на приём": "Запись на приём",
    #         "запрос информации": "Запрос информации (цены, услуги и т.д.)",
    #         "проблема или жалоба": "Проблема или жалоба",
    #         "изменение или отмена": "Изменение или отмена встречи",
    #         "повторная консультация": "Повторная консультация", 
    #         "запрос результатов": "Запрос результатов анализов",
    #         "другое": "Другое"
    #     }
        
    #     # Пытаемся определить категорию по тексту ответа
    #     for key, full_name in category_map.items():
    #         if key.lower() in response_text.lower():
    #             return full_name
        
    #     # Если не нашли по тексту, пытаемся найти числовой код в ответе
    #     try:
    #         import re
    #         numbers = re.findall(r'\d+', response_text)
    #         if numbers:
    #             call_type = int(numbers[0])
    #             if 1 <= call_type <= 8:
    #                 # Сопоставляем числовой код с полным названием
    #                 code_to_name = {
    #                     1: "Первичное обращение (новый клиент)",
    #                     2: "Запись на приём",
    #                     3: "Запрос информации (цены, услуги и т.д.)",
    #                     4: "Проблема или жалоба",
    #                     5: "Изменение или отмена встречи",
    #                     6: "Повторная консультация", 
    #                     7: "Запрос результатов анализов",
    #                     8: "Другое"
    #                 }
    #                 return code_to_name.get(call_type, "Неопределенный тип звонка")
    #     except ValueError:
    #         pass
        
    #     # Если не удалось определить категорию, возвращаем первичное обращение как наиболее вероятное
    #     return "Первичное обращение (новый клиент)"

    def analyze_call(self, dialogue):
        """Анализирует звонок (тональность + оценка оператора)"""
        prompt_template = PromptTemplate(
            input_variables=["dialogue"],
            template=self.load_prompt("analysis")
        )
        
        query = prompt_template.format(dialogue=dialogue)
        response = self.llm.invoke(query)
        return response.content.strip()
    
    # def full_call_analysis(self, dialogue, meta_info=None):
    #     """Полный анализ звонка: классификация + анализ"""
    #     call_class = self.classify_call(dialogue)
    #     call_analysis = self.analyze_call(dialogue)
        
    #     result = {
    #         "classification": call_class,
    #         "analysis": call_analysis,
    #         "meta_info": meta_info or {},
    #         "timestamp": datetime.now().isoformat()
    #     }
        
    #     return result

    # def full_call_analysis(self, dialogue, meta_info=None):
    #     """Полный анализ звонка: классификация + анализ"""
    #     # Словарь для сопоставления числового кода категории с названием
    #     category_names = {
    #         1: "Первичное обращение (новый клиент)",
    #         2: "Запись на приём",
    #         3: "Запрос информации (цены, услуги и т.д.)",
    #         4: "Проблема или жалоба",
    #         5: "Изменение или отмена встречи",
    #         6: "Повторная консультация", 
    #         7: "Запрос результатов анализов",
    #         8: "Другое",
    #         0: "Неопределенный тип звонка"
    #     }
        
    #     # Получаем числовой код категории
    #     call_class = self.classify_call(dialogue)
        
    #     # Получаем название категории
    #     call_class_name = category_names.get(call_class, "Неопределенный тип звонка")
        
    #     # Анализируем звонок
    #     call_analysis = self.analyze_call(dialogue)
        
    #     result = {
    #         "classification": call_class,  # Сохраняем числовой код для совместимости
    #         "classification_name": call_class_name,  # Добавляем название категории
    #         "analysis": call_analysis,
    #         "meta_info": meta_info or {},
    #         "timestamp": datetime.now().isoformat()
    #     }
        
    #     return result

    def full_call_analysis(self, dialogue, meta_info=None):
        """Полный анализ звонка: классификация + анализ"""
        # Получаем классификацию звонка (теперь это может быть строка)
        call_class = self.classify_call(dialogue)
        
        # Получаем текст анализа
        call_analysis = self.analyze_call(dialogue)
        
        result = {
            "classification": call_class,  # Сохраняем полученное значение (строку или число)
            "analysis": call_analysis,
            "meta_info": meta_info or {},
            "timestamp": datetime.now().isoformat()
        }
        
        return result
    
    # def save_analysis(self, analysis_result, filename=None):
    #     """Сохраняет результат анализа в текстовый файл"""
    #     if not filename:
    #         timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    #         filename = f"analysis_{timestamp}.txt"
        
    #     file_path = os.path.join(self.analysis_dir, filename)
        
    #     with open(file_path, "w", encoding="utf-8") as f:
    #         f.write(f"Дата и время анализа: {analysis_result['timestamp']}\n\n")
            
    #         # Добавляем метаданные
    #         if analysis_result.get('meta_info'):
    #             f.write("МЕТАДАННЫЕ:\n")
    #             for key, value in analysis_result['meta_info'].items():
    #                 f.write(f"{key}: {value}\n")
    #             f.write("\n")
            
    #         # Добавляем классификацию
    #         f.write(f"КЛАССИФИКАЦИЯ ЗВОНКА: {analysis_result['classification']}\n\n")
            
    #         # Добавляем анализ
    #         f.write("АНАЛИЗ ЗВОНКА:\n")
    #         f.write(analysis_result['analysis'])
        
    #     return file_path

    # def save_analysis(self, analysis_result, filename=None):
    #     """Сохраняет результат анализа в текстовый файл с названием категории вместо числа"""
    #     if not filename:
    #         timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    #         filename = f"analysis_{timestamp}.txt"
        
    #     file_path = os.path.join(self.analysis_dir, filename)
        
    #     # Словарь для сопоставления числового кода категории с названием
    #     category_names = {
    #         1: "Первичное обращение (новый клиент)",
    #         2: "Запись на приём",
    #         3: "Запрос информации (цены, услуги и т.д.)",
    #         4: "Проблема или жалоба",
    #         5: "Изменение или отмена встречи",
    #         6: "Повторная консультация", 
    #         7: "Запрос результатов анализов",
    #         8: "Другое",
    #         0: "Неопределенный тип звонка"
    #     }
        
    #     # Получаем код категории
    #     category_code = analysis_result['classification']
        
    #     # Получаем название категории по коду
    #     category_name = category_names.get(category_code, "Неопределенный тип звонка")
        
    #     with open(file_path, "w", encoding="utf-8") as f:
    #         f.write(f"Дата и время анализа: {analysis_result['timestamp']}\n\n")
            
    #         # Добавляем метаданные
    #         if analysis_result.get('meta_info'):
    #             f.write("МЕТАДАННЫЕ:\n")
    #             for key, value in analysis_result['meta_info'].items():
    #                 f.write(f"{key}: {value}\n")
    #             f.write("\n")
            
    #         # Добавляем классификацию с названием категории
    #         f.write(f"КЛАССИФИКАЦИЯ ЗВОНКА: {category_name}\n\n")
            
    #         # Добавляем анализ
    #         f.write("АНАЛИЗ ЗВОНКА:\n")
    #         f.write(analysis_result['analysis'])
        
    #     return file_path


    def save_analysis(self, analysis_result, filename=None):
        """Сохраняет результат анализа в текстовый файл"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"analysis_{timestamp}.txt"
        
        file_path = os.path.join(self.analysis_dir, filename)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"Дата и время анализа: {analysis_result['timestamp']}\n\n")
            
            # Добавляем метаданные
            if analysis_result.get('meta_info'):
                f.write("МЕТАДАННЫЕ:\n")
                for key, value in analysis_result['meta_info'].items():
                    f.write(f"{key}: {value}\n")
                f.write("\n")
            
            # Добавляем классификацию звонка
            # Проверяем, есть ли в результате текстовое название категории
            if 'classification_name' in analysis_result:
                call_type = analysis_result['classification_name']
            elif isinstance(analysis_result['classification'], str):
                # Если classification уже строка, используем её напрямую
                call_type = analysis_result['classification']
            else:
                # Для обратной совместимости: если classification - число
                category_names = {
                    1: "Первичное обращение (новый клиент)",
                    2: "Запись на приём",
                    3: "Запрос информации (цены, услуги и т.д.)",
                    4: "Проблема или жалоба",
                    5: "Изменение или отмена встречи",
                    6: "Повторная консультация", 
                    7: "Запрос результатов анализов",
                    8: "Другое",
                    0: "Неопределенный тип звонка"
                }
                call_type = category_names.get(analysis_result['classification'], "Неопределенный тип звонка")
            
            f.write(f"КЛАССИФИКАЦИЯ ЗВОНКА: {call_type}\n\n")
            
            # Добавляем анализ
            f.write("АНАЛИЗ ЗВОНКА:\n")
            f.write(analysis_result['analysis'])
        
        return file_path

# Создаем экземпляр для использования в API
call_analysis_service = CallAnalysisService()