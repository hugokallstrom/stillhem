import time
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from stillhem.admin.deps import require_auth
from stillhem.blocklist import (
    add_custom_domain,
    add_domain,
    clear_schedule,
    get_categories,
    list_domains,
    remove_domain,
    set_schedule,
    toggle_platform,
)
from stillhem.db import get_config, set_config
from stillhem.dns_control import is_unbound_running, reload_dns, total_queries
from stillhem.netinfo import primary_ip
from stillhem.schedule import hhmm_to_min
from stillhem.serving import is_serving, queries_per_minute

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).parent.parent.parent.parent.parent / "templates")
)


def _is_serving(db_path) -> bool:
    now = time.time()
    count = total_queries()
    serving = False
    prev = get_config(db_path, "serving_sample")
    if prev:
        try:
            prev_ts, prev_count = prev.split(":")
            qpm = queries_per_minute(float(prev_ts), int(prev_count), now, count)
            serving = is_serving(qpm)
        except ValueError:
            serving = False
    set_config(db_path, "serving_sample", f"{now}:{count}")
    return serving


def _dashboard_response(request: Request) -> HTMLResponse:
    db_path = request.app.state.db_path
    domains = list_domains(db_path)
    categories = get_categories(db_path)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "domains": domains,
            "domain_count": len(domains),
            "blocking_active": is_unbound_running(),
            "serving": _is_serving(db_path),
            "pi_ip": primary_ip(),
            "categories": categories,
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
    domain = domain.strip()
    if not domain:
        return RedirectResponse(url="/", status_code=302)
    db_path = request.app.state.db_path
    add_custom_domain(domain, db_path)
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


@router.post("/schedule/set")
def schedule_set(
    request: Request,
    category: str = Form(...),
    days: str = Form(""),          # CSV "0,5,6"
    start: str = Form("00:00"),    # "HH:MM"
    end: str = Form("00:00"),      # "HH:MM"
    _token: str = Depends(require_auth),
):
    db_path = request.app.state.db_path
    if category not in ("social", "video", "custom"):
        return RedirectResponse(url="/", status_code=302)
    raw_days = [d for d in days.split(",") if d != ""]
    if not raw_days:
        clear_schedule(db_path, category)          # explicit empty = back to toggles
    else:
        # Non-empty but malformed/out-of-range days is a bad request, not a clear:
        # don't let "0,9" or "-1" silently wipe an existing schedule.
        try:
            day_ints = [int(d) for d in raw_days]
        except ValueError:
            return RedirectResponse(url="/", status_code=302)
        if not all(0 <= d <= 6 for d in day_ints):
            return RedirectResponse(url="/", status_code=302)
        s, e = hhmm_to_min(start), hhmm_to_min(end)   # only place HH:MM<->min lives
        if s is None or e is None or s == e:
            return RedirectResponse(url="/", status_code=302)
        set_schedule(db_path, category, day_ints, s, e)
    reload_dns(
        db_path,
        request.app.state.blocklist_path,
        request.app.state.unbound_conf_path,
        request.app.state.template_dir,
    )
    return RedirectResponse(url="/", status_code=302)


@router.post("/blocklist/toggle")
def blocklist_toggle(
    request: Request,
    platform: str = Form(...),
    _token: str = Depends(require_auth),
):
    db_path = request.app.state.db_path
    try:
        toggle_platform(platform, db_path)
    except KeyError:
        return RedirectResponse(url="/", status_code=302)
    reload_dns(
        db_path,
        request.app.state.blocklist_path,
        request.app.state.unbound_conf_path,
        request.app.state.template_dir,
    )
    return RedirectResponse(url="/", status_code=302)
