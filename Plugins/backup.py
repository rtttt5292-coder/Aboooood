"""
نظام النسخ الاحتياطي للمجموعة (Backup)
─────────────────────────────────────────────────────────────
الأوامر:
  نسخة احتياطية        → تصدير إعدادات المجموعة كملف JSON (مالك+)
  استعادة              → استيراد إعدادات من ملف JSON (مالك+)
─────────────────────────────────────────────────────────────
ما يُصدَّر:
  - القوانين
  - رسالة الترحيب
  - الكلمات المحظورة (word_filter)
  - الفلاتر (custom_filters)
  - الملاحظات (notes)
  - إعدادات الحماية (antispam, antiflood, antiraid, captcha)
  - إعدادات الأقفال (guards_locks)
─────────────────────────────────────────────────────────────
"""

import json
import time
from io import BytesIO

from pyrogram import Client, filters
from pyrogram.types import Message

from config import r, ar, DEV_ID, botkey
from helpers.ranks import is_admin, is_mod, is_owner, is_dev
from helpers.utils import group_enabled, resolve_text


# ── مساعد جمع مفاتيح Redis لمجموعة معيّنة ───────────────────
async def _export_group_data(cid: int) -> dict:
    """يجمع كل الإعدادات المحفوظة لمجموعة ويُرجعها كـ dict"""
    data = {"chat_id": cid, "exported_at": int(time.time()), "settings": {}, "lists": {}}

    # ── مفاتيح bool/string بسيطة ──────────────────────────
    str_keys = [
        f"{cid}:rules:{DEV_ID}",          # القوانين
        f"{cid}:welcome:{DEV_ID}",         # رسالة الترحيب
        f"{cid}:welcome_on:{DEV_ID}",      # تفعيل الترحيب
        f"{cid}:antispam_on:{DEV_ID}",
        f"{cid}:antispam_limit:{DEV_ID}",
        f"{cid}:antispam_action:{DEV_ID}",
        f"{cid}:flood_on:{DEV_ID}",
        f"{cid}:flood_limit:{DEV_ID}",
        f"{cid}:flood_action:{DEV_ID}",
        f"{cid}:raid_on:{DEV_ID}",
        f"{cid}:raid_limit:{DEV_ID}",
        f"{cid}:raid_mode:{DEV_ID}",
        f"{cid}:captcha_on:{DEV_ID}",
        f"{cid}:captcha_type:{DEV_ID}",
        f"{cid}:captcha_timeout:{DEV_ID}",
        f"{cid}:nightmode_on:{DEV_ID}",
        f"{cid}:nightmode_start:{DEV_ID}",
        f"{cid}:nightmode_end:{DEV_ID}",
        f"{cid}:forcesub_on:{DEV_ID}",
        f"{cid}:forcesub_channel:{DEV_ID}",
        f"{cid}:antichannel:{DEV_ID}",
        f"{cid}:conn_allow:{DEV_ID}",
    ]

    # قفل الأقسام (guards_locks)
    lock_types = [
        "photos", "videos", "voices", "stickers", "files", "gifs",
        "links", "hashtags", "bots", "forwards", "inline", "channels",
        "chat", "join", "sub", "arabic_only", "persian", "nsfw", "kfr",
        "repeat", "long_msg",
    ]
    for lt in lock_types:
        str_keys.append(f"{cid}:lock_{lt}:{DEV_ID}")

    try:
        values = await ar.mget(*str_keys)
        for key, val in zip(str_keys, values):
            if val is not None:
                # استخدم الجزء الأوسط من المفتاح كاسم
                short = key.split(":")[1]
                data["settings"][short] = val
    except Exception:
        pass

    # ── مجموعات (sets) ──────────────────────────────────────
    set_keys = {
        "word_filter":     f"{cid}:words:{DEV_ID}",
        "blacklist_users": f"{cid}:blacklist_users:{DEV_ID}",
        "muted_users":     f"{cid}:muted:{DEV_ID}",
    }
    for name, rkey in set_keys.items():
        try:
            members = await ar.smembers(rkey)
            if members:
                data["lists"][name] = list(members)
        except Exception:
            pass

    # ── الفلاتر المخصصة (custom_filters) ──────────────────
    try:
        fkeys = await ar.keys(f"{cid}:filter:*:{DEV_ID}")
        filters_data = {}
        for fk in fkeys:
            val = await ar.get(fk)
            if val:
                trigger = fk.split(":")[2]
                filters_data[trigger] = val
        if filters_data:
            data["lists"]["custom_filters"] = filters_data
    except Exception:
        pass

    # ── الملاحظات (notes) ─────────────────────────────────
    try:
        nkeys = await ar.keys(f"{cid}:note:*:{DEV_ID}")
        notes_data = {}
        for nk in nkeys:
            val = await ar.get(nk)
            if val:
                note_name = nk.split(":")[2]
                notes_data[note_name] = val
        if notes_data:
            data["lists"]["notes"] = notes_data
    except Exception:
        pass

    return data


async def _import_group_data(cid: int, data: dict) -> tuple[int, int]:
    """يستعيد الإعدادات من dict — يُرجع (imported, failed)"""
    imported, failed = 0, 0

    settings = data.get("settings", {})
    for short_key, val in settings.items():
        # أعِد بناء المفتاح الكامل
        # نحدد المجموعة الصحيحة من chat_id في الملف
        full_key = f"{cid}:{short_key}:{DEV_ID}"
        try:
            await ar.set(full_key, val)
            imported += 1
        except Exception:
            failed += 1

    lists = data.get("lists", {})

    # استعادة word_filter
    wf = lists.get("word_filter", [])
    if wf:
        try:
            await ar.sadd(f"{cid}:words:{DEV_ID}", *wf)
            imported += len(wf)
        except Exception:
            failed += 1

    # استعادة blacklist_users
    bu = lists.get("blacklist_users", [])
    if bu:
        try:
            await ar.sadd(f"{cid}:blacklist_users:{DEV_ID}", *bu)
            imported += len(bu)
        except Exception:
            failed += 1

    # استعادة الفلاتر
    cf = lists.get("custom_filters", {})
    for trigger, resp in cf.items():
        try:
            await ar.set(f"{cid}:filter:{trigger}:{DEV_ID}", resp)
            imported += 1
        except Exception:
            failed += 1

    # استعادة الملاحظات
    notes = lists.get("notes", {})
    for note_name, note_val in notes.items():
        try:
            await ar.set(f"{cid}:note:{note_name}:{DEV_ID}", note_val)
            imported += 1
        except Exception:
            failed += 1

    return imported, failed


# ═══════════════════════════════════════════════════════════════
# معالج الأوامر
# ═══════════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.group, group=2)
async def backup_cmd(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text.strip(), cid)
    k = botkey()

    # ── نسخة احتياطية ───────────────────────────────────────
    if text in ("نسخة احتياطية", "نسخ احتياطي", "backup"):
        if not (is_owner(uid, cid) or is_dev(uid)):
            return await m.reply(f"{k} هذا الأمر للمالك فقط.")
        msg = await m.reply(f"{k} جاري تصدير إعدادات المجموعة...")
        try:
            data = await _export_group_data(cid)
            json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            file_obj = BytesIO(json_bytes)
            file_obj.name = f"backup_{cid}_{int(time.time())}.json"
            await msg.delete()
            await c.send_document(
                cid,
                file_obj,
                caption=(
                    f"{k} **نسخة احتياطية ناجحة** ✅\n\n"
                    f"📦 الإعدادات: `{len(data['settings'])}` مفتاح\n"
                    f"📋 القوائم: `{sum(len(v) if isinstance(v, (list,dict)) else 1 for v in data['lists'].values())}` عنصر\n"
                    f"📅 التاريخ: `{time.strftime('%Y-%m-%d %H:%M')}`\n\n"
                    f"احتفظ بهذا الملف لاستعادة الإعدادات لاحقاً."
                )
            )
        except Exception as e:
            await msg.edit(f"{k} ❌ فشل التصدير: `{e}`")

    # ── استعادة ─────────────────────────────────────────────
    elif text in ("استعادة", "restore"):
        if not (is_owner(uid, cid) or is_dev(uid)):
            return await m.reply(f"{k} هذا الأمر للمالك فقط.")
        if not m.reply_to_message or not m.reply_to_message.document:
            return await m.reply(
                f"{k} أرسل ملف JSON الخاص بالنسخة الاحتياطية ثم ردّ عليه بـ **استعادة**."
            )
        doc = m.reply_to_message.document
        if not doc.file_name or not doc.file_name.endswith(".json"):
            return await m.reply(f"{k} الملف يجب أن يكون بصيغة `.json`")

        msg = await m.reply(f"{k} جاري استعادة الإعدادات...")
        try:
            file_bytes = await c.download_media(m.reply_to_message, in_memory=True)
            data = json.loads(bytes(file_bytes.getbuffer()))

            # تحقق من أن الملف لهذه المجموعة
            if data.get("chat_id") != cid:
                return await msg.edit(
                    f"{k} ⚠️ هذا الملف لمجموعة مختلفة!\n"
                    f"ID في الملف: `{data.get('chat_id')}`\n"
                    f"هذه المجموعة: `{cid}`\n\n"
                    f"استخدم الأمر في المجموعة الصحيحة."
                )

            imported, failed = await _import_group_data(cid, data)
            await msg.edit(
                f"{k} **تمت الاستعادة** ✅\n\n"
                f"✅ مستعاد: `{imported}` عنصر\n"
                f"❌ فاشل: `{failed}` عنصر"
            )
        except json.JSONDecodeError:
            await msg.edit(f"{k} ❌ الملف تالف أو ليس JSON صحيحاً.")
        except Exception as e:
            await msg.edit(f"{k} ❌ خطأ: `{e}`")
