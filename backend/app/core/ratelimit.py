from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

_settings = get_settings()

# Redis-backed when REDIS_URL is set, otherwise in-memory (single process only).
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[_settings.default_rate_limit],
    storage_uri=_settings.redis_url or "memory://",
    enabled=_settings.environment != "test",
)
