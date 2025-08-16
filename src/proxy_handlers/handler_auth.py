import logging
from fastapi import Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
import hashlib
import time
from cachetools import TTLCache

logger = logging.getLogger(__name__)

AUTH_COOKIE_NAME = "emby_proxy_auth"
LOGIN_PAGE_PATH = "/auth/login"
VERIFY_PATH = "/auth/verify"
SALT = "emby_virtual_proxy_salt"

# Cache to store trusted IP addresses for 24 hours (86400 seconds)
trusted_ips = TTLCache(maxsize=1024, ttl=86400)

def get_password_hash(password: str) -> str:
    return hashlib.sha256((password + SALT).encode()).hexdigest()

def create_login_page():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Password Protection</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background-color: #141414; color: #fff; }
            .container { background-color: #1e1e1e; padding: 2rem; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); text-align: center; }
            h1 { margin-bottom: 1.5rem; }
            input[type="password"] { width: 80%; padding: 0.8rem; margin-bottom: 1.5rem; border: 1px solid #444; border-radius: 4px; background-color: #333; color: #fff; font-size: 1rem; }
            button { padding: 0.8rem 1.5rem; border: none; border-radius: 4px; background-color: #00a4dc; color: #fff; font-size: 1rem; cursor: pointer; transition: background-color 0.2s; }
            button:hover { background-color: #007b9e; }
            .error { color: #e50914; margin-top: 1rem; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>请输入密码</h1>
            <form action="/auth/verify" method="post">
                <input type="password" name="password" placeholder="Password" required>
                <br>
                <button type="submit">进入</button>
            </form>
        </div>
    </body>
    </html>
    """

async def handle_auth(request: Request, full_path: str, config: object) -> Response:
    if not getattr(config, 'enable_access_control', False):
        return None

    client_ip = request.client.host
    
    # 1. Check if IP is already trusted
    if client_ip in trusted_ips:
        return None

    password = getattr(config, 'proxy_password', None)
    authorized_keys = getattr(config, 'authorized_api_keys', [])

    if not password and not authorized_keys:
        return None

    # 2. Check for whitelisted API key
    api_key = request.headers.get("X-Emby-Token") or request.query_params.get("api_key")
    if api_key and api_key in authorized_keys:
        logger.info(f"Access granted for client {client_ip} via whitelisted API key. Trusting for 24 hours.")
        trusted_ips[client_ip] = True
        return None

    # 3. Check for auth cookie (for browsers)
    if password:
        auth_cookie = request.cookies.get(AUTH_COOKIE_NAME)
        if auth_cookie and auth_cookie == get_password_hash(password):
            logger.info(f"Access granted for client {client_ip} via valid cookie. Trusting for 24 hours.")
            trusted_ips[client_ip] = True
            return None

    # Allow access to the login page and verification endpoint itself
    if full_path.startswith("auth/"):
        return None

    # 4. If not authenticated, decide how to respond
    accept_header = request.headers.get("accept", "")
    if "html" in accept_header and password:
        logger.info(f"Authentication required for {full_path} from {client_ip}. Redirecting to login.")
        return RedirectResponse(url=LOGIN_PAGE_PATH)

    if api_key:
        logger.warning(f"Access denied for {client_ip} with unauthorized API key: {api_key}")
    else:
        logger.warning(f"Unauthenticated request for non-HTML resource '{full_path}' from {client_ip}. Denying with 401.")
        
    return Response(status_code=401, content="Unauthorized")


async def handle_login_page(request: Request, full_path: str) -> Response:
    if full_path == "auth/login":
        return HTMLResponse(content=create_login_page())
    return None

async def handle_verify_password(request: Request, full_path: str, config: object) -> Response:
    if full_path == "auth/verify" and request.method == "POST":
        form = await request.form()
        submitted_password = form.get("password")
        correct_password = getattr(config, 'proxy_password', None)
        client_ip = request.client.host

        if submitted_password and correct_password and submitted_password == correct_password:
            response = RedirectResponse(url="/", status_code=303)
            hashed_password = get_password_hash(correct_password)
            response.set_cookie(
                key=AUTH_COOKIE_NAME,
                value=hashed_password,
                httponly=True,
                max_age=86400 * 30,  # 30 days
                path='/',
                samesite='lax'
            )
            logger.info(f"Password correct for {client_ip}. Setting auth cookie and trusting IP for 24 hours.")
            trusted_ips[client_ip] = True
            return response
        else:
            logger.warning(f"Incorrect password submitted from {client_ip}.")
            return RedirectResponse(url=LOGIN_PAGE_PATH + "?error=1", status_code=303)
    return None
