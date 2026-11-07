"""echobox-go portal.

Runs behind Pangolin SSO. Pangolin forwards the signed-in user as `Remote-User`
and, configured as a custom header on the resource, a shared secret in
`X-Ebox-Proxy-Token`. The portal trusts `Remote-User` only when that secret
matches, so requests that bypass Pangolin get no identity.

Environment:
  EBOX_PROXY_TOKEN   shared secret Pangolin injects (required in production)
  EBOX_DEV_USER      local development only: act as this user without Pangolin
  EBOX_ADMINS        comma-separated users who may edit every profile
  EBOX_PROFILES_DIR  directory with <user>/profile.yaml (default: ../builder/profiles/users)
  EBOX_SCHEMA        path to profile.schema.json (default: schema/ in this repo, a copy
                     of the builder repo's profiles/schema/profile.schema.json)
"""
from __future__ import annotations

import hmac
import json
import os
import re
from pathlib import Path
from urllib.parse import quote

import jsonschema
import yaml
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BRAND = Path(os.environ.get("EBOX_BRAND_DIR", REPO / "brand"))
USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")

DESKTOPS = ["plasma", "gnome", "hyprland", "xfce", "none"]
BASES = ["cachyos", "arch"]
CPU_LEVELS = ["generic", "v3", "v4"]

app = FastAPI(title="echobox-go portal", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=HERE / "templates")


def settings() -> dict:
    return {
        "proxy_token": os.environ.get("EBOX_PROXY_TOKEN", ""),
        "dev_user": os.environ.get("EBOX_DEV_USER", ""),
        "admins": {a.strip() for a in os.environ.get("EBOX_ADMINS", "").split(",") if a.strip()},
        "profiles_dir": Path(os.environ.get("EBOX_PROFILES_DIR", REPO.parent / "builder" / "profiles" / "users")),
        "schema": Path(os.environ.get("EBOX_SCHEMA", REPO / "schema" / "profile.schema.json")),
    }


def current_user(request: Request) -> str:
    s = settings()
    if s["proxy_token"]:
        sent = request.headers.get("x-ebox-proxy-token", "")
        if not hmac.compare_digest(sent, s["proxy_token"]):
            raise HTTPException(401, "request did not come through Pangolin")
        user = request.headers.get("remote-user", "")
    elif s["dev_user"]:
        user = s["dev_user"]
    else:
        raise HTTPException(503, "portal not configured: set EBOX_PROXY_TOKEN")
    user = user.split("@", 1)[0].lower()
    if not USER_RE.match(user):
        raise HTTPException(403, "your account name cannot be used as a Linux user name")
    return user


def may_edit(actor: str, target: str) -> bool:
    return actor == target or actor in settings()["admins"]


def profile_path(user: str) -> Path:
    if not USER_RE.match(user):
        raise HTTPException(404, "no such user")
    return settings()["profiles_dir"] / user / "profile.yaml"


def read_profile(user: str) -> dict | None:
    p = profile_path(user)
    if not p.is_file():
        return None
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def validate(profile: dict) -> None:
    schema = json.loads(settings()["schema"].read_text(encoding="utf-8"))
    try:
        jsonschema.validate(profile, schema)
    except jsonschema.ValidationError as exc:
        where = "/".join(str(x) for x in exc.absolute_path) or "(root)"
        raise HTTPException(422, f"{where}: {exc.message}") from None


def write_profile(user: str, profile: dict) -> None:
    if profile.get("user") != user:
        raise HTTPException(422, "profile.user must match the URL")
    validate(profile)
    p = profile_path(user)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".yaml.tmp")
    tmp.write_text(
        "# Managed by the echobox-go portal. Public configuration only.\n"
        + yaml.safe_dump(profile, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    tmp.replace(p)
    # TODO(phase 4): commit through the Forgejo API so the build workflow runs.


# --------------------------------------------------------------------------- pages


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/favicon.svg", include_in_schema=False)
def favicon():
    return FileResponse(BRAND / "favicon.svg", media_type="image/svg+xml")


@app.get("/mark.svg", include_in_schema=False)
def mark():
    return FileResponse(BRAND / "mark-dark.svg", media_type="image/svg+xml")


@app.get("/", response_class=HTMLResponse)
def index(request: Request, user: str = Depends(current_user)):
    profile = read_profile(user) or {"user": user, "base": "cachyos", "desktop": "plasma", "keymap": "us"}
    return templates.TemplateResponse(request, "index.html", {
        "user": user,
        "profile": profile,
        "packages_text": "\n".join(profile.get("packages", [])),
        "bases": BASES, "desktops": DESKTOPS, "cpu_levels": CPU_LEVELS,
        "saved": request.query_params.get("saved") == "1",
        "error": request.query_params.get("error", ""),
    })


@app.post("/profile", include_in_schema=False)
async def save_from_form(request: Request, user: str = Depends(current_user)):
    form = await request.form()
    profile = read_profile(user) or {"user": user}
    profile.update({
        "user": user,
        "base": form.get("base", ""),
        "cpu_level": form.get("cpu_level", "generic"),
        "desktop": form.get("desktop", ""),
        "keymap": (form.get("keymap") or "").strip(),
        "packages": [p for p in re.split(r"[\s,]+", form.get("packages", "")) if p],
    })
    try:
        write_profile(user, profile)
    except HTTPException as exc:
        return RedirectResponse(f"/?error={quote(str(exc.detail))}", status_code=303)
    return RedirectResponse("/?saved=1", status_code=303)


# --------------------------------------------------------------------------- API


@app.get("/api/me")
def me(user: str = Depends(current_user)):
    return {"user": user, "admin": user in settings()["admins"]}


@app.get("/api/profiles/{target}")
def get_profile(target: str, user: str = Depends(current_user)):
    if not may_edit(user, target):
        raise HTTPException(403, "not your profile")
    profile = read_profile(target)
    if profile is None:
        raise HTTPException(404, "no profile yet")
    return profile


@app.put("/api/profiles/{target}")
def put_profile(target: str, profile: dict, user: str = Depends(current_user)):
    if not may_edit(user, target):
        raise HTTPException(403, "not your profile")
    write_profile(target, profile)
    return {"saved": True, "user": target}


# Agent API: reached by enrolled sticks over their Pangolin machine client.
# TODO(phase 2): one-time enrolment codes, per-device tokens, revocation.


@app.post("/api/agent/enrol")
def agent_enrol():
    return JSONResponse({"error": "enrolment is not implemented yet"}, status_code=501)


@app.post("/api/agent/build")
def agent_build():
    return JSONResponse({"error": "build trigger is not implemented yet"}, status_code=501)
