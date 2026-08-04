"""사용자 채팅 메시지에서 감사 대상 업권을 추출한다."""
import re

from config.industries import INDUSTRY_CODES, INDUSTRY_KEYWORDS

# 업권명 자체 + 흔히 쓰는 별칭/기관 예시로 매칭한다.
ALIASES = {
    "은행": ["은행", "신한은행", "국민은행", "우리은행", "하나은행", "농협은행", "시중은행"],
    "비은행": ["저축은행", "대부업", "비은행", "여신전문"],
    "보험": ["보험", "생명보험", "손해보험", "생보", "손보"],
    "증권선물": ["증권", "선물", "투자증권", "금융투자"],
    "자산운용": ["자산운용", "투자신탁", "한국투자신탁"],
    "복합금융": ["복합금융", "지주"],
    "신용감독": ["신용감독", "신용정보", "카드사", "신용카드"],
    "기업공시": ["기업공시", "공시"],
    "기업회계감사": ["기업회계감사", "회계감사", "회계법인"],
    "공통": ["퇴직연금", "연금", "공통"],
}

YEAR_MONTH_RE = re.compile(r"(20\d{2}|\d{2})\s*년?\s*(\d{1,2})\s*월")
YEAR_MONTH_SEP_RE = re.compile(r"(20\d{2}|\d{2})\s*[.\-/]\s*(\d{1,2})(?!\s*[.\-/]\s*\d)")
YEAR_ONLY_RE = re.compile(r"(20\d{2}|\d{2})\s*년")


def extract_industry(message: str) -> str | None:
    for industry, keywords in ALIASES.items():
        for kw in keywords:
            if kw in message:
                return industry
    return None


def extract_period(message: str) -> str | None:
    """메시지에서 기간을 추출한다. 'YYYY-MM'(월까지 특정) 또는 'YYYY'(연도만)를 반환한다."""
    m = YEAR_MONTH_RE.search(message)
    if m:
        year, month = m.groups()
        if len(year) == 2:
            year = "20" + year
        return f"{year}-{int(month):02d}"

    # "26.4", "2026-04", "26/4" 같은 구분자 표기
    m = YEAR_MONTH_SEP_RE.search(message)
    if m:
        year, month = m.groups()
        if len(year) == 2:
            year = "20" + year
        month_i = int(month)
        if 1 <= month_i <= 12:
            return f"{year}-{month_i:02d}"

    m = YEAR_ONLY_RE.search(message)
    if m:
        year = m.group(1)
        if len(year) == 2:
            year = "20" + year
        return year

    return None


def parse_audit_request(message: str) -> dict:
    industry = extract_industry(message)
    period = extract_period(message)
    return {
        "industry": industry,
        "industry_code": INDUSTRY_CODES.get(industry) if industry else None,
        "period": period,
        "raw_message": message,
    }
