import asyncio
import os

from telethon import TelegramClient
from telethon.tl.functions.account import UpdateProfileRequest, UpdateEmojiStatusRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.types import EmojiStatus
from telethon.errors import RPCError

from config import settings
from track import Track
from utils import build_listening_string, clean_whitespaces


class TelegramMonitoringException(Exception):
    pass


class TelegramClientManager:
    def __init__(self):
        os.makedirs(settings.SESSIONS_PATH, exist_ok=True)
        self.tc = TelegramClient(settings.SESSIONS_PATH + 'tg_session',
                                 settings.TELEGRAM_API_ID,
                                 settings.TELEGRAM_API_HASH)
        self.default_bio: str = ''
        self.default_emoji_status: int = 0
        self.current_bio: str = ''
        self.current_emoji_status: int = 0
        self.is_monitoring = False

    async def connect(self):
        await self.tc.start()
        self.default_emoji_status = await self.get_emoji_status()
        self.default_bio = await self.get_bio() or ''
        self.current_emoji_status = self.default_emoji_status
        self.current_bio = self.default_bio

    async def get_emoji_status(self):
        me = await self.tc.get_me()
        return me.emoji_status.document_id

    async def get_bio(self):
        me = await self.tc.get_me()
        full_me = await self.tc(GetFullUserRequest(me))
        return full_me.full_user.about

    async def display_track(self, track: Track):
        self.current_emoji_status = settings.SPOTIFY_EMOJI_STATUS_ID
        self.current_bio = build_listening_string(track)
        await self.update_bio()
        await self.update_emoji_status()

    async def hide_track(self):
        self.current_emoji_status = self.default_emoji_status
        self.current_bio = self.default_bio
        await self.update_bio()
        await self.update_emoji_status()

    async def update_bio(self):
        try:
            await self.tc(UpdateProfileRequest(about=self.current_bio))
        except RPCError:
            pass

    async def update_emoji_status(self):
        try:
            await self.tc(UpdateEmojiStatusRequest(EmojiStatus(self.current_emoji_status)))
        except RPCError:
            pass

    async def start_monitoring(self):
        if self.is_monitoring:
            raise TelegramMonitoringException('Cannot start monitoring: monitoring is already active')
        self.is_monitoring = True
        await self._monitor_bio_changes()

    def stop_monitoring(self):
        if not self.is_monitoring:
            raise TelegramMonitoringException('Cannot stop monitoring: monitoring is not active')
        self.is_monitoring = False

    async def _monitor_bio_changes(self):
        while self.is_monitoring:
            bio = clean_whitespaces(await self.get_bio())
            if bio != clean_whitespaces(self.default_bio) and bio != clean_whitespaces(self.current_bio):
                self.default_bio = bio
            emoji_status = await self.get_emoji_status()
            if emoji_status != self.default_emoji_status and emoji_status != self.current_emoji_status:
                self.default_emoji_status = emoji_status
            await asyncio.sleep(1)
