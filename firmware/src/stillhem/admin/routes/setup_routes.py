from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from stillhem.auth import is_password_set, set_password

templates = Jinja2Templates(
    directory=str(Path(__file__).parent.parent.parent.parent.parent / "templates")
)


async def setup_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "setup.html", {"error": None})


async def setup_submit(request: Request):
    form = await request.form()
    password = form.get("password", "")
    confirm = form.get("confirm", "")
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


routes = [
    Route("/setup", setup_page, methods=["GET"]),
    Route("/setup", setup_submit, methods=["POST"]),
]
