"""Regenerate the extraction fixtures in this folder (small, synthetic: no course material).

    uv run python -m tests.fixtures.make_fixtures

- lecture.pdf: 3 pages; page 2 holds only an image (a "scanned" page)
- protected.pdf: lecture.pdf with a user password
- slides.pptx: 3 slides; titles, bullets, speaker notes, and a picture-only slide
- notes.docx: two headed sections, a table, and a long section that splits by length

``slide_deck_pdf`` and ``notes_docx`` build other synthetic documents (the demo seed uses them).
"""

import io
import struct
import zlib
from pathlib import Path

import pikepdf
from docx import Document
from pptx import Presentation
from pptx.util import Inches

HERE = Path(__file__).parent

LONG_SENTENCE = (
    "Quality attributes such as availability and modifiability shape every architectural "
    "decision a team makes. "
)  # 16 words


def _pdf(pages: list[bytes | None]) -> bytes:
    """A minimal PDF. Each page is a text content stream, or None for an image-only page."""
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    pixels = bytes(range(0, 256, 4)) * 4  # 16x16 grey gradient
    image = add(
        b"<< /Type /XObject /Subtype /Image /Width 16 /Height 16 /ColorSpace /DeviceGray "
        b"/BitsPerComponent 8 /Length %d >>\nstream\n" % len(pixels) + pixels + b"\nendstream"
    )
    pages_id = len(objects) + 1 + 2 * len(pages)  # after every page and content object
    kids = []
    for text in pages:
        if text is None:
            content = b"q 400 0 0 400 100 200 cm /Im1 Do Q"
        else:
            lines = [line.replace(b"(", b"\\(").replace(b")", b"\\)") for line in text.split(b"\n")]
            ops = b"".join(b"(%s) Tj 0 -18 Td " % line for line in lines)
            content = b"BT /F1 12 Tf 72 760 Td " + ops + b"ET"
        stream = add(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        page = add(
            b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 595 842] /Contents %d 0 R "
            b"/Resources << /Font << /F1 %d 0 R >> /XObject << /Im1 %d 0 R >> >> >>"
            % (pages_id, stream, font, image)
        )
        kids.append(page)
    assert (
        add(
            b"<< /Type /Pages /Kids [%s] /Count %d >>"
            % (b" ".join(b"%d 0 R" % k for k in kids), len(kids))
        )
        == pages_id
    )
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)
    return _serialise(objects, catalog)


def _serialise(objects: list[bytes], catalog: int) -> bytes:
    """Numbered objects (1-based, in order), the xref table and the trailer."""
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(
        b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objects) + 1, catalog, xref)
    )
    return out.getvalue()


def _png(width: int = 8, height: int = 8) -> bytes:
    raw = b"".join(b"\x00" + bytes([(x * 32) % 256 for x in range(width)]) for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _pdf_text(text: str) -> bytes:
    """A PDF string literal's contents (Helvetica, WinAnsi: keep to ASCII)."""
    raw = text.encode("ascii")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


# A 16:9 slide in points, with an orange band along the top (the design system's default
# module colour) so a rendered page reads as a slide.
SLIDE_WIDTH, SLIDE_HEIGHT = 960, 540


def slide_deck_pdf(slides: list[tuple[str, list[str]]]) -> bytes:
    """A synthetic lecture deck: one 16:9 page per (title, bullets), with a real text layer.

    Used by tests and by the demo seed (scripts/demo_seed.py); the text is the caller's own.
    """
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    regular = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    pages_id = len(objects) + 1 + 2 * len(slides)
    kids = []
    for number, (title, bullets) in enumerate(slides, start=1):
        ops = [
            b"1 0.478 0.239 rg 0 %d %d 14 re f" % (SLIDE_HEIGHT - 14, SLIDE_WIDTH),
            b"0.067 0.067 0.067 rg",
            b"BT /F2 34 Tf 64 %d Td (%s) Tj ET" % (SLIDE_HEIGHT - 96, _pdf_text(title)),
        ]
        y = SLIDE_HEIGHT - 168
        for bullet in bullets:
            ops.append(b"BT /F1 21 Tf 80 %d Td (- %s) Tj ET" % (y, _pdf_text(bullet)))
            y -= 40
        ops.append(b"0.357 0.357 0.357 rg BT /F1 12 Tf 64 28 Td (%d) Tj ET" % number)
        content = b"\n".join(ops)
        stream = add(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        kids.append(
            add(
                b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R "
                b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> >>"
                % (pages_id, SLIDE_WIDTH, SLIDE_HEIGHT, stream, regular, bold)
            )
        )
    assert (
        add(
            b"<< /Type /Pages /Kids [%s] /Count %d >>"
            % (b" ".join(b"%d 0 R" % k for k in kids), len(kids))
        )
        == pages_id
    )
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)
    return _serialise(objects, catalog)


def notes_docx(sections: list[tuple[str, list[str]]]) -> bytes:
    """Synthetic study notes: a heading and paragraphs per section (the caller's own text)."""
    doc = Document()
    for heading, paragraphs in sections:
        doc.add_heading(heading, level=1)
        for paragraph in paragraphs:
            doc.add_paragraph(paragraph)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def make_pdfs() -> None:
    lecture = _pdf(
        [
            b"Week 3: Layered architecture\nEach layer only calls the layer below it.\n"
            b"Layers make change local but can cost performance.",
            None,
            b"Pipes and filters\nFilters transform a stream of data; pipes connect them.",
        ]
    )
    (HERE / "lecture.pdf").write_bytes(lecture)
    with pikepdf.open(io.BytesIO(lecture)) as pdf:
        pdf.save(
            HERE / "protected.pdf",
            encryption=pikepdf.Encryption(user="secret", owner="owner-secret", R=4),
        )


def make_pptx() -> None:
    deck = Presentation()
    title_and_content = deck.slide_layouts[1]
    blank = deck.slide_layouts[6]

    slide = deck.slides.add_slide(title_and_content)
    slide.shapes.title.text = "Architectural styles"
    body = slide.placeholders[1].text_frame
    body.text = "Layered"
    body.add_paragraph().text = "Pipes and filters"
    body.add_paragraph().text = "Event-driven"
    slide.notes_slide.notes_text_frame.text = "Ask the class which style their project uses."

    slide = deck.slides.add_slide(title_and_content)
    slide.shapes.title.text = "Quality attributes"
    slide.placeholders[1].text_frame.text = "Availability, modifiability, performance"

    slide = deck.slides.add_slide(blank)  # a picture and nothing else
    slide.shapes.add_picture(io.BytesIO(_png()), Inches(1), Inches(1), Inches(4), Inches(4))

    deck.save(str(HERE / "slides.pptx"))


def make_docx() -> None:
    doc = Document()
    doc.add_heading("Week 1: Introduction", level=1)
    doc.add_paragraph("Software architecture is the set of significant design decisions.")
    table = doc.add_table(rows=2, cols=2)
    for row, (term, meaning) in enumerate(
        [("ADR", "Decision record"), ("QA", "Quality attribute")]
    ):
        table.cell(row, 0).text = term
        table.cell(row, 1).text = meaning
    doc.add_heading("Week 2: Quality attributes", level=1)
    # ~1,700 words with no heading: split into pages of about 800 words.
    for _ in range(18):
        doc.add_paragraph(LONG_SENTENCE * 6)
    doc.save(str(HERE / "notes.docx"))


def main() -> None:
    make_pdfs()
    make_pptx()
    make_docx()
    for path in sorted(HERE.glob("*.*")):
        if path.suffix != ".py":
            print(f"{path.name}: {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
