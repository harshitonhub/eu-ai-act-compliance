from fastapi import Depends, FastAPI

from src.api.auth import require_auth
from src.api.routers.assessment import router as assessment_router

app = FastAPI(title="EU AI Act Compliance Platform")
app.include_router(assessment_router, dependencies=[Depends(require_auth)])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
