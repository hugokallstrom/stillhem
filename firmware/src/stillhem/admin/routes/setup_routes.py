from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from stillhem.auth import is_password_set, set_password

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).parent.parent.parent.parent.parent / "templates")
)


@router.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "setup.html", {"error": None})


@router.post("/setup", response_model=None)
def setup_submit(
    request: Request,
    password: str = Form(...),
    confirm: str = Form(...),
) -> HTMLResponse | RedirectResponse:
    db_path = request.app.state.db_path

    if is_password_set(db_path):
        return RedirectResponse(url="/login", status_code=302)

    if len(password) < 5:
        return templates.TemplateResponse(
            request,
            "setup.html",
            {"error": "Password must be at least 5 characters."},
            status_code=200,
        )

    if password != confirm:
        return templates.TemplateResponse(
            request,
            "setup.html",
            {"error": "Passwords do not match."},
            status_code=200,
        )

    set_password(password, db_path)
    return RedirectResponse(url="/login", status_code=302)
