"""Custom exception classes."""

from __future__ import annotations

from fastapi import HTTPException, status


class AuthenticationError(HTTPException):
    def __init__(self, detail: str = "认证失败"):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


class PermissionDenied(HTTPException):
    def __init__(self, detail: str = "权限不足"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class NotFoundError(HTTPException):
    def __init__(self, detail: str = "资源不存在"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class AgentError(Exception):
    """Base error for agent execution failures."""

    def __init__(self, agent_key: str, message: str, error_code: str = "AGENT_ERROR"):
        self.agent_key = agent_key
        self.message = message
        self.error_code = error_code
        super().__init__(f"[{agent_key}] {message}")


class AgentTimeoutError(AgentError):
    def __init__(self, agent_key: str):
        super().__init__(agent_key, "审核超时", "AGENT_TIMEOUT")


class AgentParseError(AgentError):
    def __init__(self, agent_key: str, raw_response: str = ""):
        msg = "LLM响应解析失败"
        super().__init__(agent_key, msg, "AGENT_PARSE_ERROR")
        self.raw_response = raw_response


class AllProvidersFailedError(Exception):
    """All LLM providers have failed."""


class DatabaseError(Exception):
    """Database operation error."""
