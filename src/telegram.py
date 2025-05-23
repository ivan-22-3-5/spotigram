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
        self.last_set_track_bio: str | None = None
        self.is_monitoring = False

    async def connect(self, phone, password=None):
        await self.tc.start(phone=phone, password=password)
        self.default_emoji_status = await self.get_emoji_status()
        self.default_bio = await self.get_bio() or ''
        self.last_set_track_bio = None

    async def get_emoji_status(self):
        me = await self.tc.get_me()
        return me.emoji_status.document_id

    async def get_bio(self):
        me = await self.tc.get_me()
        full_me = await self.tc(GetFullUserRequest(me))
        return full_me.full_user.about

    async def display_track(self, track: Track):
        new_bio = build_listening_string(track)

        await self._update_bio(new_bio)
        self.last_set_track_bio = new_bio

        await self._update_emoji_status(settings.SPOTIFY_EMOJI_STATUS_ID)

    async def hide_track(self):
        await self._update_bio(self.default_bio)
        await self._update_emoji_status(self.default_emoji_status)

    async def _update_bio(self, new_bio: str):
        try:
            await self.tc(UpdateProfileRequest(about=new_bio))
        except RPCError:
            pass

    async def _update_emoji_status(self, new_emoji_status: int):
        try:
            await self.tc(UpdateEmojiStatusRequest(EmojiStatus(new_emoji_status)))
        except RPCError:
            pass

    async def start_monitoring(self):
        if self.is_monitoring:
            raise TelegramMonitoringException('Cannot start monitoring: monitoring is already active')
        self.is_monitoring = True
        await asyncio.gather(self._monitor_emoji_status_changes(), self._monitor_bio_changes())

    def stop_monitoring(self):
        if not self.is_monitoring:
            raise TelegramMonitoringException('Cannot stop monitoring: monitoring is not active')
        self.is_monitoring = False

    async def _monitor_bio_changes(self):
        while self.is_monitoring:
            bio = await self.get_bio()
            if await self._was_bio_updated(bio):
                self.default_bio = bio
                self.last_set_track_bio and (await self._update_bio(self.last_set_track_bio))
            await asyncio.sleep(1)

    async def _was_bio_updated(self, bio: str) -> bool:
        differs_from_default = clean_whitespaces(bio) != clean_whitespaces(self.default_bio)

        if self.last_set_track_bio is None:
            return differs_from_default

        not_set_by_app = clean_whitespaces(bio) != clean_whitespaces(self.last_set_track_bio)

        return differs_from_default and not_set_by_app

    async def _was_emoji_status_updated(self, emoji_status: int) -> bool:
        differs_from_default = emoji_status != self.default_emoji_status
        differs_from_listening_emoji = emoji_status != settings.SPOTIFY_EMOJI_STATUS_ID

        return differs_from_default and differs_from_listening_emoji

    async def _monitor_emoji_status_changes(self):
        while self.is_monitoring:
            emoji_status = await self.get_emoji_status()
            if await self._was_emoji_status_updated(emoji_status):
                self.default_emoji_status = emoji_status
                # updates to SPOTIFY_EMOJI_STATUS_ID even if the previous emoji status isn't SPOTIFY_EMOJI_STATUS_ID
                await self._update_emoji_status(settings.SPOTIFY_EMOJI_STATUS_ID)
            await asyncio.sleep(1)
