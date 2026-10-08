"""다운로드된 hwp/pdf 첨부파일을 텍스트로 추출해 같은 폴더에 '{원본파일명}.extracted.txt'로 저장한다.

사용법:
  python extract_text.py <업권 폴더 경로>   # 예: python extract_text.py data/은행
  python extract_text.py <단일 파일 경로>   # 예: python extract_text.py data/은행/검사업무안내서/foo.hwp

이미 추출된 파일(.extracted.txt가 존재)은 건너뛴다 (재실행 시 중복 작업 방지).
"""
from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

HWP5TXT_CANDIDATES = ["hwp5txt", "hwp5txt.exe"]


def _find_hwp5txt() -> str | None:
    import shutil

    for cand in HWP5TXT_CANDIDATES:
        path = shutil.which(cand)
        if path:
            return path
    return None


def extract_pdf(path: Path) -> str:
    import pdfplumber

    parts = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            parts.append(f"--- page {i} ---\n{text}")
    return "\n\n".join(parts)


def extract_hwp(path: Path, hwp5txt_bin: str) -> str:
    result = subprocess.run(
        [hwp5txt_bin, str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"hwp5txt 실패: {result.stderr[:500]}")
    return result.stdout


def extract_hwp_syhwp(path: Path) -> str:
    """pyhwp(hwp5txt) 실패 시 syhwp 폴백으로 추출한다."""
    import syhwp
    return syhwp.extract_text(str(path))


def extract_hwpx(path: Path) -> str:
    """hwpx(HWP Open XML, .hwpx)에서 텍스트를 추출한다.
    hwpx는 ZIP 구조 안에 XML 파일들로 구성된다."""
    import zipfile, xml.etree.ElementTree as ET
    parts = []
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        # Contents/section*.xml 또는 word/document.xml 형태
        body_files = sorted(
            n for n in names
            if ("section" in n.lower() or "body" in n.lower() or "document" in n.lower())
            and n.endswith(".xml")
        )
        if not body_files:
            body_files = [n for n in names if n.endswith(".xml")]
        for name in body_files[:20]:
            try:
                xml_bytes = zf.read(name)
                root = ET.fromstring(xml_bytes)
                for elem in root.iter():
                    if elem.text and elem.text.strip():
                        parts.append(elem.text.strip())
                    if elem.tail and elem.tail.strip():
                        parts.append(elem.tail.strip())
            except Exception:
                continue
    return "\n".join(parts)


def extract_file(path: Path, hwp5txt_bin: str | None) -> Path | None:
    out_path = path.with_suffix(path.suffix + ".extracted.txt")
    if out_path.exists():
        return out_path

    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            text = extract_pdf(path)
        elif suffix == ".hwp":
            if hwp5txt_bin:
                try:
                    text = extract_hwp(path, hwp5txt_bin)
                except Exception as e:
                    # pyhwp OLE 파싱 한계 → syhwp 폴백
                    try:
                        text = extract_hwp_syhwp(path)
                        print(f"[폴백→syhwp] {path.name}")
                    except Exception as e2:
                        raise RuntimeError(f"hwp5txt 실패: {e}; syhwp 실패: {e2}")
            else:
                try:
                    text = extract_hwp_syhwp(path)
                    print(f"[syhwp] {path.name}")
                except Exception as e:
                    print(f"[스킵] hwp5txt 미설치, syhwp도 실패: {path.name}: {e}", file=sys.stderr)
                    return None
        elif suffix == ".hwpx":
            text = extract_hwpx(path)
        else:
            return None
    except Exception as e:
        print(f"[실패] {path.name}: {e}", file=sys.stderr)
        return None

    out_path.write_text(text, encoding="utf-8", errors="replace")
    return out_path


def _unzip_archives(root: Path) -> None:
    """검사업무안내서 등이 여러 hwp를 zip으로 묶어 배포하는 경우가 있다.
    같은 폴더에 '{zip이름}_unzipped/'로 풀어 이후 hwp/pdf 스캔 대상에 포함시킨다.
    이미 풀린 zip(대상 폴더 존재)은 다시 풀지 않는다."""
    for zpath in root.rglob("*.zip"):
        out_dir = zpath.with_name(zpath.stem + "_unzipped")
        if out_dir.exists():
            continue
        try:
            with zipfile.ZipFile(zpath) as zf:
                zf.extractall(out_dir)
            print(f"[압축해제] {zpath.name} -> {out_dir.name}/")
        except Exception as e:
            print(f"[실패] zip 해제 실패: {zpath.name}: {e}", file=sys.stderr)


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    target = Path(sys.argv[1])
    hwp5txt_bin = _find_hwp5txt()
    if not hwp5txt_bin:
        print("[경고] hwp5txt 실행파일을 찾지 못했습니다. "
              "`pip install pyhwp` 후 다시 시도하세요. (hwp 파일은 건너뜁니다)", file=sys.stderr)

    if target.is_dir():
        _unzip_archives(target)

    targets = [target] if target.is_file() else sorted(
        p for p in target.rglob("*") if p.suffix.lower() in (".pdf", ".hwp", ".hwpx")
    )

    done, skipped = 0, 0
    for p in targets:
        out = extract_file(p, hwp5txt_bin)
        if out:
            print(f"[완료] {p.name} -> {out.name}")
            done += 1
        else:
            skipped += 1

    print(f"\n총 {len(targets)}건 중 {done}건 추출 완료, {skipped}건 스킵/실패")


if __name__ == "__main__":
    main()
