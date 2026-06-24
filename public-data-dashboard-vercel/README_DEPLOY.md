# public-data-dashboard Vercel 배포 안내

이 프로젝트는 React/Vite 프로젝트가 아니라 `index.html`에서 CSS/JS 파일을 직접 불러오는 정적 웹사이트입니다.
따라서 별도의 `npm install`, `npm run build` 없이 Vercel에 정적 사이트로 배포하면 됩니다.

## 폴더 구조

```txt
public-data-dashboard/
├─ index.html
├─ vercel.json
├─ styles/
│  └─ App.css
└─ src/
   ├─ App.js
   └─ components/
      ├─ Panel.js
      ├─ LoginPage.js
      ├─ PromptPage.js
      └─ DashboardPage.js
```

## 방법 1. GitHub + Vercel Dashboard

1. 이 폴더 전체를 GitHub 저장소에 업로드합니다.
2. Vercel에 로그인합니다.
3. Add New → Project를 선택합니다.
4. GitHub 저장소를 Import합니다.
5. Framework Preset은 `Other` 또는 자동 감지 상태로 둡니다.
6. Build Command는 비워둡니다.
7. Output Directory는 비워두거나 `.`로 설정합니다.
8. Deploy를 누릅니다.

## 방법 2. Vercel CLI

```bash
npm i -g vercel
cd public-data-dashboard
vercel --prod
```

처음 실행하면 계정/프로젝트 연결 질문이 나오며, 대부분 기본값으로 진행하면 됩니다.

## 주의사항

- 현재 로그인/회원가입 정보와 프롬포트 기록은 브라우저 `localStorage`에 저장됩니다.
- 서버 DB가 없기 때문에 다른 브라우저나 다른 기기에서는 같은 계정 정보가 공유되지 않습니다.
- 실제 서비스 수준의 로그인 기능으로 쓰려면 Supabase, Firebase, Vercel Postgres 같은 백엔드/DB 연동이 필요합니다.
