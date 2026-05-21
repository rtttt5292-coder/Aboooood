"""
نظام الملاحظات (Notes)
───────────────────────
الأوامر:
  اضف ملاحظة [اسم]     → حفظ ملاحظة (رد على رسالة أو نص بعد الاسم)
  حذف ملاحظة [اسم]     → حذف ملاحظة
  الملاحظات            → عرض قائمة الملاحظات
  #[اسم]               → استدعاء ملاحظة مباشرة
───────────────────────
يستخدم Redis لتخزين الملاحظات
"""

import re

from pyrogram import Client, filters
from pyrogram.types import Message

from config import r, ar, DEV_ID, botkey, cached_smembers
from helpers.ranks import is_mod, is_pre
from helpers.utils import group_enabled, resolve_text


# ── مفاتيح Redis ──
def _note_key(cid: int, name: str) -> str:
    return f"{cid}:note:{name.lower()}:{DEV_ID}"

def _notes_list_key(cid: int) -> str:
    return f"{cid}:noteslist:{DEV_ID}"


# ─────────────────────────────────────────────────────────────────────────
# أوامر الملاحظات
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.text & filters.group, group=40)
async def notes_commands(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text, cid)
    k = botkey()

    # ── اضف ملاحظة [اسم] ──
    add_m = re.fullmatch(r"اضف ملاحظة\s+(\S+)(?:\s+(.+))?", text, re.DOTALL)
    if add_m:
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        name = add_m.group(1).strip().lower()
        content = None

        if m.reply_to_message:
            rep = m.reply_to_message
            if rep.text:
                content = rep.text
            elif rep.caption:
                content = rep.caption
            elif rep.sticker:
                content = f"__sticker__{rep.sticker.file_id}"
            elif rep.photo:
                content = f"__photo__{rep.photo.file_id}"
            elif rep.video:
                content = f"__video__{rep.video.file_id}"
            elif rep.document:
                content = f"__doc__{rep.document.file_id}"
            elif rep.voice:
                content = f"__voice__{rep.voice.file_id}"
            elif rep.animation:
                content = f"__gif__{rep.animation.file_id}"
        elif add_m.group(2):
            content = add_m.group(2).strip()

        if not content:
            return await m.reply(
                f"╔══ {k} ══╗\n"
                f"┃ استخدم: اضف ملاحظة [اسم] [نص]\n"
                f"┃ أو اردد على رسالة مع الأمر\n"
                f"╚══════════╝"
            )

        await ar.set(_note_key(cid, name), content)
        await ar.sadd(_notes_list_key(cid), name)
        return await m.reply(
            f"╔══ {k} ══╗\n"
            f"┃ تم حفظ الملاحظة: `#{name}` ✅\n"
            f"╚══════════╝"
        )

    # ── حذف ملاحظة [اسم] ──
    del_m = re.fullmatch(r"حذف ملاحظة\s+(\S+)", text)
    if del_m:
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        name = del_m.group(1).strip().lower()
        deleted = await ar.delete(_note_key(cid, name))
        await ar.srem(_notes_list_key(cid), name)
        if deleted:
            return await m.reply(
                f"╔══ {k} ══╗\n┃ تم حذف الملاحظة: `#{name}` 🗑️\n╚══════════╝"
            )
        return await m.reply(f"‼️ {k} لا توجد ملاحظة بهذا الاسم")

    # ── الملاحظات (قائمة) ──
    if text == "الملاحظات":
        names = cached_smembers(_notes_list_key(cid))
        if not names:
            return await m.reply(f"✨ {k} لا توجد ملاحظات محفوظة")
        lines = [f"{k} الملاحظات المحفوظة:"]
        for n in sorted(names):
            lines.append(f"• `#{n}`")
        return await m.reply("\n".join(lines))


# ── استدعاء الملاحظة بـ #اسم ──
@Client.on_message(filters.text & filters.group, group=41)
async def fetch_note(c: Client, m: Message):
    if not m.from_user or not m.text:
        return
    cid = m.chat.id
    if not group_enabled(cid):
        return

    text = m.text.strip()
    if not text.startswith("#"):
        return

    name = text[1:].strip().lower()
    if not name:
        return

    content = await ar.get(_note_key(cid, name))
    if not content:
        return

    k = botkey()

    try:
        # ملاحظات وسائط
        if content.startswith("__sticker__"):
            await c.send_sticker(cid, content[len("__sticker__"):])
        elif content.startswith("__photo__"):
            await c.send_photo(cid, content[len("__photo__"):], caption=f"{k} #{name}")
        elif content.startswith("__video__"):
            await c.send_video(cid, content[len("__video__"):], caption=f"{k} #{name}")
        elif content.startswith("__doc__"):
            await c.send_document(cid, content[len("__doc__"):], caption=f"{k} #{name}")
        elif content.startswith("__voice__"):
            await c.send_voice(cid, content[len("__voice__"):])
        elif content.startswith("__gif__"):
            await c.send_animation(cid, content[len("__gif__"):])
        else:
            await m.reply(
                f"╔══ {k} ══╗\n"
                f"┃ 📝 #{name}\n"
                f"┃ ─────────\n"
                f"┃ {content}\n"
                f"╚══════════╝"
            )
    except Exception:
        pass
