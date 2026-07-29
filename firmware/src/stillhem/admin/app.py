import os
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from stillhem.admin.routes.auth_routes import routes as auth_routes
from stillhem.admin.routes.blocklist_routes import routes as blocklist_routes
from stillhem.admin.routes.router_routes import routes as router_setup_routes
from stillhem.admin.routes.setup_routes import routes as setup_routes
from stillhem.admin.routes.wizard_routes import routes as wizard_routes
from stillhem.blocklist import ACTIVE_BLOCKLIST_PATH
from stillhem.dns_control import DEFAULT_TEMPLATE_DIR, UNBOUND_CONF_PATH

STATIC_DIR = Path(__file__).parent.parent.parent.parent / "static"


class ModeGate(BaseHTTPMiddleware):
    """In setup mode, funnel every non-wizard request to the wizard; once the
    box is configured, the wizard is off-limits. Runs before routing so even
    unmatched paths (captive-portal probes like /generate_204) are redirected.
    """

    async def dispatch(self, request, call_next):
        path = request.url.path
        is_wizard = path == "/wizard" or path.startswith("/wizard/")
        is_static = path == "/static" or path.startswith("/static/")
        if request.app.state.setup_mode:
            if not (is_wizard or is_static):
                # /wizard resolves to the outstanding step — which is not always
                # Wi-Fi (Ethernet-only boards skip it).
                return RedirectResponse(url="/wizard", status_code=302)
        elif is_wizard:
            return RedirectResponse(url="/", status_code=302)
        return await call_next(request)


def create_app(
    db_path: Path,
    blocklist_path: Path = ACTIVE_BLOCKLIST_PATH,
    unbound_conf_path: Path = UNBOUND_CONF_PATH,
    template_dir: Path = DEFAULT_TEMPLATE_DIR,
    setup_mode: bool = False,
) -> Starlette:
    routes = [
        *auth_routes,
        *blocklist_routes,
        *router_setup_routes,
        *setup_routes,
        *wizard_routes,
        Mount("/static", app=StaticFiles(directory=str(STATIC_DIR)), name="static"),
    ]
    app = Starlette(routes=routes, middleware=[Middleware(ModeGate)])
    app.state.db_path = db_path
    app.state.blocklist_path = blocklist_path
    app.state.unbound_conf_path = unbound_conf_path
    app.state.template_dir = template_dir
    app.state.setup_mode = setup_mode
    return app


app = create_app(
    db_path=Path(os.environ.get("STILLHEM_DB_PATH", "/var/lib/stillhem/stillhem.db")),
    blocklist_path=Path(os.environ.get("STILLHEM_BLOCKLIST_PATH", str(ACTIVE_BLOCKLIST_PATH))),
    unbound_conf_path=Path(os.environ.get("STILLHEM_UNBOUND_CONF", str(UNBOUND_CONF_PATH))),
    template_dir=Path(os.environ.get("STILLHEM_DNS_TEMPLATE_DIR", str(DEFAULT_TEMPLATE_DIR))),
)
