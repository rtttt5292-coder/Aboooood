"""
نظام الاتصال عن بُعد (Connection)
─────────────────────────────────────────────────────────────
يتيح للمستخدم إدارة المجموعة من الخاص (PM)
الأوامر:
  اتصال [ID المجموعة]   → الاتصال بمجموعة لإدارتها من الخاص
  قطع الاتصال           → إنهاء الاتصال الحالي
  اتصالاتي              → عرض المجموعات المتصلة
  سماح الاتصال          → السماح للأعضاء بالاتصال (مدير+)
  منع الاتصال           → منع الأعضاء من الاتصال (مدير+)
─────────────────────────────────────────────────────────────
"""

from pyrogram import Client, filters
from pyrogram.types import Message

from config import r, ar, DEV_ID, botkey
from helpers.ranks import is_admin, is_mod, is_owner, is_dev
from helpers.utils import group_enabled, resolve_text


# ── مفاتيح Redis ──────────────────────────────────────────────
def _conn_key(uid: int)         -> str: return f"{uid}:conn:{DEV_ID}"
def _allow_key(cid: int)        -> str: return f"{cid}:conn_allow:{DEV_ID}"
def _user_conns_key(uid: int)   -> str: return f"{uid}:conns:{DEV_ID}"


async def get_connection(uid: int) -> int | None:
    """يُرجع cid المتصل به حالياً أو None"""
    val = await ar.get(_conn_key(uid))
    return int(val) if val else None


# ═══════════════════════════════════════════════════════════════
# معالج الأوامر
# ═══════════════════════════════════════════════════════════════

@Client.on_message(filters.text & (filters.group | filters.private), group=2)
async def connection_cmd(c: Client, m: Message):
    if not m.from_user:
        return
    uid = m.from_user.id
    cid = m.chat.id
    is_pm = m.chat.type.value == "private"

    raw = m.text.strip()
    if is_pm:
        text = raw
    else:
        if not group_enabled(cid):
            return
        text = resolve_text(raw, cid)

    k = botkey()

    # ── اتصال [ID] ──────────────────────────────────────────
    if text.startswith("اتصال") and is_pm:
        parts = text.split(None, 1)
        if len(parts) < 2:
            conn_cid = await get_connection(uid)
            if conn_cid:
                try:
                    chat = await c.get_chat(conn_cid)
                    return await m.reply(f"{k} أنت متصل حالياً بـ **{chat.title}** (`{conn_cid}`)")
                except Exception:
                    pass
            return await m.reply(f"{k} الاستخدام: `اتصال [ID المجموعة]`")

        try:
            target_cid = int(parts[1].strip())
        except ValueError:
            return await m.reply(f"{k} ID غير صحيح. يجب أن يكون رقماً.")

        # تحقق من أن البوت في المجموعة والمستخدم عضو فيها
        try:
            chat = await c.get_chat(target_cid)
            member = await c.get_chat_member(target_cid, uid)
        except Exception:
            return await m.reply(f"{k} لم أجد المجموعة أو لستَ عضواً فيها.")

        # تحقق من سماح الاتصال
        allow = await ar.get(_allow_key(target_cid))
        if not allow:
            # يُسمح فقط للمدراء وما فوق
            if not (is_admin(uid, target_cid) or is_mod(uid, target_cid) or
                    is_owner(uid, target_cid) or is_dev(uid)):
                return await m.reply(f"{k} الاتصال بهذه المجموعة مقيّد للمدراء فقط.")

        await ar.set(_conn_key(uid), str(target_cid), ex=86400)  # 24 ساعة
        await ar.sadd(_user_conns_key(uid), str(target_cid))
        await m.reply(
            f"{k} ✅ اتصلتَ بـ **{chat.title}**\n"
            f"الآن يمكنك استخدام أوامر الإدارة من الخاص!\n\n"
            f"للقطع: `قطع الاتصال`"
        )

    # ── قطع الاتصال ─────────────────────────────────────────
    elif text == "قطع الاتصال" and is_pm:
        conn_cid = await get_connection(uid)
        if not conn_cid:
            return await m.reply(f"{k} لستَ متصلاً بأي مجموعة.")
        await ar.delete(_conn_key(uid))
        try:
            chat = await c.get_chat(conn_cid)
            await m.reply(f"{k} تم قطع الاتصال عن **{chat.title}** ✅")
        except Exception:
            await m.reply(f"{k} تم قطع الاتصال ✅")

    # ── اتصالاتي ────────────────────────────────────────────
    elif text == "اتصالاتي" and is_pm:
        conns = await ar.smembers(_user_conns_key(uid))
        if not conns:
            return await m.reply(f"{k} لا توجد اتصالات سابقة.")
        lines = [f"{k} **مجموعاتك:**\n"]
        for cid_s in conns:
            try:
                chat = await c.get_chat(int(cid_s))
                lines.append(f"• **{chat.title}** (`{cid_s}`)")
            except Exception:
                lines.append(f"• `{cid_s}` (لم يُعثر عليها)")
        await m.reply("\n".join(lines))

    # ── سماح الاتصال ────────────────────────────────────────
    elif text == "سماح الاتصال" and not is_pm:
        if not (is_admin(uid, cid) or is_mod(uid, cid)):
            return
        await ar.set(_allow_key(cid), "1")
        await m.reply(f"{k} تم السماح لجميع الأعضاء بالاتصال بهذه المجموعة من الخاص ✅")

    # ── منع الاتصال ─────────────────────────────────────────
    elif text == "منع الاتصال" and not is_pm:
        if not (is_admin(uid, cid) or is_mod(uid, cid)):
            return
        await ar.delete(_allow_key(cid))
        await m.reply(f"{k} تم تقييد الاتصال للمدراء فقط ✅")
