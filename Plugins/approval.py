"""
نظام الموافقة (Approval / Whitelist)
──────────────────────────────────────
الأوامر:
  وافق (رد) / وافق @user      → إضافة مستخدم للقائمة البيضاء
  الغاء الموافقة (رد) / الغاء الموافقة @user → إزالته
  الموافقون                     → عرض قائمة المعتمدين
──────────────────────────────────────
الأعضاء الموافق عليهم يتجاوزون:
  - فلتر الكلمات
  - ضد الفيضان
  - الأقفال (القيود)
  - فلتر NSFW
"""

import re

from pyrogram import Client, filters
from pyrogram.types import Message

from config import ar, DEV_ID, botkey, cached_smembers
from helpers.ranks import is_mod, is_pre
from helpers.utils import group_enabled, resolve_text

# ── مفاتيح Redis ──
def _approved_key(cid: int) -> str:
    return f"{cid}:approved:{DEV_ID}"

def is_approved(uid: int, cid: int) -> bool:
    return str(uid) in cached_smembers(_approved_key(cid))


# ─────────────────────────────────────────────────────────────────────────
# مساعد استخراج المستخدم
# ─────────────────────────────────────────────────────────────────────────

async def _resolve_user(c: Client, m: Message, target: str):
    if target is None and m.reply_to_message and m.reply_to_message.from_user:
        u = m.reply_to_message.from_user
        return u.id, u.mention
    if target is None:
        return None, None
    try:
        uid = int(target)
    except ValueError:
        uid = target.lstrip("@")
    try:
        u = await c.get_users(uid)
        return u.id, u.mention
    except Exception:
        return None, None


# ─────────────────────────────────────────────────────────────────────────
# الأوامر
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.text & filters.group, group=23)
async def approval_commands(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text, cid)
    k = botkey()

    # ── وافق ──
    approve_match = re.fullmatch(r"وافق(?:\s+(@?\S+))?", text)
    if approve_match:
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        target = approve_match.group(1)
        tid, mention = await _resolve_user(c, m, target)
        if not tid:
            return await m.reply(f"‼️ {k} حدد المستخدم بالرد أو المنشن")
        await ar.sadd(_approved_key(cid), tid)
        return await m.reply(
            f"╔══ {k} ══╗\n"
            f"┃ ✅ تمت الموافقة على {mention}\n"
            f"┃ سيتجاوز القيود والفلاتر\n"
            f"╚══════════╝"
        )

    # ── الغاء الموافقة ──
    unapprove_match = re.fullmatch(r"الغاء الموافقة(?:\s+(@?\S+))?", text)
    if unapprove_match:
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        target = unapprove_match.group(1)
        tid, mention = await _resolve_user(c, m, target)
        if not tid:
            return await m.reply(f"‼️ {k} حدد المستخدم بالرد أو المنشن")
        await ar.srem(_approved_key(cid), tid)
        return await m.reply(
            f"╔══ {k} ══╗\n┃ ❌ تم إلغاء الموافقة على {mention}\n╚══════════╝"
        )

    # ── الموافقون ──
    if text in ("الموافقون", "قائمة الموافقين"):
        approved_ids = cached_smembers(_approved_key(cid))
        if not approved_ids:
            return await m.reply(f"✨ {k} لا يوجد أعضاء موافق عليهم")
        lines = []
        for aid in approved_ids:
            try:
                user = await c.get_users(int(aid))
                lines.append(f"┃ • {user.mention}")
            except Exception:
                lines.append(f"┃ • `{aid}`")
        return await m.reply(
            f"╔══ {k} ══╗\n"
            f"┃ ✅ الأعضاء الموافق عليهم:\n"
            + "\n".join(lines) + "\n"
            f"╚══════════╝"
        )
