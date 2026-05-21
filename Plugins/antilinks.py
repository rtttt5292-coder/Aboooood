"""
نظام مكافحة الروابط المتقدم (Anti-Links)
─────────────────────────────────────────────────────────────
الأوامر:
  تفعيل ضد الروابط          → تشغيل الحماية (مدير+)
  تعطيل ضد الروابط          → إيقاف الحماية (مدير+)
  عقوبة الروابط [كتم|طرد|حظر] → تحديد العقوبة (مدير+)
  استثناء رابط [رابط/اسم]   → إضافة رابط مسموح (مدير+)
  حذف استثناء [رابط/اسم]    → إزالة رابط من القائمة البيضاء (مدير+)
  قائمة الاستثناءات         → عرض الروابط المسموح بها
  حالة ضد الروابط           → عرض الإعدادات الحالية
─────────────────────────────────────────────────────────────
"""

import re

from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message, ChatPermissions

from config import r, ar, DEV_ID, botkey
from helpers.ranks import is_admin, is_mod, is_owner, is_dev, is_pre
from helpers.utils import group_enabled, resolve_text


# ── مفاتيح Redis ──────────────────────────────────────────────
def _on_key(cid: int)         -> str: return f"{cid}:antilinks_on:{DEV_ID}"
def _action_key(cid: int)     -> str: return f"{cid}:antilinks_action:{DEV_ID}"
def _whitelist_key(cid: int)  -> str: return f"{cid}:antilinks_wl:{DEV_ID}"


# ── اكتشاف الروابط ────────────────────────────────────────────
_URL_RE = re.compile(
    r"(https?://[^\s]+|t\.me/[^\s]+|@[A-Za-z0-9_]{5,}|[A-Za-z0-9\-]+\.[a-z]{2,4}(/[^\s]*)?)",
    re.IGNORECASE
)

def _find_links(text: str) -> list[str]:
    return _URL_RE.findall(text) if text else []


def _is_whitelisted(link: str, whitelist: frozenset) -> bool:
    link_lower = link.lower().strip("@")
    for wl in whitelist:
        if wl.lower() in link_lower or link_lower in wl.lower():
            return True
    return False


# ═══════════════════════════════════════════════════════════════
# مراقب الرسائل
# ═══════════════════════════════════════════════════════════════

@Client.on_message(filters.group, group=12)
async def antilinks_watcher(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id

    if not group_enabled(cid):
        return
    if not await ar.get(_on_key(cid)):
        return

    # تخطي المدراء وما فوق
    if is_admin(uid, cid) or is_mod(uid, cid) or is_owner(uid, cid) or is_dev(uid) or is_pre(uid, cid):
        return

    # جمع النص من الرسالة
    text = m.text or m.caption or ""
    links = _find_links(text)

    if not links:
        # تحقق من كيانات مضمّنة
        entities = (m.entities or []) + (m.caption_entities or [])
        for ent in entities:
            if ent.type.value in ("url", "text_link"):
                url = getattr(ent, "url", None) or (text[ent.offset: ent.offset + ent.length])
                links.append(url)

    if not links:
        return

    # تحقق من القائمة البيضاء
    whitelist = await ar.smembers(_whitelist_key(cid))
    wl_set = frozenset(whitelist)

    for link in links:
        if not _is_whitelisted(str(link), wl_set):
            # رابط غير مسموح — طبّق العقوبة
            action = (await ar.get(_action_key(cid))) or "حذف"
            await _apply_action(c, m, uid, cid, action)
            return


async def _apply_action(c: Client, m: Message, uid: int, cid: int, action: str):
    k = botkey()
    try:
        await m.delete()
    except Exception:
        pass

    if action == "كتم":
        try:
            await c.restrict_chat_member(cid, uid, ChatPermissions(can_send_messages=False))
            await c.send_message(cid, f"{k} {m.from_user.mention} كتم بسبب إرسال روابط.")
        except Exception:
            pass
    elif action == "طرد":
        try:
            await c.ban_chat_member(cid, uid)
            import asyncio; await asyncio.sleep(1)
            await c.unban_chat_member(cid, uid)
            await c.send_message(cid, f"{k} {m.from_user.mention} طُرد بسبب إرسال روابط.")
        except Exception:
            pass
    elif action == "حظر":
        try:
            await c.ban_chat_member(cid, uid)
            await c.send_message(cid, f"{k} {m.from_user.mention} حُظر بسبب إرسال روابط.")
        except Exception:
            pass
    else:
        # حذف فقط
        await c.send_message(cid, f"{k} {m.from_user.mention} ⚠️ لا يُسمح بالروابط هنا!")


# ═══════════════════════════════════════════════════════════════
# أوامر الإعداد
# ═══════════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.group, group=2)
async def antilinks_cmd(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text.strip(), cid)
    k = botkey()

    if text == "تفعيل ضد الروابط":
        if not (is_admin(uid, cid) or is_mod(uid, cid)):
            return
        await ar.set(_on_key(cid), "1")
        await m.reply(f"{k} تم تفعيل الحماية ضد الروابط ✅")

    elif text == "تعطيل ضد الروابط":
        if not (is_admin(uid, cid) or is_mod(uid, cid)):
            return
        await ar.delete(_on_key(cid))
        await m.reply(f"{k} تم تعطيل الحماية ضد الروابط ✅")

    elif text.startswith("عقوبة الروابط"):
        if not (is_admin(uid, cid) or is_mod(uid, cid)):
            return
        parts = text.split(None, 1)
        if len(parts) < 2 or parts[1] not in ("حذف", "كتم", "طرد", "حظر"):
            return await m.reply(f"{k} الخيارات: **حذف** | **كتم** | **طرد** | **حظر**")
        await ar.set(_action_key(cid), parts[1])
        await m.reply(f"{k} عقوبة الروابط: **{parts[1]}** ✅")

    elif text.startswith("استثناء رابط"):
        if not (is_admin(uid, cid) or is_mod(uid, cid)):
            return
        parts = text.split(None, 1)
        if len(parts) < 2:
            return await m.reply(f"{k} الاستخدام: `استثناء رابط [رابط أو اسم]`")
        entry = parts[1].strip().lstrip("@").lower()
        await ar.sadd(_whitelist_key(cid), entry)
        await m.reply(f"{k} تمت إضافة `{entry}` للقائمة البيضاء ✅")

    elif text.startswith("حذف استثناء"):
        if not (is_admin(uid, cid) or is_mod(uid, cid)):
            return
        parts = text.split(None, 1)
        if len(parts) < 2:
            return await m.reply(f"{k} الاستخدام: `حذف استثناء [رابط أو اسم]`")
        entry = parts[1].strip().lstrip("@").lower()
        await ar.srem(_whitelist_key(cid), entry)
        await m.reply(f"{k} تمت إزالة `{entry}` من القائمة البيضاء ✅")

    elif text == "قائمة الاستثناءات":
        wl = await ar.smembers(_whitelist_key(cid))
        if not wl:
            return await m.reply(f"{k} القائمة البيضاء فارغة.")
        lines = "\n".join(f"• `{entry}`" for entry in sorted(wl))
        await m.reply(f"{k} **الروابط المسموح بها:**\n\n{lines}")

    elif text == "حالة ضد الروابط":
        on     = bool(await ar.get(_on_key(cid)))
        action = (await ar.get(_action_key(cid))) or "حذف"
        wl     = await ar.smembers(_whitelist_key(cid))
        status = "✅ مفعّل" if on else "❌ معطّل"
        await m.reply(
            f"{k} **حالة الحماية ضد الروابط**\n\n"
            f"الحالة: {status}\n"
            f"العقوبة: **{action}**\n"
            f"الاستثناءات: **{len(wl)}** رابط"
        )
