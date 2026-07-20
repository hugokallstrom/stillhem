from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from stillhem.admin.deps import require_auth
from stillhem.netinfo import primary_ip

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).parent.parent.parent.parent.parent / "templates")
)


@router.get("/router", response_class=HTMLResponse)
def router_page(request: Request, _token: str = Depends(require_auth)) -> HTMLResponse:
    return templates.TemplateResponse(request, "router.html", {"pi_ip": primary_ip()})
