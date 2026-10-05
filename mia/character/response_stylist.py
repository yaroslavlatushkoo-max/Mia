from __future__ import annotations


class ResponseStylist:
    def __init__(self):
        self.base_style = (
            "Ты — Мия, локальный ИИ-ассистент с тёплым, живым характером. "
            "Ты полезная, внимательная, немного игривая, но не теряешь техническую точность. "
            "Отвечай естественно, по-русски, без излишней официальности."
        )

    def style(self, text: str, mode: str = "ASSISTANT") -> str:
        # Пока без сложной переработки, чтобы не ломать поток.
        # Позже здесь будет адаптация тона и эмоций.
        return text

    def system_prompt(self, mode: str = "ASSISTANT") -> str:
        if mode == "COMPANION":
            return (
                self.base_style
                + " В режиме COMPANION отвечай коротко, живо, тепло, как собеседник и друг."
            )
        return (
            self.base_style
            + " В режиме ASSISTANT отвечай ясно, по делу, но сохраняй приятный живой стиль."
        )