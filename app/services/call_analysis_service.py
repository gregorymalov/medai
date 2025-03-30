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
    
    def classify_call(self, dialogue):
        """Определяет тип звонка"""
        prompt_template = PromptTemplate(
            input_variables=["dialogue"],
            template=self.load_prompt("classification")
        )
        
        query = prompt_template.format(dialogue=dialogue)
        response = self.llm.invoke(query)
        try:
            call_type = int(response.content.strip())
        except ValueError:
            call_type = 0  # Неопределенный тип звонка
        return call_type
    
    def analyze_call(self, dialogue):
        """Анализирует звонок (тональность + оценка оператора)"""
        prompt_template = PromptTemplate(
            input_variables=["dialogue"],
            template=self.load_prompt("analysis")
        )
        
        query = prompt_template.format(dialogue=dialogue)
        response = self.llm.invoke(query)
        return response.content.strip()
    
    def full_call_analysis(self, dialogue, meta_info=None):
        """Полный анализ звонка: классификация + анализ"""
        call_class = self.classify_call(dialogue)
        call_analysis = self.analyze_call(dialogue)
        
        result = {
            "classification": call_class,
            "analysis": call_analysis,
            "meta_info": meta_info or {},
            "timestamp": datetime.now().isoformat()
        }
        
        return result
    
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
            
            # Добавляем классификацию
            f.write(f"КЛАССИФИКАЦИЯ ЗВОНКА: {analysis_result['classification']}\n\n")
            
            # Добавляем анализ
            f.write("АНАЛИЗ ЗВОНКА:\n")
            f.write(analysis_result['analysis'])
        
        return file_path

# Создаем экземпляр для использования в API
call_analysis_service = CallAnalysisService()