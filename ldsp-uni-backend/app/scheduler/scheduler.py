"""APScheduler configuration and job definitions.

Replaces all setInterval-based scheduled tasks from the original Node.js backends.

Total jobs: 22 (7 LDStatusPro + 15 LD Store)
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import structlog
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore

from app.config import settings
from app.domains.store.services.schedule_service import StoreScheduleService
from app.domains.store.services.agent_runtime_service import AgentRuntimeService
from app.domains.store.services.ldc import decrypt_ldc_key, query_ldc_order

logger = structlog.get_logger(__name__)
_scheduler = AsyncIOScheduler()


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _env_bool(name: str, default: bool = False) -> bool:
    return _env(name, str(default).lower()).lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int = 0) -> int:
    v = _env(name, str(default))
    try:
        return int(v)
    except (ValueError, TypeError):
        return default


def _env_sec(name: str, default_sec: int) -> int:
    """Convert ms env var to seconds with minimum."""
    return max(_env_int(name, default_sec), 10)


# ──────────────────────────────────────────
# Config helpers (seconds)
# ──────────────────────────────────────────

BUFFER_FLUSH_INTERVAL = max(_env_int("BUFFER_FLUSH_INTERVAL_MS", 300000) // 1000, 60)
AUDIT_FLUSH_INTERVAL = max(_env_int("AUDIT_FLUSH_INTERVAL_MS", 60000) // 1000, 15)
AUDIT_RETENTION_DAYS = max(_env_int("AUDIT_RETENTION_DAYS", 30), 1)
AUDIT_CLEANUP_INTERVAL = max(
    _env_int("AUDIT_CLEANUP_INTERVAL_MS", 86400000) // 1000, 60
)
SECURITY_CLEANUP_INTERVAL = max(
    _env_int("SECURITY_CLEANUP_INTERVAL_MS", 300000) // 1000, 60
)
DAILY_LEADERBOARD_INTERVAL = max(
    _env_int("DAILY_LEADERBOARD_INTERVAL_MS", 300000) // 1000, 60
)
WEEKLY_LEADERBOARD_INTERVAL = max(
    _env_int("WEEKLY_LEADERBOARD_INTERVAL_MS", 3600000) // 1000, 120
)
MONTHLY_LEADERBOARD_INTERVAL = max(
    _env_int("MONTHLY_LEADERBOARD_INTERVAL_MS", 10800000) // 1000, 600
)

# Switches
ENABLE_BUFFER_WRITE_BACK = _env_bool("ENABLE_BUFFER_WRITE_BACK", False)
ENABLE_LEADERBOARD_PRECOMPUTE = _env_bool("ENABLE_LEADERBOARD_PRECOMPUTE", False)
ENABLE_SECURITY_CLEANUP = _env_bool("ENABLE_SECURITY_CLEANUP_JOB", True)

# LD Store intervals (seconds)
ORDER_EXPIRE_CHECK_INTERVAL = max(
    _env_int("ORDER_EXPIRE_CHECK_INTERVAL_MS", 60000) // 1000, 30
)
SHOP_TOP_EXPIRE_INTERVAL = max(
    _env_int("SHOP_TOP_EXPIRE_CHECK_INTERVAL_MS", 60000) // 1000, 30
)
PAYMENT_SYNC_INTERVAL = max(
    _env_int("PENDING_ORDER_PAYMENT_SYNC_INTERVAL_MS", 30000) // 1000, 15
)
PAID_AUTO_DELIVER_INTERVAL = max(
    _env_int("PAID_ORDER_AUTO_DELIVER_CHECK_INTERVAL_MS", 180000) // 1000, 90
)
TEST_AUTO_OFFLINE_INTERVAL = max(
    _env_int("TEST_PRODUCT_AUTO_OFFLINE_INTERVAL_MS", 60000) // 1000, 30
)
CDK_ZERO_STOCK_INTERVAL = max(
    _env_int("CDK_ZERO_STOCK_AUTO_OFFLINE_INTERVAL_MS", 300000) // 1000, 90
)
ADMIN_MSG_DISPATCH_INTERVAL = max(
    _env_int("ADMIN_MESSAGE_DISPATCH_INTERVAL_MS", 15000) // 1000, 10
)
RESTOCK_RECOVERY_INTERVAL = max(
    _env_int("RESTOCK_NOTIFICATION_RECOVERY_INTERVAL_MS", 60000) // 1000, 30
)
PRODUCT_AI_QUEUE_INTERVAL = max(
    _env_int("PRODUCT_AI_REVIEW_QUEUE_INTERVAL_MS", 5000) // 1000, 5
)
PRODUCT_AI_RECOVERY_INTERVAL = max(
    _env_int("PRODUCT_AI_REVIEW_RECOVERY_INTERVAL_MS", 300000) // 1000, 90
)
COMMENT_AI_QUEUE_INTERVAL = max(
    _env_int("COMMENT_AI_REVIEW_QUEUE_INTERVAL_MS", 5000) // 1000, 5
)
COMMENT_AI_RECOVERY_INTERVAL = max(
    _env_int("COMMENT_AI_REVIEW_RECOVERY_INTERVAL_MS", 300000) // 1000, 90
)
OPS_REPORT_INTERVAL = max(
    _env_int("SHOP_OPS_REPORT_SCHEDULER_HEARTBEAT_MS", 60000) // 1000, 30
)
OPS_COPILOT_INTERVAL = max(
    _env_int("SHOP_OPS_COPILOT_QUEUE_HEARTBEAT_MS", 5000) // 1000, 5
)
ADMIN_MSG_DISPATCH_BATCH_SIZE = max(
    _env_int("ADMIN_MESSAGE_DISPATCH_BATCH_SIZE", 200), 1
)
RESTOCK_PROCESSING_STALE_MS = max(
    _env_int("RESTOCK_NOTIFICATION_PROCESSING_STALE_MS", 600000), 60000
)
RESTOCK_NOTIFY_BATCH_SIZE = max(
    _env_int("RESTOCK_NOTIFICATION_NOTIFY_BATCH_SIZE", 2000), 1
)
SHADOW_SNAPSHOT_AUTO_ENABLED = _env_bool(
    "BUY_AGENT_SHADOW_SNAPSHOT_AUTO_ENABLED", False
)
SHADOW_SNAPSHOT_INTERVAL = max(
    _env_int("BUY_AGENT_SHADOW_SNAPSHOT_INTERVAL_MS", 0) // 1000, 0
)
SHADOW_SNAPSHOT_DAYS = min(max(_env_int("BUY_AGENT_SHADOW_SNAPSHOT_DAYS", 7), 1), 30)
SHADOW_SNAPSHOT_AGENT_KEYS = [
    item.strip()
    for item in _env(
        "BUY_AGENT_SHADOW_SNAPSHOT_AGENT_KEYS",
        "buy_request_review,buy_chat_patrol",
    ).split(",")
    if item.strip()
]


# ──────────────────────────────────────────
# Connection helpers
# ──────────────────────────────────────────


def _ldsp_db() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.ldsp_database_path)
    conn.row_factory = sqlite3.Row
    return conn


def _store_db() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.store_database_path)
    conn.row_factory = sqlite3.Row
    return conn


BEIJING_TZ = timezone(timedelta(hours=8))
STORE_ONLINE_PRODUCT_STATUSES = ("ai_approved", "manual_approved", "approved")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _safe_json_loads(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _beijing_dt(ms: int | None = None) -> datetime:
    safe_ms = _now_ms() if ms is None else int(ms)
    return datetime.fromtimestamp(safe_ms / 1000, tz=timezone.utc).astimezone(
        BEIJING_TZ
    )


def _supported_sites() -> list[str]:
    raw = (getattr(settings, "supported_sites", "linux.do,idcflare.com") or "").strip()
    sites = [item.strip() for item in raw.split(",") if item.strip()]
    return sites or ["linux.do", "idcflare.com"]


def _store_ms_expr(column_sql: str) -> str:
    text_sql = f"TRIM(COALESCE(CAST({column_sql} AS TEXT), ''))"
    return f"""CASE
        WHEN {text_sql} = '' THEN NULL
        WHEN {text_sql} NOT GLOB '*[^0-9]*' THEN
            CASE
                WHEN LENGTH({text_sql}) >= 13 THEN CAST({text_sql} AS INTEGER)
                ELSE CAST({text_sql} AS INTEGER) * 1000
            END
        WHEN {text_sql} GLOB '????-??-?? ??:??:??' THEN CAST(strftime('%s', {text_sql}, '-8 hours') AS INTEGER) * 1000
        WHEN {text_sql} GLOB '????-??-??T??:??:??*' THEN CAST(strftime('%s', {text_sql}) AS INTEGER) * 1000
        ELSE NULL
    END"""


def _ensure_shadow_snapshot_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS shadow_readiness_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_key TEXT NOT NULL,
            config TEXT,
            created_at TEXT NOT NULL
        )"""
    )


def _store_job_enabled(schedule_service: StoreScheduleService, job_key: str) -> bool:
    try:
        return schedule_service.is_job_enabled(job_key)
    except Exception:
        return True


def _start_store_job_run(
    job_key: str, trigger: str
) -> tuple[StoreScheduleService | None, int | None]:
    schedule_service = StoreScheduleService()
    if not _store_job_enabled(schedule_service, job_key):
        return None, None
    return schedule_service, schedule_service.start_run(job_key, trigger)


def _finish_store_job_run(
    schedule_service: StoreScheduleService | None,
    run_id: int | None,
    job_key: str,
    *,
    status: str,
    result: dict | None = None,
    error_message: str | None = None,
) -> None:
    if not schedule_service or not run_id:
        return
    schedule_service.finish_run(
        run_id,
        job_key,
        status=status,
        result=result,
        error_message=error_message,
    )


def _upsert_interval_job_metadata(
    schedule_service: StoreScheduleService,
    *,
    job_key: str,
    job_type: str,
    interval_seconds: int,
    runtime_config: dict | None = None,
) -> None:
    existing = schedule_service.get_job(job_key) or {}
    enabled = True
    if existing:
        try:
            enabled = bool(int(existing.get("enabled") or 0))
        except Exception:
            enabled = True
    schedule_service.upsert_job(
        job_key=job_key,
        job_type=job_type,
        enabled=enabled,
        schedule_type="interval",
        interval_seconds=interval_seconds,
        runtime_config=runtime_config or existing.get("runtime_config") or {},
    )


def _previous_month(year: int, month: int) -> tuple[int, int]:
    if month <= 1:
        return year - 1, 12
    return year, month - 1


def _resolve_shop_ops_report_slot(
    report_type: str, schedule: dict | None, now_ms: int
) -> dict[str, Any]:
    safe_type = str(report_type or "daily").strip().lower() or "daily"
    now_bj = _beijing_dt(now_ms)
    schedule = schedule or {}
    if safe_type == "weekly":
        weekday = max(0, min(6, int(schedule.get("weekday") or 6)))
        hour = max(0, min(23, int(schedule.get("hour") or 23)))
        minute = max(0, min(59, int(schedule.get("minute") or 0)))
        current_weekday = (now_bj.weekday() + 1) % 7
        slot_date = now_bj.date() + timedelta(days=weekday - current_weekday)
        slot_dt = datetime.combine(slot_date, datetime.min.time(), tzinfo=BEIJING_TZ)
        slot_dt = slot_dt.replace(hour=hour, minute=minute)
        if slot_dt > now_bj:
            slot_dt -= timedelta(days=7)
        return {
            "slotAtMs": int(slot_dt.astimezone(timezone.utc).timestamp() * 1000),
            "slotKey": f"weekly:{slot_dt.strftime('%Y-%m-%d:%H:%M')}",
        }
    if safe_type == "monthly":
        day_of_month = max(1, min(31, int(schedule.get("dayOfMonth") or 1)))
        hour = max(0, min(23, int(schedule.get("hour") or 2)))
        minute = max(0, min(59, int(schedule.get("minute") or 0)))
        year = now_bj.year
        month = now_bj.month
        while True:
            try:
                slot_dt = datetime(
                    year,
                    month,
                    min(day_of_month, 28),
                    hour,
                    minute,
                    tzinfo=BEIJING_TZ,
                )
                while True:
                    next_day = slot_dt + timedelta(days=1)
                    if next_day.month != month or next_day.day > day_of_month:
                        break
                    slot_dt = next_day
                break
            except Exception:
                day_of_month = max(1, day_of_month - 1)
        if slot_dt > now_bj:
            year, month = _previous_month(year, month)
            day = min(day_of_month, 28)
            slot_dt = datetime(year, month, day, hour, minute, tzinfo=BEIJING_TZ)
            while True:
                next_day = slot_dt + timedelta(days=1)
                if next_day.month != month or next_day.day > day_of_month:
                    break
                slot_dt = next_day
        return {
            "slotAtMs": int(slot_dt.astimezone(timezone.utc).timestamp() * 1000),
            "slotKey": f"monthly:{slot_dt.strftime('%Y-%m-%d:%H:%M')}",
        }

    interval_hours = max(1, min(24, int(schedule.get("intervalHours") or 1)))
    minute = max(0, min(59, int(schedule.get("minute") or 0)))
    day_start = now_bj.replace(hour=0, minute=0, second=0, microsecond=0)
    minute_of_day = now_bj.hour * 60 + now_bj.minute
    slot_interval_minutes = interval_hours * 60
    if minute_of_day < minute:
        previous_day_start = day_start - timedelta(days=1)
        max_slot_index = (24 * 60 - 1 - minute) // slot_interval_minutes
        slot_dt = previous_day_start + timedelta(
            minutes=minute + max_slot_index * slot_interval_minutes
        )
    else:
        slot_index = (minute_of_day - minute) // slot_interval_minutes
        slot_dt = day_start + timedelta(
            minutes=minute + slot_index * slot_interval_minutes
        )
    return {
        "slotAtMs": int(slot_dt.astimezone(timezone.utc).timestamp() * 1000),
        "slotKey": f"daily:{slot_dt.strftime('%Y-%m-%d:%H:%M')}",
    }


def _build_report_period_meta(report_type: str, now_ms: int) -> dict[str, Any]:
    safe_type = str(report_type or "daily").strip().lower() or "daily"
    now_bj = _beijing_dt(now_ms)
    if safe_type == "weekly":
        start_dt = now_bj.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=6)
        return {
            "reportType": safe_type,
            "periodLabel": f"{start_dt.strftime('%Y-%m-%d')} 至 {now_bj.strftime('%Y-%m-%d')}",
            "periodStart": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "periodEndDisplay": now_bj.strftime("%Y-%m-%d %H:%M:%S"),
            "rangeStartMs": int(start_dt.astimezone(timezone.utc).timestamp() * 1000),
            "rangeEndMs": now_ms,
            "trendDays": 7,
            "title": f"小卖部周报（{start_dt.strftime('%Y-%m-%d')} 至 {now_bj.strftime('%Y-%m-%d')}）",
        }
    if safe_type == "monthly":
        current_month_start = now_bj.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        year, month = _previous_month(
            current_month_start.year, current_month_start.month
        )
        start_dt = current_month_start.replace(year=year, month=month)
        end_dt = current_month_start - timedelta(seconds=1)
        return {
            "reportType": safe_type,
            "periodLabel": start_dt.strftime("%Y年%m月"),
            "periodStart": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "periodEndDisplay": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "rangeStartMs": int(start_dt.astimezone(timezone.utc).timestamp() * 1000),
            "rangeEndMs": int(
                current_month_start.astimezone(timezone.utc).timestamp() * 1000
            ),
            "trendDays": 31,
            "title": f"小卖部月报（{start_dt.strftime('%Y年%m月')}）",
        }
    start_dt = now_bj.replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        "reportType": safe_type,
        "periodLabel": now_bj.strftime("%Y-%m-%d"),
        "periodStart": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "periodEndDisplay": now_bj.strftime("%Y-%m-%d %H:%M:%S"),
        "rangeStartMs": int(start_dt.astimezone(timezone.utc).timestamp() * 1000),
        "rangeEndMs": now_ms,
        "trendDays": 1,
        "title": f"小卖部当日建议（{now_bj.strftime('%Y-%m-%d')}）",
    }


def _build_ops_analytics_snapshot(
    conn: sqlite3.Connection, report_type: str, now_ms: int
) -> dict[str, Any]:
    period_meta = _build_report_period_meta(report_type, now_ms)
    created_expr = _store_ms_expr("o.created_at")
    deal_statuses = ("paid", "delivered")
    today_start_ms = int(
        _beijing_dt(now_ms)
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .astimezone(timezone.utc)
        .timestamp()
        * 1000
    )
    days7_start_ms = now_ms - 7 * 24 * 60 * 60 * 1000
    days30_start_ms = now_ms - 30 * 24 * 60 * 60 * 1000

    def _period_orders(
        start_ms: int | None, end_ms: int | None = None
    ) -> dict[str, Any]:
        clauses = []
        params: list[Any] = []
        if start_ms is not None:
            clauses.append(f"{created_expr} >= ?")
            params.append(start_ms)
        if end_ms is not None:
            clauses.append(f"{created_expr} < ?")
            params.append(end_ms)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        summary = conn.execute(
            f"""SELECT COUNT(*) AS created_count,
                       SUM(CASE WHEN o.status IN ('paid', 'delivered') THEN 1 ELSE 0 END) AS deal_count,
                       COALESCE(SUM(CASE WHEN o.status IN ('paid', 'delivered') THEN o.amount ELSE 0 END), 0) AS revenue,
                       COUNT(DISTINCT CASE WHEN o.status IN ('paid', 'delivered') THEN o.buyer_site || ':' || o.buyer_user_id END) AS buyer_count,
                       COUNT(DISTINCT CASE WHEN o.status IN ('paid', 'delivered') THEN o.seller_site || ':' || o.seller_user_id END) AS seller_count
                FROM shop_orders o {where_sql}""",
            params,
        ).fetchone()
        created_count = int(summary["created_count"] or 0)
        deal_count = int(summary["deal_count"] or 0)
        revenue = float(summary["revenue"] or 0)
        return {
            "createdOrderCount": created_count,
            "dealOrderCount": deal_count,
            "revenue": revenue,
            "buyerCount": int(summary["buyer_count"] or 0),
            "sellerCount": int(summary["seller_count"] or 0),
            "avgOrderAmount": round(revenue / deal_count, 2) if deal_count > 0 else 0,
            "dealRate": round(deal_count / created_count, 4)
            if created_count > 0
            else 0,
        }

    periods = {
        "today": _period_orders(today_start_ms, now_ms + 1),
        "days7": _period_orders(days7_start_ms, now_ms + 1),
        "days30": _period_orders(days30_start_ms, now_ms + 1),
        "focus": _period_orders(
            int(period_meta["rangeStartMs"]), int(period_meta["rangeEndMs"])
        ),
        "total": _period_orders(None, None),
    }

    trend_days = max(int(period_meta["trendDays"]), 1)
    trend_rows = conn.execute(
        f"""SELECT date(({created_expr}) / 1000, 'unixepoch', '+8 hours') AS metric_bucket,
                   COUNT(*) AS created_order_count,
                   SUM(CASE WHEN o.status IN ('paid', 'delivered') THEN 1 ELSE 0 END) AS deal_order_count,
                   COALESCE(SUM(CASE WHEN o.status IN ('paid', 'delivered') THEN o.amount ELSE 0 END), 0) AS revenue,
                   COUNT(DISTINCT CASE WHEN o.status IN ('paid', 'delivered') THEN o.seller_site || ':' || o.seller_user_id END) AS seller_count
            FROM shop_orders o
            WHERE {created_expr} >= ? AND {created_expr} < ?
            GROUP BY date(({created_expr}) / 1000, 'unixepoch', '+8 hours')
            ORDER BY metric_bucket ASC""",
        (max(now_ms - trend_days * 24 * 60 * 60 * 1000, 0), now_ms + 1),
    ).fetchall()
    trend = [
        {
            "label": row["metric_bucket"] or "",
            "createdOrderCount": int(row["created_order_count"] or 0),
            "dealOrderCount": int(row["deal_order_count"] or 0),
            "revenue": float(row["revenue"] or 0),
            "sellerCount": int(row["seller_count"] or 0),
        }
        for row in trend_rows
    ]

    status_rows = conn.execute(
        f"""SELECT o.status, COUNT(*) AS order_count, COALESCE(SUM(o.amount), 0) AS amount
            FROM shop_orders o
            WHERE {created_expr} >= ? AND {created_expr} < ?
            GROUP BY o.status
            ORDER BY order_count DESC, o.status ASC""",
        (int(period_meta["rangeStartMs"]), int(period_meta["rangeEndMs"])),
    ).fetchall()
    status_distribution = [
        {
            "status": str(row["status"] or "unknown"),
            "orderCount": int(row["order_count"] or 0),
            "revenue": float(row["amount"] or 0),
        }
        for row in status_rows
    ]

    top_category_rows = conn.execute(
        f"""SELECT COALESCE(c.name, '未分类') AS category_name,
                   COUNT(*) AS order_count,
                   COALESCE(SUM(o.amount), 0) AS revenue,
                   COUNT(DISTINCT o.seller_site || ':' || o.seller_user_id) AS seller_count
            FROM shop_orders o
            LEFT JOIN shop_products p ON p.id = o.product_id
            LEFT JOIN shop_categories c ON c.id = p.category_id
            WHERE {created_expr} >= ? AND {created_expr} < ?
              AND o.status IN ('paid', 'delivered')
            GROUP BY COALESCE(c.name, '未分类')
            ORDER BY revenue DESC, order_count DESC, category_name ASC
            LIMIT 8""",
        (int(period_meta["rangeStartMs"]), int(period_meta["rangeEndMs"])),
    ).fetchall()
    top_categories = [
        {
            "categoryName": row["category_name"] or "未分类",
            "orderCount": int(row["order_count"] or 0),
            "revenue": float(row["revenue"] or 0),
            "sellerCount": int(row["seller_count"] or 0),
        }
        for row in top_category_rows
    ]

    top_seller_rows = conn.execute(
        f"""SELECT o.seller_user_id,
                   o.seller_site,
                   MAX(COALESCE(NULLIF(TRIM(o.seller_username), ''), NULLIF(TRIM(p.seller_username), ''), 'unknown')) AS seller_username,
                   MAX(COALESCE(NULLIF(TRIM(p.seller_name), ''), NULLIF(TRIM(o.seller_username), ''), '')) AS seller_name,
                   COUNT(*) AS order_count,
                   COALESCE(SUM(o.amount), 0) AS revenue,
                   COUNT(DISTINCT o.buyer_site || ':' || o.buyer_user_id) AS buyer_count
            FROM shop_orders o
            LEFT JOIN shop_products p ON p.id = o.product_id
            WHERE {created_expr} >= ? AND {created_expr} < ?
              AND o.status IN ('paid', 'delivered')
            GROUP BY o.seller_site, o.seller_user_id
            ORDER BY revenue DESC, order_count DESC, seller_username ASC
            LIMIT 10""",
        (int(period_meta["rangeStartMs"]), int(period_meta["rangeEndMs"])),
    ).fetchall()
    top_sellers = [
        {
            "sellerKey": f"{row['seller_site'] or 'linux.do'}:{row['seller_user_id'] or ''}",
            "sellerSite": row["seller_site"] or "linux.do",
            "sellerUserId": row["seller_user_id"] or "",
            "sellerUsername": row["seller_username"] or "unknown",
            "sellerName": row["seller_name"] or "",
            "orderCount": int(row["order_count"] or 0),
            "buyerCount": int(row["buyer_count"] or 0),
            "revenue": float(row["revenue"] or 0),
        }
        for row in top_seller_rows
    ]

    return {
        "generatedAt": now_ms,
        "periodMeta": period_meta,
        "periods": periods,
        "trend": trend,
        "statusDistribution": status_distribution,
        "topCategories": top_categories,
        "topSellers": top_sellers,
    }


def _build_ops_copilot_fallback_report(
    report_type: str, now_ms: int, analytics: dict[str, Any]
) -> dict[str, Any]:
    focus = analytics.get("periods", {}).get("focus", {})
    created = int(focus.get("createdOrderCount") or 0)
    deals = int(focus.get("dealOrderCount") or 0)
    revenue = float(focus.get("revenue") or 0)
    deal_rate = float(focus.get("dealRate") or 0)
    pending = 0
    expired = 0
    for item in analytics.get("statusDistribution", []):
        if item.get("status") == "pending":
            pending = int(item.get("orderCount") or 0)
        if item.get("status") == "expired":
            expired = int(item.get("orderCount") or 0)
    highlights: list[dict[str, Any]] = []
    if revenue > 0:
        highlights.append(
            {
                "title": "成交仍有产出",
                "detail": f"当前统计窗口成交额 {revenue:.2f}，成交单量 {deals}。",
                "metric": f"revenue={revenue:.2f}",
            }
        )
    if analytics.get("topCategories"):
        top_category = analytics["topCategories"][0]
        highlights.append(
            {
                "title": "重点分类贡献最高",
                "detail": f"{top_category.get('categoryName') or '未分类'} 当前贡献 {float(top_category.get('revenue') or 0):.2f} 元成交额。",
                "metric": f"categoryRevenue={float(top_category.get('revenue') or 0):.2f}",
            }
        )
    risks: list[dict[str, Any]] = []
    if pending > 0:
        risks.append(
            {
                "title": "待支付订单需要跟进",
                "detail": f"当前窗口内仍有 {pending} 笔待支付订单，需关注支付链路与转化流失。",
                "severity": "high" if pending >= 10 else "medium",
                "metric": f"pendingOrders={pending}",
            }
        )
    if expired > 0:
        risks.append(
            {
                "title": "过期订单存在损耗",
                "detail": f"当前窗口内有 {expired} 笔订单已过期，建议复核支付超时和卖家响应节奏。",
                "severity": "medium",
                "metric": f"expiredOrders={expired}",
            }
        )
    if deal_rate < 0.3 and created > 0:
        risks.append(
            {
                "title": "成交转化偏低",
                "detail": f"当前窗口订单成交率约为 {deal_rate:.2%}，建议优先排查支付与履约链路。",
                "severity": "high" if deal_rate < 0.15 else "medium",
                "metric": f"dealRate={deal_rate:.2%}",
            }
        )
    actions = [
        {
            "title": "复核待支付积压",
            "priority": "high" if pending > 0 else "medium",
            "owner": "运营",
            "reason": "优先减少支付流失，确认是否存在支付链路、价格或商家响应问题。",
            "metric": "pendingOrders",
        },
        {
            "title": "关注重点分类供给",
            "priority": "medium",
            "owner": "商家运营",
            "reason": "优先维护当前贡献最高的分类和卖家，避免供给断档影响成交。",
            "metric": "topCategoryRevenue",
        },
        {
            "title": "人工复核高影响动作",
            "priority": "medium",
            "owner": "风控",
            "reason": "对下架、封禁、集中调价等高影响动作仅提出建议，不自动决策。",
            "metric": "dealRate",
        },
    ]
    period_meta = analytics.get("periodMeta", {})
    report = {
        "reportType": report_type,
        "title": period_meta.get("title") or "小卖部运营建议",
        "summary": f"当前窗口共创建 {created} 笔订单、成交 {deals} 笔、成交额 {revenue:.2f}，系统已生成基于规则的兼容分析。",
        "overview": (
            f"本次任务使用统一后端的兼容分析逻辑处理 ops_copilot 队列，重点统计窗口为 {period_meta.get('periodLabel') or '-'}。"
            f" 当前成交率约 {deal_rate:.2%}，待支付 {pending} 笔，已过期 {expired} 笔。"
        ),
        "metrics": analytics.get("periods", {}),
        "trend": analytics.get("trend", []),
        "statusDistribution": analytics.get("statusDistribution", []),
        "topCategories": analytics.get("topCategories", []),
        "topSellers": analytics.get("topSellers", []),
        "highlights": highlights,
        "risks": risks,
        "actions": actions,
        "questions": [
            "待支付积压是否集中在少数商家或少数商品？",
            "是否需要人工复核过期订单异常增长原因？",
        ],
        "sections": [
            {
                "heading": "经营概览",
                "body": f"窗口 {period_meta.get('periodLabel') or '-'} 内创建 {created} 单，成交 {deals} 单，成交额 {revenue:.2f}。",
            },
            {
                "heading": "风险与待办",
                "body": f"当前待支付 {pending} 单、过期 {expired} 单。建议优先处理支付流失和重点分类供给连续性。",
            },
            {
                "heading": "兼容说明",
                "body": "由于统一后端尚未迁入完整 ops_copilot Agent，本次结果由调度器按照 legacy 队列语义生成兼容分析并回填 agent_runs。",
            },
        ],
        "generatedAt": now_ms,
        "reportMeta": {
            "reportType": report_type,
            "periodLabel": period_meta.get("periodLabel") or "",
            "periodStart": period_meta.get("periodStart") or "",
            "periodEndDisplay": period_meta.get("periodEndDisplay") or "",
            "generatedBy": "scheduler_fallback",
        },
    }
    return report


# ──────────────────────────────────────────
# LDStatusPro Scheduled Jobs
# ──────────────────────────────────────────

_buffer_running = False


async def buffer_flush_job(trigger: str = "interval") -> None:
    """Flush write buffers to database."""
    global _buffer_running
    if not ENABLE_BUFFER_WRITE_BACK or _buffer_running:
        return
    _buffer_running = True
    try:
        # In v1, direct writes (no buffer). In production, implement actual buffer.
        logger.debug("buffer_flush_completed", trigger=trigger)
    except Exception as e:
        logger.error("buffer_flush_failed", trigger=trigger, error=str(e))
    finally:
        _buffer_running = False


_audit_flush_running = False


async def audit_flush_job(trigger: str = "interval") -> None:
    """Flush audit log buffers."""
    global _audit_flush_running
    if _audit_flush_running:
        return
    _audit_flush_running = True
    try:
        conn = _ldsp_db()
        try:
            cursor = conn.execute(
                "SELECT COUNT(*) as cnt FROM request_logs WHERE created_at > datetime('now', '-1 hour')",
            )
            row = cursor.fetchone()
            logger.debug(
                "audit_flush_completed", trigger=trigger, count=row["cnt"] if row else 0
            )
        finally:
            conn.close()
    except Exception as e:
        logger.error("audit_flush_failed", trigger=trigger, error=str(e))
    finally:
        _audit_flush_running = False


_audit_cleanup_running = False


async def audit_cleanup_job(trigger: str = "interval") -> None:
    """Clean up old audit logs beyond retention period."""
    global _audit_cleanup_running
    if _audit_cleanup_running:
        return
    _audit_cleanup_running = True
    try:
        conn = _ldsp_db()
        try:
            cutoff = datetime.now(timezone.utc).strftime(f"%Y-%m-%d 00:00:00")
            cursor = conn.execute(
                "DELETE FROM request_logs WHERE created_at < datetime(?, ?)",
                ("now", f"-{AUDIT_RETENTION_DAYS} days"),
            )
            conn.commit()
            deleted = cursor.rowcount
            if deleted > 0 or trigger == "startup":
                logger.info(
                    "audit_cleanup_completed",
                    trigger=trigger,
                    deleted=deleted,
                    keep_days=AUDIT_RETENTION_DAYS,
                )
        finally:
            conn.close()
    except Exception as e:
        logger.error("audit_cleanup_failed", trigger=trigger, error=str(e))
    finally:
        _audit_cleanup_running = False


_security_cleanup_running = False


async def security_cleanup_job(trigger: str = "interval") -> None:
    """Clean up expired blacklist entries and old violations."""
    global _security_cleanup_running
    if not ENABLE_SECURITY_CLEANUP or _security_cleanup_running:
        return
    _security_cleanup_running = True
    try:
        conn = _ldsp_db()
        try:
            # Remove expired temporary bans
            cursor = conn.execute(
                "DELETE FROM ip_blacklist WHERE expires_at IS NOT NULL AND expires_at < ?",
                (int(time.time() * 1000),),
            )
            expired_blacklist = cursor.rowcount

            # Remove old violations (older than 90 days)
            cursor = conn.execute(
                "DELETE FROM ip_violations WHERE violation_time < datetime('now', '-90 days')",
            )
            violations_cleaned = cursor.rowcount

            conn.commit()

            if expired_blacklist > 0 or violations_cleaned > 0 or trigger == "startup":
                logger.info(
                    "security_cleanup_completed",
                    trigger=trigger,
                    expired_blacklist_removed=expired_blacklist,
                    violations_removed=violations_cleaned,
                )
        finally:
            conn.close()
    except Exception as e:
        logger.error("security_cleanup_failed", trigger=trigger, error=str(e))
    finally:
        _security_cleanup_running = False


_leaderboard_running = False


async def daily_leaderboard_job(trigger: str = "interval") -> None:
    """Precompute daily leaderboard."""
    global _leaderboard_running
    if not ENABLE_LEADERBOARD_PRECOMPUTE or _leaderboard_running:
        return
    _leaderboard_running = True
    try:
        conn = _ldsp_db()
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            total_rows = 0
            now_ms = _now_ms()
            for site in _supported_sites():
                cursor = conn.execute(
                    """SELECT u.user_id, u.username, u.trust_level, rd.minutes,
                              RANK() OVER (ORDER BY rd.minutes DESC) as rank
                       FROM reading_daily rd
                       JOIN users u ON u.site = rd.site AND u.user_id = rd.user_id
                       WHERE rd.site = ? AND rd.date = ? AND u.is_active = 1
                       ORDER BY rd.minutes DESC LIMIT 50""",
                    (site, today),
                )
                rows = cursor.fetchall()
                data = [
                    {
                        "user_id": r["user_id"],
                        "username": r["username"],
                        "minutes": r["minutes"],
                        "rank": r["rank"],
                    }
                    for r in rows
                ]
                conn.execute(
                    """INSERT OR REPLACE INTO leaderboard_cache (site, type, period, data, computed_at)
                       VALUES (?, 'daily', ?, ?, ?)""",
                    (site, today, json.dumps(data, ensure_ascii=False), now_ms),
                )
                total_rows += len(data)
            conn.commit()
            logger.info(
                "daily_leaderboard_computed",
                trigger=trigger,
                site_count=len(_supported_sites()),
                count=total_rows,
            )
        finally:
            conn.close()
    except Exception as e:
        logger.error("daily_leaderboard_failed", trigger=trigger, error=str(e))
    finally:
        _leaderboard_running = False


async def weekly_leaderboard_job(trigger: str = "interval") -> None:
    """Precompute weekly leaderboard."""
    global _leaderboard_running
    if not ENABLE_LEADERBOARD_PRECOMPUTE or _leaderboard_running:
        return
    _leaderboard_running = True
    try:
        conn = _ldsp_db()
        try:
            week = datetime.now(timezone.utc).strftime("%Y-W%W")
            total_rows = 0
            now_ms = _now_ms()
            for site in _supported_sites():
                cursor = conn.execute(
                    """SELECT u.user_id, u.username, COALESCE(rw.minutes, 0) as minutes,
                              RANK() OVER (ORDER BY COALESCE(rw.minutes, 0) DESC) as rank
                       FROM users u
                       LEFT JOIN reading_weekly rw ON rw.site = u.site AND rw.user_id = u.user_id AND rw.week = ?
                       WHERE u.site = ? AND u.is_active = 1
                       ORDER BY minutes DESC LIMIT 50""",
                    (week, site),
                )
                rows = cursor.fetchall()
                data = [
                    {
                        "user_id": r["user_id"],
                        "username": r["username"],
                        "minutes": r["minutes"],
                        "rank": r["rank"],
                    }
                    for r in rows
                ]
                conn.execute(
                    """INSERT OR REPLACE INTO leaderboard_cache (site, type, period, data, computed_at)
                       VALUES (?, 'weekly', ?, ?, ?)""",
                    (site, week, json.dumps(data, ensure_ascii=False), now_ms),
                )
                total_rows += len(data)
            conn.commit()
            logger.info(
                "weekly_leaderboard_computed",
                trigger=trigger,
                site_count=len(_supported_sites()),
                count=total_rows,
            )
        finally:
            conn.close()
    except Exception as e:
        logger.error("weekly_leaderboard_failed", trigger=trigger, error=str(e))
    finally:
        _leaderboard_running = False


async def monthly_leaderboard_job(trigger: str = "interval") -> None:
    """Precompute monthly leaderboard."""
    global _leaderboard_running
    if not ENABLE_LEADERBOARD_PRECOMPUTE or _leaderboard_running:
        return
    _leaderboard_running = True
    try:
        conn = _ldsp_db()
        try:
            month = datetime.now(timezone.utc).strftime("%Y-%m")
            total_rows = 0
            now_ms = _now_ms()
            for site in _supported_sites():
                cursor = conn.execute(
                    """SELECT u.user_id, u.username, COALESCE(rm.minutes, 0) as minutes,
                              RANK() OVER (ORDER BY COALESCE(rm.minutes, 0) DESC) as rank
                       FROM users u
                       LEFT JOIN reading_monthly rm ON rm.site = u.site AND rm.user_id = u.user_id AND rm.month = ?
                       WHERE u.site = ? AND u.is_active = 1
                       ORDER BY minutes DESC LIMIT 50""",
                    (month, site),
                )
                rows = cursor.fetchall()
                data = [
                    {
                        "user_id": r["user_id"],
                        "username": r["username"],
                        "minutes": r["minutes"],
                        "rank": r["rank"],
                    }
                    for r in rows
                ]
                conn.execute(
                    """INSERT OR REPLACE INTO leaderboard_cache (site, type, period, data, computed_at)
                       VALUES (?, 'monthly', ?, ?, ?)""",
                    (site, month, json.dumps(data, ensure_ascii=False), now_ms),
                )
                total_rows += len(data)
            conn.commit()
            logger.info(
                "monthly_leaderboard_computed",
                trigger=trigger,
                site_count=len(_supported_sites()),
                count=total_rows,
            )
        finally:
            conn.close()
    except Exception as e:
        logger.error("monthly_leaderboard_failed", trigger=trigger, error=str(e))
    finally:
        _leaderboard_running = False


# ──────────────────────────────────────────
# LD Store Scheduled Jobs
# ──────────────────────────────────────────

_order_expire_running = False


async def order_expire_check_job(trigger: str = "interval") -> None:
    """Check and expire overdue orders."""
    global _order_expire_running
    if _order_expire_running:
        return
    _order_expire_running = True
    try:
        now_ms = int(time.time() * 1000)
        conn = _store_db()
        try:
            cursor = conn.execute(
                """SELECT * FROM shop_orders
                   WHERE status IN ('pending', 'paying') AND pay_expired_at IS NOT NULL AND pay_expired_at < ?
                   LIMIT 100""",
                (now_ms,),
            )
            orders = cursor.fetchall()
            expired = 0
            recovered = 0
            for order in orders:
                order = dict(order)
                merchant_pid = str(order.get("merchant_pid_snapshot") or "").strip()
                encrypted_key = str(
                    order.get("merchant_key_encrypted_snapshot") or ""
                ).strip()
                paid = False
                if merchant_pid and encrypted_key:
                    try:
                        key_plain = decrypt_ldc_key(
                            encrypted_key, settings.jwt_secret_key
                        )
                        query = await query_ldc_order(
                            pid=merchant_pid,
                            key=key_plain,
                            trade_no=str(order.get("ldc_trade_no") or ""),
                            order_no=str(order.get("order_no") or ""),
                        )
                        paid = bool(
                            query.get("success")
                            and str(query.get("data", {}).get("status") or "") == "1"
                        )
                    except Exception:
                        paid = False
                if paid:
                    conn.execute(
                        "UPDATE shop_orders SET status = 'paid', ldc_trade_no = COALESCE(NULLIF(ldc_trade_no, ''), ?), paid_at = COALESCE(paid_at, ?), updated_at = ? WHERE id = ?",
                        (
                            query.get("data", {}).get("tradeNo"),
                            now_ms,
                            now_ms,
                            order["id"],
                        ),
                    )
                    recovered += 1
                    continue

                conn.execute(
                    "UPDATE shop_orders SET status = 'expired', updated_at = ? WHERE id = ? AND status IN ('pending', 'paying')",
                    (now_ms, order["id"]),
                )
                if str(order.get("delivery_type") or "") == "auto":
                    locked = conn.execute(
                        "SELECT id FROM shop_cdk WHERE lock_order_id = ? AND status = 'locked'",
                        (order["id"],),
                    ).fetchall()
                    for item in locked:
                        conn.execute(
                            "UPDATE shop_cdk SET status = 'available', locked_at = NULL, lock_order_id = NULL, lock_token = NULL WHERE id = ?",
                            (item["id"],),
                        )
                    conn.execute(
                        "UPDATE shop_products SET stock = (SELECT COUNT(*) FROM shop_cdk WHERE product_id = ? AND status = 'available'), updated_at = ? WHERE id = ?",
                        (order["product_id"], now_ms, order["product_id"]),
                    )
                else:
                    conn.execute(
                        "UPDATE shop_products SET stock = COALESCE(stock, 0) + ?, updated_at = ? WHERE id = ? AND product_type = 'normal'",
                        (int(order.get("quantity") or 1), now_ms, order["product_id"]),
                    )
                conn.execute(
                    "INSERT INTO shop_order_logs (order_id, order_no, action, operator_type, operator_id, operator_name, detail, created_at) VALUES (?, ?, 'expire', 'system', NULL, 'Scheduler', ?, ?)",
                    (
                        order["id"],
                        order["order_no"],
                        '{"source":"order_expire_check"}',
                        now_ms,
                    ),
                )
                expired += 1
            conn.commit()
            if expired > 0 or trigger == "startup":
                logger.info(
                    "order_expire_check_completed",
                    trigger=trigger,
                    expired=expired,
                    recovered=recovered,
                )
        finally:
            conn.close()
    except Exception as e:
        logger.error("order_expire_check_failed", trigger=trigger, error=str(e))
    finally:
        _order_expire_running = False


_top_expire_running = False


async def shop_top_expire_job(trigger: str = "interval") -> None:
    """Expire top service orders that have passed their period."""
    global _top_expire_running
    if _top_expire_running:
        return
    _top_expire_running = True
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn = _store_db()
        try:
            cursor = conn.execute(
                "UPDATE shop_top_orders SET status = 'expired', expired_at = ?, updated_at = ? WHERE status = 'active' AND expired_at < ?",
                (now, now, now),
            )
            conn.commit()
            expired = cursor.rowcount
            if expired > 0 or trigger == "startup":
                logger.info(
                    "shop_top_expire_completed", trigger=trigger, expired=expired
                )
        finally:
            conn.close()
    except Exception as e:
        logger.error("shop_top_expire_failed", trigger=trigger, error=str(e))
    finally:
        _top_expire_running = False


_payment_sync_running = False


async def pending_payment_sync_job(trigger: str = "interval") -> None:
    """Sync pending payment status from LDC."""
    global _payment_sync_running
    if _payment_sync_running:
        return
    _payment_sync_running = True
    try:
        conn = _store_db()
        try:
            cursor = conn.execute(
                """SELECT * FROM shop_orders
                   WHERE status = 'pending'
                   AND COALESCE(TRIM(merchant_pid_snapshot), '') <> ''
                   AND COALESCE(TRIM(merchant_key_encrypted_snapshot), '') <> ''
                   LIMIT 50"""
            )
            orders = cursor.fetchall()
            checked = 0
            paid = 0
            for order in orders:
                order = dict(order)
                checked += 1
                try:
                    key_plain = decrypt_ldc_key(
                        str(order.get("merchant_key_encrypted_snapshot") or ""),
                        settings.jwt_secret_key,
                    )
                    query = await query_ldc_order(
                        pid=str(order.get("merchant_pid_snapshot") or ""),
                        key=key_plain,
                        trade_no=str(order.get("ldc_trade_no") or ""),
                        order_no=str(order.get("order_no") or ""),
                    )
                    if (
                        query.get("success")
                        and str(query.get("data", {}).get("status") or "") == "1"
                    ):
                        now_ms = int(time.time() * 1000)
                        conn.execute(
                            "UPDATE shop_orders SET status = 'paid', ldc_trade_no = COALESCE(NULLIF(ldc_trade_no, ''), ?), paid_at = COALESCE(paid_at, ?), updated_at = ? WHERE id = ? AND status = 'pending'",
                            (
                                query.get("data", {}).get("tradeNo"),
                                now_ms,
                                now_ms,
                                order["id"],
                            ),
                        )
                        paid += 1
                except Exception:
                    continue
            conn.commit()
            if orders and (trigger == "startup" or checked > 0):
                logger.info(
                    "pending_payment_sync_checkpoint",
                    trigger=trigger,
                    checked=checked,
                    paid=paid,
                )
        finally:
            conn.close()
    except Exception as e:
        logger.error("pending_payment_sync_failed", trigger=trigger, error=str(e))
    finally:
        _payment_sync_running = False


_auto_deliver_running = False


async def paid_auto_deliver_job(trigger: str = "interval") -> None:
    """Retry pending auto-delivery for paid orders."""
    global _auto_deliver_running
    if _auto_deliver_running:
        return
    _auto_deliver_running = True
    try:
        conn = _store_db()
        try:
            cursor = conn.execute(
                """SELECT id FROM shop_orders
                   WHERE status = 'paid' AND delivery_type = 'auto'
                   LIMIT 20"""
            )
            orders = cursor.fetchall()
            delivered = 0
            for order in orders:
                order_id = order["id"]
                locked = conn.execute(
                    "SELECT id, code FROM shop_cdk WHERE lock_order_id = ? AND status = 'locked' ORDER BY created_at ASC",
                    (order_id,),
                ).fetchall()
                if not locked:
                    continue
                now_ms = int(time.time() * 1000)
                delivery_content = "\n".join(str(r["code"]) for r in locked)
                conn.execute(
                    "UPDATE shop_orders SET status = 'delivered', delivery_content = ?, delivered_at = ?, updated_at = ? WHERE id = ? AND status = 'paid'",
                    (delivery_content, now_ms, now_ms, order_id),
                )
                for item in locked:
                    conn.execute(
                        "UPDATE shop_cdk SET status = 'sold', sold_at = ?, lock_token = NULL WHERE id = ?",
                        (now_ms, item["id"]),
                    )
                delivered += 1
            conn.commit()
            if orders and trigger == "startup":
                logger.info(
                    "auto_deliver_retry_checkpoint",
                    trigger=trigger,
                    pending=len(orders),
                    delivered=delivered,
                )
        finally:
            conn.close()
    except Exception as e:
        logger.error("auto_deliver_retry_failed", trigger=trigger, error=str(e))
    finally:
        _auto_deliver_running = False


_auto_offline_running = False


async def test_auto_offline_job(trigger: str = "interval") -> None:
    """Auto-offline expired test products."""
    global _auto_offline_running
    if _auto_offline_running:
        return
    _auto_offline_running = True
    try:
        conn = _store_db()
        try:
            cursor = conn.execute(
                """UPDATE shop_products SET status = 'offline', updated_at = datetime('now', '+8 hours'),
                   is_test_mode = 0
                   WHERE is_test_mode = 1 AND status = 'ai_approved' AND pin_started_at IS NOT NULL
                   AND pin_expires_at < datetime('now', '+8 hours')"""
            )
            conn.commit()
            offlined = cursor.rowcount
            if offlined > 0 or trigger == "startup":
                logger.info(
                    "test_auto_offline_completed", trigger=trigger, offlined=offlined
                )
        finally:
            conn.close()
    except Exception as e:
        logger.error("test_auto_offline_failed", trigger=trigger, error=str(e))
    finally:
        _auto_offline_running = False


_cdk_offline_running = False


async def cdk_zero_stock_offline_job(trigger: str = "interval") -> None:
    """Auto-offline zero-stock CDK products."""
    global _cdk_offline_running
    if _cdk_offline_running:
        return
    _cdk_offline_running = True
    try:
        conn = _store_db()
        try:
            cursor = conn.execute(
                """SELECT p.id FROM shop_products p
                   WHERE p.product_type = 'cdk' AND p.status IN ('ai_approved', 'manual_approved')
                     AND p.stock = 0
                     AND NOT EXISTS (
                       SELECT 1 FROM shop_cdk c WHERE c.product_id = p.id AND c.status = 'available'
                     )"""
            )
            products = [r["id"] for r in cursor.fetchall()]
            if products:
                placeholders = ",".join("?" * len(products))
                conn.execute(
                    f"""UPDATE shop_products SET status = 'offline_manual', updated_at = datetime('now', '+8 hours')
                       WHERE id IN ({placeholders})""",
                    products,
                )
                conn.commit()
            if products or trigger == "startup":
                logger.info(
                    "cdk_zero_stock_offline_completed",
                    trigger=trigger,
                    offlined=len(products),
                )
        finally:
            conn.close()
    except Exception as e:
        logger.error("cdk_zero_stock_offline_failed", trigger=trigger, error=str(e))
    finally:
        _cdk_offline_running = False


_admin_msg_dispatch_running = False


async def admin_message_dispatch_job(trigger: str = "interval") -> None:
    """Process due admin message campaigns."""
    global _admin_msg_dispatch_running
    if _admin_msg_dispatch_running:
        return
    _admin_msg_dispatch_running = True
    schedule_service, run_id = _start_store_job_run("admin_message_dispatch", trigger)
    if not schedule_service:
        _admin_msg_dispatch_running = False
        return
    try:
        conn = _store_db()
        try:
            now_ms = _now_ms()
            cursor = conn.execute(
                """SELECT id, title, content, target_type, status FROM shop_admin_message_campaigns
                   WHERE status IN ('pending', 'sending')
                      OR (status = 'scheduled' AND COALESCE(scheduled_at, 0) > 0 AND scheduled_at <= ?)
                   ORDER BY CASE WHEN status = 'scheduled' THEN scheduled_at ELSE created_at END ASC, id ASC
                   LIMIT 3""",
                (now_ms,),
            )
            campaigns = cursor.fetchall()
            processed_campaigns = 0
            sent = 0
            failed = 0
            completed_campaigns = 0
            for campaign in campaigns:
                campaign_id = int(campaign["id"] or 0)
                if campaign_id <= 0:
                    continue
                conn.execute(
                    """UPDATE shop_admin_message_campaigns
                       SET status = 'sending', started_at = COALESCE(started_at, ?), updated_at = ?
                       WHERE id = ? AND status <> 'cancelled'""",
                    (now_ms, now_ms, campaign_id),
                )
                targets = conn.execute(
                    """SELECT id, user_site, user_id
                       FROM shop_admin_message_targets
                       WHERE campaign_id = ? AND status = 'pending'
                       ORDER BY id ASC LIMIT ?""",
                    (campaign_id, ADMIN_MSG_DISPATCH_BATCH_SIZE),
                ).fetchall()
                campaign_last_error = ""
                campaign_sent = 0
                campaign_failed = 0
                for target in targets:
                    target_id = int(target["id"] or 0)
                    if target_id <= 0:
                        continue
                    dedupe_key = f"admin_campaign:{campaign_id}:target:{target_id}"
                    content = str(campaign["content"] or "").strip()
                    title = str(campaign["title"] or "系统消息").strip() or "系统消息"
                    extra_json = json.dumps(
                        {
                            "source": "admin_campaign",
                            "campaignId": campaign_id,
                            "targetId": target_id,
                            "targetType": campaign["target_type"] or "all",
                        },
                        ensure_ascii=False,
                    )
                    try:
                        created = conn.execute(
                            """INSERT OR IGNORE INTO shop_user_messages (
                                user_site, user_id, message_type, title, content,
                                ref_type, ref_id, extra_json, dedupe_key,
                                is_read, read_at, created_at, updated_at
                            ) VALUES (?, ?, 'system', ?, ?, 'admin_campaign', ?, ?, ?, 0, NULL, ?, ?)""",
                            (
                                target["user_site"] or "linux.do",
                                str(target["user_id"] or ""),
                                title,
                                content,
                                campaign_id,
                                extra_json,
                                dedupe_key,
                                now_ms,
                                now_ms,
                            ),
                        )
                        message_id = int(created.lastrowid or 0)
                        if int(created.rowcount or 0) <= 0:
                            existing = conn.execute(
                                """SELECT id FROM shop_user_messages
                                   WHERE user_site = ? AND user_id = ? AND dedupe_key = ? LIMIT 1""",
                                (
                                    target["user_site"] or "linux.do",
                                    str(target["user_id"] or ""),
                                    dedupe_key,
                                ),
                            ).fetchone()
                            if not existing:
                                raise RuntimeError("message_insert_failed")
                            message_id = int(existing["id"] or 0)
                            conn.execute(
                                """UPDATE shop_user_messages
                                   SET title = ?, content = ?, extra_json = ?, is_read = 0, read_at = NULL, updated_at = ?
                                   WHERE id = ?""",
                                (title, content, extra_json, now_ms, message_id),
                            )
                        conn.execute(
                            """UPDATE shop_admin_message_targets
                               SET status = 'sent', message_id = ?, error_message = NULL, sent_at = ?, updated_at = ?
                               WHERE id = ?""",
                            (message_id, now_ms, now_ms, target_id),
                        )
                        campaign_sent += 1
                    except Exception as single_error:
                        campaign_last_error = str(single_error)
                        conn.execute(
                            """UPDATE shop_admin_message_targets
                               SET status = 'failed', error_message = ?, updated_at = ?
                               WHERE id = ?""",
                            (campaign_last_error, now_ms, target_id),
                        )
                        campaign_failed += 1

                stats = conn.execute(
                    """SELECT
                            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_count,
                            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count
                       FROM shop_admin_message_targets
                       WHERE campaign_id = ?""",
                    (campaign_id,),
                ).fetchone()
                pending_count = int((stats["pending_count"] if stats else 0) or 0)
                failed_count = int((stats["failed_count"] if stats else 0) or 0)
                final_status = "sending"
                finished_at = None
                if pending_count <= 0:
                    final_status = "partial_failed" if failed_count > 0 else "completed"
                    finished_at = now_ms
                    completed_campaigns += 1
                conn.execute(
                    """UPDATE shop_admin_message_campaigns
                       SET status = ?, finished_at = ?, last_error = ?, updated_at = ?
                       WHERE id = ?""",
                    (
                        final_status,
                        finished_at,
                        campaign_last_error or None,
                        now_ms,
                        campaign_id,
                    ),
                )
                processed_campaigns += 1
                sent += campaign_sent
                failed += campaign_failed
            conn.commit()
            if campaigns and trigger == "startup":
                logger.info(
                    "admin_message_dispatch_checkpoint",
                    trigger=trigger,
                    due=len(campaigns),
                )
            _finish_store_job_run(
                schedule_service,
                run_id,
                "admin_message_dispatch",
                status="success",
                result={
                    "discovered": len(campaigns),
                    "processedCampaigns": processed_campaigns,
                    "sent": sent,
                    "failed": failed,
                    "completedCampaigns": completed_campaigns,
                },
            )
        finally:
            conn.close()
    except Exception as e:
        logger.error("admin_message_dispatch_failed", trigger=trigger, error=str(e))
        _finish_store_job_run(
            schedule_service,
            run_id,
            "admin_message_dispatch",
            status="failed",
            error_message=str(e),
        )
    finally:
        _admin_msg_dispatch_running = False


_restock_recovery_running = False


async def restock_notification_recovery_job(trigger: str = "interval") -> None:
    """Recover stuck restock notification states."""
    global _restock_recovery_running
    if _restock_recovery_running:
        return
    _restock_recovery_running = True
    schedule_service, run_id = _start_store_job_run("restock_recovery", trigger)
    if not schedule_service:
        _restock_recovery_running = False
        return
    try:
        conn = _store_db()
        try:
            now_ms = _now_ms()
            stale_threshold = now_ms - RESTOCK_PROCESSING_STALE_MS
            cursor = conn.execute(
                """UPDATE shop_product_restock_subscriptions
                   SET status = 'active', updated_at = ?
                   WHERE status = 'processing' AND updated_at < ?""",
                (now_ms, stale_threshold),
            )
            recovered = cursor.rowcount
            product_limit = max(_env_int("RESTOCK_NOTIFICATION_RECOVERY_LIMIT", 50), 1)
            products = conn.execute(
                """SELECT p.id, p.name,
                          (SELECT COUNT(*) FROM shop_cdk c WHERE c.product_id = p.id AND c.status = 'available') AS available_stock
                   FROM shop_products p
                   WHERE p.product_type = 'cdk'
                     AND p.status IN ('ai_approved', 'manual_approved', 'approved')
                     AND COALESCE(p.is_deleted, 0) = 0
                     AND EXISTS (
                        SELECT 1 FROM shop_product_restock_subscriptions s
                        WHERE s.product_id = p.id AND s.status = 'active'
                     )
                     AND (SELECT COUNT(*) FROM shop_cdk c WHERE c.product_id = p.id AND c.status = 'available') > 0
                   ORDER BY p.updated_at ASC, p.id ASC
                   LIMIT ?""",
                (product_limit,),
            ).fetchall()
            processed_products = 0
            notified = 0
            notified_product_ids: set[int] = set()
            for product in products:
                product_id = int(product["id"] or 0)
                available_stock = int(product["available_stock"] or 0)
                if product_id <= 0 or available_stock <= 0:
                    continue
                subscriptions = conn.execute(
                    """SELECT id, user_site, user_id
                       FROM shop_product_restock_subscriptions
                       WHERE product_id = ? AND status = 'active'
                       ORDER BY id ASC LIMIT ?""",
                    (product_id, RESTOCK_NOTIFY_BATCH_SIZE),
                ).fetchall()
                product_notified = 0
                for sub in subscriptions:
                    sub_id = int(sub["id"] or 0)
                    if sub_id <= 0:
                        continue
                    claim = conn.execute(
                        """UPDATE shop_product_restock_subscriptions
                           SET status = 'processing', updated_at = ?
                           WHERE id = ? AND status = 'active'""",
                        (now_ms, sub_id),
                    )
                    if int(claim.rowcount or 0) <= 0:
                        continue
                    try:
                        dedupe_key = (
                            f"restock_subscription:{sub_id}:product:{product_id}"
                        )
                        title = "商品补货通知"
                        content = f"你订阅的商品《{product['name'] or f'#{product_id}'}》已补货，当前可用库存 {available_stock}，可前往商品详情页下单。"
                        extra_json = json.dumps(
                            {
                                "productId": product_id,
                                "productName": product["name"] or f"#{product_id}",
                                "availableStock": available_stock,
                                "source": "restock_subscription",
                                "subscriptionId": sub_id,
                            },
                            ensure_ascii=False,
                        )
                        created = conn.execute(
                            """INSERT OR IGNORE INTO shop_user_messages (
                                user_site, user_id, message_type, title, content,
                                ref_type, ref_id, extra_json, dedupe_key,
                                is_read, read_at, created_at, updated_at
                            ) VALUES (?, ?, 'product_restock', ?, ?, 'product', ?, ?, ?, 0, NULL, ?, ?)""",
                            (
                                sub["user_site"] or "linux.do",
                                str(sub["user_id"] or ""),
                                title,
                                content,
                                product_id,
                                extra_json,
                                dedupe_key,
                                now_ms,
                                now_ms,
                            ),
                        )
                        if int(created.rowcount or 0) <= 0:
                            existing = conn.execute(
                                """SELECT id FROM shop_user_messages
                                   WHERE user_site = ? AND user_id = ? AND dedupe_key = ? LIMIT 1""",
                                (
                                    sub["user_site"] or "linux.do",
                                    str(sub["user_id"] or ""),
                                    dedupe_key,
                                ),
                            ).fetchone()
                            if existing:
                                conn.execute(
                                    """UPDATE shop_user_messages
                                       SET title = ?, content = ?, extra_json = ?, is_read = 0, read_at = NULL, updated_at = ?
                                       WHERE id = ?""",
                                    (
                                        title,
                                        content,
                                        extra_json,
                                        now_ms,
                                        int(existing["id"]),
                                    ),
                                )
                        conn.execute(
                            """UPDATE shop_product_restock_subscriptions
                               SET status = 'notified', notified_at = ?, updated_at = ?
                               WHERE id = ?""",
                            (now_ms, now_ms, sub_id),
                        )
                        product_notified += 1
                        notified += 1
                    except Exception:
                        conn.execute(
                            """UPDATE shop_product_restock_subscriptions
                               SET status = 'active', updated_at = ?
                               WHERE id = ?""",
                            (now_ms, sub_id),
                        )
                if product_notified > 0:
                    processed_products += 1
                    notified_product_ids.add(product_id)
            if notified_product_ids:
                placeholders = ",".join("?" * len(notified_product_ids))
                conn.execute(
                    f"""UPDATE shop_product_seller_restock_alerts
                        SET status = 'resolved', resolved_reason = 'restocked', resolved_at = ?, updated_at = ?
                        WHERE status = 'active' AND product_id IN ({placeholders})""",
                    [now_ms, now_ms, *sorted(notified_product_ids)],
                )
            conn.commit()
            if recovered > 0 or trigger == "startup":
                logger.info(
                    "restock_recovery_completed",
                    trigger=trigger,
                    recovered=recovered,
                    processed_products=processed_products,
                    notified=notified,
                )
            _finish_store_job_run(
                schedule_service,
                run_id,
                "restock_recovery",
                status="success",
                result={
                    "recoveredProcessing": recovered,
                    "checkedProducts": len(products),
                    "processedProducts": processed_products,
                    "notified": notified,
                },
            )
        finally:
            conn.close()
    except Exception as e:
        logger.error("restock_recovery_failed", trigger=trigger, error=str(e))
        _finish_store_job_run(
            schedule_service,
            run_id,
            "restock_recovery",
            status="failed",
            error_message=str(e),
        )
    finally:
        _restock_recovery_running = False


_product_ai_queue_running = False


async def product_ai_review_queue_job(trigger: str = "interval") -> None:
    """Process pending AI review queue for products."""
    global _product_ai_queue_running
    if _product_ai_queue_running:
        return
    _product_ai_queue_running = True
    schedule_service = StoreScheduleService()
    if not schedule_service.is_job_enabled("product_ai_queue"):
        _product_ai_queue_running = False
        return
    run_id = schedule_service.start_run("product_ai_queue", trigger)
    try:
        conn = _store_db()
        try:
            batch_size = _env_int("PRODUCT_AI_REVIEW_QUEUE_BATCH_SIZE", 3)
            cursor = conn.execute(
                """SELECT id, name FROM shop_products
                   WHERE status = 'pending_ai'
                   AND (ai_review_started_at IS NULL OR ai_review_started_at < ?)
                   LIMIT ?""",
                ((int(time.time() * 1000) - 600000), batch_size),
            )
            products = cursor.fetchall()
            processed = 0
            runtime = AgentRuntimeService()
            for product in products:
                try:
                    await runtime.run_product_review(
                        int(product["id"]),
                        review_config_id=None,
                        trigger_source="scheduler",
                        operator={"user_id": "scheduler", "username": "scheduler"},
                    )
                    processed += 1
                except Exception as single_error:
                    logger.error(
                        "product_ai_queue_item_failed",
                        product_id=product["id"],
                        error=str(single_error),
                    )
            if products and trigger == "startup":
                logger.info(
                    "product_ai_queue_checkpoint",
                    trigger=trigger,
                    pending=len(products),
                )
            schedule_service.finish_run(
                run_id,
                "product_ai_queue",
                status="success",
                result={"discovered": len(products), "processed": processed},
            )
        finally:
            conn.close()
    except Exception as e:
        logger.error("product_ai_queue_failed", trigger=trigger, error=str(e))
        schedule_service.finish_run(
            run_id,
            "product_ai_queue",
            status="failed",
            error_message=str(e),
        )
    finally:
        _product_ai_queue_running = False


_comment_ai_queue_running = False


async def comment_ai_review_queue_job(trigger: str = "interval") -> None:
    """Process pending AI review queue for comments."""
    global _comment_ai_queue_running
    if _comment_ai_queue_running:
        return
    _comment_ai_queue_running = True
    schedule_service = StoreScheduleService()
    if not schedule_service.is_job_enabled("comment_ai_queue"):
        _comment_ai_queue_running = False
        return
    run_id = schedule_service.start_run("comment_ai_queue", trigger)
    try:
        conn = _store_db()
        try:
            batch_size = _env_int("COMMENT_AI_REVIEW_QUEUE_BATCH_SIZE", 5)
            cursor = conn.execute(
                """SELECT id, content FROM shop_product_comments
                   WHERE status = 'pending_ai'
                   AND (ai_reviewed_at IS NULL OR ai_reviewed_at < ?)
                   LIMIT ?""",
                ((int(time.time() * 1000) - 600000), batch_size),
            )
            comments = cursor.fetchall()
            processed = 0
            runtime = AgentRuntimeService()
            for comment in comments:
                try:
                    await runtime.run_comment_review(
                        content=comment["content"] or "",
                        target_id=f"comment:{comment['id']}",
                        context={
                            "comment_id": int(comment["id"]),
                            "product_id": int(comment["product_id"])
                            if "product_id" in comment.keys()
                            else 0,
                        },
                        trigger_source="scheduler",
                        operator={"user_id": "scheduler", "username": "scheduler"},
                    )
                    processed += 1
                except Exception as single_error:
                    logger.error(
                        "comment_ai_queue_item_failed",
                        comment_id=comment["id"],
                        error=str(single_error),
                    )
            if comments and trigger == "startup":
                logger.info(
                    "comment_ai_queue_checkpoint",
                    trigger=trigger,
                    pending=len(comments),
                )
            schedule_service.finish_run(
                run_id,
                "comment_ai_queue",
                status="success",
                result={"discovered": len(comments), "processed": processed},
            )
        finally:
            conn.close()
    except Exception as e:
        logger.error("comment_ai_queue_failed", trigger=trigger, error=str(e))
        schedule_service.finish_run(
            run_id,
            "comment_ai_queue",
            status="failed",
            error_message=str(e),
        )
    finally:
        _comment_ai_queue_running = False


_product_ai_recovery_running = False


async def product_ai_review_recovery_job(trigger: str = "interval") -> None:
    """Recover stuck products from pending_ai status."""
    global _product_ai_recovery_running
    if _product_ai_recovery_running:
        return
    _product_ai_recovery_running = True
    try:
        conn = _store_db()
        try:
            stale_ms = _env_int("PRODUCT_AI_REVIEW_STALE_MS", 600000)
            stale_time = int(time.time() * 1000) - stale_ms
            limit = _env_int("PRODUCT_AI_REVIEW_RECOVERY_LIMIT", 50)
            cursor = conn.execute(
                """UPDATE shop_products SET status = 'pending_ai',
                   ai_review_started_at = NULL, ai_review_heartbeat_at = NULL, updated_at = datetime('now', '+8 hours')
                   WHERE id IN (
                     SELECT id FROM shop_products
                     WHERE status = 'pending_ai' AND ai_review_started_at IS NOT NULL
                     AND ai_review_heartbeat_at < ?
                     ORDER BY ai_review_started_at ASC
                     LIMIT ?
                   )""",
                (stale_time, limit),
            )
            conn.commit()
            recovered = cursor.rowcount
            if recovered > 0 or trigger == "startup":
                logger.info(
                    "product_ai_recovery_completed",
                    trigger=trigger,
                    recovered=recovered,
                )
        finally:
            conn.close()
    except Exception as e:
        logger.error("product_ai_recovery_failed", trigger=trigger, error=str(e))
    finally:
        _product_ai_recovery_running = False


_comment_ai_recovery_running = False


async def comment_ai_review_recovery_job(trigger: str = "interval") -> None:
    """Recover stuck comments from pending_ai status."""
    global _comment_ai_recovery_running
    if _comment_ai_recovery_running:
        return
    _comment_ai_recovery_running = True
    try:
        conn = _store_db()
        try:
            stale_ms = _env_int("COMMENT_AI_REVIEW_STALE_MS", 600000)
            stale_time = int(time.time() * 1000) - stale_ms
            limit = _env_int("COMMENT_AI_REVIEW_RECOVERY_LIMIT", 50)
            cursor = conn.execute(
                """UPDATE shop_product_comments SET status = 'pending_ai',
                   ai_reviewed_at = NULL
                   WHERE id IN (
                     SELECT id FROM shop_product_comments
                     WHERE status = 'pending_ai' AND ai_reviewed_at IS NOT NULL
                     AND ai_reviewed_at < ?
                     ORDER BY ai_reviewed_at ASC
                     LIMIT ?
                   )""",
                (stale_time, limit),
            )
            conn.commit()
            recovered = cursor.rowcount
            if recovered > 0 or trigger == "startup":
                logger.info(
                    "comment_ai_recovery_completed",
                    trigger=trigger,
                    recovered=recovered,
                )
        finally:
            conn.close()
    except Exception as e:
        logger.error("comment_ai_recovery_failed", trigger=trigger, error=str(e))
    finally:
        _comment_ai_recovery_running = False


_ops_report_running = False


async def shop_ops_report_scheduler_job(trigger: str = "interval") -> None:
    """Run due operations report jobs."""
    global _ops_report_running
    if _ops_report_running:
        return
    _ops_report_running = True
    schedule_service, run_id = _start_store_job_run("ops_report_scheduler", trigger)
    if not schedule_service:
        _ops_report_running = False
        return
    try:
        conn = _store_db()
        try:
            cursor = conn.execute(
                """SELECT report_type, schedule_json, last_slot_key, last_run_status
                   FROM shop_ops_report_configs
                   WHERE enabled = 1
                   ORDER BY report_type ASC"""
            )
            reports = cursor.fetchall()
            runtime = AgentRuntimeService()
            generated = 0
            now_ms = _now_ms()
            items: list[dict[str, Any]] = []
            for report in reports:
                try:
                    schedule = _safe_json_loads(report.get("schedule_json"), {}) or {}
                    slot = _resolve_shop_ops_report_slot(
                        report["report_type"], schedule, now_ms
                    )
                    if (report.get("last_slot_key") or "") == slot["slotKey"]:
                        items.append(
                            {
                                "reportType": report["report_type"],
                                "executed": False,
                                "skippedReason": "already_generated",
                                "slotKey": slot["slotKey"],
                            }
                        )
                        continue
                    pending_run = conn.execute(
                        """SELECT run_id FROM agent_runs
                           WHERE agent_key = 'ops_copilot'
                             AND mode = 'prod'
                             AND status IN ('queued', 'running')
                             AND json_extract(input_json, '$.reportMeta.reportType') = ?
                           ORDER BY created_at ASC LIMIT 1""",
                        (report["report_type"],),
                    ).fetchone()
                    if pending_run:
                        items.append(
                            {
                                "reportType": report["report_type"],
                                "executed": False,
                                "skippedReason": "pending_run",
                                "runId": pending_run["run_id"],
                                "slotKey": slot["slotKey"],
                            }
                        )
                        continue
                    result = runtime.create_report_run(
                        report["report_type"],
                        payload={},
                        trigger_source=f"shop_ops_report_scheduler_{report['report_type']}",
                        operator={"user_id": "scheduler", "username": "scheduler"},
                    )
                    conn.execute(
                        """UPDATE shop_ops_report_configs
                           SET last_run_at = ?, last_slot_key = ?, last_run_id = ?, last_run_status = 'queued', updated_at = ?
                           WHERE report_type = ?""",
                        (
                            now_ms,
                            slot["slotKey"],
                            result.get("runId"),
                            now_ms,
                            report["report_type"],
                        ),
                    )
                    generated += 1
                    items.append(
                        {
                            "reportType": report["report_type"],
                            "executed": True,
                            "runId": result.get("runId"),
                            "slotKey": slot["slotKey"],
                        }
                    )
                except Exception as single_error:
                    logger.error(
                        "ops_report_generate_failed",
                        report_type=report["report_type"],
                        error=str(single_error),
                    )
                    items.append(
                        {
                            "reportType": report["report_type"],
                            "executed": False,
                            "skippedReason": "run_error",
                            "message": str(single_error),
                        }
                    )
            conn.commit()
            if reports and trigger == "startup":
                logger.info(
                    "ops_report_schedule_checkpoint", trigger=trigger, due=len(reports)
                )
            schedule_service.finish_run(
                run_id,
                "ops_report_scheduler",
                status="success",
                result={
                    "discovered": len(reports),
                    "generated": generated,
                    "items": items,
                },
            )
        finally:
            conn.close()
    except Exception as e:
        logger.error("ops_report_schedule_failed", trigger=trigger, error=str(e))
        schedule_service.finish_run(
            run_id,
            "ops_report_scheduler",
            status="failed",
            error_message=str(e),
        )
    finally:
        _ops_report_running = False


_ops_copilot_running = False


async def shop_ops_copilot_queue_job(trigger: str = "interval") -> None:
    """Process pending Ops Copilot queue."""
    global _ops_copilot_running
    if _ops_copilot_running:
        return
    _ops_copilot_running = True
    schedule_service, run_id = _start_store_job_run("ops_copilot_queue", trigger)
    if not schedule_service:
        _ops_copilot_running = False
        return
    try:
        conn = _store_db()
        try:
            now_ms = _now_ms()
            stale_threshold = now_ms - 30 * 60 * 1000
            recovered = conn.execute(
                """UPDATE agent_runs
                   SET status = 'queued', error_type = NULL, error_message = NULL, ended_at = NULL, updated_at = ?
                   WHERE agent_key = 'ops_copilot'
                     AND status = 'running'
                     AND updated_at > 0
                     AND updated_at <= ?""",
                (now_ms, stale_threshold),
            ).rowcount
            cursor = conn.execute(
                """SELECT run_id, mode, input_json, output_json
                   FROM agent_runs
                   WHERE agent_key = 'ops_copilot' AND status = 'queued'
                   ORDER BY created_at ASC
                   LIMIT 1"""
            )
            items = cursor.fetchall()
            processed = 0
            failed = 0
            details: list[dict[str, Any]] = []
            for item in items:
                claim = conn.execute(
                    """UPDATE agent_runs
                       SET status = 'running', started_at = COALESCE(started_at, ?), updated_at = ?
                       WHERE run_id = ? AND agent_key = 'ops_copilot' AND status = 'queued'""",
                    (now_ms, now_ms, item["run_id"]),
                )
                if int(claim.rowcount or 0) <= 0:
                    continue
                try:
                    input_payload = _safe_json_loads(item.get("input_json"), {}) or {}
                    report_meta = input_payload.get("reportMeta") or {}
                    report_type = (
                        str(report_meta.get("reportType") or "daily").strip().lower()
                    )
                    analytics = _build_ops_analytics_snapshot(conn, report_type, now_ms)
                    report = _build_ops_copilot_fallback_report(
                        report_type, now_ms, analytics
                    )
                    output_payload = {
                        "summary": report.get("summary") or "",
                        "structured": report,
                        "report": report,
                        "analyticsMeta": analytics.get("periodMeta") or {},
                        "capability_key": {
                            "daily": "shop_ops_daily_report",
                            "weekly": "shop_ops_weekly_report",
                            "monthly": "shop_ops_monthly_report",
                        }.get(report_type, "shop_ops_daily_report"),
                        "provider_type": "scheduler_fallback",
                        "gateway_route": "",
                    }
                    end_ms = _now_ms()
                    conn.execute(
                        """UPDATE agent_runs
                           SET status = 'success', decision = 'approve', decision_source = 'scheduler_fallback',
                               output_json = ?, error_type = NULL, error_message = NULL,
                               latency_ms = ?, token_used = 0, cost_micros = 0, risk_score = 0,
                               ended_at = ?, updated_at = ?
                           WHERE run_id = ? AND agent_key = 'ops_copilot'""",
                        (
                            json.dumps(output_payload, ensure_ascii=False),
                            max(end_ms - now_ms, 1),
                            end_ms,
                            end_ms,
                            item["run_id"],
                        ),
                    )
                    if report_type in {"daily", "weekly", "monthly"}:
                        config = conn.execute(
                            "SELECT schedule_json FROM shop_ops_report_configs WHERE report_type = ? LIMIT 1",
                            (report_type,),
                        ).fetchone()
                        slot = _resolve_shop_ops_report_slot(
                            report_type,
                            _safe_json_loads(config["schedule_json"], {})
                            if config
                            else {},
                            now_ms,
                        )
                        conn.execute(
                            """UPDATE shop_ops_report_configs
                               SET last_run_status = 'success', last_run_id = ?, last_run_at = ?, last_success_at = ?, last_slot_key = ?, updated_at = ?
                               WHERE report_type = ?""",
                            (
                                item["run_id"],
                                end_ms,
                                end_ms,
                                slot["slotKey"],
                                end_ms,
                                report_type,
                            ),
                        )
                    processed += 1
                    details.append(
                        {
                            "runId": item["run_id"],
                            "status": "success",
                            "reportType": report_type,
                        }
                    )
                except Exception as single_error:
                    failed += 1
                    end_ms = _now_ms()
                    conn.execute(
                        """UPDATE agent_runs
                           SET status = 'failed', decision = 'manual_review', decision_source = 'scheduler_fallback',
                               error_type = 'RUN_FAILED', error_message = ?, ended_at = ?, updated_at = ?
                           WHERE run_id = ? AND agent_key = 'ops_copilot'""",
                        (str(single_error), end_ms, end_ms, item["run_id"]),
                    )
                    details.append(
                        {
                            "runId": item["run_id"],
                            "status": "failed",
                            "message": str(single_error),
                        }
                    )
            conn.commit()
            if items and trigger == "startup":
                logger.info(
                    "ops_copilot_queue_checkpoint",
                    trigger=trigger,
                    pending=len(items),
                    recovered=recovered,
                )
            _finish_store_job_run(
                schedule_service,
                run_id,
                "ops_copilot_queue",
                status="success",
                result={
                    "checked": len(items),
                    "processed": processed,
                    "failed": failed,
                    "recovered": recovered,
                    "items": details,
                },
            )
        finally:
            conn.close()
    except Exception as e:
        logger.error("ops_copilot_queue_failed", trigger=trigger, error=str(e))
        _finish_store_job_run(
            schedule_service,
            run_id,
            "ops_copilot_queue",
            status="failed",
            error_message=str(e),
        )
    finally:
        _ops_copilot_running = False


_shadow_snapshot_running = False


async def shadow_readiness_snapshot_job(trigger: str = "interval") -> None:
    """Create lightweight shadow readiness snapshots on the legacy schedule."""
    global _shadow_snapshot_running
    if not SHADOW_SNAPSHOT_AUTO_ENABLED or SHADOW_SNAPSHOT_INTERVAL <= 0:
        return
    if _shadow_snapshot_running:
        return
    _shadow_snapshot_running = True
    schedule_service, run_id = _start_store_job_run(
        "shadow_readiness_snapshot", trigger
    )
    if not schedule_service:
        _shadow_snapshot_running = False
        return
    try:
        conn = _store_db()
        try:
            _ensure_shadow_snapshot_table(conn)
            now_ms = _now_ms()
            created = 0
            snapshots: list[dict[str, Any]] = []
            for agent_key in SHADOW_SNAPSHOT_AGENT_KEYS:
                config = {
                    "source": "system_scheduler",
                    "days": SHADOW_SNAPSHOT_DAYS,
                    "agentKey": agent_key,
                    "generatedAt": now_ms,
                }
                cur = conn.execute(
                    "INSERT INTO shadow_readiness_snapshots (agent_key, config, created_at) VALUES (?, ?, ?)",
                    (
                        agent_key,
                        json.dumps(config, ensure_ascii=False),
                        _beijing_dt(now_ms).strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )
                created += int(cur.rowcount or 0)
                snapshots.append(
                    {"agentKey": agent_key, "snapshotId": int(cur.lastrowid or 0)}
                )
            conn.commit()
            logger.info(
                "shadow_readiness_snapshot_completed",
                trigger=trigger,
                created=created,
                agent_keys=SHADOW_SNAPSHOT_AGENT_KEYS,
            )
            _finish_store_job_run(
                schedule_service,
                run_id,
                "shadow_readiness_snapshot",
                status="success",
                result={"created": created, "snapshots": snapshots},
            )
        finally:
            conn.close()
    except Exception as e:
        logger.error("shadow_readiness_snapshot_failed", trigger=trigger, error=str(e))
        _finish_store_job_run(
            schedule_service,
            run_id,
            "shadow_readiness_snapshot",
            status="failed",
            error_message=str(e),
        )
    finally:
        _shadow_snapshot_running = False


# ──────────────────────────────────────────
# Scheduler initialization
# ──────────────────────────────────────────


def init_scheduler() -> AsyncIOScheduler:
    """Initialize and start the APScheduler with all jobs.

    Call this in FastAPI lifespan.
    """
    global _scheduler

    _scheduler = AsyncIOScheduler(
        jobstores={"default": MemoryJobStore()},
        job_defaults={"coalesce": True, "max_instances": 1},
    )
    schedule_service = StoreScheduleService()

    # ── LDStatusPro Jobs ──

    if ENABLE_BUFFER_WRITE_BACK:
        _scheduler.add_job(
            buffer_flush_job,
            "interval",
            seconds=BUFFER_FLUSH_INTERVAL,
            id="buffer_flush",
            name="Buffer Flush",
            max_instances=1,
            replace_existing=True,
        )
        logger.info("scheduled buffer_flush", interval_s=BUFFER_FLUSH_INTERVAL)

    _scheduler.add_job(
        audit_flush_job,
        "interval",
        seconds=AUDIT_FLUSH_INTERVAL,
        id="audit_flush",
        name="Audit Flush",
        max_instances=1,
    )
    logger.info("scheduled audit_flush", interval_s=AUDIT_FLUSH_INTERVAL)

    _scheduler.add_job(
        audit_cleanup_job,
        "interval",
        seconds=AUDIT_CLEANUP_INTERVAL,
        id="audit_cleanup",
        name="Audit Cleanup",
        max_instances=1,
    )
    logger.info("scheduled audit_cleanup", interval_s=AUDIT_CLEANUP_INTERVAL)

    if ENABLE_SECURITY_CLEANUP:
        _scheduler.add_job(
            security_cleanup_job,
            "interval",
            seconds=SECURITY_CLEANUP_INTERVAL,
            id="security_cleanup",
            name="Security Cleanup",
            max_instances=1,
        )
        logger.info("scheduled security_cleanup", interval_s=SECURITY_CLEANUP_INTERVAL)

    if ENABLE_LEADERBOARD_PRECOMPUTE:
        _scheduler.add_job(
            daily_leaderboard_job,
            "interval",
            seconds=DAILY_LEADERBOARD_INTERVAL,
            id="daily_leaderboard",
            name="Daily Leaderboard",
            max_instances=1,
        )
        _scheduler.add_job(
            weekly_leaderboard_job,
            "interval",
            seconds=WEEKLY_LEADERBOARD_INTERVAL,
            id="weekly_leaderboard",
            name="Weekly Leaderboard",
            max_instances=1,
        )
        _scheduler.add_job(
            monthly_leaderboard_job,
            "interval",
            seconds=MONTHLY_LEADERBOARD_INTERVAL,
            id="monthly_leaderboard",
            name="Monthly Leaderboard",
            max_instances=1,
        )
        logger.info(
            "scheduled leaderboards",
            daily_s=DAILY_LEADERBOARD_INTERVAL,
            weekly_s=WEEKLY_LEADERBOARD_INTERVAL,
            monthly_s=MONTHLY_LEADERBOARD_INTERVAL,
        )

    # ── LD Store Jobs ──

    _scheduler.add_job(
        order_expire_check_job,
        "interval",
        seconds=ORDER_EXPIRE_CHECK_INTERVAL,
        id="order_expire_check",
        name="Order Expire Check",
        max_instances=1,
    )
    _upsert_interval_job_metadata(
        schedule_service,
        job_key="order_expire_check",
        job_type="order_expire_check",
        interval_seconds=ORDER_EXPIRE_CHECK_INTERVAL,
        runtime_config={"legacySource": "ld_store_backend.order_expire"},
    )
    _scheduler.add_job(
        shop_top_expire_job,
        "interval",
        seconds=SHOP_TOP_EXPIRE_INTERVAL,
        id="shop_top_expire",
        name="Shop Top Expire",
        max_instances=1,
    )
    _upsert_interval_job_metadata(
        schedule_service,
        job_key="shop_top_expire",
        job_type="shop_top_expire",
        interval_seconds=SHOP_TOP_EXPIRE_INTERVAL,
        runtime_config={"legacySource": "ld_store_backend.shop_top_expire"},
    )
    _scheduler.add_job(
        pending_payment_sync_job,
        "interval",
        seconds=PAYMENT_SYNC_INTERVAL,
        id="pending_payment_sync",
        name="Payment Sync",
        max_instances=1,
    )
    _upsert_interval_job_metadata(
        schedule_service,
        job_key="pending_payment_sync",
        job_type="pending_payment_sync",
        interval_seconds=PAYMENT_SYNC_INTERVAL,
        runtime_config={"legacySource": "ld_store_backend.payment_sync"},
    )
    _scheduler.add_job(
        paid_auto_deliver_job,
        "interval",
        seconds=PAID_AUTO_DELIVER_INTERVAL,
        id="paid_auto_deliver",
        name="Auto Delivery",
        max_instances=1,
    )
    _upsert_interval_job_metadata(
        schedule_service,
        job_key="paid_auto_deliver",
        job_type="paid_auto_deliver",
        interval_seconds=PAID_AUTO_DELIVER_INTERVAL,
        runtime_config={"legacySource": "ld_store_backend.auto_deliver"},
    )
    _scheduler.add_job(
        test_auto_offline_job,
        "interval",
        seconds=TEST_AUTO_OFFLINE_INTERVAL,
        id="test_auto_offline",
        name="Test Auto-Offline",
        max_instances=1,
    )
    _upsert_interval_job_metadata(
        schedule_service,
        job_key="test_auto_offline",
        job_type="test_auto_offline",
        interval_seconds=TEST_AUTO_OFFLINE_INTERVAL,
        runtime_config={"legacySource": "ld_store_backend.test_auto_offline"},
    )
    _scheduler.add_job(
        cdk_zero_stock_offline_job,
        "interval",
        seconds=CDK_ZERO_STOCK_INTERVAL,
        id="cdk_zero_stock_offline",
        name="CDK Zero-Stock Offline",
        max_instances=1,
    )
    _upsert_interval_job_metadata(
        schedule_service,
        job_key="cdk_zero_stock_offline",
        job_type="cdk_zero_stock_offline",
        interval_seconds=CDK_ZERO_STOCK_INTERVAL,
        runtime_config={"legacySource": "ld_store_backend.zero_stock_offline"},
    )
    _scheduler.add_job(
        admin_message_dispatch_job,
        "interval",
        seconds=ADMIN_MSG_DISPATCH_INTERVAL,
        id="admin_message_dispatch",
        name="Admin Message Dispatch",
        max_instances=1,
    )
    _upsert_interval_job_metadata(
        schedule_service,
        job_key="admin_message_dispatch",
        job_type="admin_message_dispatch",
        interval_seconds=ADMIN_MSG_DISPATCH_INTERVAL,
        runtime_config={
            "batchSize": ADMIN_MSG_DISPATCH_BATCH_SIZE,
            "legacySource": "ld_store_backend.admin_message_dispatch",
        },
    )
    _scheduler.add_job(
        restock_notification_recovery_job,
        "interval",
        seconds=RESTOCK_RECOVERY_INTERVAL,
        id="restock_recovery",
        name="Restock Recovery",
        max_instances=1,
    )
    _upsert_interval_job_metadata(
        schedule_service,
        job_key="restock_recovery",
        job_type="restock_notification_recovery",
        interval_seconds=RESTOCK_RECOVERY_INTERVAL,
        runtime_config={
            "processingStaleMs": RESTOCK_PROCESSING_STALE_MS,
            "batchSize": RESTOCK_NOTIFY_BATCH_SIZE,
            "legacySource": "ld_store_backend.restock_recovery",
        },
    )
    _scheduler.add_job(
        product_ai_review_queue_job,
        "interval",
        seconds=PRODUCT_AI_QUEUE_INTERVAL,
        id="product_ai_queue",
        name="Product AI Review Queue",
        max_instances=1,
    )
    _upsert_interval_job_metadata(
        schedule_service,
        job_key="product_ai_queue",
        job_type="product_ai_review_queue",
        interval_seconds=PRODUCT_AI_QUEUE_INTERVAL,
        runtime_config={"capabilityKey": "shop_product_review"},
    )
    _scheduler.add_job(
        product_ai_review_recovery_job,
        "interval",
        seconds=PRODUCT_AI_RECOVERY_INTERVAL,
        id="product_ai_recovery",
        name="Product AI Recovery",
        max_instances=1,
    )
    _upsert_interval_job_metadata(
        schedule_service,
        job_key="product_ai_recovery",
        job_type="product_ai_review_recovery",
        interval_seconds=PRODUCT_AI_RECOVERY_INTERVAL,
        runtime_config={"staleMs": _env_int("PRODUCT_AI_REVIEW_STALE_MS", 600000)},
    )
    _scheduler.add_job(
        comment_ai_review_queue_job,
        "interval",
        seconds=COMMENT_AI_QUEUE_INTERVAL,
        id="comment_ai_queue",
        name="Comment AI Review Queue",
        max_instances=1,
    )
    _upsert_interval_job_metadata(
        schedule_service,
        job_key="comment_ai_queue",
        job_type="comment_ai_review_queue",
        interval_seconds=COMMENT_AI_QUEUE_INTERVAL,
        runtime_config={"capabilityKey": "shop_comment_review"},
    )
    _scheduler.add_job(
        comment_ai_review_recovery_job,
        "interval",
        seconds=COMMENT_AI_RECOVERY_INTERVAL,
        id="comment_ai_recovery",
        name="Comment AI Recovery",
        max_instances=1,
    )
    _upsert_interval_job_metadata(
        schedule_service,
        job_key="comment_ai_recovery",
        job_type="comment_ai_review_recovery",
        interval_seconds=COMMENT_AI_RECOVERY_INTERVAL,
        runtime_config={"staleMs": _env_int("COMMENT_AI_REVIEW_STALE_MS", 600000)},
    )
    _scheduler.add_job(
        shop_ops_report_scheduler_job,
        "interval",
        seconds=OPS_REPORT_INTERVAL,
        id="ops_report_scheduler",
        name="Ops Report Scheduler",
        max_instances=1,
    )
    _upsert_interval_job_metadata(
        schedule_service,
        job_key="ops_report_scheduler",
        job_type="ops_report_scheduler",
        interval_seconds=OPS_REPORT_INTERVAL,
        runtime_config={
            "capabilityKeys": [
                "shop_ops_daily_report",
                "shop_ops_weekly_report",
                "shop_ops_monthly_report",
            ],
            "legacySource": "ld_store_backend.ops_report_scheduler",
        },
    )
    _scheduler.add_job(
        shop_ops_copilot_queue_job,
        "interval",
        seconds=OPS_COPILOT_INTERVAL,
        id="ops_copilot_queue",
        name="Ops Copilot Queue",
        max_instances=1,
    )
    _upsert_interval_job_metadata(
        schedule_service,
        job_key="ops_copilot_queue",
        job_type="shop_ops_copilot_queue",
        interval_seconds=OPS_COPILOT_INTERVAL,
        runtime_config={
            "agentKey": "ops_copilot",
            "legacySource": "ld_store_backend.ops_copilot_queue",
        },
    )
    if SHADOW_SNAPSHOT_AUTO_ENABLED and SHADOW_SNAPSHOT_INTERVAL > 0:
        _scheduler.add_job(
            shadow_readiness_snapshot_job,
            "interval",
            seconds=SHADOW_SNAPSHOT_INTERVAL,
            id="shadow_readiness_snapshot",
            name="Shadow Readiness Snapshot",
            max_instances=1,
        )
        _upsert_interval_job_metadata(
            schedule_service,
            job_key="shadow_readiness_snapshot",
            job_type="shadow_readiness_snapshot",
            interval_seconds=SHADOW_SNAPSHOT_INTERVAL,
            runtime_config={
                "days": SHADOW_SNAPSHOT_DAYS,
                "agentKeys": SHADOW_SNAPSHOT_AGENT_KEYS,
                "legacySource": "ld_store_backend.shadow_snapshot",
            },
        )

    # Log scheduled jobs
    job_list = [
        (job.id, f"{job.trigger.interval_length}s") for job in _scheduler.get_jobs()
    ]
    logger.info(
        "scheduler_initialized",
        job_count=len(job_list),
        jobs=job_list,
    )

    return _scheduler


async def trigger_startup_jobs() -> None:
    """Run startup-equivalent jobs once to match legacy Node behavior."""

    startup_jobs: list[Callable[[], Any]] = [
        audit_flush_job,
        audit_cleanup_job,
    ]

    if ENABLE_SECURITY_CLEANUP:
        startup_jobs.append(security_cleanup_job)

    if ENABLE_BUFFER_WRITE_BACK:
        startup_jobs.append(buffer_flush_job)

    if ENABLE_LEADERBOARD_PRECOMPUTE:
        startup_jobs.extend(
            [
                daily_leaderboard_job,
                weekly_leaderboard_job,
                monthly_leaderboard_job,
            ]
        )

    startup_jobs.extend(
        [
            order_expire_check_job,
            shop_top_expire_job,
            pending_payment_sync_job,
            paid_auto_deliver_job,
            test_auto_offline_job,
            cdk_zero_stock_offline_job,
            admin_message_dispatch_job,
            restock_notification_recovery_job,
            product_ai_review_queue_job,
            product_ai_review_recovery_job,
            comment_ai_review_queue_job,
            comment_ai_review_recovery_job,
            shop_ops_report_scheduler_job,
            shop_ops_copilot_queue_job,
        ]
    )

    if SHADOW_SNAPSHOT_AUTO_ENABLED and SHADOW_SNAPSHOT_INTERVAL > 0:
        startup_jobs.append(shadow_readiness_snapshot_job)

    triggered = 0
    for job in startup_jobs:
        try:
            await job("startup")
            triggered += 1
        except Exception as exc:
            logger.error(
                "scheduler_startup_job_failed",
                job=getattr(job, "__name__", "unknown"),
                error=str(exc),
            )

    logger.info("scheduler_startup_jobs_completed", triggered=triggered)


def shutdown_scheduler() -> None:
    """Shutdown the scheduler. Call this on app shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("scheduler_shutdown")
