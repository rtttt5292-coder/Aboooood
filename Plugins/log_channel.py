"""
قناة السجلات (Log Channel)
────────────────────────────
الأوامر:
  قناة السجل [@channel أو id]    → ربط قناة السجلات
  الغاء قناة السجل                → إلغاء الربط
  قناة السجل                      → عرض القناة الحالية
────────────────────────────
ما يُسجَّل:
  - الحظر / الطرد / الكتم
  - رفع وخفض الرتب
  - التحذيرات
  - تغييرات الإعدادات (الأقفال، الضد الفيض...)

استخدم log_event() في أي Plugin آخر لتسجيل حدث
"""

import re
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import Message

from config import ar, DEV_ID, botkey
from helpers.ranks import is_mod
from helpers.utils import group_enabled, resolve_text

# ── مفاتيح Redis ──
def _log_channel_key(cid: int) -> str:
    return f"{cid}:log_channel:{DEV_ID}"

# ── في الذاكرة: كاش سريع للـ log channels ──
_log_cache: dict[int, int | None] = {}


async def get_log_channel(cid: int) -> int | None:
    """يُرجع معرّف قناة السجلات للمجموعة — None إذا لم تُعيَّن"""
    if cid in _log_cache:
        return _log_cache[cid]
    val = await ar.get(_log_channel_key(cid))
    result = int(val) if val else None
    _log_cache[cid] = result
    return result


async def log_event(c: Client, cid: int, text: str):
    """
    يُرسل حدثاً إلى قناة السجلات — آمن تماماً (لا يرفع استثناء).

    مثال الاستخدام في plugin آخر:
        from Plugins.log_channel import log_event
        await log_event(c, m.chat.id, f"⚠️ تحذير: {mention}")
    """
    log_ch = await get_log_channel(cid)
    if not log_ch:
        return
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await c.send_message(log_ch, f"[{now}]\n{text}")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────
# أوامر الإعداد
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.text & filters.group, group=22)
async def log_channel_commands(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text, cid)
    k = botkey()

    # ── قناة السجل [قناة] ──
    set_match = re.fullmatch(r"قناة السجل\s+(@?\S+)", text)
    if set_match:
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        channel = set_match.group(1)
        try:
            ch = await c.get_chat(channel)
            ch_id = ch.id
            ch_name = ch.title
        except Exception:
            return await m.reply(f"‼️ {k} لم أجد القناة، تأكد من أن البوت مشرف فيها")
        await ar.set(_log_channel_key(cid), ch_id)
        _log_cache[cid] = ch_id
        await log_event(
            c, cid,
            f"✅ تم ربط قناة السجلات بـ: {m.chat.title} (`{cid}`)"
        )
        return await m.reply(
            f"╔══ {k} ══╗\n"
            f"┃ ✅ تم ربط قناة السجلات\n"
            f"┃ القناة: {ch_name}\n"
            f"╚══════════╝"
        )

    # ── الغاء قناة السجل ──
    if text in ("الغاء قناة السجل", "حذف قناة السجل"):
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        await ar.delete(_log_channel_key(cid))
        _log_cache.pop(cid, None)
        return await m.reply(
            f"╔══ {k} ══╗\n┃ ❌ تم إلغاء ربط قناة السجلات\n╚══════════╝"
        )

    # ── قناة السجل (بدون معامل = عرض) ──
    if text == "قناة السجل":
        ch_id = await get_log_channel(cid)
        if not ch_id:
            return await m.reply(f"✨ {k} لم تُحدَّد قناة سجلات لهذه المجموعة")
        try:
            ch = await c.get_chat(ch_id)
            ch_text = f"{ch.title} (`{ch_id}`)"
        except Exception:
            ch_text = f"`{ch_id}`"
        return await m.reply(
            f"╔══ {k} ══╗\n┃ 📋 قناة السجلات: {ch_text}\n╚══════════╝"
        )
