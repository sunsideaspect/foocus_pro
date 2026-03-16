from fastapi import Header

from app.config import get_settings


def get_current_user(x_dev_user: str | None = Header(default=None)) -> str:
    settings = get_settings()
    return x_dev_user or settings.dev_auth_user
