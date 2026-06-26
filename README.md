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
- 정적 프론트엔드는 `public-data-dashboard/src/api.js`의 최소 `fetch` 클라이언트로 FastAPI 백엔드의 `/api/keywords`와 `/api/visualize`를 호출합니다. `/api/visualize`는 대시보드 파일 업로드 UI와 연결되어 CSV/Excel 분석 결과를 표시합니다. 공공데이터포털 데이터셋 검색 후보 목록은 `/api/datasets/search`로 1차 연동했고, 선택한 데이터셋의 상세 metadata와 다운로드/API 링크 후보는 `/api/datasets/detail`로 표시합니다. 선택한 데이터셋의 실제 다운로드/자동 시각화와 실제 인증 연동은 추가하지 않습니다.

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


대시보드의 “공공데이터 후보” 섹션은 키워드 추출 성공 시 추출 topic으로 `/api/datasets/search`를 자동 호출하고, 실패 시 원래 프롬프트 또는 수동 검색어로 후보 검색을 시도합니다. 현재 범위는 후보 목록 표시, 선택 상태 표시, 선택한 데이터셋의 상세 metadata 및 다운로드/API 링크 후보 표시, 사용자가 누른 resource의 CSV/TSV/JSON 소량 미리보기까지입니다. 링크는 새 탭으로 열 수 있지만 자동 다운로드하지 않으며, 선택한 데이터셋을 실제 CSV/API로 전체 다운로드하거나 `/api/visualize`에 자동 연결하는 기능은 후속 PR에서 구현합니다.

공공데이터포털 검색 API를 사용하려면 로컬 `.env` 또는 배포 환경 변수에 다음 값을 설정합니다. 실제 키는 절대 커밋하지 않습니다. `PUBLIC_DATA_PORTAL_BASE_URL`은 공공데이터포털의 실제 데이터셋 검색 endpoint가 확정되면 해당 URL로 덮어씁니다.

```bash
PUBLIC_DATA_API_KEY=your-public-data-api-key
PUBLIC_DATA_PORTAL_BASE_URL=https://api.odcloud.kr/api
```

데이터셋 후보 카드에서 **선택**을 누르면 프론트엔드가 선택한 검색 item 전체를 `/api/datasets/detail`의 `raw`로 전달해 우선 fixture/mock 기반 정규화 계층으로 상세 정보와 리소스 후보를 표시합니다. 실제 공공데이터포털 상세 endpoint가 확정된 환경에서는 `dataset_id` 또는 `url`만으로도 `PUBLIC_DATA_PORTAL_BASE_URL`/`PUBLIC_DATA_API_KEY` 기반 조회를 연결할 수 있게 backend helper를 분리했습니다. 실제 파일 다운로드 및 자동 시각화 연결은 후속 작업입니다.

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
5. 공공데이터 후보에서 **선택**을 누른 뒤 “선택한 데이터셋 상세”와 다운로드/API 링크 후보가 표시되는지 확인합니다.
6. 성공 시 차트 제목/유형/전략 이유, 라벨, 데이터셋, 일부 표 행, 창업 유의사항이 표시되는지 확인합니다.

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

### `POST /api/datasets/detail`

선택한 공공데이터 후보의 상세 metadata와 다운로드/API 링크 후보를 안전하게 정규화해 반환합니다. 실제 공공데이터포털 상세 endpoint는 환경 설정으로 연결하도록 남겨 두었고, 프론트엔드는 선택한 후보 item 전체를 `raw`로 전달해 외부 호출 없이도 정규화 결과를 표시할 수 있습니다. `resources[].url`은 표시/새 탭 열기 후보일 뿐이며 이번 범위에서 자동 다운로드하거나 `/api/visualize`에 연결하지 않습니다.

요청 예시:

```bash
curl -X POST http://localhost:8000/api/datasets/detail \
  -H "Content-Type: application/json" \
  -d '{"dataset_id":"ds-1","url":"https://www.data.go.kr/...","raw":{}}'
```

성공 응답 예시:

```json
{
  "status": "success",
  "dataset": {
    "id": "string-or-null",
    "title": "데이터셋 제목",
    "description": "설명",
    "provider": "제공기관",
    "category": "분류",
    "format": "CSV/API/JSON 등",
    "updated_at": "날짜 또는 null",
    "url": "상세 페이지"
  },
  "resources": [
    {
      "name": "파일/API 이름",
      "format": "CSV/XLSX/JSON/API/unknown",
      "url": "다운로드 또는 API 후보 URL",
      "description": "설명",
      "is_downloadable": true,
      "is_api": false
    }
  ],
  "message": ""
}
```

`dataset_id`와 `url`이 모두 없고 `raw`에서도 식별자를 찾지 못하면 400을 반환합니다. API key/base URL 누락 또는 외부 API 실패 시 실제 key 값을 노출하지 않는 안전한 JSON 오류를 반환합니다.


### `POST /api/datasets/resource/preview`

사용자가 데이터셋 상세 카드에서 명시적으로 선택한 resource URL을 backend에서 먼저 안전하게 검사한 뒤, CSV/TSV/JSON에 한해 작은 preview를 반환합니다. preview 자체는 소량 확인용이며, resource 전체 분석은 자동으로 실행되지 않습니다. 원격 Excel(`.xls`, `.xlsx`)은 보안/크기 이슈 때문에 직접 파싱하지 않고, 사용자가 파일을 내려받아 기존 업로드 UI로 직접 올리는 흐름을 안내합니다.

요청 예시:

```bash
curl -X POST http://localhost:8000/api/datasets/resource/preview \
  -H "Content-Type: application/json" \
  -d '{"resource":{"name":"파일/API 이름","format":"CSV","url":"https://example.test/data.csv","description":"설명","is_downloadable":true,"is_api":false},"max_rows":10}'
```

성공 응답 예시:

```json
{
  "status": "success",
  "resource": {
    "name": "파일/API 이름",
    "format": "CSV",
    "url": "https://example.test/data.csv",
    "description": "설명",
    "is_downloadable": true,
    "is_api": false
  },
  "preview": {
    "kind": "table",
    "headers": ["col1", "col2"],
    "rows": [["a", "1"], ["b", "2"]],
    "truncated": false,
    "message": "처음 2행만 표시합니다."
  },
  "metadata": {
    "content_type": "text/csv",
    "bytes_read": 18,
    "source_url": "https://example.test/data.csv"
  },
  "message": ""
}
```

`resource.url`이 없으면 400을 반환합니다. `http://`와 `https://`만 허용하며 `file://`, localhost, private IP, loopback, link-local, internal host 접근은 차단합니다. 외부 요청은 timeout과 최대 byte 수 제한을 두고, redirect 후 최종 URL host도 다시 검사합니다. 응답 metadata URL에는 `serviceKey`, `api_key`, `token`, `secret` 등 민감 query 값을 `REDACTED`로 치환해 실제 key/secret이 노출되지 않도록 합니다. 외부 요청 실패, timeout, 파싱 실패는 안전한 오류 메시지로만 반환합니다.


### `POST /api/datasets/resource/visualize`

사용자가 resource preview 또는 후보 카드에서 **“이 리소스로 시각화”** 버튼을 명시적으로 누른 경우에만 원격 resource 분석을 수행합니다. 후보 검색, 상세 조회, preview 성공만으로는 원격 원본을 전체 다운로드하거나 분석하지 않습니다.

지원 범위는 원격 CSV/TSV/JSON입니다. CSV/TSV는 제한된 byte 범위 안에서 임시 파일로 저장한 뒤 기존 `backend.data_visualizer.IntelligentVisualizerEngine` 분석 흐름을 재사용합니다. JSON은 top-level 객체 배열 또는 `data`/`items`/`records` 같은 배열을 표 형태 CSV로 변환할 수 있을 때만 분석하고, 변환이 어렵다면 안전한 422 오류를 반환합니다. 원격 Excel(`.xls`, `.xlsx`) 자동 분석은 아직 지원하지 않으며 기존 파일 업로드 UI를 사용해야 합니다.

보안/운영 제한은 preview와 같은 URL 안전성 원칙을 재사용합니다. `http`/`https` 외 scheme, `file://`, localhost, loopback, private IP, link-local/internal host 접근을 차단하고, redirect 후 최종 host도 다시 검사합니다. timeout과 최대 다운로드 byte 제한을 적용하며, `serviceKey`, `api_key`, `token`, `secret` 등 민감 query string은 응답 metadata에서 `REDACTED`로 마스킹합니다. 원격 원본은 repository 내부에 저장하지 않고 `tempfile` 임시 파일로만 처리하며 `finally`에서 삭제합니다.

요청 예시:

```bash
curl -X POST http://localhost:8000/api/datasets/resource/visualize \
  -H 'Content-Type: application/json' \
  -d '{
    "resource": {
      "name": "샘플 CSV",
      "format": "CSV",
      "url": "https://example.test/data.csv",
      "description": "설명",
      "is_downloadable": true,
      "is_api": false
    },
    "query": "사용자 프롬프트",
    "core_keyword": "키워드"
  }'
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
rg -n "<<<<<<<|=======|>>>>>>>" . --hidden -g '!*.git/*' || true
rg -n "AQ\.Ab|AIza|GOOGLE_API_KEY\s*=|PUBLIC_DATA_API_KEY\s*=|BEGIN (RSA|OPENSSH|PRIVATE)|api[_-]?key|secret" . --hidden -g '!*.git/*' -g '!backend/**pycache**/*' || true
test ! -e public-data-dashboard-vercel && test ! -e public-data-keyword && test ! -e data_visualizer.py && echo forbidden-root-paths-ok
```

GitHub Actions의 `CI` workflow는 `main` 브랜치 push와 `main` 대상 pull request에서 Python 3.12, Node.js 20 환경으로 백엔드 컴파일/import/pytest와 프론트엔드 JavaScript syntax check를 자동 실행합니다.

## TODO / 남은 작업

- `/api/visualize` 고급 차트 렌더링 및 대용량 데이터 UX 개선
- 공공데이터포털 실제 상세 endpoint 확정 및 실데이터 다운로드/API 호출 연동
- resource preview 후 사용자가 명시적으로 “이 리소스로 시각화”를 누르는 CSV/TSV/JSON 분석 UX 확인
- 원격 Excel 자동 분석은 미지원이므로 파일 업로드 안내가 표시되는지 확인
- 실제 인증 방식 도입 및 localStorage 데모 회원가입/로그인 제거
- 운영 배포 시 허용할 정확한 CORS origin 설정
- 운영 배포 시 `GOOGLE_API_KEY` 등 secret을 배포 플랫폼의 secret manager 또는 환경 변수로 안전하게 관리
- 샘플 데이터와 통합 테스트 보강

## 보안 주의

- API 키, `.env`, 개인 설정 파일은 커밋하지 않습니다.
- `.gitignore`에 `.env`, `.env.*`, 가상환경, 빌드 산출물, Vercel 로컬 설정을 제외하도록 추가했습니다.
- 업로드 파일은 저장소 내부에 저장하지 않고 API 처리 중 임시 파일로만 사용해야 합니다.

## 실제 end-to-end 점검 절차

이 프로젝트의 핵심 흐름은 정적 프론트엔드가 FastAPI 백엔드에 연결되어 CSV 업로드 분석과 data.go.kr 후보 검색을 수행하는 방식입니다. 더 이상 후보 표시만 하는 스켈레톤이 아니며, `/api/datasets/search`와 `/api/datasets/detail`은 공개 `https://www.data.go.kr/tcs/dss/selectDataSetList.do` 및 검색 결과의 상세 페이지 HTML을 요청해 후보/상세/리소스 링크를 정규화합니다.

### 로컬 또는 Codespaces 실행

1. 백엔드 실행

   ```bash
   uvicorn backend.app:app --reload --port 8000
   ```

2. 프론트엔드 실행

   ```bash
   cd public-data-dashboard
   python -m http.server 5173
   ```

3. 브라우저에서 `http://127.0.0.1:5173`을 열고, 필요하면 `localStorage.PUBLIC_DATA_API_BASE_URL` 또는 `window.PUBLIC_DATA_API_BASE_URL`을 배포된 백엔드 URL로 설정합니다. 기본값은 `http://localhost:8000`입니다.

### 기능별 확인

- CSV 직접 업로드 분석: 대시보드 시각화 패널에서 `tests/fixtures/visualize_sample.csv`처럼 범주형 열과 숫자형 열이 있는 CSV/XLS/XLSX를 선택하고 **시각화 실행**을 누릅니다. 백엔드/프론트엔드 모두 timeout과 오류 응답 처리를 적용하므로 30초 내 성공 결과 또는 명확한 오류가 표시되어야 하며 “분석 중...” 상태가 무한히 남지 않아야 합니다.
- data.go.kr 후보 검색: 프롬프트 또는 수동 검색어에 `서울 부동산 가격`, `광주 맛집`, `공영자전거` 등을 입력하면 백엔드가 data.go.kr 데이터목록 HTML을 요청해 title, description, provider, category, format, updated_at, detail URL, keywords를 추출합니다.
- 후보 선택/detail 표시: 후보 카드의 선택 버튼을 누르면 검색 결과의 detail URL 또는 raw payload를 사용해 상세 정보를 표시합니다. 상세 페이지에서 다운로드/API 링크를 찾으면 `resources`에 표시하고, 찾지 못하면 “상세 페이지에서 직접 다운로드가 필요합니다” 안내와 상세 페이지 링크를 제공합니다.
- resource preview: 리소스 URL이 있는 CSV/TSV/JSON 후보만 사용자가 버튼을 누른 뒤 제한된 byte 범위로 미리보기합니다. URL이 없거나 미지원 형식이면 버튼이 비활성화되거나 명확한 안내가 표시됩니다.
- resource visualize: 사용자가 **이 리소스로 시각화**를 누른 경우에만 원격 CSV/TSV/JSON을 가져와 기존 시각화 엔진으로 분석합니다. 원격 Excel은 안전상 자동 분석하지 않으며 직접 파일 업로드를 사용해야 합니다.

### API key 필요 여부

- `PUBLIC_DATA_API_KEY`: data.go.kr HTML 검색/detail fallback에는 필요하지 않습니다. 인증이 필요한 개별 OpenAPI 리소스를 사용자가 직접 호출하려는 경우에만 해당 API 문서에 맞는 키가 필요할 수 있으며, 실제 키는 서버 환경 변수 또는 사용자의 안전한 런타임 설정에만 둬야 합니다.
- `GOOGLE_API_KEY`: `/api/keywords`에서 Gemini 기반 키워드 추출을 사용하려면 필요합니다. 키가 없거나 외부 AI 호출이 실패해도 프론트엔드는 원래 프롬프트로 data.go.kr 검색을 계속 시도하고 loading을 해제합니다.

### data.go.kr HTML 파싱 한계

공개 HTML 구조를 파싱하는 fallback이므로 data.go.kr의 마크업이 크게 바뀌면 일부 필드 또는 리소스 URL 자동 추출이 실패할 수 있습니다. 이 경우에도 API는 JSON 오류 또는 빈 결과/안내 메시지를 반환하고, 프론트엔드는 무한 loading 대신 오류 메시지를 표시합니다. 실제 배포 사이트 점검은 백엔드 배포 URL, CORS 허용 origin, 프론트엔드 API base URL 설정을 맞춘 뒤 수행하세요.

### Smoke checks

기본 smoke는 외부 포털을 호출하지 않습니다.

```bash
uvicorn backend.app:app --host 127.0.0.1 --port 8000
python scripts/smoke_api_flow.py --base-url http://127.0.0.1:8000
```

실제 data.go.kr live smoke는 명시적으로 opt-in 해야 합니다.

```bash
python scripts/smoke_api_flow.py --base-url http://127.0.0.1:8000 --live-data-go-kr --query "서울 부동산 가격"
```

## 배포/런타임 연결 진단 가이드

이번 저장소는 정적 frontend와 FastAPI backend를 별도로 배포할 수 있습니다. 실제 사이트에서 CSV 업로드 분석 또는 공공데이터 검색이 동작하지 않으면 먼저 frontend가 올바른 backend URL을 바라보는지, backend CORS가 frontend origin을 허용하는지 확인해야 합니다.

### Local/Codespaces 실행

백엔드는 저장소 루트에서 실행합니다.

```bash
uvicorn backend.app:app --reload --port 8000
```

정적 frontend는 별도 터미널에서 실행합니다.

```bash
cd public-data-dashboard
python -m http.server 5173
```

브라우저에서 `http://localhost:5173`을 열고 대시보드의 **API 연결 상태** 영역에서 현재 API base URL과 `/api/health` 결과를 확인합니다.

### Static frontend 배포 시 backend URL 설정

frontend 기본 backend URL은 `http://localhost:8000`입니다. 배포 사이트에서는 실제 backend URL을 아래 중 하나로 설정합니다.

1. 정적 호스팅에 `public-data-dashboard/config.example.js`를 참고해 별도의 `config.js`를 만들고, frontend HTML보다 먼저 로드되도록 설정합니다. 실제 배포 URL은 예시 파일에 하드코딩하지 않습니다.

```javascript
window.PUBLIC_DATA_API_BASE_URL = "https://YOUR-BACKEND-URL";
```

2. 긴급 점검 또는 preview 환경에서는 브라우저 개발자 도구 Console에서 localStorage override를 설정할 수 있습니다.

```javascript
localStorage.setItem("PUBLIC_DATA_API_BASE_URL", "https://YOUR-BACKEND-URL");
location.reload();
```

localStorage override를 지우려면 다음을 실행합니다.

```javascript
localStorage.removeItem("PUBLIC_DATA_API_BASE_URL");
location.reload();
```

frontend에는 `PUBLIC_DATA_API_KEY`, data.go.kr 인증키, `GOOGLE_API_KEY`, secret/token을 넣지 않습니다. backend URL만 설정합니다.

### Backend 배포 시 필요한 환경변수

키워드 추출과 공공데이터포털 live 호출이 필요한 backend 배포 환경에는 서버 환경변수로만 값을 설정합니다. `.env` 파일이나 실제 키는 커밋하지 않습니다.

```bash
GOOGLE_API_KEY=your-server-side-google-key
PUBLIC_DATA_API_KEY=your-server-side-data-go-kr-key
PUBLIC_DATA_PORTAL_BASE_URL=https://api.odcloud.kr/api
APP_ENV=production
```

`/api/health`는 빠른 상태 확인용이며 data.go.kr live 접근을 직접 호출하지 않습니다.

### CORS 설정

backend는 localhost 개발 origin을 기본 허용합니다. 배포 frontend origin은 comma-separated `ALLOWED_ORIGINS`로 추가합니다.

```bash
ALLOWED_ORIGINS=https://your-frontend-site.com,https://another-preview-url.com
```

보안상 `*`를 기본 허용하지 않습니다. 개발 편의를 위해 명시적으로 `ALLOWED_ORIGINS=*`를 설정한 경우에만 wildcard를 사용하며, 이때 credentials는 비활성화됩니다. 운영 배포에서는 실제 frontend origin을 명시하세요.

### 실제 사이트 점검 순서

1. 대시보드의 **API 연결 상태**가 success인지 확인합니다.
2. CSV 업로드 분석(`/api/visualize`)을 확인합니다.
3. 공공데이터 검색(`/api/datasets/search`)을 확인합니다.
4. 후보 선택/detail(`/api/datasets/detail`)을 확인합니다.
5. resource preview(`/api/datasets/resource/preview`)를 확인합니다.
6. resource visualize(`/api/datasets/resource/visualize`)를 확인합니다.

배포 provider의 outbound 정책, 방화벽, WAF, data.go.kr의 차단/제한 때문에 live data.go.kr 접근이 실패할 수 있습니다. live smoke가 실패하더라도 frontend는 무한 loading에 빠지면 안 되며, “백엔드 API에 연결할 수 없습니다. API base URL과 배포 상태를 확인하세요.” 또는 endpoint별 실패 메시지를 보여야 합니다.

### Smoke script

기본 smoke는 외부 data.go.kr live 호출에 의존하지 않고 `/api/health`와 CSV 업로드 분석만 확인합니다.

```bash
python scripts/smoke_api_flow.py --base-url http://127.0.0.1:8000
```

live data.go.kr 검색까지 확인할 때만 명시적으로 opt-in 합니다.

```bash
python scripts/smoke_api_flow.py --base-url http://127.0.0.1:8000 --live-data-go-kr
```

## data.go.kr 연결 진단

`/api/health`는 backend 프로세스가 실행 중인지 확인하는 빠른 local-only health check입니다. 이 endpoint는 느려지지 않도록 data.go.kr 같은 외부 서비스를 live 호출하지 않습니다.

배포 환경에서 backend가 실제로 data.go.kr까지 outbound 접근할 수 있는지 확인하려면 명시적으로 다음 endpoint를 호출합니다.

```bash
curl "http://localhost:8000/api/diagnostics/data-portal?query=서울%20부동산%20가격"
```

`GET /api/diagnostics/data-portal`은 고정된 `https://www.data.go.kr/tcs/dss/selectDataSetList.do` 검색 URL만 짧은 timeout으로 호출하고, HTML 원문 대신 `status`, sanitized `search_url`, `http_status`, `elapsed_ms`, `candidate_count`, 첫 후보의 안전한 metadata, `reason_code`만 반환합니다. 임의 URL을 받아 fetch하지 않으므로 SSRF 진단 endpoint로 사용하면 안 됩니다.

대표 reason code는 다음과 같습니다.

- `DATA_PORTAL_TIMEOUT`: data.go.kr 검색 페이지 호출 timeout
- `DATA_PORTAL_HTTP_ERROR`: 403/5xx 등 HTTP 오류
- `DATA_PORTAL_NETWORK_ERROR`: DNS, proxy, 연결 차단 등 네트워크 오류
- `DATA_PORTAL_PARSE_EMPTY`: 응답은 받았지만 HTML 구조 변경 등으로 후보를 해석하지 못함

배포 환경에서 data.go.kr 접근이 실패하면 backend 배포 provider의 outbound 정책, proxy 설정, 방화벽/WAF, data.go.kr 측 제한 또는 HTML 구조 변경 가능성을 함께 확인해야 합니다. live diagnostics는 사용자가 `/api/diagnostics/data-portal`을 직접 호출하거나 대시보드 버튼을 누를 때만 외부 요청을 보냅니다.

실제 사이트 점검 순서:

1. 대시보드 **API 연결 상태**가 success인지 확인합니다.
2. 같은 패널의 **data.go.kr 연결 확인** 버튼을 클릭합니다.
3. diagnostics 결과의 후보 count와 첫 후보 제목을 확인합니다.
4. 공공데이터 검색, detail, resource preview, visualize 순서로 확인합니다.

### 프롬프트 기반 분석 UX 수동 검증 절차

이번 UX에서는 `/api/keywords`가 `GOOGLE_API_KEY` 미설정 또는 외부 AI 오류로 실패해도 화면 흐름을 멈추지 않고 deterministic fallback keyword로 계속 진행합니다. 예를 들어 `서울 부동산 가격`은 불용어와 긴 문장을 줄여 `서울 부동산 가격` 같은 검색어로 후보 검색, 목차, 코멘트에 사용됩니다.

1. `GOOGLE_API_KEY` 없이 backend와 frontend를 실행한 뒤 프롬프트 `서울 부동산 가격`을 입력합니다.
2. 키워드 영역에 “AI 키워드 추출은 실패했지만 입력 프롬프트 기반 검색으로 계속 진행합니다.”와 fallback keyword가 표시되는지 확인합니다.
3. fallback keyword로 공공데이터 후보 검색이 계속 진행되고, 분석 목차가 정적 문구가 아니라 프롬프트/키워드 기반으로 생성되는지 확인합니다.
4. `tests/fixtures/visualize_sample.csv` 같은 CSV를 직접 업로드해 시각화한 뒤 데이터 코멘트가 최대/최소값, chart_type, labels/table_data를 근거로 갱신되는지 확인합니다.
5. 추가 프롬프트 대화에 `지역별 차이를 비교해줘`를 입력하고 전송합니다.
6. 분석 목차와 데이터 코멘트에 “지역별 차이 비교” 관점이 반영되고, 추가 프롬프트 전송만으로 data.go.kr 검색이나 resource 다운로드가 자동 반복되지 않는지 확인합니다.
7. 공공데이터 후보를 선택한 뒤 상세/resource 영역에서 `미리보기`와 `이 리소스로 시각화` 안내가 보이는지 확인합니다. URL이 없거나 CSV/TSV/JSON이 아닌 형식은 미지원 안내가 표시되어야 합니다.
8. 로컬 파일 업로드는 “직접 파일 업로드 (대안 경로)”로 유지되며 기존 CSV/XLS/XLSX 시각화가 계속 동작하는지 확인합니다.

## Resource-first public data runbook

The dashboard is designed to keep 공공데이터포털 resources as the primary path and direct file upload as a fallback path:

1. Enter a natural-language prompt.
2. If `/api/keywords` cannot run because `GOOGLE_API_KEY` is not configured, the frontend uses a deterministic fallback keyword and continues to `/api/datasets/search`.
3. Select a public-data candidate, then wait for `/api/datasets/detail` to show metadata and resource cards.
4. Use `미리보기` first, then click `이 리소스로 시각화` only for the selected resource. Search/detail never auto-downloads resource URLs.
5. Use `직접 파일 업로드` only as an alternative path for local CSV/XLS/XLSX files or remote Excel files that are not auto-analyzed.

### Codespaces/API connection checks

- Backend: run on port `8000` (for example `python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000`).
- Frontend: serve on port `5173`.
- Set `ALLOWED_ORIGINS` to include the Codespaces frontend origin when testing across forwarded ports.
- In the browser console, check `localStorage.getItem("PUBLIC_DATA_API_BASE_URL")`; set it to the forwarded backend URL only when the default API base URL is wrong, and remove it to return to auto-detection.

### Manual resource-first verification checklist

In the browser Network tab, verify these endpoints complete and do not remain pending:

- `/api/keywords`
- `/api/datasets/search`
- `/api/datasets/detail`
- `/api/datasets/resource/preview`
- `/api/datasets/resource/visualize`
- `/api/visualize`

Also verify candidate cards avoid generic navigation titles such as `데이터찾기`, resource cards show preview/visualize support and unsupported reasons, preview shows table/JSON samples, and comments/outline change after additional prompts without automatically repeating search/detail/resource fetch.

### Smoke tests

Default smoke mode does not call `data.go.kr`; it checks local backend health, local visualization, and keyword fallback behavior. Live portal checks only run with the explicit opt-in flag:

```bash
python scripts/smoke_api_flow.py --base-url http://127.0.0.1:8000
python scripts/smoke_api_flow.py --base-url http://127.0.0.1:8000 --live-data-go-kr --query "서울 부동산 가격"
```

## 시연 직전 체크리스트

### Codespaces 실행

1. 백엔드: `python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000` 로 8000 포트를 실행합니다.
2. 프론트엔드: `cd public-data-dashboard && python -m http.server 5173` 또는 현재 정적 서버 방식으로 5173 포트를 실행합니다.
3. Codespaces **Ports** 탭에서 8000과 5173 포트를 모두 **Public**으로 설정합니다.
4. CORS가 막히면 백엔드 실행 전에 프론트 주소를 포함해 설정합니다. 예: `ALLOWED_ORIGINS=https://YOUR-5173-preview.app.github.dev,http://localhost:5173`.
5. 프론트가 잘못된 백엔드를 보고 있으면 브라우저 콘솔에서 확인/수정합니다.
   - 확인: `localStorage.getItem('PUBLIC_DATA_API_BASE_URL')`
   - 적용: `localStorage.setItem('PUBLIC_DATA_API_BASE_URL', 'https://YOUR-8000-preview.app.github.dev')` 후 새로고침
   - 초기화: `localStorage.removeItem('PUBLIC_DATA_API_BASE_URL')` 후 새로고침

### 브라우저 수동 확인 순서

1. 데모 로그인/회원가입 화면에서 계정을 만들고 로그인합니다.
2. 프롬프트 입력 화면에서 “서울 부동산 가격” 같은 자연어 프롬프트를 입력합니다.
3. 분석 목차 또는 검증 상태 패널에서 AI keyword 실패 시 fallback keyword가 표시되는지 확인합니다.
4. “API 연결 상태”에서 `/api/health`가 성공하는지 확인합니다.
5. “data.go.kr 연결 확인” 버튼을 눌러 live 진단 결과 또는 Codespaces/WAF 제한 안내를 확인합니다.
6. 공공데이터 후보 검색 결과가 표시되는지 확인합니다.
7. 후보 제목이 “데이터찾기/로그인/사이트맵” 같은 generic navigation 항목으로 채워지지 않는지 확인합니다.
8. 후보 하나를 선택합니다.
9. 선택한 데이터셋 상세 metadata와 resource 후보가 표시되는지 확인합니다.
10. resource 카드에서 preview 가능/제한, visualize 가능/제한, 미지원 사유를 확인합니다.
11. CSV/TSV/JSON resource의 “미리보기”를 눌러 표본 행과 bytes/content-type/source URL metadata를 확인합니다.
12. “이 리소스로 시각화”를 눌러 차트/표/metadata가 갱신되는지 확인합니다.
13. 추가 프롬프트에 “지역별 차이도 비교해줘” 같은 요청을 입력합니다.
14. 분석 목차와 데이터 코멘트가 추가 프롬프트 관점으로 갱신되는지 확인합니다.
15. 원격 Excel 또는 API key가 필요한 resource가 제한될 때 CSV/XLS/XLSX 직접 업로드 대안 경로를 확인합니다.
16. “검증 상태” 패널의 최근 endpoint 상태에서 오래 남은 pending/timeout 요청이 없는지 확인합니다.

### 문제 발생 시 빠른 진단

- `/api/health` 실패: 검증 상태 패널의 API base URL과 Codespaces 8000 포트 Public 여부를 먼저 봅니다. 백엔드가 실행 중인지 터미널 로그도 확인합니다.
- CORS 실패: 브라우저 콘솔의 CORS 메시지와 백엔드 `ALLOWED_ORIGINS` 값에 현재 5173 preview origin이 포함되어 있는지 확인합니다.
- data.go.kr diagnostic 실패: `reason_code`가 `DATA_PORTAL_NETWORK_ERROR` 또는 timeout이면 Codespaces outbound/WAF 제한일 수 있습니다. 앱 기본 기능 실패와 분리해서 판단합니다.
- keyword API 503: `GOOGLE_API_KEY` 미설정이면 예상 가능한 제한입니다. 화면에 fallback keyword가 표시되고 후보 검색이 계속 진행되는지 확인합니다.
- search 503: 검증 상태 패널과 백엔드 로그의 `reason_code`를 봅니다. 기본 smoke는 live data.go.kr를 호출하지 않으므로 live 연결 문제와 코드 문제를 분리합니다.
- detail 실패: 선택 후보의 URL이 `https://www.data.go.kr` 상세 URL인지 확인합니다. redirect 후 최종 URL도 data.go.kr가 아니면 차단됩니다.
- preview/visualize unsupported: resource 카드의 format과 `unsupported_reason`을 봅니다. CSV/TSV/JSON만 원격 자동 처리하고 Excel은 직접 업로드를 사용합니다.
- resource private host blocked: localhost/private IP/link-local/multicast/reserved/unspecified host는 SSRF 방어로 차단되는 것이 정상입니다.
- request timeout: 검증 상태 패널의 최근 endpoint 상태에서 timeout/오래 걸리는 요청을 확인하고, 백엔드 실행 상태와 외부 포털 연결 상태를 분리해 봅니다.

## 시연 모드 사용법

- 대시보드의 **오프라인 데모 → 데모 흐름으로 확인** 버튼은 실제 `data.go.kr` 호출이 아니라 frontend fixture 기반 시연 경로입니다.
- 화면과 리포트에는 “데모 데이터 기반”, “오프라인 데모”, “실제 data.go.kr 결과 아님” 문구가 표시됩니다.
- 다음 상황에서 사용하세요.
  - Codespaces outbound/WAF 또는 포털 상태로 live `data.go.kr` 후보 검색/진단이 실패할 때
  - 발표 중 네트워크가 불안정할 때
  - 후보 선택 → 상세/resource → preview → visualize → 리포트 요약 흐름을 빠르게 설명할 때
- demo mode는 기본값이 아니며 사용자가 버튼을 명시적으로 눌렀을 때만 현재 화면 상태를 fixture로 채웁니다.
- demo mode는 API key, secret, serviceKey를 요구하거나 저장하지 않습니다.

## 발표용 flow

1. 로그인/회원가입 demo로 로컬 계정 흐름을 보여줍니다.
2. 프롬프트 입력 화면에서 자연어 프롬프트를 입력합니다.
3. `GOOGLE_API_KEY`가 없어도 fallback keyword로 계속 진행되는지 확인합니다.
4. `data.go.kr 연결 확인` 버튼으로 live diagnostic이 opt-in임을 보여줍니다.
5. live 후보 검색이 가능하면 후보를 사용하고, 실패하면 **데모 흐름으로 확인**을 눌러 오프라인 fixture 경로임을 설명합니다.
6. dataset 후보를 선택해 상세 metadata와 resource 후보를 확인합니다.
7. resource preview로 일부 행과 content-type/bytes metadata를 확인합니다.
8. resource visualize 또는 직접 CSV/XLS/XLSX 업로드로 차트/표를 확인합니다.
9. **분석 리포트 요약** 패널에서 prompt/keyword/dataset/resource/preview/visualization/주의사항을 확인합니다.
10. 추천 후속 질문 chip을 클릭해 추가 프롬프트 입력창에 채우고, 추가 프롬프트는 현재 화면 상태 재해석이며 자동 재검색이 아님을 설명합니다.
11. **요약 복사**, **Markdown 다운로드**, **JSON 다운로드**로 제출/발표용 요약을 저장합니다.
12. validation panel의 최근 endpoint 상태에서 pending/timeout이 남지 않았는지 확인합니다.

## 최종 제출 체크리스트

- secret/API key/token이 repo에 없고 `.env`를 추가하지 않았는지 확인합니다.
- frontend에 API key 입력 UI가 없는지 확인합니다.
- `/api/health`가 live `data.go.kr` 호출을 하지 않는지 확인합니다.
- 기본 smoke/test가 live `data.go.kr`를 호출하지 않고, live smoke는 `--live-data-go-kr` opt-in일 때만 실행되는지 확인합니다.
- 배포/Codespaces에서는 `ALLOWED_ORIGINS`에 frontend origin을 포함합니다.
- Codespaces Ports 탭에서 backend/frontend port가 Public인지 확인합니다.
- localStorage API base URL override는 `PUBLIC_DATA_API_BASE_URL`만 사용하고, 잘못 설정했으면 제거 후 새로고침합니다.
- live `data.go.kr` 실패 시 오프라인 데모 경로로 전체 UX를 검증합니다.
- 원격 Excel 또는 API key/serviceKey 필요 resource는 직접 CSV/XLS/XLSX 업로드 대안 경로로 안내합니다.
