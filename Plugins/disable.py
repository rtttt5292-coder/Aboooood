"""
نظام تعطيل الأوامر (Disable Commands)
─────────────────────────────────────────────────────────────
الأوامر:
  تعطيل [أمر]          → تعطيل أمر معيّن في المجموعة (مدير+)
  تفعيل [أمر]          → إعادة تفعيل أمر معطّل (مدير+)
  الأوامر المعطلة       → عرض قائمة الأوامر المعطّلة
─────────────────────────────────────────────────────────────
الأوامر القابلة للتعطيل: الألعاب، التحميل، الملاحظات،
  الفلاتر، الهوية، الترحيب، وغيرها
─────────────────────────────────────────────────────────────
"""

from pyrogram import Client, filters
from pyrogram.types import Message

from config import r, ar, DEV_ID, botkey, cached_smembers
from helpers.ranks import is_admin, is_mod
from helpers.utils import group_enabled, resolve_text, utils_cache_invalidate


# ── الأوامر القابلة للتعطيل ────────────────────────────────────
DISABLEABLE = {
    # تسليه
    "الألعاب", "لعبة", "نقاطي", "الترتيب", "انهاء",
    # تحميل
    "بحث", "يوت", "تيك", "ساوند", "شازام",
    # معلومات
    "هويتي", "هوية", "من",
    # ملاحظات
    "الملاحظات", "ملاحظة",
    # أخرى
    "ترجمة", "طقس", "اخبار",
}


def _dis_key(cid: int) -> str:
    return f"{cid}:disabled_cmds:{DEV_ID}"


def is_cmd_disabled(cid: int, cmd: str) -> bool:
    """يتحقق من أن الأمر معطّل في المجموعة (sync، يستخدم cache)"""
    disabled = cached_smembers(_dis_key(cid))
    return cmd in disabled


# ═══════════════════════════════════════════════════════════════
# معالج الأوامر
# ═══════════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.group, group=2)
async def disable_cmd(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text.strip(), cid)
    k = botkey()

    # ── تعطيل [أمر] ─────────────────────────────────────────
    if text.startswith("تعطيل "):
        if not (is_admin(uid, cid) or is_mod(uid, cid)):
            return
        cmd = text[len("تعطيل "):].strip()
        if not cmd:
            return await m.reply(f"{k} الاستخدام: `تعطيل [اسم الأمر]`")
        if cmd not in DISABLEABLE:
            list_str = "، ".join(sorted(DISABLEABLE))
            return await m.reply(
                f"{k} الأمر **{cmd}** غير قابل للتعطيل.\n\n"
                f"**الأوامر القابلة للتعطيل:**\n{list_str}"
            )
        await ar.sadd(_dis_key(cid), cmd)
        utils_cache_invalidate(f"sm:{_dis_key(cid)}")
        await m.reply(f"{k} تم تعطيل الأمر **{cmd}** في هذه المجموعة ✅")

    # ── تفعيل [أمر] ─────────────────────────────────────────
    elif text.startswith("تفعيل "):
        if not (is_admin(uid, cid) or is_mod(uid, cid)):
            return
        cmd = text[len("تفعيل "):].strip()
        if not cmd:
            return await m.reply(f"{k} الاستخدام: `تفعيل [اسم الأمر]`")
        await ar.srem(_dis_key(cid), cmd)
        utils_cache_invalidate(f"sm:{_dis_key(cid)}")
        await m.reply(f"{k} تم تفعيل الأمر **{cmd}** مجدداً ✅")

    # ── الأوامر المعطلة ──────────────────────────────────────
    elif text == "الأوامر المعطلة":
        disabled = await ar.smembers(_dis_key(cid))
        if not disabled:
            return await m.reply(f"{k} لا توجد أوامر معطّلة في هذه المجموعة.")
        lines = "\n".join(f"• `{cmd}`" for cmd in sorted(disabled))
        await m.reply(
            f"{k} **الأوامر المعطّلة:**\n\n{lines}\n\n"
            f"لإعادة تفعيلها: `تفعيل [الأمر]`"
        )
