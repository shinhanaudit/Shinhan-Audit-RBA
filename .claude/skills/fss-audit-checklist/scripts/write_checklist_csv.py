"""체크리스트 행 데이터(JSON)를 표준 CSV로 안전하게 저장한다.

절대 Write 도구로 "필드1,필드2,필드3..." 문자열을 직접 이어붙여 CSV를 만들지 않는다.
셀 안에 쉼표·줄바꿈·따옴표가 섞이면 수동 조립은 반드시 깨진다 — python csv 모듈이
이스케이프를 전담하도록 이 스크립트를 거친다.

사용법:
  python write_checklist_csv.py <입력.json> <출력.csv>

입력 JSON 형식: 리스트, 각 원소는 아래 6개 키를 모두 가진 객체.
  [
    {"리스크ID": "R1-001", "테마": "...", "소제목": "...",
     "리스크": "...", "감사항목": "...", "근거": "..."},
    ...
  ]
"""
from __future__ import annotations

import csv
import json
import sys

HEADER = ["리스크ID", "테마", "소제목", "리스크", "감사항목", "근거"]


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    in_path, out_path = sys.argv[1], sys.argv[2]

    with open(in_path, encoding="utf-8") as f:
        rows = json.load(f)

    if not isinstance(rows, list) or not rows:
        print("[실패] 입력 JSON은 비어있지 않은 리스트여야 합니다.", file=sys.stderr)
        sys.exit(1)

    for i, row in enumerate(rows):
        missing = [k for k in HEADER if k not in row]
        if missing:
            print(f"[실패] {i+1}번째 항목에 컬럼 누락: {missing}", file=sys.stderr)
            sys.exit(1)

    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for row in rows:
            w.writerow([row[k] for k in HEADER])

    print(f"[완료] {len(rows)}건 -> {out_path}")


if __name__ == "__main__":
    main()
