from starlette.requests import Request
from starlette.responses import RedirectResponse


def require_auth(request: Request) -> RedirectResponse | None:
    """Guard for protected handlers.

    Returns a redirect to /login when the request has no valid session, or
    None when the caller may proceed. Call at the top of a handler and return
    the result immediately if it is not None.
    """
    from stillhem.auth import validate_session_token
    token = request.cookies.get("session", "")
    db_path = request.app.state.db_path
    if not token or not validate_session_token(token, db_path):
        return RedirectResponse(url="/login", status_code=302)
    return None
