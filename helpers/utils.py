"""
وظائف مساعدة مشتركة
"""
import time
import hashlib
from config import r, DEV_ID, botname, cached_smembers
from helpers.ranks import is_admin


def _txt_key(text: str) -> str:
    """
    ينتج مفتاح كاش قصيراً من النص:
    - نصوص <= 40 حرفاً: تُستخدم مباشرة.
    - نصوص أطول: أول 20 حرف + md5 مختصر لمنع تضخم الكاش.
    """
    if len(text) <= 40:
        return text
    digest = hashlib.md5(text.encode("utf-8", errors="replace"), usedforsecurity=False).hexdigest()[:8]
    return f"{text[:20]}{digest}"

_utils_cache: dict = {}
_utils_cache_order: list = []    # لتتبع ترتيب الوصول (LRU)
_MAX_UTILS_CACHE = 10000         # رُفع من 5000
_ENABLE_TTL = 120
_MUTE_TTL   = 30
_RTXT_TTL   = 60


def _utils_cache_cleanup():
    """LRU eviction: يحذف الأقل استخداماً عند امتلاء الكاش"""
    if len(_utils_cache) < _MAX_UTILS_CACHE:
        return
    now = time.monotonic()
    expired = [k for k, (_, t, ttl) in _utils_cache.items() if now - t > ttl]
    for k in expired:
        _utils_cache.pop(k, None)
        try: _utils_cache_order.remove(k)
        except ValueError: pass
    evict_count = max(0, len(_utils_cache) - int(_MAX_UTILS_CACHE * 0.8))
    for k in _utils_cache_order[:evict_count]:
        _utils_cache.pop(k, None)
    del _utils_cache_order[:evict_count]


def _bool_cached(key: str, ttl: float = _ENABLE_TTL) -> bool:
    now = time.monotonic()
    entry = _utils_cache.get(key)
    if entry and now - entry[1] < ttl:
        return entry[0]
    try:
        val = bool(r.get(key))
    except Exception:
        return False
    _utils_cache_cleanup()
    _utils_cache[key] = (val, now, ttl)
    try: _utils_cache_order.remove(key)
    except ValueError: pass
    _utils_cache_order.append(key)
    return val


def _str_cached(cache_key: str, redis_key: str) -> str | None:
    now = time.monotonic()
    entry = _utils_cache.get(cache_key)
    if entry and now - entry[1] < _RTXT_TTL:
        return entry[0]
    try:
        val = r.get(redis_key)
    except Exception:
        val = None
    _utils_cache_cleanup()
    _utils_cache[cache_key] = (val, now, _RTXT_TTL)
    try: _utils_cache_order.remove(cache_key)
    except ValueError: pass
    _utils_cache_order.append(cache_key)
    return val


def utils_cache_invalidate(key: str):
    _utils_cache.pop(key, None)
    try: _utils_cache_order.remove(key)
    except ValueError: pass


def group_enabled(cid: int) -> bool:
    return _bool_cached(f"{cid}:enable:{DEV_ID}")


def is_muted_user(uid: int, cid: int) -> bool:
    return (
        _bool_cached(f"{uid}:mute:{cid}:{DEV_ID}", ttl=_MUTE_TTL) or
        _bool_cached(f"{uid}:mute:{DEV_ID}", ttl=_MUTE_TTL)
    )


def is_gbanned(uid: int) -> bool:
    return _bool_cached(f"{uid}:gban:{DEV_ID}", ttl=_MUTE_TTL)


def group_muted(cid: int) -> bool:
    return _bool_cached(f"{cid}:mute:{DEV_ID}")


def can_speak(uid: int, cid: int) -> bool:
    if group_muted(cid) and not is_admin(uid, cid):
        return False
    if is_muted_user(uid, cid):
        return False
    return True


def resolve_text(text: str, cid: int) -> str:
    name = botname()
    if text.startswith(f"{name} "):
        text = text[len(name) + 1:]

    # نستخدم _txt_key لتقصير مفتاح الكاش — يمنع تضخم الكاش بالنصوص الطويلة
    k = _txt_key(text)
    local = _str_cached(f"rtxt:l:{cid}:{k}", f"{cid}:Custom:{cid}:{DEV_ID}&text={text}")
    if local:
        return local

    global_ = _str_cached(f"rtxt:g:{k}", f"Custom:{DEV_ID}&text={text}")
    if global_:
        return global_

    return text
