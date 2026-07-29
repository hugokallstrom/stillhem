from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from stillhem.admin.deps import require_auth
from stillhem.netinfo import primary_ip

templates = Jinja2Templates(
    directory=str(Path(__file__).parent.parent.parent.parent.parent / "templates")
)


async def router_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "router.html", {"pi_ip": primary_ip()})


routes = [
    Route("/router", router_page, methods=["GET"]),
]
