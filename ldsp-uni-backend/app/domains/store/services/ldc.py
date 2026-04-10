"""LDC payment gateway utilities migrated from ld-store-backend."""

from __future__ import annotations

import base64
import hashlib
from urllib.parse import urlencode

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

LDC_GATEWAY = "https://credit.linux.do/epay"
LDC_REQUEST_TIMEOUT_MS = 8000


def generate_ldc_sign(params: dict, secret: str) -> str:
    filtered = {}
    for key, value in params.items():
        if value not in ("", None) and key not in ("sign", "sign_type"):
            filtered[key] = str(value)
    sorted_keys = sorted(filtered.keys())
    raw = "&".join(f"{k}={filtered[k]}" for k in sorted_keys)
    return hashlib.md5((raw + secret).encode("utf-8")).hexdigest()


def verify_ldc_sign(params: dict, secret: str) -> bool:
    received = str(params.get("sign") or "").strip().lower()
    if not received:
        return False
    return received == generate_ldc_sign(params, secret).lower()


def build_ldc_payment_url(
    *,
    pid: str,
    key: str,
    order_no: str,
    product_name: str,
    amount: float,
    notify_url: str = "",
    return_url: str = "",
) -> dict:
    params = {
        "pid": pid,
        "type": "epay",
        "out_trade_no": order_no,
        "name": product_name or "LD Store Order",
        "money": f"{amount:.2f}",
    }
    if notify_url:
        params["notify_url"] = notify_url
    if return_url:
        params["return_url"] = return_url
    params["sign"] = generate_ldc_sign(params, key)
    params["sign_type"] = "MD5"
    return {
        "success": True,
        "paymentUrl": f"{LDC_GATEWAY}/pay/submit.php?{urlencode(params)}",
    }


async def create_ldc_order(
    *,
    pid: str,
    key: str,
    order_no: str,
    product_name: str,
    amount: float,
    notify_url: str = "",
    return_url: str = "",
) -> dict:
    params = {
        "pid": pid,
        "type": "epay",
        "out_trade_no": order_no,
        "name": product_name or "LD Store Order",
        "money": f"{amount:.2f}",
    }
    if notify_url:
        params["notify_url"] = notify_url
    if return_url:
        params["return_url"] = return_url
    params["sign"] = generate_ldc_sign(params, key)
    params["sign_type"] = "MD5"

    try:
        async with httpx.AsyncClient(
            timeout=LDC_REQUEST_TIMEOUT_MS / 1000, follow_redirects=False
        ) as client:
            response = await client.post(
                f"{LDC_GATEWAY}/pay/submit.php",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                content=urlencode(params),
            )
        if response.status_code in (301, 302):
            location = response.headers.get("Location")
            if location:
                return {"success": True, "paymentUrl": location}
        if response.status_code == 200:
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                error = response.json()
                return {
                    "success": False,
                    "error": error.get("error_msg")
                    or error.get("msg")
                    or "LDC创建订单失败",
                }
            return {
                "success": True,
                "paymentUrl": f"{LDC_GATEWAY}/pay/submit.php?{urlencode(params)}",
            }
        return {
            "success": False,
            "error": f"LDC创建订单失败（状态码：{response.status_code}）",
        }
    except httpx.TimeoutException:
        return {"success": False, "error": "LDC 支付创建超时"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def query_ldc_order(
    *, pid: str, key: str, trade_no: str = "", order_no: str = ""
) -> dict:
    safe_trade_no = trade_no.strip()
    safe_order_no = order_no.strip()
    is_business_order = safe_trade_no.upper().startswith(("LS", "LB"))
    has_trade_no = bool(safe_trade_no) and not is_business_order
    if not has_trade_no and not safe_order_no:
        return {"success": False, "error": "缺少有效的LDC订单号", "code": -2}
    params = {"act": "order", "pid": pid, "key": key}
    if has_trade_no:
        params["trade_no"] = safe_trade_no
    if safe_order_no:
        params["out_trade_no"] = safe_order_no
    try:
        async with httpx.AsyncClient(timeout=LDC_REQUEST_TIMEOUT_MS / 1000) as client:
            response = await client.get(f"{LDC_GATEWAY}/api.php?{urlencode(params)}")
        if response.status_code == 404:
            try:
                data = response.json()
            except Exception:
                data = {}
            return {
                "success": False,
                "error": data.get("msg") or "服务不存在或订单已完成",
                "code": -1,
            }
        data = response.json()
        if int(data.get("code", 0)) == 1:
            return {
                "success": True,
                "data": {
                    "tradeNo": data.get("trade_no"),
                    "outTradeNo": data.get("out_trade_no"),
                    "status": data.get("status"),
                    "money": data.get("money"),
                    "addtime": data.get("addtime"),
                    "endtime": data.get("endtime"),
                },
            }
        return {
            "success": False,
            "error": data.get("msg") or "查询失败",
            "code": data.get("code"),
        }
    except httpx.TimeoutException:
        return {"success": False, "error": "查询 LDC 订单超时"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def decrypt_ldc_key(ciphertext: str, key: str) -> str:
    combined = base64.b64decode(ciphertext)
    iv = combined[:12]
    encrypted = combined[12:]
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    aes = AESGCM(digest)
    return aes.decrypt(iv, encrypted, None).decode("utf-8")
