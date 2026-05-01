from fastapi import APIRouter

api_router = APIRouter()

def register_routes():
    from api.endpoints import upload, analyze, report, template

    api_router.include_router(template.router, tags=["Template"])
    api_router.include_router(upload.router, tags=["Upload"])
    api_router.include_router(analyze.router, tags=["Analysis"])
    api_router.include_router(report.router, tags=["Reports"])