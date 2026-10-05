# -*- coding: utf-8 -*-
import os
import random
import yaml

class SkillLoader:
    def __init__(self):
        self.skills = []
        self.skills_dir = os.path.join(os.path.dirname(__file__), "..", "skills_md")
        self.load_all()
    
    def load_all(self):
        """Загрузить все .md навыки"""
        if not os.path.exists(self.skills_dir):
            return
        
        for filename in os.listdir(self.skills_dir):
            if filename.endswith(".md"):
                skill = self.parse_skill(os.path.join(self.skills_dir, filename))
                if skill:
                    self.skills.append(skill)
                    print(f"Загружен навык: {skill['name']}")
    
    def parse_skill(self, filepath):
        """Разобрать MD-файл навыка"""
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Разделить frontmatter и тело
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = yaml.safe_load(parts[1])
                body = parts[2].strip()
                frontmatter["body"] = body
                return frontmatter
        
        return None
    
    def find_skill(self, command):
        """Найти навык по триггерам"""
        cmd = command.lower()
        for skill in self.skills:
            for trigger in skill.get("triggers", []):
                if trigger in cmd:
                    return skill
        return None