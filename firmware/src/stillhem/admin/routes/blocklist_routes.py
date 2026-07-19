from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from stillhem.admin.deps import require_auth
from stillhem.blocklist import add_domain, list_domains, remove_domain
from stillhem.dns_control import is_unbound_running, reload_dns

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).parent.parent.parent.parent.parent / "templates")
)


def _dashboard_response(request: Request) -> HTMLResponse:
    db_path = request.app.state.db_path
    domains = list_domains(db_path)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "domains": domains,
            "domain_count": len(domains),
            "blocking_active": is_unbound_running(),
        },
    )


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, _token: str = Depends(require_auth)) -> HTMLResponse:
    return _dashboard_response(request)


@router.post("/blocklist/add")
def blocklist_add(
    request: Request,
    domain: str = Form(...),
    _token: str = Depends(require_auth),
):
    if not domain.strip():
        return RedirectResponse(url="/", status_code=302)
    db_path = request.app.state.db_path
    add_domain(domain, db_path)
    reload_dns(
        db_path,
        request.app.state.blocklist_path,
        request.app.state.unbound_conf_path,
        request.app.state.template_dir,
    )
    return RedirectResponse(url="/", status_code=302)


@router.post("/blocklist/remove")
def blocklist_remove(
    request: Request,
    domain: str = Form(...),
    _token: str = Depends(require_auth),
):
    db_path = request.app.state.db_path
    remove_domain(domain, db_path)
    reload_dns(
        db_path,
        request.app.state.blocklist_path,
        request.app.state.unbound_conf_path,
        request.app.state.template_dir,
    )
    return RedirectResponse(url="/", status_code=302)
