from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import scenarios, uploads

router = APIRouter(prefix="/api")


class Upload(BaseModel):
    filename: str = Field(max_length=200)
    content: str = Field(max_length=2_000_000)
    title: str | None = Field(None, max_length=100)
    base: str = Field("normal", max_length=64)


@router.post("/scenarios/upload")
def upload(body: Upload):
    try:
        d = uploads.parse(body.filename, body.content, body.base, body.title)
    except uploads.Invalid as e:
        raise HTTPException(422, {"message": e.message, "errors": e.errors})
    return scenarios.save_uploaded(d)
