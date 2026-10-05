class BaseSkill:
    def __init__(self, speech, config=None):
        self.speech = speech
        self.config = config or {}
    def can_handle(self, command):
        return False
    def execute(self, command):
        return False