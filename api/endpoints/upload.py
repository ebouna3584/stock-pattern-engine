"""
POST /upload_csv

Accepts a CSV file upload, validates it, and stores the parsed
DataFrame in a simple in-memory session store (upgrade to Redis/DB in prod).
"""

import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException
from models.schemas import UploadResponse
from models.enums import ValidationStatus
from core.validator import validate_csv

router = APIRouter()

# In-memory session store. Replace with Redis or a database in production.
_session_store: dict = {}


@router.post("/upload_csv", response_model=UploadResponse)
async def upload_csv(file: UploadFile = File(...)) -> UploadResponse:
    """
    Upload a CSV file conforming to the stock pattern engine template.

    Returns a session_id to use in subsequent /analyze calls.
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    file_bytes = await file.read()
    validation, df = validate_csv(file_bytes)

    if validation.status == ValidationStatus.INVALID:
        # Return 422 with all error details so the user knows exactly what to fix
        raise HTTPException(
            status_code=422,
            detail={
                "message": "CSV validation failed. Please fix the errors and re-upload.",
                "errors": validation.errors,
                "warnings": validation.warnings,
            },
        )

    session_id = str(uuid.uuid4())
    _session_store[session_id] = df

    return UploadResponse(
        session_id=session_id,
        validation=validation,
        message=(
            f"Upload successful. {validation.row_count} rows loaded for ticker(s): "
            f"{df['ticker'].unique().tolist()}. "
            f"Use session_id '{session_id}' to run /analyze."
        ),
    )


def get_session_df(session_id: str):
    """Retrieve a stored DataFrame by session_id."""
    df = _session_store.get(session_id)
    if df is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found. Please re-upload your CSV.",
        )
    return df
