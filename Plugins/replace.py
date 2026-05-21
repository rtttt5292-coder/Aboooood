"""
استبدال كلمة في ملفات السورس
أوامر:
  استبدال كلمه / استبدال كلمة → يبدأ عملية الاستبدال (يحتاج botowner)
  الغاء → إلغاء العملية الجارية
"""

import os, sys
from pyrogram import Client, filters
from pyrogram.types import Message

from config import r, DEV_ID, botkey, ar
from helpers.ranks import is_botowner, isLockCommand
from helpers.utils import group_enabled, can_speak, resolve_text


@Client.on_message(filters.text & filters.group, group=36)
async def replace_handler(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    if not can_speak(uid, cid):
        return

    text = resolve_text(m.text, cid)
    k    = botkey()
    ch   = await ar.get(f"{DEV_ID}:BotChannel") or "yqyqy66"

    # مفاتيح الجلسة
    step1 = f"{cid}:replace1:{uid}:{DEV_ID}"
    step2 = f"{cid}:replace2:{uid}:{DEV_ID}"
    step3 = f"{cid}:replace3:{uid}:{DEV_ID}"

    # إلغاء العملية
    if text == "الغاء" and (await ar.get(step1) or await ar.get(step2) or await ar.get(step3)):
        await ar.delete(step1, step2, step3)
        return await m.reply(f"{k} من عيوني لغيت استبدال كلمة")

    # بدء العملية
    if text in ("استبدال كلمه", "استبدال كلمة"):
        if not is_botowner(uid, cid):
            return await m.reply(f"{k} هذا الأمر يخص ( مبرمج السورس ) بس")
        await ar.set(step1, 1, ex=600)
        return await m.reply(f"{k} ارسل الكلمة القديمة الآن")

    # الخطوة 1: استلام الكلمة القديمة
    if await ar.get(step1) and is_botowner(uid, cid):
        await ar.set(step2, m.text, ex=600)
        await ar.delete(step1)
        return await m.reply(f"{k} ارسل الكلمة الجديدة الحين")

    # الخطوة 2: استلام الكلمة الجديدة وعرض الملفات
    if await ar.get(step2) and is_botowner(uid, cid):
        old_word = await ar.get(step2)
        await ar.set(step3, f"{old_word}&&new&&{m.text}", ex=600)
        await ar.delete(step2)
        files = sorted(f for f in os.listdir("Plugins") if f.endswith(".py"))
        txt = f"{k} ارسل اسم الملف الي تبي تعدل فيه الحين:\n\n——— ملفات السورس ———"
        for i, fname in enumerate(files, 1):
            txt += f"\n{i}) `{fname}`"
        txt += f"\n——— @{ch} ———"
        return await m.reply(txt)

    # الخطوة 3: استلام اسم الملف وتنفيذ الاستبدال
    if await ar.get(step3) and is_botowner(uid, cid) and m.text in os.listdir("Plugins"):
        mm = await m.reply(f"{k} جاري تعديل الملف")
        data  = await ar.get(step3)
        old_w = data.split("&&new&&")[0]
        new_w = data.split("&&new&&")[1]
        await ar.delete(step3)
        fname = m.text
        try:
            with open(f"Plugins/{fname}", "r", encoding="utf-8") as f:
                content = f.read()
            await mm.edit(f"{k} تم فتح الملف وقراءته")
            with open(f"Plugins/{fname}", "w", encoding="utf-8") as f:
                f.write(content.replace(old_w, new_w))
            await mm.edit(
                f"{k} تم تعديل الملف `{fname}`\n"
                f"{k} تم استبدال ( {old_w} ) بـ ( {new_w} )"
            )
            python = sys.executable
            # إغلاق نظيف قبل إعادة التشغيل
            try:
                from config import Client as _Client
                await _Client.stop()
            except Exception:
                pass
            os.execl(python, python, *sys.argv)
        except Exception as e:
            await mm.edit(f"{k} حدث خطأ: {e}")
