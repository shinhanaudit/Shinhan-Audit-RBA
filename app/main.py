"""감사 체크리스트 생성 에이전트 - 로컬 웹앱 백엔드."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.intent import parse_audit_request
from app.llm import generate_checklist
from config.industries import INDUSTRY_CODES
from config.settings import load_config, save_config
from crawler.fss_crawler import FssCrawler

app = FastAPI(title="감사 체크리스트 생성 에이전트")

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ChatMessage(BaseModel):
    message: str


class CrawlRequest(BaseModel):
    industry: str
    manual_pages: int = 3
    sanction_pages: int = 3
    impr_pages: int = 3
    period: str | None = None
    window_months: int = 3


class ConfigUpdate(BaseModel):
    save_dir: str | None = None
    llm_provider: str | None = None
    anthropic_api_key: str | None = None
    anthropic_model: str | None = None
    openai_api_key: str | None = None
    openai_model: str | None = None


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/config")
def get_config():
    cfg = load_config()
    cfg["anthropic_api_key"] = "설정됨" if cfg.get("anthropic_api_key") else ""
    cfg["openai_api_key"] = "설정됨" if cfg.get("openai_api_key") else ""
    return cfg


@app.post("/api/config")
def update_config(body: ConfigUpdate):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    save_config(updates)
    return {"ok": True}


@app.post("/api/chat/parse")
def chat_parse(body: ChatMessage):
    """사용자 메시지에서 업권/기간을 추출 (1~2단계)."""
    parsed = parse_audit_request(body.message)
    if not parsed["industry"]:
        return {
            "ok": False,
            "reply": "어떤 업권에 대한 감사인지 파악하지 못했습니다. "
                     "예: '26년 3월 신한은행 감사업무 시작'처럼 업권/기관명을 포함해 다시 말씀해주세요.",
            "parsed": parsed,
        }
    return {
        "ok": True,
        "reply": f"'{parsed['industry']}' 업권(코드 {parsed['industry_code']})으로 인식했습니다. "
                 f"이 업권으로 금감원 자료를 크롤링할까요?",
        "parsed": parsed,
    }


@app.post("/api/crawl")
def crawl(body: CrawlRequest):
    """3단계: 검사업무안내서 / 검사결과제재 / 경영유의사항 크롤링 및 저장."""
    if body.industry not in INDUSTRY_CODES:
        return {"ok": False, "error": f"알 수 없는 업권: {body.industry}"}

    cfg = load_config()
    crawler = FssCrawler(cfg["save_dir"])
    result = crawler.run(
        body.industry,
        manual_pages=body.manual_pages,
        sanction_pages=body.sanction_pages,
        impr_pages=body.impr_pages,
        period=body.period,
        window_months=body.window_months,
    )
    summary = {cat: len(docs) for cat, docs in result.items()}
    return {
        "ok": True,
        "summary": summary,
        "save_dir": str(Path(cfg["save_dir"]) / body.industry),
    }


@app.post("/api/checklist")
def checklist(body: CrawlRequest):
    """4단계: 저장된 자료 기반 체크리스트 생성."""
    return generate_checklist(body.industry)
