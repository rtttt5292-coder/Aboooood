"""
فلتر الكلمات السيئة
أوامر:
  اضف كلمة [كلمة]        → إضافة كلمة محظورة
  حذف كلمة [كلمة]        → حذف كلمة من القائمة
  الكلمات المحظورة        → عرض القائمة
  تفعيل فلتر الكلمات      → تشغيل الفلتر
  تعطيل فلتر الكلمات      → إيقاف الفلتر
"""
import re
from pyrogram import Client, filters
from pyrogram.types import Message

from config import r, DEV_ID, botkey, cached_smembers, ar
from helpers.ranks import is_mod, is_pre
from helpers.utils import group_enabled, resolve_text


@Client.on_message(filters.text & filters.group, group=17)
async def word_filter_commands(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text, cid)
    k    = botkey()

    add_m = re.fullmatch(r"اضف كلمة\s+(.+)", text)
    if add_m:
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـديـر وفـوق فـقـط")
        word = add_m.group(1).strip().lower()
        await ar.sadd(f"{cid}:badwords:{DEV_ID}", word)
        return await m.reply(f"╔══ {k} ══╗\n┃ تـم حـظـر الـكـلـمـة: `{word}` 🚫\n╚══════════╝")

    del_m = re.fullmatch(r"حذف كلمة\s+(.+)", text)
    if del_m:
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـديـر وفـوق فـقـط")
        word = del_m.group(1).strip().lower()
        await ar.srem(f"{cid}:badwords:{DEV_ID}", word)
        return await m.reply(f"╔══ {k} ══╗\n┃ تـم رفـع حـظـر الـكـلـمـة: `{word}` ✅\n╚══════════╝")

    if text == "الكلمات المحظورة":
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـديـر وفـوق فـقـط")
        words = cached_smembers(f"{cid}:badwords:{DEV_ID}")
        if not words:
            return await m.reply(f"✨ {k} لا تـوجـد كـلـمـات مـحـظـورة")
        return await m.reply(
            f"{k} الكلمات المحظورة:\n" +
            "\n".join(f"• `{w}`" for w in sorted(words))
        )

    if text in ("تفعيل فلتر الكلمات",):
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـديـر وفـوق فـقـط")
        await ar.set(f"{cid}:wordfilter:{DEV_ID}", 1)
        return await m.reply(f"╔══ {k} ══╗\n┃ تـم تـفـعـيـل فـلـتـر الـكـلـمـات ✅\n╚══════════╝")

    if text in ("تعطيل فلتر الكلمات",):
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـديـر وفـوق فـقـط")
        await ar.delete(f"{cid}:wordfilter:{DEV_ID}")
        return await m.reply(f"╔══ {k} ══╗\n┃ تـم تـعـطـيـل فـلـتـر الـكـلـمـات ❌\n╚══════════╝")


@Client.on_message(filters.text & filters.group, group=16)
async def apply_word_filter(c: Client, m: Message):
    """يحذف الرسائل التي تحتوي كلمات محظورة"""
    if not m.from_user or not m.text:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    if not await ar.get(f"{cid}:wordfilter:{DEV_ID}"):
        return
    # الإداريون والمميزون محصّنون
    if is_pre(uid, cid):
        return

    words = cached_smembers(f"{cid}:badwords:{DEV_ID}")
    if not words:
        return

    msg_lower = m.text.lower()
    for w in words:
        if w in msg_lower:
            k = botkey()
            mention = m.from_user.mention
            cid = m.chat.id
            deleted = False
            try:
                await m.delete()
                deleted = True
            except Exception:
                pass
            # لا ترسل تحذيراً إذا فشل الحذف (البوت بدون صلاحية)
            if deleted:
                try:
                    await c.send_message(cid, f"{k} {mention}، رسالتك تحتوي كلمة محظورة 🚫")
                except Exception:
                    pass
            return
