"""S2's prompts (the starting point for Phase 6 task 3, ADR 0032).

Course text only: a page's text, a page image, the module's topic names. Never anything
about the student (decision 0002); names printed on a paper are redacted first
(``privacy.redact_text``, and masks over page images).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.ai.messages import Image, Message, system, user

TYPES_GUIDE = """Question types (pick one):
- recall: state, define, name or list facts.
- explain: describe or explain how or why something works, in the student's own words.
- apply: use knowledge on a given scenario, example, figure, table or data.
- calculate: carry out a procedure to a worked result (a count, a cipher, a computed value).
- essay: an extended argued discussion, usually 5 marks or more, judged on reasoning."""

PARTS_RULES = """How to list the parts:
- List every part that carries its own marks, in paper order. Never list a question itself
  when its parts are listed.
- number: the part's FULL number from the top, never a bare label. Join the levels with dots:
  Question 2 with parts a), b) gives "2.a", "2.b"; part (ii) of 1 a) gives "1.a.ii". When a
  question numbers its items afresh (Question 3 with items 1., 2. and item 2 with (a), (b)),
  include the item: "3.1", "3.2.a", "3.2.b". A question with no sub-parts is "4".
- Items that share one mark total (e.g. "a) Virus b) Worm ... [10]") are ONE part with that total.
- A bracketed total after a question's last part (e.g. "[20]") is the question's total, not a part.
- parent: the enclosing number in the same form ("3.2" for "3.2.a", "3" for "3.1"), or null.
- marks: the part's own marks as printed, e.g. "(5)", "[5]", "(5 marks)".
- page: the page where the part starts.
- first_words: the first words of the part's own text (not its number), at most 12.
- The paper may include a memo or model answers. Skip them: list questions only.
- Never invent a part that isn't printed. Never merge two printed parts that each carry marks.
- Check: the parts' marks should add up to the paper total when one is printed."""

# The first version (S2 run 1), kept for the record: it gave no rule for nested numbers, and
# models answered with bare labels ("a" under question 2) and lost restarted item numbers.
PARTS_RULES_V1 = """How to list the parts:
- List every part that carries its own marks, in paper order, numbered as printed: "1a", "1a.ii",
  "3.2", "1.1(a)". A question with no sub-parts is one part ("4").
- Items that share one mark total (e.g. "a) Virus b) Worm ... [10]") are ONE part with that total.
- A bracketed total after the last sub-part (e.g. "[20]") is the question's total, not a part.
- parent: the enclosing question's number ("3" for "3.2"), or null for a whole question.
- marks: the part's own marks as printed, e.g. "(5)", "[5]", "(5 marks)".
- page: the page where the part starts.
- first_words: the first words of the part's own text (not its number), at most 12.
- The paper may include a memo or model answers. Skip them: list questions only.
- Never invent a part that isn't printed. Never merge two printed parts that each carry marks."""


TRANSCRIPTION_SYSTEM = (
    "You transcribe one page of a university test paper into plain text for software that "
    "splits papers into questions and counts their marks. Copy the printed text faithfully, top "
    "to bottom. Keep every question number and label exactly as printed (Question 3, 3.2, a), "
    "(ii)). Marks are the most important thing on the page: they are usually printed at the "
    "right margin, in brackets ((5), [10], (2 marks)), on the part's line or just below it, and "
    "they are easy to miss. Look along the right margin for each part and put its marks at the "
    "end of that part's line, exactly as printed; never drop or move one. Keep tables as rows of "
    "text. For a figure or diagram write [figure: a few words]. Leave out handwriting, stamps "
    "and blank answer lines. Reply with the text only."
)
# Run 1's prompt, kept for the record: it lost the right-margin marks of one scanned page.
TRANSCRIPTION_SYSTEM_V1 = (
    "You transcribe one page of a university test paper into plain text for software "
    "that splits papers into questions. Copy the printed text faithfully, top to bottom. "
    "Keep every question number and label exactly as printed (Question 3, 3.2, a), (ii)) "
    "and every mark as printed ((5), [10], (2 marks)), on the line where it appears. "
    "Keep tables as rows of text. For a figure or diagram write [figure: a few words]. "
    "Leave out handwriting, stamps and blank answer lines. Reply with the text only."
)


def transcription_messages(page_number: int, image: Image) -> list[Message]:
    return [system(TRANSCRIPTION_SYSTEM), user(f"Page {page_number}.", image)]


@dataclass(frozen=True)
class PageText:
    number: int
    text: str


def paper_text(pages: Sequence[PageText]) -> str:
    return "\n\n".join(f"=== Page {p.number} ===\n{p.text.strip()}" for p in pages)


def segmentation_messages(pages: Sequence[PageText]) -> list[Message]:
    """Segmentation A: the whole paper at once."""
    return [
        system(
            "You split a university test paper into its marked parts. Reply in JSON: "
            '{"total_marks": number or null, "questions": [{"number", "parent", "marks", '
            '"page", "first_words"}]}. total_marks is the paper total if one is printed, '
            "else null.\n\n" + PARTS_RULES
        ),
        user(paper_text(pages)),
    ]


def page_segmentation_messages(
    page: PageText, *, last_number: str | None, open_parent: str | None
) -> list[Message]:
    """Segmentation B: one page, with the previous page's last number and open question."""
    carry = (
        f"The previous page ended at part {last_number!r}"
        + (f", inside question {open_parent!r}" if open_parent else "")
        + ". Until this page shows a new question heading (such as 'Question 4'), every part "
        "on it belongs to that open question: a numbered item at the top of the page ('3.', "
        "'(c)') is the next item of the open question, never a new question, and its number "
        "includes the open question's number."
        if last_number
        else "This is the first page."
    )
    return [
        system(
            "You split one page of a university test paper into the marked parts that START on "
            "this page. Reply in JSON: "
            '{"total_marks": number or null, "questions": [{"number", "parent", "marks", '
            '"page", "first_words"}], "last_number": string or null, '
            '"open_parent": string or null}. total_marks: a paper total printed on this page, '
            "else null. last_number: the last part's number on this page (or the previous "
            "page's when none starts here). open_parent: the question still open at the "
            "bottom of the page, or null.\n\n" + PARTS_RULES
        ),
        user(f"{carry}\n\n{paper_text([page])}"),
    ]


@dataclass(frozen=True)
class TopicOption:
    code: str  # "t12"
    name: str
    chapter: str  # the chapter's name; equal to ``name`` for a chapter


def topic_list(options: Sequence[TopicOption]) -> str:
    lines: list[str] = []
    for option in options:
        if option.name == option.chapter:
            lines.append(f"{option.code}: {option.name}")
        else:
            lines.append(f"  {option.code}: {option.name} (in {option.chapter})")
    return "\n".join(lines)


CLASSIFY_RULES = (
    "Choose 1 to 3 topic codes per part, the best first. Prefer the most specific topic "
    "(a subtopic) that the part is about; give a chapter code only when no subtopic fits. "
    "Use only codes from the list. If the paper uses older chapter names or numbers, ignore "
    "them and judge by content.\n\n" + TYPES_GUIDE
)


def paper_classification_messages(
    pages: Sequence[PageText], numbers: Sequence[str], options: Sequence[TopicOption]
) -> list[Message]:
    """Classification C1: every part of a paper in one call, with the module's topics."""
    return [
        system(
            "You classify the parts of a university test paper by the module's topics and by "
            'question type. Reply in JSON: {"questions": [{"number", "topics", "type"}]}, one '
            "entry per part number given, in the same order.\n\n" + CLASSIFY_RULES
        ),
        user(
            f"Topics:\n{topic_list(options)}\n\nParts to classify: {', '.join(numbers)}\n\n"
            f"Paper:\n{paper_text(pages)}"
        ),
    ]


def part_classification_messages(
    number: str, marks: float, text: str, options: Sequence[TopicOption]
) -> list[Message]:
    """Classification C2: one part, with its candidate topics (the closest by meaning)."""
    return [
        system(
            "You classify one part of a university test paper by topic and by question type. "
            'Reply in JSON: {"topics": [codes], "type": string}.\n\n' + CLASSIFY_RULES
        ),
        user(
            f"Candidate topics:\n{topic_list(options)}\n\n"
            f"Part {number} ({marks:g} marks):\n{text.strip()}"
        ),
    ]
