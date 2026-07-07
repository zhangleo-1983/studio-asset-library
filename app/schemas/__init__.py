"""输出 schema(按 task_type 版本化)。【不变量四】"""
from app.schemas.tagging_output import (
    TAGGING_OUTPUT_SCHEMA_VERSION,
    ColorScheme,
    TaggingOutput,
)

__all__ = ["TaggingOutput", "ColorScheme", "TAGGING_OUTPUT_SCHEMA_VERSION"]
