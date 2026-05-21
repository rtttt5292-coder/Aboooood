"""
الأوامر المخصصة - تغيير اسم الأوامر
أوامر:
  اضف امر         → تعيين اسم بديل لأمر موجود
  حذف امر [امر]   → حذف أمر مخصص
  الاوامر المضافة → قائمة الأوامر المخصصة
"""
import re
from pyrogram import Client, filters
from pyrogram.types import Message

from config import r, DEV_ID, botkey, ar
from helpers.ranks import is_owner, is_admin
from helpers.utils import group_enabled, can_speak, resolve_text, utils_cache_invalidate


@Client.on_message(filters.text & filters.group, group=999)
async def custom_commands(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    if not can_speak(uid, cid):
        return

    text = resolve_text(m.text, cid)
    k    = botkey()

    # ── إلغاء في منتصف العملية ────────────────────────────────────────────
    if text == "الغاء":
        if await ar.delete(f"{cid}:addCustom:{uid}:{DEV_ID}"):
            return await m.reply(f"╔══ {k} ══╗\n┃ تـم إلـغـاء إضـافـة الأمـر ❌\n╚══════════╝")
        if await ar.delete(f"{cid}:addCustom2:{uid}:{DEV_ID}"):
            return await m.reply(f"╔══ {k} ══╗\n┃ تـم إلـغـاء إضـافـة الأمـر ❌\n╚══════════╝")
        return

    # ── مرحلة 2: استقبال الاسم الجديد ────────────────────────────────────
    if await ar.get(f"{cid}:addCustom2:{uid}:{DEV_ID}") and is_admin(uid, cid) and len(text) < 60:
        old_cmd = await ar.get(f"{cid}:addCustom2:{uid}:{DEV_ID}")
        new_cmd = text
        await ar.delete(f"{cid}:addCustom2:{uid}:{DEV_ID}")
        await ar.set(f"{cid}:Custom:{cid}:{DEV_ID}&text={new_cmd}", old_cmd)
        await ar.sadd(f"{cid}:listCustom:{cid}:{DEV_ID}", new_cmd)
        utils_cache_invalidate(f"rtxt:l:{cid}:{new_cmd}")
        return await m.reply(
            f"{k} تم إضافة الأمر:\n"
            f"الاسم الجديد: `{new_cmd}`\n"
            f"يُحوَّل إلى: `{old_cmd}` ✅"
        )

    # ── مرحلة 1: استقبال الأمر الأصلي ───────────────────────────────────
    if await ar.get(f"{cid}:addCustom:{uid}:{DEV_ID}") and is_admin(uid, cid) and len(text) < 60:
        await ar.delete(f"{cid}:addCustom:{uid}:{DEV_ID}")
        await ar.set(f"{cid}:addCustom2:{uid}:{DEV_ID}", text, ex=300)
        return await m.reply(
            f"{k} ممتاز! الأمر الأصلي هو: `{text}`\n"
            f"الآن أرسل الاسم البديل الذي تريده\n"
            "أرسل **الغاء** للتراجع"
        )

    # ── قائمة الأوامر المضافة ─────────────────────────────────────────────
    if text in ("الاوامر المضافه", "الاوامر المضافة"):
        if not is_owner(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـالـك وفـوق فـقـط")
        cmds = await ar.smembers(f"{cid}:listCustom:{cid}:{DEV_ID}")
        if not cmds:
            return await m.reply(f"✨ {k} لا تـوجـد أوامـر مـخـصـصـة بـعـد")
        lines = [f"{k} الأوامر المخصصة:\n"]
        for i, alias in enumerate(sorted(cmds), 1):
            original = await ar.get(f"{cid}:Custom:{cid}:{DEV_ID}&text={alias}") or "؟"
            lines.append(f"{i}. `{alias}` ← `{original}`")
        return await m.reply("\n".join(lines))

    # ── اضف امر ──────────────────────────────────────────────────────────
    if text in ("اضف امر", "تغيير امر"):
        if not is_owner(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـالـك وفـوق فـقـط")
        if await ar.get(f"{cid}:addCustom:{uid}:{DEV_ID}"):
            return await m.reply(f"⚠️ {k} أنـت فـي مـنـتـصـف إضـافـة أمـر، أرسـل **الغاء** أولاً")
        await ar.set(f"{cid}:addCustom:{uid}:{DEV_ID}", 1, ex=300)
        return await m.reply(
            f"{k} أرسل الأمر الأصلي (الموجود مسبقاً) الآن\n"
            "أرسل **الغاء** للتراجع"
        )

    # ── حذف امر ──────────────────────────────────────────────────────────
    del_m = re.fullmatch(r"حذف امر\s+(.+)", text)
    if del_m:
        if not is_owner(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـالـك وفـوق فـقـط")
        alias = del_m.group(1).strip()
        key   = f"{cid}:Custom:{cid}:{DEV_ID}&text={alias}"
        if not await ar.get(key):
            return await m.reply(f"🔍 {k} لا يـوجـد أمـر بـهـذا الاسـم")
        await ar.delete(key)
        await ar.srem(f"{cid}:listCustom:{cid}:{DEV_ID}", alias)
        utils_cache_invalidate(f"rtxt:l:{cid}:{alias}")
        return await m.reply(f"╔══ {k} ══╗\n┃ تـم حـذف الأمـر «{alias}» 🗑️\n╚══════════╝")
