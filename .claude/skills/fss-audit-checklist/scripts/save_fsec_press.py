"""내장 브라우저로 수집한 금융보안원(FSEC) 보도자료 JSON을 크롤러와 동일한 .txt 형식으로 저장한다.

금융보안원은 TLS JA3 기반 WAF로 Python HTTP 클라이언트를 차단하므로(crawler/fsec_crawler.py는 0건),
SKILL.md Phase 2.5 절차대로 내장 브라우저에서 /bbs/list API를 호출해 얻은 JSON을 이 스크립트로 저장한다.

입력 JSON: [{"no": 11939, "date": "2026-04-28", "title": "...", "text": "..."}, ...]
  - "text"를 비우면 목록(제목·등록일·원문 링크)만 저장된다.

사용법:
    python .claude/skills/fss-audit-checklist/scripts/save_fsec_press.py <입력.json> data/FSEC/FSEC_보도자료
"""
import html
import json
import re
import sys
from pathlib import Path

DETAIL_URL = "https://www.fsec.or.kr/bbs/detail?menuNo=69&bbsNo={no}"


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    items = json.loads(src.read_text(encoding="utf-8"))
    for it in items:
        title = html.unescape(it["title"]).strip()
        name = re.sub(r'[\\/:*?"<>|]', "_", title)[:120]
        body = it.get("text", "")
        (out / f"{name}.txt").write_text(
            f"제목: {title}\n등록일: {it['date']}\n출처: 금융보안원\n"
            f"원문: {DETAIL_URL.format(no=it['no'])}\n수집방식: 내장 브라우저(/bbs/list API)\n\n{body}",
            encoding="utf-8",
        )
        print("[저장]", it["date"], title)
    print(f"총 {len(items)}건 -> {out}")


if __name__ == "__main__":
    main()
