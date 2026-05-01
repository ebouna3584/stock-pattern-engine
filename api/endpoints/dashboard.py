import os
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard():
    html_path = os.path.join(os.path.dirname(__file__), "../../frontend/index.html")
    with open(os.path.abspath(html_path), "r") as f:
        return HTMLResponse(content=f.read())
