# -*- coding: utf-8 -*-
import chromadb
import os
import json
import time
import re
from datetime import datetime

class MemorySkill:
    def __init__(self, speech):
        self.speech = speech
        self.db_path = os.path.join(os.path.dirname(__file__), "..", "data", "memory_db")
        os.makedirs(self.db_path, exist_ok=True)
        
        self.client = chromadb.PersistentClient(path=self.db_path)
        self.facts = self.client.get_or_create_collection("facts")
        self.preferences = self.client.get_or_create_collection("prefs")
        self.events = self.client.get_or_create_collection("events")
    
    def _fix_pronouns(self, text):
        """Заменяет местоимения с 'я/мне' на 'ты/тебе' только целые слова"""
        text = re.sub(r'\bя\b', 'ты', text)
        text = re.sub(r'\bмне\b', 'тебе', text)
        text = re.sub(r'\bменя\b', 'тебя', text)
        text = re.sub(r'\bмой\b', 'твой', text)
        text = re.sub(r'\bмоя\b', 'твоя', text)
        text = re.sub(r'\bмоё\b', 'твоё', text)
        return text
    
    def remember(self, category, content, metadata=None):
        """Запомнить информацию"""
        try:
            collection = self.get_collection(category)
            doc_id = f"mem_{int(time.time())}_{hash(content) % 10000}"
            
            collection.add(
                documents=[content],
                ids=[doc_id],
                metadatas=[metadata or {"date": datetime.now().strftime("%Y-%m-%d %H:%M")}]
            )
            
            print(f"Запомнено: {content[:50]}...")
            return True
        except Exception as e:
            print(f"Memory error: {e}")
            return False
    
    def recall(self, query, category=None, n_results=3):
        """Вспомнить информацию"""
        try:
            results = []
            
            if category:
                collections = [self.get_collection(category)]
            else:
                collections = [self.facts, self.preferences, self.events]
            
            for collection in collections:
                try:
                    result = collection.query(
                        query_texts=[query],
                        n_results=n_results
                    )
                    if result and result['documents'] and result['documents'][0]:
                        results.extend(result['documents'][0])
                except:
                    pass
            
            return results[:n_results]
        except Exception as e:
            print(f"Recall error: {e}")
            return []
    
    def get_collection(self, category):
        """Получить коллекцию по имени"""
        if category == "facts":
            return self.facts
        elif category == "prefs":
            return self.preferences
        elif category == "events":
            return self.events
        else:
            return self.facts
    
    def list_all_memories(self, category=None):
        """Показать все воспоминания"""
        try:
            all_memories = []
            
            collections = [self.get_collection(category)] if category else [self.facts, self.preferences, self.events]
            
            for collection in collections:
                try:
                    result = collection.get()
                    if result and result['documents']:
                        for doc, meta in zip(result['documents'], result['metadatas']):
                            all_memories.append(f"{doc} (дата: {meta.get('date', 'неизвестно')})")
                except:
                    pass
            
            return all_memories
        except Exception as e:
            print(f"List error: {e}")
            return []
    
    def forget(self, query, category=None):
        """Забыть информацию"""
        try:
            collections = [self.get_collection(category)] if category else [self.facts, self.preferences, self.events]
            
            for collection in collections:
                try:
                    result = collection.query(query_texts=[query], n_results=1)
                    if result and result['ids'] and result['ids'][0]:
                        collection.delete(ids=result['ids'][0])
                        return True
                except:
                    pass
            
            return False
        except Exception as e:
            print(f"Forget error: {e}")
            return False
    
    def can_handle(self, command):
        keywords = [
            "запомни", "напомни", "что ты помнишь", "что ты знаешь",
            "вспомни", "забудь", "моя память", "твоя память",
            "когда у меня", "какой у меня", "что я люблю", "что мне нравится",
        ]
        return any(kw in command for kw in keywords)
    
    def execute(self, command):
        cmd = command.lower()
        
        # Запомнить
        if "запомни" in cmd or "сохрани в память" in cmd:
            content = cmd
            for phrase in ["запомни что ", "запомни ", "сохрани в память ", "запомни, ", "запомни: "]:
                content = content.replace(phrase, "")
            content = content.strip()
            if content:
                category = "facts"
                if "люблю" in content or "нравится" in content or "предпочитаю" in content:
                    category = "prefs"
                elif "день рождения" in content or "встреча" in content or "событие" in content:
                    category = "events"
                
                self.remember(category, content)
                self.speech.speak(f"Запомнила!")
                return True
        
        # Вспомнить
        if "вспомни" in cmd or "что ты помнишь" in cmd or "что ты знаешь обо мне" in cmd:
            query = cmd.replace("вспомни", "").replace("что ты помнишь", "").replace("что ты знаешь обо мне", "").strip()
            if not query:
                query = "пользователь"
            
            memories = self.recall(query)
            if memories:
                memory_text = self._fix_pronouns(memories[0][:200])
                self.speech.speak(f"Я помню: {memory_text}")
                if len(memories) > 1:
                    memory_text2 = self._fix_pronouns(memories[1][:200])
                    self.speech.speak(f"Ещё: {memory_text2}")
            else:
                self.speech.speak("Я пока ничего не помню об этом")
            return True
        
        # Показать все воспоминания
        if "покажи память" in cmd or "вся память" in cmd:
            memories = self.list_all_memories()
            if memories:
                self.speech.speak(f"У меня {len(memories)} воспоминаний")
                for mem in memories[:5]:
                    self.speech.speak(mem[:150])
            else:
                self.speech.speak("Память пуста")
            return True
        
        # Забыть
        if "забудь" in cmd:
            query = cmd.replace("забудь", "").strip()
            if query:
                self.forget(query)
                self.speech.speak(f"Забыла информацию о: {query}")
                return True
        
        # Вопросы о пользователе (поиск в памяти)
        if any(w in cmd for w in ["когда у меня", "какой у меня", "что я люблю", "что мне нравится"]):
            query = cmd
            memories = self.recall(query)
            if memories:
                memory_text = self._fix_pronouns(memories[0][:200])
                self.speech.speak(f"Я помню: {memory_text}")
            else:
                self.speech.speak("Я пока не знаю этого. Скажите 'запомни' и я сохраню информацию.")
            return True
        
        return False