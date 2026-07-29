import subprocess
from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from stillhem import netmode
from stillhem.auth import is_password_set, set_password
from stillhem.blocklist import import_preset
from stillhem.db import delete_config, get_config, set_config
from stillhem.dns_control import reload_dns

templates = Jinja2Templates(
    directory=str(Path(__file__).parent.parent.parent.parent.parent / "templates")
)

PRESETS = ["social_only", "social_news", "hard_mode"]


def _current_step(db_path: Path) -> str:
    # On Ethernet-only hardware there is no network to choose, and the box is
    # already reachable over the wire — skip straight to the content steps.
    if netmode.wifi_present() and not get_config(db_path, "home_wifi_ssid"):
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


async def wizard_index(request: Request):
    """Entry point: send the browser to whichever step is outstanding."""
    return RedirectResponse(url=_current_step(request.app.state.db_path), status_code=302)


async def wifi_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    networks = netmode.read_cached_scan()
    return templates.TemplateResponse(request, "wizard_wifi.html", {"networks": networks, "error": None})


async def wifi_submit(request: Request):
    form = await request.form()
    ssid = form.get("ssid", "")
    ssid_manual = form.get("ssid_manual", "")
    password = form.get("password", "")
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


async def preset_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "wizard_preset.html", {"presets": PRESETS, "error": None})


async def preset_submit(request: Request):
    form = await request.form()
    preset = form.get("preset", "")
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


async def password_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "wizard_password.html", {"error": None})


async def password_submit(request: Request):
    form = await request.form()
    password = form.get("password", "")
    confirm = form.get("confirm", "")
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


async def done_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    ssid = get_config(request.app.state.db_path, "home_wifi_ssid") or ""
    return templates.TemplateResponse(request, "wizard_done.html", {"ssid": ssid})


async def finish(request: Request):
    db_path = request.app.state.db_path
    if _current_step(db_path) != "/wizard/done":
        return RedirectResponse(url=_current_step(db_path), status_code=302)
    ssid = get_config(db_path, "home_wifi_ssid") or ""
    psk = get_config(db_path, "home_wifi_psk") or ""
    # No SSID means the Wi-Fi step was skipped (Ethernet-only board); saving a
    # profile for a wlan0 that does not exist would fail the request.
    if ssid:
        netmode.save_home_wifi(ssid, psk)
        # NetworkManager now owns the persistent copy of the PSK; drop the
        # plaintext one from the DB so it does not linger in the config table.
        delete_config(db_path, "home_wifi_psk")
    # Tear down the setup AP now that the box has its real network config.
    # Ethernet-only boards (e.g. Pi B+) never brought one up, so a missing
    # profile must not fail the request — match the guard-tuple precedent in
    # dns_control.py / reconcile.py.
    try:
        netmode.stop_ap()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    netmode.mark_setup_complete()
    # Deferred so the HTTP response flushes before the box reboots.
    subprocess.Popen(["systemd-run", "--on-active=3", "systemctl", "reboot"])
    return templates.TemplateResponse(request, "wizard_done.html", {"ssid": ssid, "restarting": True})


routes = [
    Route("/wizard", wizard_index, methods=["GET"]),
    Route("/wizard/wifi", wifi_page, methods=["GET"]),
    Route("/wizard/wifi", wifi_submit, methods=["POST"]),
    Route("/wizard/preset", preset_page, methods=["GET"]),
    Route("/wizard/preset", preset_submit, methods=["POST"]),
    Route("/wizard/password", password_page, methods=["GET"]),
    Route("/wizard/password", password_submit, methods=["POST"]),
    Route("/wizard/done", done_page, methods=["GET"]),
    Route("/wizard/finish", finish, methods=["POST"]),
]
