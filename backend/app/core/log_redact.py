"""Keep secrets out of logs.

httpx logs every request URL at INFO level, and EODHD takes its key as a query
parameter, so without this filter the key would be written to the console and log files.
"""

import logging
import re

_SECRET_PARAMS = re.compile(r"(?i)(api_token|apikey|api_key|token|access_key)=([^&\s\"']+)")


class RedactSecretsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        redacted = _SECRET_PARAMS.sub(r"\1=***", msg)
        if redacted != msg:
            record.msg, record.args = redacted, ()
        return True


def install() -> None:
    f = RedactSecretsFilter()
    for name in ("", "httpx", "httpcore", "uvicorn", "uvicorn.access", "uvicorn.error", "hss"):
        lg = logging.getLogger(name)
        lg.addFilter(f)
        for h in lg.handlers:
            h.addFilter(f)
    # Request-level URL logging is noise here and the main leak risk; keep warnings only.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
