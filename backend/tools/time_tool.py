from datetime import datetime


def get_current_time(_: dict[str, object]) -> str:
    return datetime.now().astimezone().strftime("%A, %B %d, %Y at %I:%M %p %Z")