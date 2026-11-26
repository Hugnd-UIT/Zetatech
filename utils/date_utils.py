from datetime import datetime
from typing import Optional


def days_ago(raw: Optional[str]) -> int:
    if not raw:
        return 9999

    try:
        dt = datetime.strptime(raw.split(" ")[0], "%Y-%m-%d")
        diff = datetime.now() - dt
        return diff.days
    except ValueError:
        return 9999
