"""引擎注册表：把 config.yml 里的 engine 名映射到具体 Signer 类。"""

from __future__ import annotations

from .forum import ForumSigner
from .api import ApiSigner
from .hyperdown import HyperdownSigner

ENGINE_MAP = {
    "forum": ForumSigner,        # Discuz! 等表单流论坛
    "api": ApiSigner,            # JSON 接口流（京东/B站/网盘等，v1 预留）
    "hyperdown": HyperdownSigner,  # Hyperdown（SealJSON 加密签到）
}

__all__ = ["ENGINE_MAP", "ForumSigner", "ApiSigner", "HyperdownSigner"]
