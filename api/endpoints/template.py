"""
GET /api/v1/download_template

Returns a dynamically generated Excel template (.xlsx) as a file download.
No static file dependency — workbook is built in-memory on every request.
"""

import io
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from templates.excel_generator import (
    build_template_bytes,
    FILENAME,
    TEMPLATE_VERSION,
)
from auth.dependencies import get_current_user
from db.models import User

router = APIRouter()


@router.get(
    "/download_template",
    summary="Download Excel CSV Template",
    description=(
        "Download the standardised Excel template (.xlsx). "
        "Fill in your OHLCV + indicator data, then export as **CSV UTF-8** "
        "and upload via `POST /api/v1/upload_csv`."
    ),
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}
            },
            "description": f"Excel template v{TEMPLATE_VERSION}",
        }
    },
)
async def download_template(user: User = Depends(get_current_user)) -> StreamingResponse:
    xlsx_bytes = build_template_bytes()
    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{FILENAME}"',
            "Content-Length": str(len(xlsx_bytes)),
            "Cache-Control": "no-cache",
        },
    )
