"""Small valid files of each allowed type, built in code (no binary fixtures in git)."""

import io
import zipfile

import pypdfium2 as pdfium

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


def pdf(pages: int = 3) -> bytes:
    document = pdfium.PdfDocument.new()
    for _ in range(pages):
        document.new_page(595, 842)
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def _zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def pptx(slides: int = 4) -> bytes:
    files = {f"ppt/slides/slide{i}.xml": "<p:sld/>" for i in range(1, slides + 1)}
    files["ppt/slides/_rels/slide1.xml.rels"] = "<Relationships/>"
    files["ppt/presentation.xml"] = "<p:presentation/>"
    return _zip(files)


def docx(pages: int | None = 2) -> bytes:
    files = {"word/document.xml": "<w:document/>"}
    if pages is not None:
        files["docProps/app.xml"] = (
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
            f'extended-properties"><Pages>{pages}</Pages></Properties>'
        )
    return _zip(files)


TXT = b"Layered architecture notes.\n"
MD = b"# Week 3\n\n- pipes and filters\n"
