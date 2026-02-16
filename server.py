import asyncio
import base64
import json
import os
import re
import secrets
import signal
import time
from collections import deque
from pathlib import Path

from starlette.applications import Starlette
from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    AuthenticationError,
    SimpleUser,
)
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.templating import Jinja2Templates

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
SECRET_FIELDS = {
    "api_key", "token", "app_secret", "encrypt_key",
    "verification_token", "bot_token", "app_token",
    "channel_secret", "channel_access_token", "client_secret",
}

CONFIG_DIR = Path(os.environ.get("PICOCLAW_HOME", Path.home() / ".picoclaw"))
CONFIG_PATH = CONFIG_DIR / "config.json"

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

if not ADMIN_PASSWORD:
    ADMIN_PASSWORD = secrets.token_urlsafe(16)
    print(f"Generated admin password: {ADMIN_PASSWORD}")


class BasicAuthBackend(AuthenticationBackend):
    async def authenticate(self, conn):
        if "Authorization" not in conn.headers:
            return None

        auth = conn.headers["Authorization"]
        try:
            scheme, credentials = auth.split()
            if scheme.lower() != "basic":
                return None
            decoded = base64.b64decode(credentials).decode("ascii")
        except (ValueError, UnicodeDecodeError):
            raise AuthenticationError("Invalid credentials")

        username, _, password = decoded.partition(":")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            return AuthCredentials(["authenticated"]), SimpleUser(username)

        raise AuthenticationError("Invalid credentials")


def require_auth(request: Request):
    if not request.user.is_authenticated:
        return PlainTextResponse(
            "Unauthorized",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="picoclaw"'},
        )
    return None


def load_config():
    if not CONFIG_PATH.exists():
        return default_config()
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception:
        return default_config()


def save_config(data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2))


def default_config():
    return {
        "agents": {
            "defaults": {
                "workspace": "~/.picoclaw/workspace",
                "restrict_to_workspace": True,
                "provider": "",
                "model": "glm-4.7",
                "max_tokens": 8192,
                "temperature": 0.7,
                "max_tool_iterations": 20,
            }
        },
        "channels": {
            "telegram": {"enabled": False, "token": "", "proxy": "", "allow_from": []},
            "discord": {"enabled": False, "token": "", "allow_from": []},
            "slack": {"enabled": False, "bot_token": "", "app_token": "", "allow_from": []},
            "whatsapp": {"enabled": False, "bridge_url": "ws://localhost:3001", "allow_from": []},
            "feishu": {"enabled": False, "app_id": "", "app_secret": "", "encrypt_key": "", "verification_token": "", "allow_from": []},
            "dingtalk": {"enabled": False, "client_id": "", "client_secret": "", "allow_from": []},
            "qq": {"enabled": False, "app_id": "", "app_secret": "", "allow_from": []},
            "line": {"enabled": False, "channel_secret": "", "channel_access_token": "", "webhook_host": "0.0.0.0", "webhook_port": 18791, "webhook_path": "/webhook/line", "allow_from": []},
            "maixcam": {"enabled": False, "host": "0.0.0.0", "port": 18790, "allow_from": []},
        },
        "providers": {
            "anthropic": {"api_key": ""},
            "openai": {"api_key": "", "api_base": ""},
            "openrouter": {"api_key": ""},
            "deepseek": {"api_key": ""},
            "groq": {"api_key": ""},
            "gemini": {"api_key": ""},
            "zhipu": {"api_key": "", "api_base": ""},
            "vllm": {"api_key": "", "api_base": ""},
            "nvidia": {"api_key": "", "api_base": ""},
            "moonshot": {"api_key": ""},
        },
        "gateway": {"host": "0.0.0.0", "port": 18790},
        "tools": {
            "web": {
                "brave": {"enabled": False, "api_key": "", "max_results": 5},
                "duckduckgo": {"enabled": True, "max_results": 5},
            }
        },
        "heartbeat": {"enabled": True, "interval": 30},
        "devices": {"enabled": False, "monitor_usb": False},
    }


def mask_secrets(data, _path=""):
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            if k in SECRET_FIELDS and isinstance(v, str) and v:
                result[k] = v[:8] + "***" if len(v) > 8 else "***"
            else:
                result[k] = mask_secrets(v, f"{_path}.{k}")
        return result
    if isinstance(data, list):
        return [mask_secrets(item, _path) for item in data]
    return data


def merge_secrets(new_data, existing_data):
    if isinstance(new_data, dict) and isinstance(existing_data, dict):
        result = {}
        for k, v in new_data.items():
            if k in SECRET_FIELDS and isinstance(v, str) and (v.endswith("***") or v == ""):
                result[k] = existing_data.get(k, "")
            else:
                result[k] = merge_secrets(v, existing_data.get(k, {}))
        return result
    return new_data


class GatewayManager:
    def __init__(self):
        self.process: asyncio.subprocess.Process | None = None
        self.state = "stopped"
        self.logs: deque[str] = deque(maxlen=500)
        self.start_time: float | None = None
        self.restart_count = 0
        self._read_tasks: list[asyncio.Task] = []

    async def start(self):
        if self.process and self.process.returncode is None:
            return
        self.state = "starting"
        try:
            self.process = await asyncio.create_subprocess_exec(
                "picoclaw", "gateway",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            self.state = "running"
            self.start_time = time.time()
            task = asyncio.create_task(self._read_output())
            self._read_tasks.append(task)
        except Exception as e:
            self.state = "error"
            self.logs.append(f"Failed to start gateway: {e}")

    async def stop(self):
        if not self.process or self.process.returncode is not None:
            self.state = "stopped"
            return
        self.state = "stopping"
        self.process.terminate()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=10)
        except asyncio.TimeoutError:
            self.process.kill()
            await self.process.wait()
        self.state = "stopped"
        self.start_time = None

    async def restart(self):
        await self.stop()
        self.restart_count += 1
        await self.start()

    async def _read_output(self):
        try:
            while self.process and self.process.stdout:
                line = await self.process.stdout.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip()
                cleaned = ANSI_ESCAPE.sub("", decoded)
                self.logs.append(cleaned)
        except asyncio.CancelledError:
            return
        if self.process and self.process.returncode is not None and self.state == "running":
            self.state = "error"
            self.logs.append(f"Gateway exited with code {self.process.returncode}")

    def get_status(self) -> dict:
        pid = None
        if self.process and self.process.returncode is None:
            pid = self.process.pid
        uptime = None
        if self.start_time and self.state == "running":
            uptime = int(time.time() - self.start_time)
        return {
            "state": self.state,
            "pid": pid,
            "uptime": uptime,
            "restart_count": self.restart_count,
        }


gateway = GatewayManager()
config_lock = asyncio.Lock()


async def homepage(request: Request):
    auth_err = require_auth(request)
    if auth_err:
        return auth_err
    return templates.TemplateResponse(request, "index.html")


async def health(request: Request):
    return JSONResponse({"status": "ok", "gateway": gateway.state})


async def api_config_get(request: Request):
    auth_err = require_auth(request)
    if auth_err:
        return auth_err
    config = load_config()
    return JSONResponse(mask_secrets(config))


async def api_config_put(request: Request):
    auth_err = require_auth(request)
    if auth_err:
        return auth_err

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    try:
        restart = body.pop("_restartGateway", False)

        async with config_lock:
            existing = load_config()
            merged = merge_secrets(body, existing)
            save_config(merged)

        if restart:
            asyncio.create_task(gateway.restart())

        return JSONResponse({"ok": True, "restarting": restart})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_status(request: Request):
    auth_err = require_auth(request)
    if auth_err:
        return auth_err

    config = load_config()

    providers = {}
    for name, prov in config.get("providers", {}).items():
        providers[name] = {"configured": bool(prov.get("api_key"))}

    channels = {}
    for name, chan in config.get("channels", {}).items():
        channels[name] = {"enabled": chan.get("enabled", False)}

    cron_dir = CONFIG_DIR / "cron"
    cron_jobs = []
    if cron_dir.exists():
        for f in cron_dir.glob("*.json"):
            try:
                cron_jobs.append(json.loads(f.read_text()))
            except Exception:
                pass

    return JSONResponse({
        "gateway": gateway.get_status(),
        "providers": providers,
        "channels": channels,
        "cron": {"count": len(cron_jobs), "jobs": cron_jobs},
    })


async def api_logs(request: Request):
    auth_err = require_auth(request)
    if auth_err:
        return auth_err
    return JSONResponse({"lines": list(gateway.logs)})


async def api_gateway_start(request: Request):
    auth_err = require_auth(request)
    if auth_err:
        return auth_err
    asyncio.create_task(gateway.start())
    return JSONResponse({"ok": True})


async def api_gateway_stop(request: Request):
    auth_err = require_auth(request)
    if auth_err:
        return auth_err
    asyncio.create_task(gateway.stop())
    return JSONResponse({"ok": True})


async def api_gateway_restart(request: Request):
    auth_err = require_auth(request)
    if auth_err:
        return auth_err
    asyncio.create_task(gateway.restart())
    return JSONResponse({"ok": True})


async def auto_start_gateway():
    config = load_config()
    has_key = False
    for prov in config.get("providers", {}).values():
        if isinstance(prov, dict) and prov.get("api_key"):
            has_key = True
            break
    if has_key:
        asyncio.create_task(gateway.start())


routes = [
    Route("/", homepage),
    Route("/health", health),
    Route("/api/config", api_config_get, methods=["GET"]),
    Route("/api/config", api_config_put, methods=["PUT"]),
    Route("/api/status", api_status),
    Route("/api/logs", api_logs),
    Route("/api/gateway/start", api_gateway_start, methods=["POST"]),
    Route("/api/gateway/stop", api_gateway_stop, methods=["POST"]),
    Route("/api/gateway/restart", api_gateway_restart, methods=["POST"]),
]

app = Starlette(
    routes=routes,
    middleware=[Middleware(AuthenticationMiddleware, backend=BasicAuthBackend())],
    on_startup=[auto_start_gateway],
    on_shutdown=[gateway.stop],
)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info", loop="asyncio")
    server = uvicorn.Server(config)

    def handle_signal():
        loop.create_task(gateway.stop())
        server.should_exit = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal)

    loop.run_until_complete(server.serve())
