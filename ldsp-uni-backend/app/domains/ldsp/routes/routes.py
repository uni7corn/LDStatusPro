"""LDStatusPro domain routes registration."""

from __future__ import annotations

from app.domains.ldsp.routes import (
    admin,
    backups,
    health,
    internal,
    users,
    reading,
    leaderboard,
    tickets,
    sub_admins,
    client_config,
    archive,
    annual_report,
    tools,
    audit,
    security,
    dashboard,
    tg_bot,
    requirements,
    auth,
)


def include_ldsp_routers(app):
    """Register all LDStatusPro domain routers."""
    app.include_router(health.router)
    app.include_router(internal.router)
    app.include_router(admin.router)
    app.include_router(backups.router)
    app.include_router(users.router)
    app.include_router(users.compat_router)
    app.include_router(reading.router)
    app.include_router(leaderboard.router)
    app.include_router(tickets.router)
    app.include_router(sub_admins.router)
    app.include_router(client_config.router)
    app.include_router(archive.router)
    app.include_router(annual_report.router)
    app.include_router(tools.router)
    app.include_router(audit.router)
    app.include_router(security.router)
    app.include_router(dashboard.router)
    app.include_router(tg_bot.router)
    app.include_router(requirements.router)
    app.include_router(auth.router)
