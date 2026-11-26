from typing import Callable, List, TypeVar
import math

T = TypeVar("T")


def label_risk(
    items: List[T],
    get_score: Callable[[T], int],
    set_label: Callable[[T, str], None],
) -> None:
    if not items:
        return


    for item in items:
        score = int(get_score(item) or 0)
        if score >= 65:
            set_label(item, "CRITICAL")
        else:
            set_label(item, "")

    rest = [item for item in items if int(get_score(item) or 0) < 65]
    n = len(rest)
    if n == 0:
        return


    if n < 8:
        for item in rest:
            score = int(get_score(item) or 0)
            if score >= 40:
                set_label(item, "HIGH")
            elif score >= 20:
                set_label(item, "MEDIUM")
            else:
                set_label(item, "LOW")
        return

    ordered = sorted(
        rest, key=lambda item: int(get_score(item) or 0), reverse=True
    )
    high_n = max(1, math.ceil(n * 0.15))
    med_n = max(1, math.ceil(n * 0.25))
    if high_n + med_n > n:
        med_n = max(0, n - high_n)

    for idx, item in enumerate(ordered):
        if idx < high_n:
            set_label(item, "HIGH")
        elif idx < high_n + med_n:
            set_label(item, "MEDIUM")
        else:
            set_label(item, "LOW")
