"""Pure detection helpers for the repetition failure mode T3.37 first
found and T3.28 found recurring on a different model. Kept side-effect-
free and provider-agnostic -- no client, no network -- so it can be unit
tested directly against plain strings (T4.21).
"""

from __future__ import annotations

# T4.18: both observed repetition loops (gemma, T3.37; gemini-3.1-pro-
# preview, T3.28) present the same way -- a short unit repeated exactly
# and *immediately consecutively* many times, not merely a token that
# recurs often. That distinction is what separates this from legitimate
# content: a class with several members typed "str" repeats the word
# "str" plenty, but the differing attribute names between occurrences
# break exact equality at every candidate period length, so a real
# response never satisfies "same substring, back to back, N+ times."
_MIN_PERIOD = 3
_MAX_PERIOD = 80
_MIN_CONSECUTIVE_REPEATS = 5
_MIN_REPEATED_SPAN = 100


def detect_repetition(text: str) -> bool:
    """True if `text` contains a short unit repeated immediately and
    consecutively often enough to be a degenerate loop rather than
    ordinary content.
    """
    n = len(text)
    if n < _MIN_REPEATED_SPAN:
        return False

    max_period = min(_MAX_PERIOD, n // _MIN_CONSECUTIVE_REPEATS)
    for period in range(_MIN_PERIOD, max_period + 1):
        i = 0
        while i + period * _MIN_CONSECUTIVE_REPEATS <= n:
            unit = text[i : i + period]
            j = i + period
            repeats = 1
            while j + period <= n and text[j : j + period] == unit:
                repeats += 1
                j += period
            if repeats >= _MIN_CONSECUTIVE_REPEATS and repeats * period >= _MIN_REPEATED_SPAN:
                return True
            i = j if repeats > 1 else i + period
    return False
