# coding: utf-8
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..db import get_metadata

router = APIRouter()


@router.get('/{node:int}/metadata/', name='metadata')
async def metadata(node: int):
    return JSONResponse(await get_metadata())
