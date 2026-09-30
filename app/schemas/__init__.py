"""输出 schema(按 task_type 版本化)。【不变量四】"""
from app.schemas.tagging_output import TaggingOutput, output_schema_version

__all__ = ["TaggingOutput", "output_schema_version"]
