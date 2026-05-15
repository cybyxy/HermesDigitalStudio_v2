"""向后兼容：schemas.response 现在委托到 models.response.api。

本文件仅用于保持现有导入路径有效。
新代码请直接从 ``backend.models.response`` 导入。
"""

from backend.models.response.api import (  # noqa: F401
    ApiResponse,
    FieldError,
    PaginatedData,
    PaginationMeta,
    created,
    error,
    paginated,
    success,
)
