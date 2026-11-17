import re
import uuid
from collections.abc import Iterator
from typing import Annotated, BinaryIO
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    Path,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.core.db import SessionDep
from app.models import Material, MaterialPage
from app.schemas.materials import (
    MaterialKind,
    MaterialOut,
    MaterialUpdate,
    PageOut,
    PageSummary,
)
from app.services import materials
from app.services.errors import TooLarge
from app.storage.base import Storage
from app.storage.local import get_storage

router = APIRouter(tags=["materials"])

StorageDep = Annotated[Storage, Depends(get_storage)]
# Room for the multipart boundaries and the other form fields.
_FORM_OVERHEAD = 64 * 1024


@router.post(
    "/modules/{module_id}/materials",
    response_model=MaterialOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_material(
    module_id: uuid.UUID,
    request: Request,
    file: Annotated[UploadFile, File(description="PDF, PPTX, DOCX, MD, TXT, PNG or JPG")],
    kind: Annotated[MaterialKind, Form()],
    session: SessionDep,
    user: CurrentUser,
    storage: StorageDep,
    title: Annotated[str | None, Form(max_length=200)] = None,
    allow_ai: Annotated[bool, Form()] = True,
) -> Material:
    """Upload one file (at most 50 MB) to the module and queue it for processing.

    The same file twice in one module is a 409; a wrong type is a 415.
    """
    limit = get_settings().max_upload_bytes
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit + _FORM_OVERHEAD:
        raise TooLarge(f"Files can be at most {limit // (1024 * 1024)} MB.")
    return await materials.upload_material(
        session,
        storage,
        module_id,
        user_id=user.id,
        source=file.file,
        filename=file.filename or "",
        kind=kind,
        title=title,
        allow_ai=allow_ai,
        max_bytes=limit,
    )


@router.get("/modules/{module_id}/materials", response_model=list[MaterialOut])
async def list_materials(
    module_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> list[Material]:
    """The module's materials, newest first."""
    return await materials.list_materials(session, module_id, user_id=user.id)


@router.get("/materials/{material_id}", response_model=MaterialOut)
async def get_material(material_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> Material:
    return await materials.get_material(session, material_id, user_id=user.id)


@router.patch("/materials/{material_id}", response_model=MaterialOut)
async def update_material(
    material_id: uuid.UUID, data: MaterialUpdate, session: SessionDep, user: CurrentUser
) -> Material:
    """Change the title, the kind or whether AI may process it."""
    return await materials.update_material(session, material_id, data, user_id=user.id)


@router.delete("/materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_material(
    material_id: uuid.UUID, session: SessionDep, user: CurrentUser, storage: StorageDep
) -> None:
    """Delete the material (its file too, unless another of your modules has the same file)."""
    await materials.delete_material(session, storage, material_id, user_id=user.id)


@router.post("/materials/{material_id}/retry", response_model=MaterialOut)
async def retry_material(
    material_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> Material:
    """Queue a failed material for processing again."""
    return await materials.retry_material(session, material_id, user_id=user.id)


@router.get("/materials/{material_id}/pages", response_model=list[PageSummary])
async def list_pages(
    material_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> list[MaterialPage]:
    """The extracted pages (without their text), in order. Empty until extraction has run."""
    return await materials.list_pages(session, material_id, user_id=user.id)


@router.get("/materials/{material_id}/pages/{page_number}", response_model=PageOut)
async def get_page(
    material_id: uuid.UUID,
    page_number: Annotated[int, Path(ge=1)],
    session: SessionDep,
    user: CurrentUser,
) -> MaterialPage:
    """One page's extracted text."""
    return await materials.get_page(session, material_id, page_number, user_id=user.id)


_CHUNK = 64 * 1024
# A year: the blob is content-addressed (its sha256), so a URL's bytes never change.
_IMMUTABLE = "private, max-age=31536000, immutable"


def _chunks(stream: BinaryIO) -> Iterator[bytes]:
    try:
        while chunk := stream.read(_CHUNK):
            yield chunk
    finally:
        stream.close()


def content_disposition(filename: str) -> str:
    """``inline`` with the filename: an ASCII fallback and the RFC 5987 UTF-8 form."""
    fallback = re.sub(r'[^\x20-\x7e]|["\\]', "_", filename) or "file"
    return f"inline; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


def _matches(if_none_match: str | None, etag: str) -> bool:
    if if_none_match is None:
        return False
    tags = [tag.strip().removeprefix("W/") for tag in if_none_match.split(",")]
    return "*" in tags or etag in tags


@router.get(
    "/materials/{material_id}/file",
    response_class=StreamingResponse,
    responses={
        200: {"description": "The original file, as uploaded", "content": {"*/*": {}}},
        304: {"description": "Not modified (If-None-Match matched the ETag)"},
    },
)
async def get_material_file(
    material_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    storage: StorageDep,
    if_none_match: Annotated[str | None, Header()] = None,
) -> Response:
    """The original file, for the viewer. Cached for good (the ETag is its sha256), so an
    If-None-Match with that ETag gets a 304. 404 for another user's material or a lost file."""
    opened = await materials.open_file(session, storage, material_id, user_id=user.id)
    material = opened.material
    etag = f'"{material.sha256}"'
    headers = {"ETag": etag, "Cache-Control": _IMMUTABLE, "X-Content-Type-Options": "nosniff"}
    if _matches(if_none_match, etag):
        opened.stream.close()
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    headers |= {
        "Content-Disposition": content_disposition(material.original_filename),
        "Content-Length": str(opened.size),
    }
    return StreamingResponse(
        _chunks(opened.stream), media_type=material.content_type, headers=headers
    )
