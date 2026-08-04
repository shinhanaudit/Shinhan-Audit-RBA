# FSS 감사 체크리스트 하네스 - 초기 설정 스크립트
# 더블클릭으로 실행 가능하도록 install.bat에서 이 스크립트를 호출한다.
# 이 스크립트가 하는 일: (1) Python 설치 확인 (2) .venv 가상환경 생성 (3) requirements.txt 설치
# Claude Code 설치와 Gmail 연결은 이 스크립트로 자동화할 수 없어 README.md 안내를 따로 둔다.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "=== FSS 감사 체크리스트 하네스 설치 시작 ===" -ForegroundColor Cyan

# 1. Python 확인
$pythonCmd = $null
foreach ($candidate in @("python", "py")) {
    try {
        $versionOutput = & $candidate --version 2>&1
        if ($LASTEXITCODE -eq 0 -and $versionOutput -match "Python 3\.(\d+)") {
            $minor = [int]$Matches[1]
            if ($minor -ge 10) {
                $pythonCmd = $candidate
                break
            }
        }
    } catch {}
}

if (-not $pythonCmd) {
    Write-Host ""
    Write-Host "Python 3.10 이상이 설치되어 있지 않습니다." -ForegroundColor Red
    Write-Host "https://www.python.org/downloads/ 에서 Python을 설치한 뒤(설치 화면에서 'Add python.exe to PATH' 체크 필수) 이 스크립트를 다시 실행해주세요."
    Read-Host "엔터를 누르면 종료합니다"
    exit 1
}

Write-Host "[OK] Python 발견: $pythonCmd" -ForegroundColor Green

# 2. 가상환경 생성 (.venv)
if (-not (Test-Path "$root\.venv")) {
    Write-Host "가상환경(.venv)을 생성합니다..."
    & $pythonCmd -m venv .venv
} else {
    Write-Host "[OK] 가상환경(.venv)이 이미 있습니다."
}

$venvPython = "$root\.venv\Scripts\python.exe"

# 3. 의존성 설치
Write-Host "필요한 패키지를 설치합니다 (몇 분 걸릴 수 있습니다)..."
& $venvPython -m pip install --upgrade pip -q
& $venvPython -m pip install -r requirements.txt -q

if ($LASTEXITCODE -ne 0) {
    Write-Host "패키지 설치 중 오류가 발생했습니다. 인터넷 연결을 확인하고 다시 시도해주세요." -ForegroundColor Red
    Read-Host "엔터를 누르면 종료합니다"
    exit 1
}

Write-Host ""
Write-Host "=== 설치 완료 ===" -ForegroundColor Green
Write-Host "다음 단계는 README.md의 '2단계: Claude Code 설치'부터 이어서 진행해주세요."
Read-Host "엔터를 누르면 창을 닫습니다"
