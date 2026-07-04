"""鉴权：简单的 Bearer token 校验。

生产应换成 JWT / OAuth2 / mTLS。本文件仅做"破冰"。
"""

from __future__ import annotations

import os
import secrets
from typing import Optional

from fastapi import Header, HTTPException, status


def verify_token(authorization: Optional[str] = Header(default=None)) -> None:
    """要求 `Authorization: Bearer <token>`。

    token 必须等于环境变量 GATEWAY_AUTH_TOKEN。
    """
    expected = os.getenv("GATEWAY_AUTH_TOKEN")
    if not expected:
        # 未配置即放行（仅 dev）；生产必须配置
        return

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")

    token = authorization.split(" ", 1)[1].strip()
    if not secrets.compare_digest(token, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
