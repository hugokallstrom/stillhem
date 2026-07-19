from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from stillhem.auth import check_password, create_session_token, validate_session_token
from stillhem.admin.deps import require_auth

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent.parent.parent / "templates"))


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
def login(request: Request, password: str = Form(...)):
    db_path = request.app.state.db_path
    if not check_password(password, db_path):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid password."},
            status_code=200,
        )
    token = create_session_token(db_path)
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie("session", token, httponly=True, samesite="strict")
    return response


@router.post("/logout")
def logout(request: Request, _token: str = Depends(require_auth)):
    from stillhem.db import get_db
    db_path = request.app.state.db_path
    with get_db(db_path) as conn:
        conn.execute("DELETE FROM config WHERE key = 'session_token'")
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session")
    return response
