# Public Data MOTIR

공공데이터 기반 키워드 추출, 데이터 시각화, 프론트엔드 대시보드 초안을 한 저장소에서 관리하기 위한 프로젝트입니다.

## 프로젝트 구조

```text
.
├── backend/
│   ├── __init__.py
│   ├── app.py                  # FastAPI 백엔드 API skeleton
│   ├── data_visualizer.py      # CSV/Excel 데이터를 분석해 차트용 구조화 데이터 생성
│   ├── keyword_extractor.py    # 사용자 문장에서 공공데이터 검색 키워드 추출
│   └── requirements.txt        # 백엔드/API/분석 모듈 의존성
├── public-data-dashboard/
│   ├── index.html
│   ├── vercel.json
│   ├── src/
│   │   ├── App.js
│   │   ├── api.js               # 정적 프론트엔드 fetch API 클라이언트
│   │   └── components/
│   └── styles/
│       └── App.css
├── tests/
│   └── test_backend_api.py
├── .env.example
├── .gitignore
└── README.md
```

## 정리 방향

- 프론트엔드는 `public-data-dashboard/` 하나만 유지합니다.
- 기존 `public-data-dashboard`와 `public-data-dashboard-vercel`처럼 역할이 겹치는 구조는 하나의 최종 프론트엔드 폴더로 통일하는 방향으로 정리합니다.
- 기존 `public-data-keyword` 스크립트는 `backend/keyword_extractor.py`로 옮겨 import 가능한 Python 모듈로 정리했습니다.
- 기존 루트의 `data_visualizer.py`는 `backend/data_visualizer.py`로 옮겨 import 가능한 Python 모듈로 정리했습니다.
- 정적 프론트엔드는 `public-data-dashboard/src/api.js`의 최소 `fetch` 클라이언트로 FastAPI 백엔드의 `/api/keywords`를 호출합니다. 공공데이터포털 실제 API 연동과 실제 인증 연동은 추가하지 않습니다.

## 로컬 실행 방법

### 프론트엔드와 백엔드 함께 실행

터미널 1에서 FastAPI 백엔드를 실행합니다.

```bash
uvicorn backend.app:app --reload --port 8000
```

터미널 2에서 정적 프론트엔드 서버를 실행합니다.

```bash
cd public-data-dashboard
python -m http.server 5173
```

브라우저에서 `http://localhost:5173`에 접속합니다. 프론트엔드 API 기본 주소는 `http://localhost:8000`이며, 배포/개발 환경에서는 `window.PUBLIC_DATA_API_BASE_URL` 또는 브라우저 `localStorage`의 `PUBLIC_DATA_API_BASE_URL` 값으로 덮어쓸 수 있습니다. 백엔드가 꺼져 있으면 대시보드 placeholder UI와 데모 로그인은 계속 동작하지만 키워드 API 결과 영역에는 연결/추출 실패 메시지가 표시될 수 있습니다.

`/api/visualize`는 `public-data-dashboard/src/api.js`에 `visualizeDataset(file, query, coreKeyword)` 함수만 준비되어 있으며, 파일 업로드 UI와 차트 렌더링은 후속 작업입니다.

### 1. 프론트엔드 대시보드 실행

정적 HTML/CSS/JavaScript로 구성되어 있으므로 별도 빌드 없이 로컬 서버로 확인할 수 있습니다.

```bash
cd public-data-dashboard
python -m http.server 5173
```

브라우저에서 `http://localhost:5173`에 접속합니다.

> 현재 회원가입/로그인은 `localStorage`를 사용하는 데모용 구현입니다. 사용자 정보와 비밀번호가 브라우저 `localStorage`에 저장되므로 실제 인증이나 보안 기능이 아니며, 운영 환경에서는 반드시 Supabase, Firebase, 자체 백엔드 인증 API 등 안전한 인증/세션 관리로 대체해야 합니다.

### 2. 백엔드 로컬 실행

루트 디렉터리에서 가상환경을 만들고 백엔드 의존성을 설치합니다.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

환경 변수 예시 파일을 복사한 뒤 실제 Gemini API 키를 로컬에만 설정합니다. 실제 키가 들어간 `.env` 파일은 커밋하지 않습니다.

```bash
cp .env.example .env
# .env 파일에서 GOOGLE_API_KEY 값을 로컬 키로 설정
```

FastAPI 개발 서버를 실행합니다.

```bash
uvicorn backend.app:app --reload --port 8000
```

브라우저 또는 HTTP 클라이언트에서 `http://localhost:8000/docs`로 Swagger 문서를 확인할 수 있습니다.

### 3. Vercel 배포 초안

Vercel에서 프로젝트를 연결할 때 **Root Directory**를 `public-data-dashboard`로 설정합니다. 최종 프론트엔드 폴더는 `public-data-dashboard/` 하나만 사용하며, 별도의 `public-data-dashboard-vercel/` 폴더는 만들지 않습니다.

`public-data-dashboard/vercel.json`에는 정적 프론트엔드 배포를 위한 최소 설정으로 `cleanUrls`를 켭니다.

## 백엔드 API 목록

### `GET /api/health`

API 서버 상태를 확인합니다.

요청 예시:

```bash
curl http://localhost:8000/api/health
```

응답 예시:

```json
{
  "status": "ok"
}
```

### `POST /api/keywords`

사용자 아이디어 문장을 `backend.keyword_extractor.analyze_project_idea(prompt)`에 전달해 공공데이터 검색에 적합한 키워드 묶음을 생성합니다. `GOOGLE_API_KEY`는 서버 import/startup 시점이 아니라 이 API 호출 시점에 확인됩니다.

요청 예시:

```bash
curl -X POST http://localhost:8000/api/keywords \
  -H "Content-Type: application/json" \
  -d '{"prompt":"서울시 빈집 문제를 분석하고 싶어"}'
```

성공 응답 예시:

```json
{
  "status": "success",
  "topic": "서울특별시 빈집 주거환경 도시재생 부동산"
}
```

`prompt`가 비어 있거나 `GOOGLE_API_KEY`가 없거나 Gemini 호출에 실패하면 API 키 값을 노출하지 않는 안전한 JSON 에러를 반환합니다.

에러 응답 예시:

```json
{
  "detail": {
    "status": "error",
    "message": "키워드 추출을 사용할 수 없습니다.",
    "detail": "GOOGLE_API_KEY 설정을 확인한 뒤 다시 시도해 주세요."
  }
}
```

### `POST /api/visualize`

CSV 또는 Excel 파일을 업로드하면 `backend.data_visualizer.IntelligentVisualizerEngine`으로 분석해 차트 렌더링에 사용할 JSON 데이터를 반환합니다. 업로드 파일은 임시 파일로만 저장되며 처리 후 삭제됩니다.

요청 예시:

```bash
curl -X POST http://localhost:8000/api/visualize \
  -F "file=@sample.csv" \
  -F "query=카페 창업 상권 분석" \
  -F "core_keyword=상권"
```

성공 응답 예시:

```json
{
  "status": "success",
  "chart_type": "bar",
  "chart_title": "'카페 창업 상권 분석' 맞춤형 지역별 매출 분석",
  "labels": ["서울", "부산", "대구"],
  "datasets": [
    {
      "label": "매출",
      "data": [1000, 700, 500]
    }
  ],
  "strategy_reason": "항목 간의 크기 비교를 직관적으로 전달하기 위해 막대그래프(bar)를 선택했습니다.",
  "table_data": {
    "headers": ["지역", "매출"],
    "rows": [["서울", 1000], ["부산", 700], ["대구", 500]]
  },
  "startup_precautions": ["..."]
}
```

허용 확장자는 `.csv`, `.xlsx`, `.xls`입니다.

## 키워드 추출 모듈 직접 실행

`GOOGLE_API_KEY`는 저장소에 커밋하지 말고 로컬 환경 변수 또는 커밋되지 않는 `.env` 파일로만 설정합니다.

```bash
export GOOGLE_API_KEY="your-local-api-key"
python -m backend.keyword_extractor
```

## 데이터 시각화 모듈 직접 사용 예시

```python
from backend.data_visualizer import IntelligentVisualizerEngine

visualizer = IntelligentVisualizerEngine()
result = visualizer.process("sample.csv", query="카페 창업 상권 분석")
```

## 테스트 및 검증

```bash
python -m compileall backend
python - <<'PY'
from backend.app import app
print(app.title)
PY
node --check public-data-dashboard/src/components/LoginPage.js
node --check public-data-dashboard/src/App.js
node --check public-data-dashboard/src/components/DashboardPage.js
pytest
```

## TODO / 남은 작업

- `/api/visualize` 파일 업로드 UI와 차트 렌더링 구현
- 공공데이터포털 실제 API 연동
- 실제 인증 방식 도입 및 localStorage 데모 회원가입/로그인 제거
- 운영 배포 시 허용할 정확한 CORS origin 설정
- 운영 배포 시 `GOOGLE_API_KEY` 등 secret을 배포 플랫폼의 secret manager 또는 환경 변수로 안전하게 관리
- 샘플 데이터와 통합 테스트 보강

## 보안 주의

- API 키, `.env`, 개인 설정 파일은 커밋하지 않습니다.
- `.gitignore`에 `.env`, `.env.*`, 가상환경, 빌드 산출물, Vercel 로컬 설정을 제외하도록 추가했습니다.
- 업로드 파일은 저장소 내부에 저장하지 않고 API 처리 중 임시 파일로만 사용해야 합니다.
