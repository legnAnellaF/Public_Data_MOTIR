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
    return selected.join(" ") || compact.slice(0, 40).trim();
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

  function deriveAnalysisOutline({ prompt, keyword, dataset, resource, visualization, additionalPrompt, additionalPrompts }) {
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
    items.push(visualization ? "시각화 결과의 주요 수치와 항목 비교" : "preview 또는 CSV 업로드 후 시각화 결과 확인");
    if (latest) {
      items.push(`추가 요청 반영: ${summarize(latest, 34)}`);
    }
    items.push("데이터 한계, 해석 주의점, 추가 질문 정리");
    return items.slice(0, 6);
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

  function deriveDataComment({ prompt, keyword, dataset, resource, visualization, insights, additionalPrompt, additionalPrompts }) {
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
      comments.push(`선택한 리소스는 ‘${titleOf(resource, "리소스 후보")}’입니다. CSV/TSV/JSON이면 preview 후 명시적으로 시각화할 수 있습니다.`);
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

  window.PublicDataDashboard.AnalysisHelpers = {
    deriveFallbackKeyword,
    deriveAnalysisOutline,
    deriveDataComment,
    getKeywordText,
  };
})();
