import asyncio
from aiogram import types
from typing import List

class ProgressAnimation:
    def __init__(self, message: types.Message, base_text: str, emojis: List[str] = None):
        self.message = message
        self.base_text = base_text
        self.emojis = emojis or ["🔍", "⚙️", "⏳", "📡"]
        self.is_running = False
        self._task = None

    async def _animate(self):
        idx = 0
        while self.is_running:
            try:
                emoji = self.emojis[idx % len(self.emojis)]
                await self.message.edit_text(f"{emoji} **{self.base_text}**")
                idx += 1
                await asyncio.sleep(1.5) # Telegram rate limits updates
            except Exception:
                break

    def start(self):
        self.is_running = True
        self._task = asyncio.create_task(self._animate())

    async def stop(self, final_text: str = None):
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        if final_text:
            try:
                await self.message.edit_text(final_text)
            except Exception:
                pass

progress_animation = ProgressAnimation
