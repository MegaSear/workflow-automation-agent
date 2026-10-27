from datetime import datetime


def get_current_time() -> str:
    """Возвращает текущее локальное время сервера."""
    result = datetime.now().astimezone().isoformat(timespec="seconds")
    print(f"[TOOL] get_current_time -> {result}")
    return result
