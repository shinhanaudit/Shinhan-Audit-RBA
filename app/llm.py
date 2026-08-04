"""체크리스트 생성용 LLM 연동. anthropic_api 모드만 실제 API 호출을 수행한다.
claude_code 모드는 API 키 없이 Claude Code(현재 세션)에서 직접 생성하는 것을 전제로 하므로,
여기서는 프롬프트만 구성해 반환한다 (사용자가 Claude Code 채팅에 붙여넣거나, 세션이 파일을 읽어 처리).
"""
from pathlib import Path

from config.settings import load_config

CHECKLIST_INSTRUCTIONS = """\
당신은 금융감독원 감사 체크리스트를 작성하는 전문가입니다.
아래 제공된 [검사업무 안내서 / 제재사례 / 경영유의사항] 원문을 바탕으로,
최근 해당 업권에서 발생하고 있는 유의사항과 감사 시 점검해야 할 항목을 추출하여
다음 표 형식으로 정리하세요.

| 리스크 ID | 테마 | 소제목 | 리스크(1문장) | 감사항목(설계/운영) | 근거 |
|---|---|---|---|---|---|
| R2-001 | 소비자보호 | 불완전판매 | 설명의무 및 약관 교부 미흡으로... | 상품정보 제공 절차 설계 및 준수여부, 프로세스 운영 및 점검 | 검사업무 안내서 OOp '불완전판매 관련 검사사항' |

요구사항:
- 근거 컬럼에는 반드시 원문 문서명과 (가능하면) 페이지/조항을 명시할 것
- 검사업무 안내서 내용을 우선 반영하고, 제재/경영유의사항은 보강 자료로 사용할 것
- 표만 출력하고, 사용자 확인 후 추가/보강 요청을 받을 수 있도록 마지막에 "추가로 보강하거나 제거할 항목이 있으면 말씀해주세요."라고 덧붙일 것
"""


def build_prompt(industry: str, save_dir: str) -> str:
    base = Path(save_dir) / industry
    chunks = []
    for category in ["검사업무안내서", "검사결과제재", "경영유의사항"]:
        folder = base / category
        if not folder.exists():
            continue
        for f in sorted(folder.glob("*.txt")):
            text = f.read_text(encoding="utf-8", errors="ignore")
            chunks.append(f"### [{category}] {f.stem}\n{text[:4000]}")
    joined = "\n\n".join(chunks)
    return f"{CHECKLIST_INSTRUCTIONS}\n\n=== 업권: {industry} 원문 자료 ===\n\n{joined}"


def generate_checklist(industry: str) -> dict:
    cfg = load_config()
    prompt = build_prompt(industry, cfg["save_dir"])
    provider = cfg["llm_provider"]

    if provider == "anthropic_api":
        if not cfg.get("anthropic_api_key"):
            return {"ok": False, "mode": provider, "message": "Anthropic API 키가 설정되지 않았습니다."}
        import anthropic

        client = anthropic.Anthropic(api_key=cfg["anthropic_api_key"])
        resp = client.messages.create(
            model=cfg.get("anthropic_model") or "claude-sonnet-5",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        return {"ok": True, "mode": provider, "checklist": resp.content[0].text}

    if provider == "openai_api":
        if not cfg.get("openai_api_key"):
            return {"ok": False, "mode": provider, "message": "OpenAI API 키가 설정되지 않았습니다."}
        if not cfg.get("openai_model"):
            return {"ok": False, "mode": provider, "message": "OpenAI 모델명을 설정에서 입력해주세요."}
        from openai import OpenAI

        client = OpenAI(api_key=cfg["openai_api_key"])
        resp = client.chat.completions.create(
            model=cfg["openai_model"],
            messages=[{"role": "user", "content": prompt}],
        )
        return {"ok": True, "mode": provider, "checklist": resp.choices[0].message.content}

    # claude_code 모드: 프롬프트만 반환 (Claude Code 세션에서 직접 처리)
    return {
        "ok": True,
        "mode": "claude_code",
        "prompt": prompt,
        "message": "API 키가 설정되지 않아 자동 생성을 건너뜁니다. "
                   "이 prompt를 Claude Code 세션에 전달해 체크리스트를 생성하세요.",
    }
