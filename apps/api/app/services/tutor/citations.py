"""Which sources an answer cited. Pure: text and labels in, labels out.

An answer cites with ``[S1]``, ``[S2][S4]`` or ``[S2, S4]``. A label that wasn't among the
answer's sources (``[S9]``, or ``[S5]`` when there were three) is reported apart, so it can
be left out of the citations and the message flagged. The text itself is never changed.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

_GROUP = re.compile(r"\[\s*(S\d+(?:\s*[,;]\s*S\d+)*)\s*\]")
_LABEL = re.compile(r"S\d+")


@dataclass(frozen=True)
class Citations:
    # The sources' labels the answer cited, in the sources' order.
    cited: list[str]
    # Labels it cited that weren't among its sources, in the order they first appear.
    unknown: list[str]


def parse_citations(text: str, labels: Sequence[str]) -> Citations:
    found: list[str] = []
    for group in _GROUP.finditer(text):
        for label in _LABEL.findall(group.group(1)):
            if label not in found:
                found.append(label)
    known = set(labels)
    return Citations(
        cited=[label for label in labels if label in found],
        unknown=[label for label in found if label not in known],
    )
