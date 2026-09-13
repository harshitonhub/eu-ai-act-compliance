"""Login and logout. Public by construction -- these are the routes you reach *before*
having a session, so they're mounted outside the authenticated router."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from src.api.rate_limit import login_rate_limit
from src.auth.sessions import COOKIE_NAME, DEFAULT_MAX_AGE_SECONDS, issue_session
from src.auth.users import authenticate
from src.persistence.db import get_session

router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "web" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["public_page"] = True


@router.get("/login", response_class=HTMLResponse)
def show_login(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {})


@router.post("/login")
def submit_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
    _rate_limit: None = Depends(login_rate_limit),
):
    """Rate-limited on its own budget (see src/api/rate_limit.py): an unauthenticated
    endpoint doing 600k PBKDF2 iterations per call is both a credential-stuffing target
    and a CPU-exhaustion one."""
    user = authenticate(session, email, password)
    if user is None:
        # One message for both "no such user" and "wrong password" -- see users.authenticate.
        return templates.TemplateResponse(
            request,
            "login.html",
            {"email": email, "error": "Incorrect email or password."},
            status_code=401,
        )

    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        COOKIE_NAME,
        issue_session(user.id),
        max_age=DEFAULT_MAX_AGE_SECONDS,
        httponly=True,  # not readable by JS, so an XSS bug can't lift the session
        samesite="lax",  # blocks the cookie on cross-site POSTs, i.e. basic CSRF cover
        secure=request.url.scheme == "https",
    )
    return response


@router.post("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response
