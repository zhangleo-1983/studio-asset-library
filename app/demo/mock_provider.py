"""Manifest 驱动的 provider(确定性 seed / 断网兜底 / 零 token)。

按图片内容 hash 映射到预置的"模型原始输出"文本,驱动**真实** process_task(溯源正常写全,
满足所有 CHECK)。用途:① demo-seed 无密钥时确定性预打标;② 单元/演练不烧 token。
生产 demo 用真实 QwenVLProvider,同一条 process_task 路径,行为一致。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.tagging.provider import CallResult, ProviderCallError, TaggingProvider


class ManifestProvider(TaggingProvider):
    model_id = "qwen-vl-max"
    provider_id = "mock"

    def __init__(self, manifest: dict[str, dict]):
        # manifest: {content_hash_hex: tagging_output_dict}
        self._m = manifest

    @classmethod
    def from_file(cls, path: str | Path) -> "ManifestProvider":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def call(self, image_bytes: bytes, prompt_text: str) -> CallResult:
        h = hashlib.sha256(image_bytes).hexdigest()
        obj = self._m.get(h)
        if obj is None:
            raise ProviderCallError(f"manifest 无此图 hash={h[:12]}…(demo 素材未登记)")
        return CallResult(text=json.dumps(obj, ensure_ascii=False),
                          input_tokens=100, output_tokens=50, latency_ms=8, retries=0)
