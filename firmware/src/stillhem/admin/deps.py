from fastapi import HTTPException, Request


def require_auth(request: Request) -> str:
    from stillhem.auth import validate_session_token
    token = request.cookies.get("session", "")
    db_path = request.app.state.db_path
    if not token or not validate_session_token(token, db_path):
        raise HTTPException(status_code=302, headers={"location": "/login"})
    return token
