"""LDStatusPro ticket routes using Service Layer."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.common.utils.response import success_response, error_response
from app.domains.ldsp.schemas.tickets import (
    TicketCreateRequest,
    TicketReplyRequest,
)
from app.domains.ldsp.services.tickets import TicketService

router = APIRouter(prefix="/api", tags=["tickets"])

ticket_service = TicketService()


@router.get("/tickets/types")
async def ticket_types():
    """Get ticket type definitions."""
    return success_response(
        data={"types": ticket_service.get_ticket_types(), "fromCache": False}
    )


@router.post("/tickets")
async def create_ticket(req: TicketCreateRequest, request: Request):
    """Create a new support ticket."""
    user = request.state.user
    try:
        result = ticket_service.create_ticket(
            user.get("site"),
            user.get("user_id"),
            user.get("username"),
            req.type_name,
            req.title,
            req.content,
        )
        return success_response(data=result)
    except Exception as e:
        return error_response("CREATE_FAILED", str(e), 400)


@router.get("/tickets")
async def get_tickets(
    request: Request,
    page: int = 1,
    pageSize: int = 20,
    status: str | None = None,
):
    """Get user's ticket list."""
    user = request.state.user
    try:
        data = ticket_service.get_user_tickets(
            user.get("site"), user.get("user_id"), page, pageSize
        )
        if status in ("open", "closed"):
            filtered = [
                item for item in data.get("items", []) if item.get("status") == status
            ]
            total = len(filtered)
            data = {
                "tickets": filtered,
                "pagination": {
                    "page": page,
                    "pageSize": pageSize,
                    "total": total,
                    "totalPages": (total + pageSize - 1) // pageSize
                    if total > 0
                    else 1,
                },
            }
        else:
            items = data.get("items", [])
            total = int(data.get("total") or 0)
            data = {
                "tickets": items,
                "pagination": {
                    "page": page,
                    "pageSize": pageSize,
                    "total": total,
                    "totalPages": (total + pageSize - 1) // pageSize
                    if total > 0
                    else 1,
                },
            }
        return success_response(data=data)
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)


@router.get("/tickets/{ticket_id}")
async def get_ticket(ticket_id: int, request: Request):
    """Get ticket detail."""
    user = request.state.user
    ticket = ticket_service.get_ticket_detail(
        ticket_id, user.get("site"), user.get("user_id")
    )
    if not ticket:
        return error_response("NOT_FOUND", "工单不存在", 404)
    return success_response(data=ticket)


@router.post("/tickets/{ticket_id}/reply")
async def reply_ticket(ticket_id: int, req: TicketReplyRequest, request: Request):
    """Reply to own ticket."""
    user = request.state.user
    try:
        ticket_service.user_reply(
            ticket_id,
            user.get("site"),
            user.get("user_id"),
            user.get("username"),
            req.content,
        )
        return success_response(message="回复已发送")
    except Exception as e:
        return error_response("REPLY_FAILED", str(e), 400)


@router.get("/tickets/unread/count")
async def unread_count(request: Request):
    """Get unread replies count."""
    user = request.state.user
    count = ticket_service.get_unread_count(user.get("site"), user.get("user_id"))
    return success_response(data={"count": count})


# --- Admin Routes ---


@router.get("/admin/tickets/types")
async def admin_ticket_types():
    return success_response(data={"types": ticket_service.get_ticket_types()})


@router.put("/admin/tickets/types")
async def admin_update_ticket_types(request: Request):
    try:
        body = await request.json()
        types = ticket_service.update_ticket_types(body.get("types") or [])
        return success_response(data={"types": types}, message="工单类型已更新")
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 400)


@router.get("/admin/tickets/stats")
async def admin_ticket_stats():
    return success_response(data=ticket_service.get_stats())


@router.get("/admin/tickets")
async def admin_tickets(
    request: Request,
    page: int = 1,
    pageSize: int = 20,
    limit: int | None = None,
    site: str | None = None,
    status: str | None = None,
    type: str | None = None,
    search: str | None = None,
):
    data = ticket_service.get_admin_tickets(
        {
            "page": page,
            "pageSize": pageSize if limit is None else limit,
            "site": site,
            "status": status,
            "type": type,
            "search": search,
        }
    )
    return success_response(data=data)


@router.get("/admin/tickets/{ticket_id}")
async def admin_ticket_detail(ticket_id: int):
    try:
        return success_response(data=ticket_service.get_admin_ticket_detail(ticket_id))
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 404)


@router.post("/admin/tickets/{ticket_id}/reply")
async def admin_reply(ticket_id: int, req: TicketReplyRequest, request: Request):
    try:
        current_user = request.state.user if request.state.user else {}
        admin_name = (
            "Admin"
            if current_user.get("is_super_admin")
            else current_user.get("nickname") or current_user.get("username") or "Admin"
        )
        ticket_service.admin_reply(ticket_id, admin_name, req.content)
        return success_response(message="回复已发送")
    except Exception as e:
        return error_response("REPLY_FAILED", str(e), 400)


@router.post("/admin/tickets/{ticket_id}/close")
async def close_ticket(ticket_id: int, request: Request):
    try:
        current_user = request.state.user if request.state.user else {}
        admin_name = (
            "Admin"
            if current_user.get("is_super_admin")
            else current_user.get("nickname") or current_user.get("username") or "Admin"
        )
        ticket_service.close_ticket(ticket_id, admin_name)
        return success_response(message="工单已关闭")
    except Exception as e:
        return error_response("CLOSE_FAILED", str(e), 400)


@router.post("/admin/tickets/{ticket_id}/reopen")
async def reopen_ticket(ticket_id: int):
    try:
        ticket_service.reopen_ticket(ticket_id)
        return success_response(message="工单已重新打开")
    except Exception as e:
        return error_response("REOPEN_FAILED", str(e), 400)
