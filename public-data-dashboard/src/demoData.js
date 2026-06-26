(function () {
  window.PublicDataDashboard = window.PublicDataDashboard || {};

  const demoDataset = {
    id: "offline-demo-seoul-real-estate",
    title: "[오프라인 데모] 서울 지역별 부동산 가격 변화 예시",
    provider: "시연용 fixture (실제 data.go.kr 결과 아님)",
    format: "CSV",
    category: "데모 데이터",
    updated_at: "2026-06-26",
    description: "공공데이터포털 연결이 제한된 환경에서 resource-first 흐름을 설명하기 위한 오프라인 검증용 예시입니다.",
    url: "https://www.data.go.kr/demo/offline-fixture"
  };

  const demoResource = {
    name: "[오프라인 데모] 서울 부동산 가격 CSV fixture",
    format: "CSV",
    description: "강남·마포·노원·송파·관악의 예시 가격 지수를 담은 시연용 fixture입니다.",
    url: "https://demo.local/offline/seoul-real-estate.csv",
    is_downloadable: true,
    is_api: false,
    is_previewable: true,
    is_visualizable: true
  };

  const demoPreview = {
    preview: {
      kind: "table",
      headers: ["지역", "2022", "2023", "2024", "가격지수"],
      rows: [["강남", "100", "111", "124", "124"], ["마포", "100", "106", "115", "115"], ["노원", "100", "99", "103", "103"], ["송파", "100", "109", "121", "121"], ["관악", "100", "104", "110", "110"]],
      message: "오프라인 데모 fixture preview입니다. 실제 포털 응답이 아닙니다."
    },
    metadata: {
      content_type: "text/csv; charset=utf-8",
      bytes_read: 512,
      source_url: "https://demo.local/offline/seoul-real-estate.csv"
    }
  };

  const demoVisualization = {
    status: "success",
    chart_type: "bar",
    chart_title: "오프라인 데모: 서울 지역별 2024 가격지수 비교",
    strategy_reason: "지역 라벨과 가격지수 수치가 있어 막대그래프로 지역별 차이를 비교합니다.",
    labels: ["강남", "마포", "노원", "송파", "관악"],
    datasets: [{ label: "2024 가격지수", data: [124, 115, 103, 121, 110] }],
    table_data: {
      headers: ["지역", "2022", "2023", "2024", "가격지수"],
      rows: [["강남", "100", "111", "124", "124"], ["마포", "100", "106", "115", "115"], ["노원", "100", "99", "103", "103"], ["송파", "100", "109", "121", "121"], ["관악", "100", "104", "110", "110"]]
    },
    startup_precautions: ["데모 데이터 기반 관찰값이며 실제 공공데이터포털 결과가 아닙니다.", "원인 단정이 아니라 시연용 표본의 수치 비교입니다."]
  };

  window.PublicDataDashboard.DemoData = {
    prompt: "서울 부동산 가격 변화를 지역별로 비교하고 싶어",
    keyword: "서울 부동산 가격",
    searchResult: { query: "서울 부동산 가격", source: "offline-demo-fixture", items: [demoDataset, { ...demoDataset, id: "offline-demo-housing", title: "[오프라인 데모] 서울 주거 지표 예시", format: "JSON" }] },
    dataset: demoDataset,
    detailResult: { dataset: demoDataset, resources: [demoResource, { ...demoResource, name: "[오프라인 데모] 원격 Excel 제한 예시", format: "XLSX", url: "https://demo.local/offline/seoul-real-estate.xlsx", is_previewable: false, is_visualizable: false, unsupported_reason: "원격 Excel은 직접 파일 업로드 경로를 사용하세요." }] },
    resource: demoResource,
    preview: demoPreview,
    visualization: demoVisualization
  };
})();
