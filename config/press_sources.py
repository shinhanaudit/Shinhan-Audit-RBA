"""fss-audit-checklist-news에서 사용하는 우선 검색 언론사 목록.

순서는 검색 시 우선순위가 아니라 단순 나열이다. 신규 언론사를 추가할 때는
이 딕셔너리에 한 줄만 추가하면 된다 (표시명: 검색 힌트용 도메인/별칭).
"""

PRESS_SOURCES = {
    "경향신문": "khan.co.kr",
    "국민일보": "kmib.co.kr",
    "동아일보": "donga.com",
    "문화일보": "munhwa.com",
    "조선일보": "chosun.com",
    "중앙일보": "joongang.co.kr",
    "연합뉴스": "yna.co.kr",
}
