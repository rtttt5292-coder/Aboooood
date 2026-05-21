import os
import time
import logging
import sqlite3
import json
import redis
import redis.asyncio as aioredis
from pyrogram import Client

logger = logging.getLogger("config")

API_ID    = int(os.getenv("API_ID", "0"))
API_HASH  = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
REDIS_URL = os.getenv("REDIS_URL", "")
DEV_ID    = os.getenv("DEV_ID", "").strip()

# ── التحقق من المتغيرات الإلزامية عند الإقلاع ─────────────────────────────
_missing = [k for k, v in {"API_ID": API_ID, "API_HASH": API_HASH,
                             "BOT_TOKEN": BOT_TOKEN, "DEV_ID": DEV_ID}.items()
            if not v or str(v) == "0"]
if _missing:
    raise EnvironmentError(
        f"❌ المتغيرات البيئية التالية مفقودة أو غير مضبوطة: {', '.join(_missing)}\n"
        f"   أضفها في إعدادات Render / Heroku قبل التشغيل."
    )

try:
    DEV_ID_INT: int = int(DEV_ID)
except ValueError:
    raise EnvironmentError("❌ DEV_ID يجب أن يكون رقم Telegram صحيح (أرقام فقط).")

if DEV_ID == "123456789":
    raise EnvironmentError(
        "❌ DEV_ID لا يزال على القيمة الافتراضية '123456789'.\n"
        "   هذا خطر أمني — اضبط DEV_ID بـ ID الحقيقي الخاص بك."
    )


# ══════════════════════════════════════════════════════════════════════════
#  FallbackDB — بديل SQLite عند غياب Redis أو انقطاع الاتصال
# ══════════════════════════════════════════════════════════════════════════

class FallbackDB:
    """
    محاكاة لأوامر Redis الأساسية باستخدام SQLite المحلي.
    يُستخدم تلقائياً عند عدم توفر Redis.
    """

    def __init__(self, path: str = "bot_fallback.db"):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS sets (k TEXT, v TEXT, PRIMARY KEY(k,v))"
        )
        self._conn.commit()
        logger.warning("⚠️  Redis غير متاح — يعمل البوت بوضع SQLite الاحتياطي")

    # ── أوامر String ──────────────────────────────────────────────────────

    def get(self, key, default=None):
        try:
            row = self._conn.execute(
                "SELECT v FROM kv WHERE k=?", (key,)
            ).fetchone()
            return row[0] if row else default
        except Exception as e:
            logger.warning("FallbackDB.get error: %s", e)
            return default

    def set(self, key, value, ex=None, px=None, **kwargs):
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO kv VALUES (?,?)", (key, str(value))
            )
            self._conn.commit()
            return True
        except Exception as e:
            logger.warning("FallbackDB.set error: %s", e)
            return False

    def delete(self, *keys):
        try:
            for k in keys:
                self._conn.execute("DELETE FROM kv WHERE k=?", (k,))
            self._conn.commit()
            return len(keys)
        except Exception as e:
            logger.warning("FallbackDB.delete error: %s", e)
            return 0

    def exists(self, *keys):
        count = 0
        for k in keys:
            row = self._conn.execute(
                "SELECT 1 FROM kv WHERE k=?", (k,)
            ).fetchone()
            if row:
                count += 1
        return count

    def expire(self, key, seconds):
        return True  # SQLite لا يدعم TTL — نتجاهله بأمان

    # ── أوامر Set ─────────────────────────────────────────────────────────

    def sadd(self, key, *values):
        try:
            for v in values:
                self._conn.execute(
                    "INSERT OR IGNORE INTO sets VALUES (?,?)", (key, str(v))
                )
            self._conn.commit()
            return len(values)
        except Exception as e:
            logger.warning("FallbackDB.sadd error: %s", e)
            return 0

    def srem(self, key, *values):
        try:
            for v in values:
                self._conn.execute(
                    "DELETE FROM sets WHERE k=? AND v=?", (key, str(v))
                )
            self._conn.commit()
            return len(values)
        except Exception as e:
            logger.warning("FallbackDB.srem error: %s", e)
            return 0

    def smembers(self, key):
        try:
            rows = self._conn.execute(
                "SELECT v FROM sets WHERE k=?", (key,)
            ).fetchall()
            return {row[0] for row in rows}
        except Exception as e:
            logger.warning("FallbackDB.smembers error: %s", e)
            return set()

    def sismember(self, key, value):
        row = self._conn.execute(
            "SELECT 1 FROM sets WHERE k=? AND v=?", (key, str(value))
        ).fetchone()
        return bool(row)

    def smove(self, src, dst, value):
        self.srem(src, value)
        self.sadd(dst, value)
        return True

    # ── أوامر Hash ────────────────────────────────────────────────────────

    def hset(self, name, key=None, value=None, mapping=None):
        if mapping:
            for k, v in mapping.items():
                self.set(f"{name}:{k}", v)
        elif key is not None:
            self.set(f"{name}:{key}", value)
        return True

    def hget(self, name, key):
        return self.get(f"{name}:{key}")

    def hgetall(self, name):
        prefix = f"{name}:"
        rows = self._conn.execute(
            "SELECT k, v FROM kv WHERE k LIKE ?", (prefix + "%",)
        ).fetchall()
        return {row[0][len(prefix):]: row[1] for row in rows}

    def hdel(self, name, *keys):
        for k in keys:
            self.delete(f"{name}:{k}")
        return len(keys)

    # ── Pipeline وهمي ─────────────────────────────────────────────────────

    def pipeline(self):
        return _FakePipeline(self)

    # ── ping ──────────────────────────────────────────────────────────────

    def ping(self):
        return True


class _FakePipeline:
    """Pipeline وهمي يُنفّذ الأوامر فوراً (بدون batching)"""

    def __init__(self, db: FallbackDB):
        self._db = db

    def get(self, key):         self._db.get(key);       return self
    def set(self, k, v, **kw):  self._db.set(k, v, **kw); return self
    def delete(self, *keys):    self._db.delete(*keys);   return self
    def sadd(self, k, *v):      self._db.sadd(k, *v);    return self
    def srem(self, k, *v):      self._db.srem(k, *v);    return self
    def smembers(self, k):      self._db.smembers(k);    return self
    def expire(self, k, s):     return self

    def execute(self):
        return []


# ══════════════════════════════════════════════════════════════════════════
#  اتصال Redis مع Fallback تلقائي
# ══════════════════════════════════════════════════════════════════════════

def _connect_redis_sync():
    if REDIS_URL:
        client = redis.from_url(REDIS_URL, decode_responses=True, max_connections=20)
    else:
        client = redis.Redis(host="localhost", port=6379, db=0,
                             decode_responses=True, max_connections=20)
    try:
        client.ping()
        logger.info("✅ اتصال Redis ناجح")
        return client
    except Exception as e:
        logger.warning("❌ Redis غير متاح (%s) — التبديل إلى SQLite", e)
        return FallbackDB()


def _connect_redis_async():
    if REDIS_URL:
        return aioredis.from_url(REDIS_URL, decode_responses=True, max_connections=20)
    return aioredis.Redis(host="localhost", port=6379, db=0,
                          decode_responses=True, max_connections=20)


r  = _connect_redis_sync()
_ar = _connect_redis_async()
ar  = _ar

__all__ = [
    "r", "ar", "DEV_ID", "DEV_ID_INT",
    "botkey", "botname", "cached_smembers",
    "cache_invalidate", "cache_invalidate_prefix",
    "safe_get", "safe_set", "safe_delete", "Client",
]


# ══════════════════════════════════════════════════════════════════════════
#  Cache موحّد (LRU) — بدون تغيير
# ══════════════════════════════════════════════════════════════════════════

_cache: dict = {}
_cache_order: list = []
_MAX_CACHE_SIZE = 10000

_STR_TTL = 180
_SET_TTL = 60


def _cache_cleanup():
    if len(_cache) < _MAX_CACHE_SIZE:
        return
    now = time.monotonic()
    expired = [k for k, (_, t, ttl) in _cache.items() if now - t > ttl]
    for k in expired:
        _cache.pop(k, None)
        try: _cache_order.remove(k)
        except ValueError: pass
    evict_count = max(0, len(_cache) - int(_MAX_CACHE_SIZE * 0.8))
    for k in _cache_order[:evict_count]:
        _cache.pop(k, None)
    del _cache_order[:evict_count]


def _cached_get(cache_key: str, redis_key: str, default: str, ttl: int = _STR_TTL) -> str:
    now = time.monotonic()
    entry = _cache.get(cache_key)
    if entry:
        value, ts, _ = entry
        if now - ts < ttl:
            return value
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_refresh_cached_get(cache_key, redis_key, default, ttl))
        except RuntimeError:
            pass
        return value
    try:
        value = r.get(redis_key) or default
    except Exception:
        value = default
    _cache_cleanup()
    _cache[cache_key] = (value, now, ttl)
    try: _cache_order.remove(cache_key)
    except ValueError: pass
    _cache_order.append(cache_key)
    return value


async def _refresh_cached_get(cache_key: str, redis_key: str, default: str, ttl: int):
    try:
        value = await _ar.get(redis_key) or default
    except Exception:
        return
    _cache_cleanup()
    _cache[cache_key] = (value, time.monotonic(), ttl)


def _cached_smembers(cache_key: str, redis_key: str) -> frozenset:
    now = time.monotonic()
    entry = _cache.get(cache_key)
    if entry and now - entry[1] < _SET_TTL:
        return entry[0]
    try:
        value = frozenset(r.smembers(redis_key))
    except Exception:
        return frozenset()
    _cache_cleanup()
    _cache[cache_key] = (value, now, _SET_TTL)
    try: _cache_order.remove(cache_key)
    except ValueError: pass
    _cache_order.append(cache_key)
    return value


def cache_invalidate(cache_key: str):
    _cache.pop(cache_key, None)


def cache_invalidate_prefix(prefix: str):
    for k in list(_cache.keys()):
        if k.startswith(prefix):
            _cache.pop(k, None)


def botkey() -> str:
    return _cached_get("botkey", f"{DEV_ID}:botkey", "⚡")


def botname() -> str:
    return _cached_get("botname", f"{DEV_ID}:BotName", "بوتي")


def cached_smembers(redis_key: str) -> frozenset:
    return _cached_smembers(f"sm:{redis_key}", redis_key)


def safe_get(key: str, default=None):
    try:
        return r.get(key) or default
    except Exception as e:
        logger.warning("Redis get error: %s", e)
        return default


def safe_set(key: str, value, **kwargs) -> bool:
    try:
        r.set(key, value, **kwargs)
        return True
    except Exception as e:
        logger.warning("Redis set error: %s", e)
        return False


def safe_delete(*keys) -> bool:
    try:
        r.delete(*keys)
        return True
    except Exception as e:
        logger.warning("Redis delete error: %s", e)
        return False


Client = Client(
    "my_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    plugins=dict(root="Plugins"),
)
