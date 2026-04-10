"""User OAuth auth routes compatible with the original ldsp-backend."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.parse

import httpx
from fastapi import APIRouter, Request

from app.common.utils.response import error_response, success_response
from app.config import settings
from app.core.auth import create_access_token, decode_access_token
from app.db.engine import get_ldsp_session_context
from app.domains.ldsp.services.users import UserService

router = APIRouter(tags=["auth"])

SITE_OAUTH_CONFIGS = {
    "linux.do": {
        "name": "Linux.do",
        "site_url": "https://linux.do",
        "connect_url": "https://connect.linux.do",
        "client_id": lambda: settings.oauth_client_id,
        "client_secret": lambda: settings.oauth_client_secret,
    },
    "idcflare.com": {
        "name": "IDCFlare",
        "site_url": "https://idcflare.com",
        "connect_url": "https://connect.idcflare.com",
        "client_id": lambda: settings.idcflare_client_id,
        "client_secret": lambda: settings.idcflare_client_secret,
    },
}


def _site_config(site: str) -> dict:
    return SITE_OAUTH_CONFIGS.get(site or "linux.do", SITE_OAUTH_CONFIGS["linux.do"])


def _redirect_uri() -> str:
    base_url = (
        settings.worker_url or settings.api_base_url or "https://api1.ldspro.qzz.io"
    )
    return f"{base_url.rstrip('/')}/api/auth/callback"


def _is_registration_paused() -> bool:
    return bool(settings.registration_paused)


def _state_signature(payload: str) -> str:
    secret = settings.jwt_secret_key.encode("utf-8")
    return hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _generate_signed_state(site: str, mode: str = "same", return_url: str = "") -> str:
    timestamp = int(time.time() * 1000)
    random = hashlib.sha256(
        f"{site}:{timestamp}:{time.time_ns()}".encode()
    ).hexdigest()[:32]
    encoded_return_url = (
        base64.b64encode(urllib.parse.quote(return_url).encode("utf-8")).decode("utf-8")
        if return_url
        else ""
    )
    payload = f"{site}:{timestamp}:{random}:{mode}:{encoded_return_url}"
    signature = _state_signature(payload)
    return f"{payload}:{signature}"


def _verify_signed_state(state: str) -> dict | None:
    parts = state.split(":")
    if len(parts) not in (4, 6):
        return None

    if len(parts) == 4:
        site, timestamp_str, random, signature = parts
        mode = "popup"
        encoded_return_url = ""
        payload = f"{site}:{timestamp_str}:{random}"
    else:
        site, timestamp_str, random, mode, encoded_return_url, signature = parts
        payload = f"{site}:{timestamp_str}:{random}:{mode}:{encoded_return_url}"

    if _state_signature(payload) != signature:
        return None

    try:
        timestamp = int(timestamp_str)
    except ValueError:
        return None

    if int(time.time() * 1000) - timestamp > 5 * 60 * 1000:
        return None

    return_url = ""
    if encoded_return_url:
        try:
            return_url = urllib.parse.unquote(
                base64.b64decode(encoded_return_url).decode("utf-8")
            )
        except Exception:
            return_url = ""

    return {
        "site": site,
        "timestamp": timestamp,
        "random": random,
        "mode": mode,
        "returnUrl": return_url,
    }


def _build_avatar_url(
    site: str, avatar_template: str | None, size: int = 128
) -> str | None:
    if not avatar_template:
        return None
    site_url = _site_config(site)["site_url"]
    url = avatar_template.replace("{size}", str(size))
    if url.startswith("http"):
        return url
    if url.startswith("//"):
        return f"https:{url}"
    return f"{site_url}{url}"


async def _exchange_code_for_token(site: str, code: str) -> dict:
    cfg = _site_config(site)
    token_url = f"{cfg['connect_url']}/oauth2/token"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            token_url,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _redirect_uri(),
                "client_id": cfg["client_id"](),
                "client_secret": cfg["client_secret"](),
            },
        )
    response.raise_for_status()
    return response.json()


async def _get_user_info(site: str, access_token: str) -> dict:
    cfg = _site_config(site)
    user_info_url = f"{cfg['connect_url']}/api/user"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            user_info_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )
    response.raise_for_status()
    user_info = response.json()
    if not user_info.get("animated_avatar"):
        user_info["animated_avatar"] = (
            user_info.get("animatedAvatar")
            or user_info.get("animated_avatar_url")
            or user_info.get("animatedAvatarUrl")
        )
    if not user_info.get("avatar_template"):
        user_info["avatar_template"] = user_info.get("avatar") or user_info.get(
            "avatar_url"
        )
    return user_info


def _build_callback_html(
    result: dict, mode: str = "same", return_url: str = "", site: str = "linux.do"
) -> str:
    target_url = return_url or _site_config(site)["site_url"]
    redirect_url = target_url
    if result.get("success"):
        oauth_data = {
            "t": result.get("token"),
            "u": result.get("user"),
            "j": 1 if result.get("isJoined") else 0,
            "e": result.get("expiresIn"),
            "ts": int(time.time() * 1000),
        }
        encoded = base64.b64encode(
            urllib.parse.quote(json.dumps(oauth_data)).encode("utf-8")
        ).decode("utf-8")
        separator = "&" if "#" in target_url else "#"
        redirect_url = (
            f"{target_url}{separator}ldsp_oauth={urllib.parse.quote(encoded)}"
        )

    title = "授权成功" if result.get("success") else "授权失败"
    message = "正在跳转，请稍候..." if result.get("success") else "请返回后重试。"
    icon = "✓" if result.get("success") else "✗"
    error_detail = ""
    if not result.get("success") and result.get("error"):
        error_detail = f'<div class="error-detail">{result["error"].get("message", "授权失败")}</div>'

    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>LDStatus Pro - 授权完成</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }}
    .container {{ text-align: center; padding: 32px 24px; background: rgba(255,255,255,0.1); border-radius: 20px; backdrop-filter: blur(10px); max-width: 340px; width: 90%; }}
    .icon {{ font-size: 56px; margin-bottom: 16px; }}
    .title {{ font-size: 22px; font-weight: 600; margin-bottom: 8px; }}
    .message {{ font-size: 15px; opacity: 0.9; line-height: 1.5; }}
    .action-btn {{ margin-top: 20px; padding: 12px 28px; background: rgba(255,255,255,0.25); border: none; border-radius: 12px; color: white; font-size: 15px; font-weight: 500; cursor: pointer; text-decoration: none; display: inline-block; transition: background 0.2s; }}
    .hidden {{ display: none !important; }}
    .error-detail {{ font-size: 13px; opacity: 0.7; margin-top: 12px; word-break: break-all; }}
  </style>
</head>
<body>
  <div class=\"container\">
    <div class=\"icon\">{icon}</div>
    <div class=\"title\">{title}</div>
    <div class=\"message\" id=\"message\">{message}</div>
    {error_detail}
    <a class=\"action-btn hidden\" id=\"returnBtn\" href=\"{redirect_url}\">返回</a>
  </div>
  <script>
    (function() {{
      const success = {str(bool(result.get("success"))).lower()};
      const redirectUrl = {json.dumps(redirect_url)};
      const showReturnBtn = () => {{ const btn = document.getElementById('returnBtn'); if (btn) btn.classList.remove('hidden'); }};
      const setMessage = (text) => {{ const el = document.getElementById('message'); if (el) el.textContent = text; }};
      if (success) {{
        setTimeout(() => {{ window.location.replace(redirectUrl); }}, 500);
        setTimeout(() => {{ setMessage('若未自动跳转，请点击下方按钮。'); showReturnBtn(); }}, 3000);
      }} else {{
        showReturnBtn();
      }}
    }})();
  </script>
</body>
</html>
    """.strip()


@router.get("/api/auth/init")
async def auth_init(request: Request):
    site = request.query_params.get("site", "linux.do")
    return_url = request.query_params.get("return_url", "")
    cfg = _site_config(site)
    client_id = cfg["client_id"]()
    if not client_id:
        return error_response(
            "OAUTH_NOT_CONFIGURED", f"{site} OAuth 未配置 client_id", 500
        )

    state = _generate_signed_state(site, "same", return_url)
    params = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": _redirect_uri(),
            "response_type": "code",
            "scope": "openid profile",
            "state": state,
        }
    )
    auth_url = f"{cfg['connect_url']}/oauth2/authorize?{params}"
    return success_response(data={"auth_url": auth_url, "state": state})


@router.get("/api/auth/callback")
async def auth_callback(request: Request):
    code = request.query_params.get("code", "")
    state = request.query_params.get("state", "")
    error = request.query_params.get("error", "")

    if error:
        return error_response(
            "OAUTH_ERROR",
            request.query_params.get("error_description", "OAuth 授权失败"),
            400,
        )
    if not code or not state:
        return error_response("INVALID_PARAMS", "缺少 code 或 state 参数", 400)

    state_data = _verify_signed_state(state)
    if not state_data:
        return error_response("INVALID_STATE", "state 无效或已过期", 400)

    site = state_data["site"]
    return_url = state_data.get("returnUrl", "")
    login_mode = state_data.get("mode", "same")

    try:
        token_response = await _exchange_code_for_token(site, code)
        access_token = token_response.get("access_token")
        if not access_token:
            return error_response("TOKEN_ERROR", "获取访问令牌失败", 500)

        user_info = await _get_user_info(site, access_token)
        user_id = str(user_info.get("id") or "")
        if not user_id:
            return error_response("USER_INFO_ERROR", "获取用户信息失败", 500)

        async with get_ldsp_session_context() as db:
            user_service = UserService()
            existing_user = await user_service.get_user_row(db, site, user_id)
            has_joined_before = bool(existing_user)
            is_ld_store_login = bool(
                return_url
                and (
                    "ldshiduo" in return_url
                    or "ld-store" in return_url
                    or "/auth/callback" in return_url
                )
            )

            if (
                _is_registration_paused()
                and not has_joined_before
                and not is_ld_store_login
            ):
                html = _build_callback_html(
                    {
                        "success": False,
                        "error": {
                            "code": "REGISTRATION_PAUSED",
                            "message": "新用户注册已暂停，已有用户仍可登录。",
                        },
                    },
                    login_mode,
                    return_url,
                    site,
                )
                from fastapi.responses import HTMLResponse

                return HTMLResponse(html)

            oauth_trust_level = int(user_info.get("trust_level") or 0)
            db_trust_level = (
                int(existing_user["trust_level"])
                if existing_user and existing_user.get("trust_level") is not None
                else 0
            )
            effective_trust_level = max(oauth_trust_level, db_trust_level)

            persisted_user = await user_service.upsert_oauth_user(
                db=db,
                site=site,
                user_info=user_info,
                trust_level=effective_trust_level,
            )
            is_joined = bool(persisted_user.get("is_active") == 1)

        animated_avatar_url = _build_avatar_url(site, user_info.get("animated_avatar"))
        avatar_url = _build_avatar_url(site, user_info.get("avatar_template"))
        preferred_avatar_url = animated_avatar_url or avatar_url

        jwt_token = create_access_token(
            {
                "sub": user_id,
                "username": user_info.get("username"),
                "name": user_info.get("name"),
                "animated_avatar": user_info.get("animated_avatar"),
                "avatar_template": user_info.get("avatar_template"),
                "avatar_url": preferred_avatar_url,
                "trust_level": effective_trust_level,
                "site": site,
            }
        )

        html = _build_callback_html(
            {
                "success": True,
                "token": jwt_token,
                "user": {
                    "id": user_id,
                    "username": user_info.get("username"),
                    "name": user_info.get("name"),
                    "avatar": preferred_avatar_url,
                    "avatar_url": preferred_avatar_url,
                    "avatar_template": user_info.get("avatar_template"),
                    "animated_avatar": user_info.get("animated_avatar"),
                    "trust_level": effective_trust_level,
                },
                "isJoined": is_joined,
                "expiresIn": settings.jwt_expire_minutes * 60,
            },
            login_mode,
            return_url,
            site,
        )
        from fastapi.responses import HTMLResponse

        return HTMLResponse(html)
    except httpx.HTTPError as exc:
        return error_response("OAUTH_CALLBACK_ERROR", str(exc), 500)
    except Exception as exc:
        return error_response("OAUTH_CALLBACK_ERROR", str(exc), 500)


@router.post("/api/auth/verify")
async def auth_verify(request: Request):
    user = getattr(request.state, "user", None)
    if user:
        return {
            "success": True,
            "user": {
                "id": user.get("user_id") or user.get("sub"),
                "username": user.get("username"),
                "name": user.get("name"),
            },
        }

    body = await request.json()
    token = body.get("token", "")
    if not token:
        return error_response("MISSING_TOKEN", "未提供令牌", 401)
    payload = decode_access_token(token)
    if payload is None:
        return error_response("INVALID_TOKEN", "令牌无效或已过期", 401)
    return {
        "success": True,
        "user": {
            "id": payload.get("sub"),
            "username": payload.get("username"),
            "name": payload.get("name"),
        },
    }
