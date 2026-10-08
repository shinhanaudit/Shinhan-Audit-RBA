"""금융감독원(FSS) 감사 관련 게시판 크롤러.

대상 게시판 3종:
  1. 검사업무 안내서       /fss/bbs/B0000167/list.do  (업권 코드 필터 지원)
  2. 검사결과제재(제재관련공시) /fss/job/openInfo/list.do   (업권 필터 없음 -> 키워드 매칭)
  3. 경영유의사항 등 공시    /fss/job/openInfoImpr/list.do (업권 필터 없음 -> 키워드 매칭)
"""
from __future__ import annotations

import calendar
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import unquote_plus, urljoin

import requests
from bs4 import BeautifulSoup

from config.industries import INDUSTRY_CODES, INDUSTRY_KEYWORDS

BASE_URL = "https://www.fss.or.kr"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

MANUAL_LIST_URL = f"{BASE_URL}/fss/bbs/B0000167/list.do"
SANCTION_LIST_URL = f"{BASE_URL}/fss/job/openInfo/list.do"
IMPR_LIST_URL = f"{BASE_URL}/fss/job/openInfoImpr/list.do"
FILE_DOWN_URL = f"{BASE_URL}/fss/cmmn/file/fileDown.do"


FILE_LINK_MARKERS = ("hpdownload", "fileDown.do")
FILE_EXTENSIONS = (".pdf", ".hwp", ".zip", ".xlsx", ".xls", ".doc", ".docx")


def _is_file_link(href: str) -> bool:
    lower = href.lower()
    return any(m.lower() in lower for m in FILE_LINK_MARKERS) or lower.endswith(FILE_EXTENSIONS)


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + delta
    return total // 12, total % 12 + 1


def compute_period_range(period: str, window_months: int = 3) -> dict:
    """기간 문자열 기준으로 검색 범위를 계산한다.

    - 'YYYY-MM' 형식: 해당 월 앞뒤 window_months개월
    - 'YYYY' 형식(연도만): 해당 연도 1월 1일 ~ 12월 31일 전체

    반환값:
      sdate/edate: 검사결과제재·경영유의사항 게시판용 (YYYY-MM-DD)
      years: 검사업무안내서 게시판용 연도 목록 (selectDate)
    """
    today = date.today()

    if "-" not in period:
        year = int(period)
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        if end > today:
            end = today
        return {"sdate": start.isoformat(), "edate": end.isoformat(), "years": [str(year)]}

    year, month = (int(x) for x in period.split("-"))
    sy, sm = _shift_month(year, month, -window_months)
    ey, em = _shift_month(year, month, window_months)

    start = date(sy, sm, 1)
    end = date(ey, em, calendar.monthrange(ey, em)[1])
    if end > today:
        end = today
    if start > end:
        start = end

    years = sorted({str(y) for y in range(sy, ey + 1)})
    return {
        "sdate": start.isoformat(),
        "edate": end.isoformat(),
        "years": years,
    }


def compute_explicit_range(start: str, end: str) -> dict:
    """감사 시작일/종료일(YYYY-MM-DD)을 그대로 검색 범위로 쓴다 (window 근사 없음).

    반환값 형식은 compute_period_range와 동일하다.
    """
    start_d = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    if start_d > end_d:
        start_d, end_d = end_d, start_d
    today = date.today()
    if end_d > today:
        end_d = today
    years = sorted({str(y) for y in range(start_d.year, end_d.year + 1)})
    return {"sdate": start_d.isoformat(), "edate": end_d.isoformat(), "years": years}


def _safe_filename(name: str) -> str:
    name = unicodedata.normalize("NFC", name)
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip()
    return name[:150]


@dataclass
class Attachment:
    title: str
    url: str


@dataclass
class Document:
    category: str          # "검사업무안내서" | "검사결과제재" | "경영유의사항"
    title: str
    detail_url: str
    dept: str = ""
    date: str = ""
    attachments: list[Attachment] = field(default_factory=list)
    is_file_link: bool = False   # detail_url 자체가 상세페이지가 아니라 첨부파일(pdf 등) 직링크인 경우


class FssCrawler:
    def __init__(self, out_dir: str | Path, sleep: float = 0.4):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.out_dir = Path(out_dir)
        self.sleep = sleep

    def _get(self, url: str, params: dict | None = None) -> BeautifulSoup:
        resp = self.session.get(url, params=params, timeout=20)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        time.sleep(self.sleep)
        return BeautifulSoup(resp.text, "lxml")

    # ---------------------------------------------------------------- 1) 검사업무안내서
    def fetch_manuals(self, industry: str, max_pages: int = 5, years: list[str] | None = None) -> list[Document]:
        code = INDUSTRY_CODES[industry]
        docs: list[Document] = []
        year_values = years or [None]
        for year in year_values:
            fetched = self._fetch_manuals_for_year(code, max_pages, year)
            docs.extend(fetched)
        # 연도 필터 결과가 0건이면 필터 없이 최신 max_pages 페이지를 재수집한다.
        # (검사업무안내서는 연 1~2회 갱신되므로 감사기간 연도에 신규 버전이 없을 수 있다.)
        if not docs and years:
            docs.extend(self._fetch_manuals_for_year(code, max_pages, None))
        return docs

    def _fetch_manuals_for_year(self, code: str, max_pages: int, year: str | None) -> list[Document]:
        docs: list[Document] = []
        _year = year  # 첫 시도용 연도 (None이면 필터 없음)
        for page in range(1, max_pages + 1):
            params = {"menuNo": "200177", "selectCate": code, "pageIndex": page}
            if _year:
                params["selectDate"] = _year
            soup = self._get(MANUAL_LIST_URL, params=params)
            # 현재 사이트 구조: <table class="tbl col list-data">
            rows = soup.select("table.list-data tbody tr")
            if not rows:
                break
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 5:
                    continue
                # td[2]: 제목(링크), td[3]: 담당부서, td[4]: 등록일, td[5]: 첨부파일
                title_a = cells[2].find("a")
                if not title_a:
                    continue
                title = title_a.get_text(strip=True)
                detail_url = urljoin(BASE_URL, title_a["href"])
                dept = cells[3].get_text(strip=True)
                date_text = cells[4].get_text(strip=True)
                doc = Document(
                    category="검사업무안내서",
                    title=title,
                    detail_url=detail_url,
                    dept=dept,
                    date=date_text,
                )
                # td[5]: 첨부파일 다운로드 링크
                if len(cells) > 5:
                    for a in cells[5].find_all("a", href=True):
                        href = a["href"]
                        if _is_file_link(href) or "fileDown" in href or "hpdownload" in href:
                            name = a.get("title") or a.get_text(strip=True) or "첨부파일"
                            doc.attachments.append(
                                Attachment(title=name[:80], url=urljoin(BASE_URL, href))
                            )
                docs.append(doc)
        return docs

    # ---------------------------------------------------------------- 2) 검사결과제재
    def fetch_sanctions(
        self,
        industry: str,
        max_pages: int = 10,
        sdate: str | None = None,
        edate: str | None = None,
        company: str | None = None,
    ) -> list[Document]:
        keywords = [company] if company else INDUSTRY_KEYWORDS.get(industry, [])
        docs: list[Document] = []
        for page in range(1, max_pages + 1):
            params = {"menuNo": "200476", "pageIndex": page}
            if sdate:
                params["sdate"] = sdate
            if edate:
                params["edate"] = edate
            soup = self._get(SANCTION_LIST_URL, params=params)
            rows = soup.select("table.list-data tbody tr")
            if not rows:
                break
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 5:
                    continue
                org = cells[1].get_text(strip=True)
                date = cells[2].get_text(strip=True)
                link_a = cells[3].find("a")
                dept = cells[4].get_text(strip=True)
                if not link_a:
                    continue
                haystack = f"{org} {dept}"
                if keywords and not any(kw in haystack for kw in keywords):
                    continue
                href = urljoin(BASE_URL, link_a["href"])
                is_file = _is_file_link(href)
                doc = Document(
                    category="검사결과제재",
                    title=org,
                    detail_url=href,
                    dept=dept,
                    date=date,
                    is_file_link=is_file,
                )
                if is_file:
                    doc.attachments.append(Attachment(title=f"{org}_{date}", url=href))
                docs.append(doc)
        return docs

    # ---------------------------------------------------------------- 3) 경영유의사항 등 공시
    def fetch_impr(
        self,
        industry: str,
        max_pages: int = 10,
        sdate: str | None = None,
        edate: str | None = None,
        company: str | None = None,
    ) -> list[Document]:
        keywords = [company] if company else INDUSTRY_KEYWORDS.get(industry, [])
        docs: list[Document] = []
        for page in range(1, max_pages + 1):
            params = {"menuNo": "200483", "pageIndex": page}
            if sdate:
                params["sdate"] = sdate
            if edate:
                params["edate"] = edate
            soup = self._get(IMPR_LIST_URL, params=params)
            rows = soup.select("table.list-data tbody tr")
            if not rows:
                break
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 5:
                    continue
                org = cells[1].get_text(strip=True)
                date = cells[2].get_text(strip=True)
                link_a = cells[3].find("a")
                dept = cells[4].get_text(strip=True)
                if not link_a:
                    continue
                haystack = f"{org} {dept}"
                if keywords and not any(kw in haystack for kw in keywords):
                    continue
                href = urljoin(BASE_URL, link_a["href"])
                is_file = _is_file_link(href)
                doc = Document(
                    category="경영유의사항",
                    title=org,
                    detail_url=href,
                    dept=dept,
                    date=date,
                    is_file_link=is_file,
                )
                if is_file:
                    doc.attachments.append(Attachment(title=f"{org}_{date}", url=href))
                docs.append(doc)
        return docs

    # ---------------------------------------------------------------- 상세/본문 텍스트 + 첨부파일
    def fetch_detail(self, doc: Document) -> tuple[str, list[Attachment]]:
        """상세 페이지에서 본문 텍스트와 첨부파일 링크를 함께 추출한다.

        검사업무안내서는 목록에서 이미 첨부파일(a.file-single)을 얻지만, 검사결과제재·경영유의사항은
        상세페이지 안의 file-list__set__item (/fss.hpdownload?... 또는 fileDown.do 링크)에서 얻어야 한다.
        """
        soup = self._get(doc.detail_url)

        # 본문 영역: .contents > .tbl-view 테이블, 또는 .contents 전체
        content_el = soup.select_one(".contents") or soup.select_one("main") or soup.body
        parts = []
        if content_el:
            # dl/dt/dd 구조가 있으면 그것을 우선 파싱
            for dl in content_el.select("dl"):
                dt = dl.find("dt")
                dd = dl.find("dd")
                if dt and dd:
                    parts.append(f"{dt.get_text(strip=True)}: {dd.get_text(' ', strip=True)}")
            # tbl-view 테이블(th/td 쌍)도 파싱
            for row in content_el.select("table.tbl-view tr, table tr"):
                th = row.find("th")
                td = row.find("td")
                if th and td:
                    parts.append(f"{th.get_text(strip=True)}: {td.get_text(' ', strip=True)}")
            if not parts:
                # 파싱 못 하면 텍스트만
                parts.append(content_el.get_text("\n", strip=True)[:3000])
        text = "\n".join(parts)

        attachments: list[Attachment] = []
        search_el = content_el if content_el else soup
        for a in search_el.find_all("a", href=True):
            href = a["href"]
            if _is_file_link(href) or "fileDown" in href or "hpdownload" in href.lower():
                name_el = a.select_one(".name")
                name = name_el.get_text(strip=True) if name_el else (a.get("title") or a.get_text(strip=True) or "첨부파일")
                attachments.append(Attachment(title=name[:80], url=urljoin(BASE_URL, href)))
        return text, attachments

    # ---------------------------------------------------------------- 파일 저장
    def save_document(self, industry: str, doc: Document, save_attachments: bool = True) -> Path:
        folder = self.out_dir / industry / doc.category
        folder.mkdir(parents=True, exist_ok=True)

        if doc.is_file_link:
            # 목록의 "내용보기" 링크 자체가 첨부파일(pdf 등)이라 별도 상세페이지가 없다.
            detail_text = ""
            all_attachments = doc.attachments
        else:
            detail_text, detail_attachments = self.fetch_detail(doc)
            all_attachments = doc.attachments or detail_attachments

        meta_path = folder / f"{_safe_filename(doc.title)}.txt"
        meta_path.write_text(
            f"제목: {doc.title}\n담당부서: {doc.dept}\n등록일: {doc.date}\n원문: {doc.detail_url}\n\n{detail_text}",
            encoding="utf-8",
        )

        if save_attachments:
            for att in all_attachments:
                self._download_file(att.url, folder, att.title)
        return meta_path

    def _download_file(self, url: str, folder: Path, hint_name: str) -> Path | None:
        resp = self.session.get(url, timeout=30)
        if resp.status_code != 200:
            return None
        cd = resp.headers.get("Content-Disposition", "")
        m = re.search(r'filename="?([^";]+)"?', cd)
        filename = _safe_filename(unquote_plus(m.group(1))) if m else _safe_filename(hint_name)
        path = folder / filename
        path.write_bytes(resp.content)
        time.sleep(self.sleep)
        return path

    # ---------------------------------------------------------------- 전체 실행
    def run(
        self,
        industry: str,
        manual_pages: int = 5,
        sanction_pages: int = 10,
        impr_pages: int = 10,
        period: str | None = None,
        window_months: int = 3,
        max_window_months: int = 12,
        start: str | None = None,
        end: str | None = None,
        company: str | None = None,
        sanction_years: int = 3,
    ):
        """감사 기간 범위를 정하는 우선순위:

        1. start/end(YYYY-MM-DD)가 둘 다 주어지면 그 구간을 그대로 쓴다(근사 window 없음) — 감사팀이
           명시한 감사 기간을 정확히 반영하기 위함.
        2. start/end가 없고 period가 주어지면(YYYY-MM 또는 YYYY) 그 앞뒤 window_months개월 범위를 쓴다.
        3. 아무 것도 없으면 무제한 과거까지 긁어오지 않도록 오늘 기준 최근 max_window_months개월로
           기본 범위를 강제한다 (안전장치).

        company가 주어지면 검사결과제재/경영유의사항 게시판을 업권 키워드 대신 해당 기관명으로만
        필터링한다(특정 회사 감사이므로 동일 업권 타사 건은 근거에서 제외).

        sanction_years: 제재·경영유의사항 수집 기간을 감사기간과 독립적으로 오늘 기준 최근 N년으로
        확장한다(기본 3년). 관련 사례는 감사기간 외 기간도 참고해야 하기 때문이다.
        검사업무안내서(업권 전체 문서)는 감사기간(rng["years"])으로만 조회한다.
        """
        assert industry in INDUSTRY_CODES, f"알 수 없는 업권: {industry}"

        if start and end:
            rng = compute_explicit_range(start, end)
        else:
            if not period:
                today = date.today()
                period = f"{today.year}-{today.month:02d}"
                window_months = max_window_months
            rng = compute_period_range(period, window_months)

        # 제재·경영유의사항은 최근 sanction_years년 전체를 수집한다 (감사기간과 독립적)
        today = date.today()
        try:
            sanction_start = today.replace(year=today.year - sanction_years).isoformat()
        except ValueError:
            # 윤년(2월 29일) 예외 처리
            import datetime as _dt
            sanction_start = (today - _dt.timedelta(days=sanction_years * 365)).isoformat()
        sanction_rng = {"sdate": sanction_start, "edate": today.isoformat()}

        results = {
            "검사업무안내서": self.fetch_manuals(industry, manual_pages, years=rng["years"]),
            "검사결과제재": self.fetch_sanctions(
                industry, sanction_pages,
                sdate=sanction_rng["sdate"], edate=sanction_rng["edate"],
                company=company,
            ),
            "경영유의사항": self.fetch_impr(
                industry, impr_pages,
                sdate=sanction_rng["sdate"], edate=sanction_rng["edate"],
                company=company,
            ),
        }
        for docs in results.values():
            for doc in docs:
                self.save_document(industry, doc)
        return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FSS 감사 자료 크롤러")
    parser.add_argument("industry", choices=list(INDUSTRY_CODES.keys()))
    parser.add_argument("--out", default="data")
    parser.add_argument("--manual-pages", type=int, default=3)
    parser.add_argument("--sanction-pages", type=int, default=3)
    parser.add_argument("--impr-pages", type=int, default=3)
    parser.add_argument("--period", default=None, help="YYYY-MM, 주어지면 해당 기간 앞뒤 window로 자료 수집")
    parser.add_argument("--window-months", type=int, default=3)
    parser.add_argument("--start", default=None, help="YYYY-MM-DD, --end와 함께 주어지면 감사 기간을 그대로 사용(근사 없음)")
    parser.add_argument("--end", default=None, help="YYYY-MM-DD, --start와 함께 사용")
    parser.add_argument("--company", default=None, help="특정 기관명, 주어지면 제재/경영유의사항을 해당 기관으로만 필터링")
    parser.add_argument("--sanction-years", type=int, default=3,
                        help="제재·경영유의사항을 오늘 기준 최근 N년으로 수집 (기본 3년). "
                             "감사기간(--start/--end)과 독립적으로 적용된다.")
    args = parser.parse_args()

    crawler = FssCrawler(args.out)
    result = crawler.run(
        args.industry,
        args.manual_pages,
        args.sanction_pages,
        args.impr_pages,
        period=args.period,
        window_months=args.window_months,
        start=args.start,
        end=args.end,
        company=args.company,
        sanction_years=args.sanction_years,
    )
    for cat, docs in result.items():
        print(f"[{cat}] {len(docs)}건 저장 완료")
