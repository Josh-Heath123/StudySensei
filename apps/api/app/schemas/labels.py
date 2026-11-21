"""Source labels as models write them. Shared by the tutor's quiz and practice generation."""

import re

_LABEL = re.compile(r"[\[【]?\s*[sS](\d+)\s*[\]】]?")


def plain_labels(value: object) -> object:
    """ "[S1]", "【S1】" and "s1" all mean "S1"; anything else is kept, and won't match a
    source. For a ``field_validator(mode="before")`` on a list of labels."""
    if not isinstance(value, list):
        return value
    labels: list[object] = []
    for item in value:
        match = _LABEL.fullmatch(item.strip()) if isinstance(item, str) else None
        labels.append(f"S{int(match.group(1))}" if match else item)
    return labels
