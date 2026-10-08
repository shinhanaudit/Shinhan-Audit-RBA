"""금융보안원(FSEC, Financial Security Institute) 보도자료 크롤러.

대상 게시판: 보도자료(알림마당) /bbs/69
  - 전자금융·IT보안·사이버보안 관련 보도자료
  - 업권 키워드로 관련 자료를 필터링해 data/FSEC/보도자료/ 에 저장

⚠️  봇 차단(WAF): 금융보안원은 TLS JA3 핑거프린트 기반 WAF를 운용한다.
    Python requests/httpx 등 자동화 클라이언트는 접속 즉시 Connection reset으로
    차단된다. 차단 시 크롤러는 경고만 출력하고 0건으로 종료한다 — 오류로 중단하지 않는다.
    FSEC 크롤링은 선택(optional)이므로 0건이어도 감사 체크리스트 생성은 정상 진행된다.

⚠️  제재·경영유의사항 게시판 없음: FSEC는 규제기관이 아니므로 이 게시판 자체가 없다.
    전자금융 위반 제재는 FSS 금감원(fss_crawler.py)에서 관리한다.
"""
from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote_plus, urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.fsec.or.kr"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# 보도자료 게시판 (알림마당)
# 목록: /bbs/69
# 상세: /bbs/detail?menuNo=69&bbsNo={bbsNo}
PRESS_LIST_URL = f"{BASE_URL}/bbs/69"
PRESS_MENU_NO = "69"

FILE_LINK_MARKERS = ("download", "fileDown", "atchFileId", "bbsNo")
FILE_EXTENSIONS = (".pdf", ".hwp", ".zip", ".xlsx", ".xls", ".doc", ".docx")

# FSEC 보도자료가 다루는 도메인 키워드 — 업권과 무관하게 항상 관련성이 높은 항목
ALWAYS_RELEVANT_KEYWORDS = [
    "전자금융", "사이버보안", "정보보호", "IT보안", "개인정보",
    "보안취약점", "전산사고", "API보안", "클라우드보안",
]


def _is_file_link(href: str) -> bool:
    lower = href.lower()
    return any(m.lower() in lower for m in FILE_LINK_MARKERS) or lower.endswith(FILE_EXTENSIONS)


def _safe_filename(name: str) -> str:
    name = unicodedata.normalize("NFC", name)
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip()
    return name[:150]


@dataclass
class FsecAttachment:
    title: str
    url: str


@dataclass
class FsecDocument:
    category: str  # "FSEC_보도자료"
    title: str
    detail_url: str
    date: str = ""
    attachments: list[FsecAttachment] = field(default_factory=list)
    is_file_link: bool = False


class FsecCrawler:
    def __init__(self, out_dir: str | Path, sleep: float = 1.0):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.out_dir = Path(out_dir)
        self.sleep = sleep
        self._waf_blocked = False  # WAF 차단 감지 플래그

    def _get(self, url: str, params: dict | None = None) -> BeautifulSoup | None:
        if self._waf_blocked:
            return None
        try:
            resp = self.session.get(url, params=params, timeout=20)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            time.sleep(self.sleep)
            return BeautifulSoup(resp.text, "lxml")
        except requests.exceptions.ConnectionError as e:
            err_str = str(e)
            if "ConnectionReset" in err_str or "ECONNRESET" in err_str or "reset" in err_str.lower():
                self._waf_blocked = True
                print(
                    "\n[FSEC WAF 차단] 금융보안원이 자동화 클라이언트 접속을 차단했습니다.\n"
                    "  원인: TLS JA3 핑거프린트 기반 WAF (Python requests = 비브라우저 클라이언트로 식별)\n"
                    "  처리: FSEC 보도자료 크롤링을 건너뜁니다 (0건). 감사 체크리스트는 정상 생성됩니다.\n"
                    "  수동 방법: https://www.fsec.or.kr/bbs/69 에서 직접 다운로드하세요.\n"
                )
            else:
                print(f"[FSEC 연결 오류] {url}: {e}")
            return None
        except Exception as e:
            print(f"[FSEC 크롤링 오류] {url}: {e}")
            return None

    # ---------------------------------------------------------------- 보도자료 목록
    def fetch_press(
        self,
        max_pages: int = 5,
        keywords: list[str] | None = None,
        sdate: str | None = None,
        edate: str | None = None,
    ) -> list[FsecDocument]:
        """보도자료 게시판을 크롤링한다.

        keywords: 제목에 이 키워드 중 하나 이상 포함된 건만 수집.
                  None이면 ALWAYS_RELEVANT_KEYWORDS 기본 필터 적용.
        sdate/edate: YYYY-MM-DD 형식. 날짜 필터 (없으면 최신 max_pages 페이지).
        """
        filter_kws = keywords if keywords is not None else ALWAYS_RELEVANT_KEYWORDS
        docs: list[FsecDocument] = []

        for page in range(1, max_pages + 1):
            params: dict = {"pageIndex": page}
            if sdate:
                params["sDate"] = sdate.replace("-", "")
            if edate:
                params["eDate"] = edate.replace("-", "")

            soup = self._get(PRESS_LIST_URL, params=params)
            if soup is None:
                break

            rows = self._parse_list_rows(soup)
            if not rows:
                break

            found = False
            for title, href, date_val in rows:
                # 키워드 필터
                if filter_kws and not any(kw in title for kw in filter_kws):
                    continue
                detail_url = urljoin(BASE_URL, href)
                docs.append(FsecDocument(
                    category="FSEC_보도자료",
                    title=title,
                    detail_url=detail_url,
                    date=date_val,
                    is_file_link=_is_file_link(href),
                ))
                found = True

            if not found and page > 1:
                # 키워드 필터 때문에 아무 것도 안 걸렸을 수 있음 → 계속 시도
                pass

        return docs

    def _parse_list_rows(self, soup: BeautifulSoup) -> list[tuple[str, str, str]]:
        """목록 페이지에서 (제목, href, 날짜) 튜플 리스트를 추출한다.
        FSEC 게시판 HTML 구조: <table> tbody tr > td a 링크."""
        rows_out = []
        # 테이블 기반 레이아웃 시도
        for row in soup.select("table tbody tr"):
            title_a = row.find("a")
            if not title_a:
                continue
            title = title_a.get_text(strip=True)
            href = title_a.get("href", "")
            if not href or not title:
                continue
            cells = row.find_all("td")
            date_val = cells[-1].get_text(strip=True) if cells else ""
            rows_out.append((title, href, date_val))

        if rows_out:
            return rows_out

        # ul/li 기반 레이아웃 폴백
        for item in soup.select("ul.board-list li, .list-type li"):
            a = item.find("a")
            if not a:
                continue
            title = a.get_text(strip=True)
            href = a.get("href", "")
            if not href or not title:
                continue
            date_tag = item.find(class_=re.compile(r"date|time|regdt", re.I))
            date_val = date_tag.get_text(strip=True) if date_tag else ""
            rows_out.append((title, href, date_val))

        return rows_out

    # ---------------------------------------------------------------- 상세/첨부
    def fetch_detail(self, doc: FsecDocument) -> tuple[str, list[FsecAttachment]]:
        soup = self._get(doc.detail_url)
        if soup is None:
            return "", []
        body = soup.select_one(".board-view, .view-content, #content, .bbs-view, .view-area")
        text = body.get_text("\n", strip=True) if body else soup.get_text("\n", strip=True)[:2000]

        attachments: list[FsecAttachment] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if _is_file_link(href):
                name = a.get_text(strip=True) or a.get("title", "첨부파일")
                attachments.append(FsecAttachment(title=name, url=urljoin(BASE_URL, href)))
        return text, attachments

    # ---------------------------------------------------------------- 저장
    def save_document(self, doc: FsecDocument, save_attachments: bool = True) -> Path:
        folder = self.out_dir / "FSEC" / doc.category
        folder.mkdir(parents=True, exist_ok=True)

        if doc.is_file_link:
            detail_text = ""
            all_attachments = doc.attachments
        else:
            detail_text, detail_attachments = self.fetch_detail(doc)
            all_attachments = doc.attachments or detail_attachments

        meta_path = folder / f"{_safe_filename(doc.title)}.txt"
        meta_path.write_text(
            f"제목: {doc.title}\n등록일: {doc.date}\n"
            f"출처: 금융보안원\n원문: {doc.detail_url}\n\n{detail_text}",
            encoding="utf-8",
        )
        if save_attachments:
            for att in all_attachments:
                self._download_file(att.url, folder, att.title)
        return meta_path

    def _download_file(self, url: str, folder: Path, hint_name: str) -> Path | None:
        try:
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
        except Exception as e:
            print(f"[FSEC 다운로드 실패] {hint_name}: {e}")
            return None

    # ---------------------------------------------------------------- 전체 실행
    def run(
        self,
        press_pages: int = 3,
        keywords: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, list[FsecDocument]]:
        """금융보안원 보도자료를 크롤링한다 (선택적, WAF 차단 시 0건으로 종료).

        press_pages: 수집할 최대 페이지 수.
        keywords: 제목 필터 키워드. None이면 ALWAYS_RELEVANT_KEYWORDS 적용.
        start/end(YYYY-MM-DD): 날짜 필터.
        """
        docs = self.fetch_press(
            max_pages=press_pages,
            keywords=keywords,
            sdate=start,
            edate=end,
        )

        if self._waf_blocked:
            return {"FSEC_보도자료": []}

        for doc in docs:
            self.save_document(doc)

        return {"FSEC_보도자료": docs}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="금융보안원(FSEC) 보도자료 크롤러 (선택적, WAF 차단 시 graceful skip)"
    )
    parser.add_argument("--out", default="data", help="저장 루트 폴더 (기본: data)")
    parser.add_argument("--press-pages", type=int, default=3, help="보도자료 최대 페이지 수")
    parser.add_argument("--keywords", nargs="*", default=None,
                        help="제목 필터 키워드 (없으면 기본 IT보안 키워드 사용)")
    parser.add_argument("--start", default=None, help="날짜 필터 시작 YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="날짜 필터 종료 YYYY-MM-DD")
    args = parser.parse_args()

    crawler = FsecCrawler(args.out)
    result = crawler.run(
        press_pages=args.press_pages,
        keywords=args.keywords if args.keywords else None,
        start=args.start,
        end=args.end,
    )
    for cat, docs in result.items():
        status = "(WAF 차단으로 수집 불가)" if crawler._waf_blocked else f"{len(docs)}건 저장 완료"
        print(f"[{cat}] {status}")
