"""Integration tests for UserService with Async SQLAlchemy."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.ldsp.services.users import UserService
from app.domains.ldsp.schemas.users import UserRegisterRequest


@pytest.mark.asyncio
async def test_user_register_and_get_profile(ldsp_db: AsyncSession):
    service = UserService()
    req = UserRegisterRequest(site="linux.do", user_id="99999", username="test_user")

    # Register
    assert await service.register_user(ldsp_db, req) is True

    # Get Profile
    profile = await service.get_profile(ldsp_db, "linux.do", "99999")
    assert profile is not None
    assert profile.username == "test_user"
