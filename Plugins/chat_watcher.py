"""
chat_watcher.py — مراقب الدردشات (Chat Watcher)
مُستوحى من WilliamButcherBot، مُعاد كتابته لنظام ggggg (Pyrogram + Redis)

يعمل على البوت (Client) — group=10 (أولوية منخفضة)

الوظائف:
  • تسجيل كل مستخدم تفاعل مع البوت (UsersList)
  • تسجيل كل مجموعة نشطة (ChatsList)
  • مغادرة المجموعات المحظورة تلقائياً

المفاتيح في Redis:
  {DEV_ID}:UsersList  → Set  (user_ids)
  {DEV_ID}:ChatsList  → Set  (chat_ids)
  {DEV_ID}:BannedChats→ Set  (chat_ids محظورة)
"""

import logging

from pyrogram import Client, filters
from pyrogram.types import Message

from config import r, ar, DEV_ID, DEV_ID_INT

logger = logging.getLogger("chat_watcher")

from config import Client as _BotClient   # noqa

# ─── مفاتيح Redis ────────────────────────────────────────────
_USERS_KEY        = f"{DEV_ID}:UsersList"
_CHATS_KEY        = f"{DEV_ID}:ChatsList"
_BANNED_CHATS_KEY = f"{DEV_ID}:BannedChats"


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

async def _add_user(user_id: int):
    await ar.sadd(_USERS_KEY, str(user_id))

async def _add_chat(chat_id: int):
    await ar.sadd(_CHATS_KEY, str(chat_id))

async def _is_banned_chat(chat_id: int) -> bool:
    return bool(await ar.sismember(_BANNED_CHATS_KEY, str(chat_id)))

async def ban_chat(chat_id: int):
    await ar.sadd(_BANNED_CHATS_KEY, str(chat_id))

async def unban_chat(chat_id: int):
    await ar.srem(_BANNED_CHATS_KEY, str(chat_id))

async def get_banned_chats() -> list[int]:
    members = await ar.smembers(_BANNED_CHATS_KEY)
    return [int(m) for m in members]


# ─────────────────────────────────────────────────────────────
# المستمع الرئيسي (group=10)
# ─────────────────────────────────────────────────────────────

@_BotClient.on_message(group=10)
async def chat_watcher_func(client: Client, message: Message):
    """يُسجِّل كل مستخدم ومجموعة، ويغادر المجموعات المحظورة"""
    try:
        # تسجيل المستخدم
        if message.from_user:
            await _add_user(message.from_user.id)

        # تسجيل المجموعة وفحص الحظر
        chat_id = message.chat.id if message.chat else None
        if not chat_id:
            return

        if await _is_banned_chat(chat_id):
            try:
                await client.leave_chat(chat_id)
                logger.info("chat_watcher: غادر المجموعة المحظورة %s", chat_id)
            except Exception as e:
                logger.warning("chat_watcher: فشل المغادرة من %s: %s", chat_id, e)
            return

        await _add_chat(chat_id)

    except Exception as e:
        logger.debug("chat_watcher error: %s", e)
