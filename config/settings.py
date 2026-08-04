"""런타임 설정: 저장 폴더, LLM 연동 방식."""
import json
import os
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "user_config.json"

DEFAULTS = {
    "save_dir": str(Path(__file__).resolve().parent.parent / "data"),
    "llm_provider": "claude_code",   # "claude_code" | "anthropic_api" | "openai_api"
    "anthropic_api_key": "",
    "anthropic_model": "claude-sonnet-5",
    "openai_api_key": "",
    "openai_model": "",   # 사용자가 직접 입력 (예: gpt-4.1, o3 등 OpenAI 대시보드에서 확인한 모델 ID)
}

# 프로바이더별로 UI에 노출할 추천 모델 목록 (자유 입력도 허용)
MODEL_CHOICES = {
    "anthropic_api": ["claude-sonnet-5", "claude-opus-4-8", "claude-haiku-4-5-20251001"],
    "openai_api": [],  # OpenAI는 계정마다 접근 가능한 모델이 달라 자유 입력만 지원
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return {**DEFAULTS, **cfg}
    return dict(DEFAULTS)


def save_config(cfg: dict) -> None:
    current = load_config()
    current.update(cfg)
    CONFIG_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
