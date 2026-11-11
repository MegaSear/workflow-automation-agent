import os


def get_logging_config() -> dict:
    level = os.getenv("LOG_LEVEL", "INFO").upper()

    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        level = "INFO"

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": ("%(asctime)s | %(levelname)s | %(name)s | %(message)s"),
            },
            "access": {
                "()": "uvicorn.logging.AccessFormatter",
                "fmt": (
                    "%(asctime)s | %(levelprefix)s %(client_addr)s "
                    '- "%(request_line)s" %(status_code)s'
                ),
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stdout",
            },
            "access": {
                "class": "logging.StreamHandler",
                "formatter": "access",
                "stream": "ext://sys.stdout",
            },
        },
        "root": {
            "level": level,
            "handlers": ["console"],
        },
        "loggers": {
            "uvicorn": {
                "level": level,
                "handlers": ["console"],
                "propagate": False,
            },
            "uvicorn.error": {
                "level": level,
            },
            "uvicorn.access": {
                "level": "INFO",
                "handlers": ["access"],
                "propagate": False,
            },
        },
    }
