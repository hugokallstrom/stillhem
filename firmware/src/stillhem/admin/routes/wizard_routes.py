import subprocess
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from stillhem import netmode
from stillhem.auth import is_password_set, set_password
from stillhem.blocklist import import_preset
from stillhem.db import get_config, set_config
from stillhem.dns_control import reload_dns

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).parent.parent.parent.parent.parent / "templates")
)

PRESETS = ["social_only", "social_news", "hard_mode"]


def _current_step(db_path: Path) -> str:
    if not get_config(db_path, "home_wifi_ssid"):
        return "/wizard/wifi"
    if not get_config(db_path, "wizard_preset"):
        return "/wizard/preset"
    if not is_password_set(db_path):
        return "/wizard/password"
    return "/wizard/done"


def _guard(request: Request):
    """Snap a wizard GET to the current step; returns a redirect or None."""
    step = _current_step(request.app.state.db_path)
    if request.url.path != step:
        return RedirectResponse(url=step, status_code=302)
    return None


@router.get("/wizard/wifi", response_class=HTMLResponse)
def wifi_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    networks = netmode.read_cached_scan()
    return templates.TemplateResponse(request, "wizard_wifi.html", {"networks": networks, "error": None})


@router.post("/wizard/wifi")
def wifi_submit(
    request: Request,
    ssid: str = Form(""),
    ssid_manual: str = Form(""),
    password: str = Form(""),
):
    # A typed-in network name takes precedence over the dropdown selection.
    chosen = ssid_manual.strip() or ssid.strip()
    if not chosen:
        networks = netmode.read_cached_scan()
        return templates.TemplateResponse(
            request, "wizard_wifi.html",
            {"networks": networks, "error": "Please choose or enter a network."}, status_code=200)
    db_path = request.app.state.db_path
    set_config(db_path, "home_wifi_ssid", chosen)
    set_config(db_path, "home_wifi_psk", password)
    return RedirectResponse(url="/wizard/preset", status_code=302)


@router.get("/wizard/preset", response_class=HTMLResponse)
def preset_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "wizard_preset.html", {"presets": PRESETS, "error": None})


@router.post("/wizard/preset")
def preset_submit(request: Request, preset: str = Form(...)):
    db_path = request.app.state.db_path
    if preset not in PRESETS:
        return templates.TemplateResponse(
            request, "wizard_preset.html",
            {"presets": PRESETS, "error": "Please choose a preset."}, status_code=200)
    import_preset(preset, db_path)
    set_config(db_path, "wizard_preset", preset)
    reload_dns(
        db_path,
        request.app.state.blocklist_path,
        request.app.state.unbound_conf_path,
        request.app.state.template_dir,
    )
    return RedirectResponse(url="/wizard/password", status_code=302)


@router.get("/wizard/password", response_class=HTMLResponse)
def password_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "wizard_password.html", {"error": None})


@router.post("/wizard/password")
def password_submit(request: Request, password: str = Form(...), confirm: str = Form(...)):
    db_path = request.app.state.db_path
    if len(password) < 5:
        return templates.TemplateResponse(
            request, "wizard_password.html",
            {"error": "Password must be at least 5 characters."}, status_code=200)
    if password != confirm:
        return templates.TemplateResponse(
            request, "wizard_password.html",
            {"error": "Passwords do not match."}, status_code=200)
    set_password(password, db_path)
    return RedirectResponse(url="/wizard/done", status_code=302)


@router.get("/wizard/done", response_class=HTMLResponse)
def done_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    ssid = get_config(request.app.state.db_path, "home_wifi_ssid") or "your home network"
    return templates.TemplateResponse(request, "wizard_done.html", {"ssid": ssid})


@router.post("/wizard/finish")
def finish(request: Request):
    db_path = request.app.state.db_path
    if _current_step(db_path) != "/wizard/done":
        return RedirectResponse(url=_current_step(db_path), status_code=302)
    ssid = get_config(db_path, "home_wifi_ssid") or ""
    psk = get_config(db_path, "home_wifi_psk") or ""
    netmode.save_home_wifi(ssid, psk)
    netmode.mark_setup_complete()
    # Deferred so the HTTP response flushes before the box reboots.
    subprocess.Popen(["systemd-run", "--on-active=3", "systemctl", "reboot"])
    return templates.TemplateResponse(request, "wizard_done.html", {"ssid": ssid, "restarting": True})
