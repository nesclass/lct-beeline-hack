from fastapi import APIRouter

from .. import scenarios

router = APIRouter(prefix="/api")


@router.get("/scenarios")
def listing():
    return scenarios.listing()
