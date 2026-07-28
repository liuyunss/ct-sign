"""CT-Sign（尘签）通用层。

包含：签到基类与统一结果、HTTP 客户端、配置读取、通知、日志。
所有平台/引擎共用，避免重复造轮子。
"""

__all__ = ["base", "client", "config", "log", "notify", "engines", "loader", "qlapi"]
