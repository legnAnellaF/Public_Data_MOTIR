(function () {
  window.PublicDataDashboard = window.PublicDataDashboard || {};

  const STOP_WORDS = new Set([
    "관련", "대한", "대해", "으로", "에서", "에게", "하고", "그리고", "하지만", "또는", "있는", "없는",
    "보여줘", "알려줘", "분석", "비교", "확인", "해주세요", "해줘", "데이터", "공공데이터", "현황"
  ]);

  function compactText(value) {
    return String(value || "").replace(/[^0-9A-Za-z가-힣\s]/g, " ").replace(/\s+/g, " ").trim();
  }

  function deriveFallbackKeyword(prompt) {
    const compact = compactText(prompt);
    if (!compact) {
      return "";
    }
    const tokens = compact.split(" ").map((token) => token.trim()).filter(Boolean);
    const meaningful = tokens.filter((token) => token.length > 1 && !STOP_WORDS.has(token));
    const selected = (meaningful.length ? meaningful : tokens).slice(0, 5);
    const base = selected.join(" ") || compact.slice(0, 40).trim();
    if (/(^|\s)집값($|\s)/.test(compact) || compact.includes("집값")) {
      const additions = ["부동산", "실거래가", "아파트", "전월세", "주택 가격"].filter((term) => !base.includes(term));
      return `${base} ${additions.slice(0, 2).join(" ")}`.trim();
    }
    return base;
  }

  function getKeywordText(keywordResult, fallbackKeyword, prompt) {
    if (keywordResult && typeof keywordResult === "object") {
      if (typeof keywordResult.topic === "string" && keywordResult.topic.trim()) {
        return keywordResult.topic.trim();
      }
      if (Array.isArray(keywordResult.keywords)) {
        const text = keywordResult.keywords.filter(Boolean).join(" ").trim();
        if (text) {
          return text;
        }
      }
    }
    return fallbackKeyword || deriveFallbackKeyword(prompt);
  }

  function titleOf(item, fallback) {
    const source = item && typeof item === "object" ? item : {};
    return source.title || source.name || fallback;
  }

  function latestAdditional(additionalPrompt, additionalPrompts) {
    const fromInput = String(additionalPrompt || "").trim();
    if (fromInput) {
      return fromInput;
    }
    const list = Array.isArray(additionalPrompts) ? additionalPrompts : [];
    return list.length ? String(list[list.length - 1] || "").trim() : "";
  }

  function summarizeResourcePreview(previewResult) {
    const result = previewResult && typeof previewResult === "object" ? previewResult : {};
    const preview = result.preview && typeof result.preview === "object" ? result.preview : null;
    const meta = result.metadata && typeof result.metadata === "object" ? result.metadata : {};
    if (!preview) {
      return "";
    }
    if (preview.kind === "table") {
      const rowCount = Array.isArray(preview.rows) ? preview.rows.length : 0;
      const colCount = Array.isArray(preview.headers) ? preview.headers.length : 0;
      return `preview 표 ${rowCount}행 ${colCount}열 · ${meta.content_type || "content-type 미상"} · ${meta.bytes_read || 0} bytes`;
    }
    return `preview ${preview.kind || "데이터"} · ${meta.content_type || "content-type 미상"} · ${meta.bytes_read || 0} bytes`;
  }

  function summarizeVisualizationMetadata(visualization) {
    const source = visualization && typeof visualization === "object" ? visualization : {};
    const meta = source.metadata && typeof source.metadata === "object" ? source.metadata : {};
    const parts = [];
    if (meta.source_url) parts.push("source URL 확인됨");
    if (meta.resource_format) parts.push(`형식 ${meta.resource_format}`);
    if (meta.content_type) parts.push(`content-type ${meta.content_type}`);
    if (meta.bytes_read) parts.push(`${meta.bytes_read} bytes 분석`);
    return parts.join(" · ");
  }

  function getResourceSupportState(resource) {
    const item = resource && typeof resource === "object" ? resource : {};
    const format = String(item.format || "").toUpperCase();
    const urlText = String(item.url || "");
    const url = urlText.toLowerCase().split("?")[0];
    const isPortalPage = /https?:\/\/(www\.)?data\.go\.kr\//i.test(urlText) && (/\/(data|catalog|tcs\/dss|ugs|bbs|cmm)\//i.test(urlText) || url.endsWith(".do"));
    const explicitlyBlocked = item.is_previewable === false || item.is_visualizable === false || Boolean(item.unsupported_reason) || Boolean(item.reason_code);
    const inferredSupported = Boolean(item.url) && !isPortalPage && (format.includes("CSV") || format.includes("TSV") || format.includes("JSON") || url.endsWith(".csv") || url.endsWith(".tsv") || url.endsWith(".json"));
    const previewable = item.is_previewable === true || (!explicitlyBlocked && inferredSupported);
    const visualizable = item.is_visualizable === true || (!explicitlyBlocked && inferredSupported);
    return {
      isPreviewable: Boolean(previewable),
      isVisualizable: Boolean(visualizable),
      unsupportedReason: item.unsupported_reason || (isPortalPage ? "공공데이터포털 상세/목록 페이지는 직접 미리보기할 수 없습니다. 실제 파일/API 리소스를 선택하세요." : (inferredSupported ? "" : "CSV/TSV/JSON 리소스만 자동 지원합니다.")),
      reasonCode: item.reason_code || (isPortalPage ? "RESOURCE_UNSUPPORTED_PORTAL_PAGE" : ""),
    };
  }

  function deriveAnalysisOutline({ prompt, keyword, dataset, resource, resourcePreview, visualization, additionalPrompt, additionalPrompts }) {
    const focus = keyword || deriveFallbackKeyword(prompt) || "입력 프롬프트";
    const latest = latestAdditional(additionalPrompt, additionalPrompts);
    const items = [`${focus} 관련 공공데이터 후보 탐색`];
    if (dataset) {
      items.push(`선택 데이터셋 ‘${titleOf(dataset, "제목 없는 데이터셋")}’ metadata와 제공기관 확인`);
    } else {
      items.push("공공데이터 후보 선택 후 상세/resource 확인");
    }
    if (resource) {
      items.push(`선택 리소스 ‘${titleOf(resource, "리소스 후보")}’ 미리보기 및 지원 형식 확인`);
    }
    const previewSummary = summarizeResourcePreview(resourcePreview);
    if (previewSummary) {
      items.push(`리소스 ${previewSummary} 기반 컬럼/표본 확인`);
    }
    items.push(visualization ? "시각화 결과의 주요 수치와 항목 비교" : "preview 또는 CSV 업로드 후 시각화 결과 확인");
    if (latest) {
      items.push(`추가 요청 반영: ${summarize(latest, 34)}`);
    }
    items.push("데이터 한계, 해석 주의점, 추가 질문 정리");
    return items.slice(0, 6);
  }

  const SENSITIVE_QUERY_KEYS = new Set(["servicekey", "apikey", "api_key", "secret", "token", "authkey", "access_token", "refresh_token"]);

  function sanitizeUrl(value) {
    const text = String(value || "").trim();
    if (!text) return "";
    try {
      const url = new URL(text);
      Array.from(url.searchParams.keys()).forEach((key) => {
        if (SENSITIVE_QUERY_KEYS.has(String(key).toLowerCase())) {
          url.searchParams.set(key, "[REDACTED]");
        }
      });
      return url.toString().replace(/%5BREDACTED%5D/gi, "[REDACTED]");
    } catch (error) {
      return text.replace(/([?&](?:serviceKey|apiKey|api_key|secret|token|authKey|access_token|refresh_token)=)[^&\s]+/gi, "$1[REDACTED]");
    }
  }

  function summarize(value, maxLength) {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
  }

  function extractVisualizationStats(visualization) {
    const source = visualization && typeof visualization === "object" ? visualization : {};
    const labels = Array.isArray(source.labels) ? source.labels : [];
    const firstDataset = Array.isArray(source.datasets) ? source.datasets[0] : null;
    const data = firstDataset && Array.isArray(firstDataset.data) ? firstDataset.data : [];
    const pairs = data.map((value, index) => ({ label: labels[index] || `항목 ${index + 1}`, value: Number(value) }))
      .filter((item) => Number.isFinite(item.value));
    if (!pairs.length) {
      return null;
    }
    const max = pairs.reduce((best, item) => (item.value > best.value ? item : best), pairs[0]);
    const min = pairs.reduce((best, item) => (item.value < best.value ? item : best), pairs[0]);
    return { max, min, count: pairs.length, datasetLabel: firstDataset.label || "데이터셋" };
  }

  function deriveDataComment({ prompt, keyword, dataset, resource, resourcePreview, visualization, insights, additionalPrompt, additionalPrompts }) {
    const focus = keyword || deriveFallbackKeyword(prompt) || summarize(prompt, 30) || "입력 프롬프트";
    const latest = latestAdditional(additionalPrompt, additionalPrompts);
    const comments = [`현재 분석은 ‘${focus}’ 키워드와 최초 프롬프트를 기준으로 구성했습니다.`];
    if (latest) {
      comments.push(`현재 요청은 ‘${latest}’ 관점을 반영해 기존 화면 상태를 재해석하는 데 초점을 둡니다.`);
      comments.push("이 질문으로 새 공공데이터 검색을 하려면 후보 검색 버튼을 눌러주세요.");
    }
    if (dataset) {
      comments.push(`선택한 데이터셋은 ‘${titleOf(dataset, "제목 없는 데이터셋")}’이며, provider/format/resource 정보를 먼저 확인하는 흐름입니다.`);
    }
    if (resource) {
      const support = getResourceSupportState(resource);
      comments.push(`선택한 리소스는 ‘${titleOf(resource, "리소스 후보")}’입니다. 자동 미리보기 ${support.isPreviewable ? "가능" : "제한"}, 자동 시각화 ${support.isVisualizable ? "가능" : "제한"} 상태입니다.`);
      if (support.unsupportedReason) comments.push(`미지원/주의 사유: ${support.unsupportedReason}`);
    }
    const previewSummary = summarizeResourcePreview(resourcePreview);
    if (previewSummary) {
      comments.push(`최근 리소스 미리보기 metadata: ${previewSummary}. 이 표본을 기준으로 컬럼 구조와 결측 가능성을 먼저 확인하세요.`);
    }
    const visualizationMeta = summarizeVisualizationMetadata(visualization);
    if (visualizationMeta) {
      comments.push(`시각화 입력 metadata: ${visualizationMeta}.`);
    }
    const stats = extractVisualizationStats(visualization);
    if (stats) {
      comments.push(`${stats.datasetLabel} 기준 ${stats.count}개 항목 중 최대값은 ${stats.max.label}(${stats.max.value}), 최소값은 ${stats.min.label}(${stats.min.value})입니다.`);
      comments.push(`차트 유형은 ${visualization.chart_type || "미정"}이며, 이 차이는 원인 단정이 아니라 현재 표본의 관찰값으로만 해석해야 합니다.`);
    } else {
      comments.push("아직 시각화된 데이터가 없어 프롬프트 기준의 분석 방향만 제안합니다.");
    }
    if (Array.isArray(insights) && insights.length) {
      comments.push(`기존 insights: ${insights.slice(0, 2).join(" / ")}`);
    }
    return comments;
  }

  function buildVisualizationSummary(visualization) {
    const source = visualization && typeof visualization === "object" ? visualization : {};
    const table = source.table_data && typeof source.table_data === "object" ? source.table_data : {};
    const stats = extractVisualizationStats(source);
    return {
      chart_type: source.chart_type || "미정",
      labels_count: Array.isArray(source.labels) ? source.labels.length : 0,
      datasets_count: Array.isArray(source.datasets) ? source.datasets.length : 0,
      table_rows_count: Array.isArray(table.rows) ? table.rows.length : 0,
      max: stats && stats.max,
      min: stats && stats.min,
    };
  }

  function deriveFollowUpQuestions({ prompt, keyword, dataset, resource, resourcePreview, visualization, additionalPrompt, additionalPrompts }) {
    const text = [prompt, keyword, latestAdditional(additionalPrompt, additionalPrompts), dataset && dataset.title, resource && resource.name].filter(Boolean).join(" ");
    const preview = resourcePreview && resourcePreview.preview;
    const headers = preview && Array.isArray(preview.headers) ? preview.headers.join(" ") : "";
    const support = resource ? getResourceSupportState(resource) : null;
    const questions = [];
    function add(q) { if (q && !questions.includes(q) && questions.length < 5) questions.push(q); }
    if (/지역|시군구|구별|동별|서울|부산|경기/.test(`${text} ${headers}`)) {
      add("지역별 상위/하위 차이가 큰 이유를 추가로 확인할까요?");
      add("연도별 변화 추세를 지역별로 비교할까요?");
    }
    if (/연도|년도|년|월|일|date|time|기준/.test(`${text} ${headers}`)) add("최근 연도 기준으로 증가/감소 추세를 볼까요?");
    if (dataset && (dataset.provider || dataset.title)) add("같은 제공기관의 다른 관련 데이터도 찾아볼까요?");
    if (visualization) {
      add("최대값과 최소값 항목을 중심으로 비교할까요?");
      add("이상치로 보이는 항목을 확인할까요?");
    } else if (preview) {
      add("이 리소스를 시각화해볼까요?");
    }
    if (support && (!support.isPreviewable || !support.isVisualizable)) add("직접 파일 업로드 경로로 분석해볼까요?");
    add("현재 결과의 해석 주의사항을 발표용 문장으로 정리할까요?");
    add("추가로 필요한 컬럼이나 결측 가능성을 확인할까요?");
    return questions.slice(0, 5);
  }

  function buildReportSummaryMarkdown(context) {
    const c = context && typeof context === "object" ? context : {};
    const dataset = c.dataset || {};
    const resource = c.resource || {};
    const previewSummary = summarizeResourcePreview(c.resourcePreview) || "preview 없음";
    const viz = buildVisualizationSummary(c.visualization);
    const comments = deriveDataComment(c).slice(0, 3);
    const followUps = c.followUpQuestions || deriveFollowUpQuestions(c);
    const mode = c.isDemoMode ? "데모 데이터 기반(오프라인 fixture, 실제 data.go.kr 결과 아님)" : "실제/사용자 선택 흐름";
    return [
      `# 공공데이터 분석 리포트 요약`,
      ``,
      `- 모드: ${mode}`,
      `- 최초 프롬프트: ${c.prompt || "-"}`,
      `- 사용 키워드: ${c.keyword || deriveFallbackKeyword(c.prompt) || "-"}`,
      `- 선택 데이터셋: ${titleOf(dataset, "-")} / 제공기관: ${dataset.provider || "-"} / 형식: ${dataset.format || "-"}`,
      `- 선택 리소스: ${titleOf(resource, "-")} / 형식: ${resource.format || "-"} / URL: ${sanitizeUrl(resource.url || "") || "-"}`,
      `- Preview summary: ${previewSummary}`,
      `- Visualization summary: chart_type=${viz.chart_type}, labels=${viz.labels_count}, datasets=${viz.datasets_count}, table_rows=${viz.table_rows_count}${viz.max ? `, max=${viz.max.label}(${viz.max.value}), min=${viz.min.label}(${viz.min.value})` : ""}`,
      ``,
      `## 데이터 코멘트 요약`,
      ...comments.map((item) => `- ${item}`),
      ``,
      `## 후속 질문 추천`,
      ...followUps.map((item) => `- ${item}`),
      ``,
      `## 주의사항`,
      `- live data.go.kr 연결은 Codespaces outbound/WAF/포털 상태에 영향을 받을 수 있습니다.`,
      `- API key/serviceKey가 필요한 resource는 자동 preview/visualize가 제한될 수 있습니다.`,
      `- 원격 Excel은 직접 CSV/XLS/XLSX 업로드 경로를 사용하세요.`,
      `- preview는 일부 행만 표시합니다.`,
      `- 원인 단정이 아니라 현재 데이터의 관찰값입니다.`,
    ].join("\n");
  }

  function buildReportSummaryJson(context) {
    const c = context && typeof context === "object" ? context : {};
    const dataset = c.dataset || {};
    const resource = c.resource || {};
    return {
      mode: c.isDemoMode ? "offline-demo-fixture" : "standard-flow",
      prompt: c.prompt || "",
      keyword: c.keyword || deriveFallbackKeyword(c.prompt),
      dataset: { title: dataset.title || "", provider: dataset.provider || "", format: dataset.format || "" },
      resource: { name: resource.name || resource.title || "", format: resource.format || "", source_url: sanitizeUrl(resource.url || "") },
      preview_summary: summarizeResourcePreview(c.resourcePreview),
      visualization_summary: buildVisualizationSummary(c.visualization),
      data_comment_summary: deriveDataComment(c).slice(0, 3),
      follow_up_questions: c.followUpQuestions || deriveFollowUpQuestions(c),
      cautions: ["live data.go.kr 연결 상태는 외부 네트워크/WAF 영향을 받을 수 있음", "API key/serviceKey resource 제한", "remote Excel은 직접 업로드 권장", "preview는 일부 행", "현재 데이터 관찰값"]
    };
  }

  window.PublicDataDashboard.AnalysisHelpers = {
    deriveFallbackKeyword,
    deriveAnalysisOutline,
    deriveDataComment,
    summarizeResourcePreview,
    summarizeVisualizationMetadata,
    getResourceSupportState,
    getKeywordText,
    sanitizeUrl,
    buildVisualizationSummary,
    deriveFollowUpQuestions,
    buildReportSummaryMarkdown,
    buildReportSummaryJson,
  };
})();
