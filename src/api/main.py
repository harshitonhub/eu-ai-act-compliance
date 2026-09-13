from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.api.auth import NotAuthenticated, NotAuthorised, get_current_user
from src.api.routers.ai_risk_check import router as ai_risk_check_router
from src.api.routers.assessment import router as assessment_router
from src.api.routers.auth_routes import router as auth_router
from src.persistence.tenancy import TenantIsolationError

app = FastAPI(title="EU AI Act Compliance Platform")

# Depending on get_current_user at router level does double duty: it rejects anonymous
# requests, and it binds the tenant context every query in these routes relies on.
app.include_router(assessment_router, dependencies=[Depends(get_current_user)])
app.include_router(auth_router)  # public: /login, /logout
app.include_router(ai_risk_check_router)  # public, no auth


@app.exception_handler(NotAuthenticated)
def _redirect_to_login(_request: Request, _exc: NotAuthenticated) -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(NotAuthorised)
def _forbidden(_request: Request, exc: NotAuthorised) -> HTMLResponse:
    return HTMLResponse(f"<h1>403 Forbidden</h1><p>{exc}</p>", status_code=403)


@app.exception_handler(TenantIsolationError)
def _tenant_isolation_failure(_request: Request, _exc: TenantIsolationError) -> HTMLResponse:
    """A tenant-isolation failure is a bug in this application, never a user error. It
    surfaces as a generic 500 with no detail -- the specifics go to the logs, not to
    whoever tripped it, since they would describe another tenant's data boundary."""
    return HTMLResponse("<h1>500 Internal Server Error</h1>", status_code=500)


@app.exception_handler(HTTPException)
def _http_error_as_html(request: Request, exc: HTTPException):
    """These routes render HTML for a browser, so errors should too -- the default JSON
    body is jarring mid-session. Note what is *not* here: a 404 for another tenant's
    record says only "not found", never "exists but is not yours", which would confirm
    the id and leak the fact that the record exists at all."""
    if exc.status_code == 404:
        return HTMLResponse(
            "<h1>404 Not Found</h1><p>No such record. "
            '<a href="/history">Back to my AI systems</a></p>',
            status_code=404,
        )
    return HTMLResponse(f"<h1>{exc.status_code}</h1><p>{exc.detail}</p>", status_code=exc.status_code)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
