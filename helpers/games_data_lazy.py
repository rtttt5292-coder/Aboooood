"""
Lazy loader لبيانات الألعاب — يُحمَّل عند أول استخدام فقط
بدلاً من تحميل 191KB عند الإقلاع
"""
import importlib
from typing import Any

_module = None

def _load() -> Any:
    global _module
    if _module is None:
        _module = importlib.import_module("helpers.games_data")
    return _module


class _LazyProxy:
    """Proxy يُؤجّل تحميل games_data حتى أول وصول فعلي"""
    def __getattr__(self, name: str):
        return getattr(_load(), name)


_proxy = _LazyProxy()

# متغيرات قابلة للاستيراد مباشرة بنمط lazy
def __getattr__(name: str):
    _vars = {
        "Maths","words","Arab","gomal","trteep","emojis","english",
        "m3any","countries","mthal","countries_","cut","deen",
        "cars","anime","emojis_pics","pics","jobs","knzs",
        "tashfeer","football","tarkeeb",
    }
    if name in _vars:
        return getattr(_load(), name)
    raise AttributeError(f"module 'helpers.games_data_lazy' has no attribute {name!r}")
