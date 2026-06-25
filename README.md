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
│   ├── public_data_portal.py   # 공공데이터포털 데이터셋 검색 client/응답 정규화
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
- 정적 프론트엔드는 `public-data-dashboard/src/api.js`의 최소 `fetch` 클라이언트로 FastAPI 백엔드의 `/api/keywords`와 `/api/visualize`를 호출합니다. `/api/visualize`는 대시보드 파일 업로드 UI와 연결되어 CSV/Excel 분석 결과를 표시합니다. 공공데이터포털 데이터셋 검색 후보 목록은 `/api/datasets/search`로 1차 연동했으며, 선택한 데이터셋의 실제 다운로드/자동 시각화와 실제 인증 연동은 추가하지 않습니다.

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

Codespaces처럼 frontend forwarded URL과 backend forwarded URL이 서로 다르면 브라우저 개발자 도구 Console에서 백엔드 forwarded URL을 직접 지정합니다. 예를 들어 백엔드가 `https://example-8000.app.github.dev`로 열려 있다면 다음을 실행한 뒤 프론트엔드 페이지를 새로고침합니다.

```js
localStorage.setItem("PUBLIC_DATA_API_BASE_URL", "https://example-8000.app.github.dev");
```

로컬 기본값으로 되돌리려면 다음을 실행합니다.

```js
localStorage.removeItem("PUBLIC_DATA_API_BASE_URL");
```

대시보드의 시각화 패널에서 `.csv`, `.xlsx`, `.xls` 파일을 선택한 뒤 **시각화 실행**을 누르면 `visualizeDataset(file, query, coreKeyword)`가 `/api/visualize`를 호출합니다. 응답의 `chart_title`, `chart_type`, `strategy_reason`, `labels`, `datasets`, `table_data`, `startup_precautions`를 Vanilla JS/HTML/CSS로 표시하며, Chart.js/React/Vite 또는 추가 npm 패키지는 사용하지 않습니다. `bar` 결과는 CSS 기반 간단 막대그래프로도 미리 보여주고, `line`/`pie` 등은 요약/목록/표 중심으로 표시합니다. 응답 일부가 없거나 형식이 달라도 시각화 영역은 “표시 가능한 데이터가 제한적입니다. 일부 결과만 표시됩니다.” 안내와 함께 가능한 항목만 표시합니다. 백엔드가 꺼져 있거나 분석에 실패해도 대시보드 전체가 깨지지 않고 시각화 영역에만 오류가 표시됩니다.

테스트용 CSV는 `tests/fixtures/visualize_sample.csv`를 사용할 수 있으며, 직접 만들 때는 아래처럼 범주형 컬럼 1개와 숫자형 컬럼 1개 이상을 포함합니다.

```csv
지역,매출,점포수
서울,1000,10
부산,700,7
대구,500,5
```


대시보드의 “공공데이터 후보” 섹션은 키워드 추출 성공 시 추출 topic으로 `/api/datasets/search`를 자동 호출하고, 실패 시 원래 프롬프트 또는 수동 검색어로 후보 검색을 시도합니다. 현재 범위는 후보 목록 표시와 선택 상태 표시까지입니다. 선택한 데이터셋을 실제 CSV/API로 다운로드하거나 `/api/visualize`에 자동 연결하는 기능은 후속 PR에서 구현합니다.

공공데이터포털 검색 API를 사용하려면 로컬 `.env` 또는 배포 환경 변수에 다음 값을 설정합니다. 실제 키는 절대 커밋하지 않습니다. `PUBLIC_DATA_PORTAL_BASE_URL`은 공공데이터포털의 실제 데이터셋 검색 endpoint가 확정되면 해당 URL로 덮어씁니다.

```bash
PUBLIC_DATA_API_KEY=your-public-data-api-key
PUBLIC_DATA_PORTAL_BASE_URL=https://api.odcloud.kr/api
```

실제 배포 사이트에서 `/api/visualize`를 확인하려면 백엔드 배포가 먼저 완료되어야 하며, 배포된 정적 프론트엔드에 올바른 API base URL 설정이 적용되어 있어야 합니다.

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


### `/api/visualize` 프론트엔드 연결 테스트

1. 백엔드와 정적 프론트엔드를 각각 실행합니다.
2. 브라우저에서 `http://localhost:5173`에 접속해 데모 계정으로 회원가입/로그인합니다.
3. 메인 프롬프트를 제출해 대시보드로 이동합니다.
4. 시각화 패널에서 `.csv`, `.xlsx`, `.xls` 파일을 선택하고 **시각화 실행**을 누릅니다.
5. 성공 시 차트 제목/유형/전략 이유, 라벨, 데이터셋, 일부 표 행, 창업 유의사항이 표시되는지 확인합니다.

> 현재 표시는 Vanilla JS와 CSS 기반의 간단한 대시보드 표시입니다. Chart.js, React, Vite 같은 프론트엔드 빌드 체계나 차트 라이브러리는 도입하지 않았으며, 공공데이터포털 실제 API 검색/수집 연동은 후속 작업입니다.

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


### `POST /api/datasets/search`

공공데이터포털 데이터셋 후보를 키워드로 검색하고 프론트엔드가 바로 표시하기 쉬운 정규화 구조를 반환합니다. 실제 포털 endpoint가 환경마다 다를 수 있어 `backend/public_data_portal.py`는 `PUBLIC_DATA_PORTAL_BASE_URL`과 `PUBLIC_DATA_API_KEY`를 사용하도록 만들었고, 응답 정규화는 fixture/mock 테스트로 검증합니다. 키가 없거나 외부 API 호출에 실패하면 실제 키 값을 노출하지 않는 안전한 오류를 반환합니다.

요청 예시:

```bash
curl -X POST http://localhost:8000/api/datasets/search \
  -H "Content-Type: application/json" \
  -d '{"keyword":"서울 빈집","page":1,"per_page":10}'
```

성공 응답 예시:

```json
{
  "status": "success",
  "query": "서울 빈집",
  "items": [
    {
      "id": "string-or-null",
      "title": "데이터셋 제목",
      "description": "설명",
      "provider": "제공기관",
      "category": "분류",
      "format": "CSV/API/JSON 등",
      "updated_at": "날짜 또는 null",
      "url": "상세 페이지 또는 API 링크",
      "raw": {}
    }
  ],
  "message": ""
}
```

`keyword`가 비어 있으면 400을 반환합니다. `PUBLIC_DATA_API_KEY`가 없거나 외부 호출이 실패하면 503과 안전한 JSON 오류를 반환합니다. 이번 구현은 검색 후보 목록 표시까지이며, 선택 데이터셋의 실제 다운로드와 `/api/visualize` 자동 연결은 후속 작업입니다.

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

허용 확장자는 `.csv`, `.xlsx`, `.xls`입니다. 프론트엔드에서도 동일한 확장자만 선택하도록 안내하며, 결과 표는 데이터가 많을 수 있어 처음 일부 행만 표시합니다.

#### `/api/visualize` 성공 응답 스키마

현재 프론트엔드 렌더러가 기대하는 성공 응답 계약은 다음과 같습니다. 백엔드는 별도 Pydantic response model로 강제하지 않지만, 프론트는 누락/형식 오류를 방어적으로 처리하며 불완전한 응답이면 제한 표시 안내를 보여줍니다.

| 필드 | 타입 | 필수 여부 | 설명 |
| --- | --- | --- | --- |
| `status` | string | 필수 | 성공 시 `"success"`. 다른 값이 오면 불완전한 결과로 안내합니다. |
| `chart_type` | string | 권장 | `"bar"`, `"line"`, `"pie"` 등 추천 차트 유형. 누락 시 `유형 미정`으로 표시합니다. |
| `chart_title` | string | 권장 | 시각화 제목. 누락 시 `제목 없음`으로 표시합니다. |
| `labels` | array | 권장 | 차트/목록 X축 라벨 배열. 배열이 아니거나 없으면 빈 라벨 상태로 표시합니다. |
| `datasets` | array of object | 권장 | 각 항목은 `label` string과 `data` array를 가집니다. 없거나 비어 있으면 데이터셋 없음 안내를 표시합니다. |
| `datasets[].data` | array | 권장 | 숫자 렌더링을 기대하지만 문자열/빈 값/null이 섞여도 프론트는 숫자로 변환 가능한 값만 그래프에 반영하고 나머지는 0 또는 `(빈 값)`으로 안전 표시합니다. |
| `strategy_reason` | string | 권장 | 차트 선택 이유. 누락 시 기본 안내 문구를 표시합니다. |
| `table_data.headers` | array | 권장 | 표 헤더 배열. 없거나 배열이 아니면 표 fallback UI를 표시합니다. |
| `table_data.rows` | array | 권장 | 표 행 배열. 행은 배열 또는 헤더 키를 가진 객체일 수 있습니다. 없거나 배열이 아니면 표 fallback UI를 표시합니다. |
| `startup_precautions` | array of string | 권장 | 창업 유의사항 문자열 배열. 문자열 배열이 아니면 표시 가능한 문자열만 사용하고 없으면 fallback 문구를 표시합니다. |

오류 응답은 FastAPI `HTTPException.detail`에 `{ "status": "error", "message": "..." }` 형태의 안전한 메시지를 담습니다. 지원하지 않는 확장자는 400, 빈 파일 또는 숫자형 지표가 없어 시각화할 수 없는 파일은 422를 반환합니다.

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

저장소 루트의 `pytest.ini`가 `tests/`를 테스트 경로로 지정하고 repo root를 Python import path에 추가하므로, 로컬/Codespaces/CI에서 `pytest`만 실행해도 `backend` 패키지를 안정적으로 import할 수 있습니다.

```bash
python -m compileall backend
python - <<'PY'
from backend.app import app
print(app.title)
PY
pytest
node --check public-data-dashboard/src/api.js
node --check public-data-dashboard/src/App.js
node --check public-data-dashboard/src/components/DashboardPage.js
node --check public-data-dashboard/src/components/LoginPage.js
```

GitHub Actions의 `CI` workflow는 `main` 브랜치 push와 `main` 대상 pull request에서 Python 3.12, Node.js 20 환경으로 백엔드 컴파일/import/pytest와 프론트엔드 JavaScript syntax check를 자동 실행합니다.

## TODO / 남은 작업

- `/api/visualize` 고급 차트 렌더링 및 대용량 데이터 UX 개선
- 공공데이터포털 실제 API 연동
- 실제 인증 방식 도입 및 localStorage 데모 회원가입/로그인 제거
- 운영 배포 시 허용할 정확한 CORS origin 설정
- 운영 배포 시 `GOOGLE_API_KEY` 등 secret을 배포 플랫폼의 secret manager 또는 환경 변수로 안전하게 관리
- 샘플 데이터와 통합 테스트 보강

## 보안 주의

- API 키, `.env`, 개인 설정 파일은 커밋하지 않습니다.
- `.gitignore`에 `.env`, `.env.*`, 가상환경, 빌드 산출물, Vercel 로컬 설정을 제외하도록 추가했습니다.
- 업로드 파일은 저장소 내부에 저장하지 않고 API 처리 중 임시 파일로만 사용해야 합니다.
