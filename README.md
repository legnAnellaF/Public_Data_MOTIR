# Public Data MOTIR

공공데이터 기반 키워드 추출, 데이터 시각화, 프론트엔드 대시보드 초안을 한 저장소에서 관리하기 위한 프로젝트입니다.

## 변경된 구조 초안

```text
.
├── backend/
│   ├── __init__.py
│   ├── data_visualizer.py        # CSV/Excel 데이터를 분석해 차트용 구조화 데이터 생성
│   ├── keyword_extractor.py      # 사용자 문장에서 공공데이터 검색 키워드 추출
│   └── requirements.txt          # 백엔드/분석 모듈 의존성
├── public-data-dashboard/
│   ├── index.html
│   ├── vercel.json
│   ├── src/
│   │   ├── App.js
│   │   └── components/
│   └── styles/
│       └── App.css
├── .gitignore
└── README.md
```

## 정리 방향

- 프론트엔드는 `public-data-dashboard/` 하나만 유지합니다.
- 기존 `public-data-dashboard`와 `public-data-dashboard-vercel`처럼 역할이 겹치는 구조는 하나의 최종 프론트엔드 폴더로 통일하는 방향으로 정리합니다.
- 기존 `public-data-keyword` 스크립트는 `backend/keyword_extractor.py`로 옮겨 import 가능한 Python 모듈로 정리했습니다.
- 기존 루트의 `data_visualizer.py`는 `backend/data_visualizer.py`로 옮겨 import 가능한 Python 모듈로 정리했습니다.
- 이번 단계에서는 실제 프론트엔드-백엔드 API 연결을 추가하지 않습니다. 폴더 구조 정리와 모듈화까지만 포함합니다.

## 로컬 실행 방법 초안

### 1. 프론트엔드 대시보드 실행

정적 HTML/CSS/JavaScript로 구성되어 있으므로 별도 빌드 없이 로컬 서버로 확인할 수 있습니다.

```bash
cd public-data-dashboard
python -m http.server 5173
```

브라우저에서 `http://localhost:5173`에 접속합니다.

> 현재 회원가입/로그인은 `localStorage`를 사용하는 데모용 구현입니다. 사용자 정보와 비밀번호가 브라우저 `localStorage`에 저장되므로 실제 인증이나 보안 기능이 아니며, 운영 환경에서는 반드시 Supabase, Firebase, 자체 백엔드 인증 API 등 안전한 인증/세션 관리로 대체해야 합니다.

### 2. Vercel 배포 초안

Vercel에서 프로젝트를 연결할 때 **Root Directory**를 `public-data-dashboard`로 설정합니다. 최종 프론트엔드 폴더는 `public-data-dashboard/` 하나만 사용하며, 별도의 `public-data-dashboard-vercel/` 폴더는 만들지 않습니다.

`public-data-dashboard/vercel.json`에는 정적 프론트엔드 배포를 위한 최소 설정으로 `cleanUrls`를 켭니다.

### 3. 백엔드 모듈 의존성 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### 4. 키워드 추출 모듈 실행

`GOOGLE_API_KEY`는 저장소에 커밋하지 말고 로컬 환경 변수 또는 커밋되지 않는 `.env` 파일로만 설정합니다.

```bash
export GOOGLE_API_KEY="your-local-api-key"
python -m backend.keyword_extractor
```

### 5. 데이터 시각화 모듈 사용 예시

```python
from backend.data_visualizer import IntelligentVisualizerEngine

visualizer = IntelligentVisualizerEngine()
result = visualizer.process("sample.csv", query="카페 창업 상권 분석")
```

## 남은 작업

- 프론트엔드에서 백엔드 API를 호출하는 연동 계층 설계
- 실제 인증 방식 도입 및 localStorage 데모 회원가입/로그인 제거
- 백엔드 API 연결 미완성: FastAPI 앱, `/api/keywords`, `/api/visualize` 등 API skeleton 추가
- 키워드 추출/시각화 API 라우터 추가
- 샘플 데이터와 자동 테스트 추가
- 배포 환경별 설정 문서 보강

## 보안 주의

- API 키, `.env`, 개인 설정 파일은 커밋하지 않습니다.
- `.gitignore`에 `.env`, `.env.*`, 가상환경, 빌드 산출물, Vercel 로컬 설정을 제외하도록 추가했습니다.
