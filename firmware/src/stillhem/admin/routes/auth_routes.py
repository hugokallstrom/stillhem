from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from stillhem.auth import check_password, create_session_token
from stillhem.admin.deps import require_auth

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent.parent.parent / "templates"))


async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"error": None})


async def login(request: Request):
    form = await request.form()
    password = form.get("password", "")
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


async def logout(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    from stillhem.db import get_db
    db_path = request.app.state.db_path
    with get_db(db_path) as conn:
        conn.execute("DELETE FROM config WHERE key = 'session_token'")
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session")
    return response


routes = [
    Route("/login", login_page, methods=["GET"]),
    Route("/login", login, methods=["POST"]),
    Route("/logout", logout, methods=["POST"]),
]
