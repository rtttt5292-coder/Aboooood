"""
error_logger.py — إرسال أخطاء البوت تلقائياً للمطور عبر Telegram
─────────────────────────────────────────────────────────────────
الاستخدام:
    from helpers.error_logger import log_error

    try:
        ...
    except Exception as e:
        await log_error(e, context="اسم_الهاندلر")
"""
import traceback
import logging
from datetime import datetime

logger = logging.getLogger("error_logger")


async def log_error(
    error: Exception,
    context: str = "غير محدد",
    extra: str = "",
) -> None:
    """
    يرسل تفاصيل الخطأ للمطور عبر رسالة Telegram خاصة.

    المعاملات:
        error   : الاستثناء الذي وقع
        context : اسم الدالة أو الملف الذي وقع فيه الخطأ
        extra   : أي معلومات إضافية تريد إرفاقها (اختياري)
    """
    try:
        from config import Client, DEV_ID_INT

        tb = traceback.format_exc()
        # نقطّع التتبع إلى 3000 حرف لتجنب حد تيليغرام
        tb_trimmed = tb[-3000:] if len(tb) > 3000 else tb

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            "⚠️ **خطأ في البوت**",
            f"🕐 الوقت   : `{now}`",
            f"📍 المصدر  : `{context}`",
            f"❌ النوع   : `{type(error).__name__}`",
            f"📝 الرسالة : `{str(error)[:300]}`",
        ]

        if extra:
            lines.append(f"ℹ️ تفاصيل  : {extra[:300]}")

        lines += [
            "",
            "```",
            tb_trimmed,
            "```",
        ]

        msg = "\n".join(lines)

        await Client.send_message(DEV_ID_INT, msg)

    except Exception as send_err:
        # إذا فشل إرسال الخطأ، نسجله في console فقط
        logger.error(
            "error_logger: فشل إرسال الخطأ للمطور: %s | الخطأ الأصلي: %s",
            send_err,
            error,
        )
