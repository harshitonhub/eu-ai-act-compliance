from fastapi import Depends, FastAPI

from src.api.auth import require_auth
from src.api.routers.assessment import router as assessment_router
from src.api.routers.hiring_check import router as hiring_check_router

app = FastAPI(title="EU AI Act Compliance Platform")
app.include_router(assessment_router, dependencies=[Depends(require_auth)])
app.include_router(hiring_check_router)  # public, no auth -- see ROADMAP.md's committed niche


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
