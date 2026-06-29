(function () {
  window.PublicDataDashboard = window.PublicDataDashboard || {};

  function safeText(value, fallback) {
    const text = String(value == null ? "" : value).replace(/\s+/g, " ").trim();
    return text || fallback || "";
  }

  function maskUrl(value) {
    const text = safeText(value, "");
    if (!text) return "설정 없음";
    try {
      const url = new URL(text);
      return `${url.origin}${url.pathname}`.replace(/\/+$/, "") || url.origin;
    } catch (error) {
      return text.split("?")[0].replace(/(serviceKey|apiKey|token|secret)=([^&]+)/gi, "$1=REDACTED");
    }
  }

  function mark(status) {
    if (status === "success") return "✅";
    if (status === "warning") return "⚠️";
    if (status === "error") return "❌";
    if (status === "loading" || status === "pending" || status === "checking") return "⏳";
    return "○";
  }

  function statusItem(label, status, details) {
    return { label, status, icon: mark(status), details: safeText(details, "") };
  }

  function keywordSummary(state) {
    if (state.isKeywordLoading) return statusItem("keyword", "loading", "AI keyword 추출 중");
    if (state.keywordError) return statusItem("keyword", "warning", `${state.keywordError} · fallback keyword: ${state.keywordFallback || "생성 중"}`);
    const result = state.keywordResult || {};
    const keyword = result.topic || (Array.isArray(result.keywords) ? result.keywords.join(" ") : "") || state.keywordFallback;
    if (keyword && state.keywordFallback) return statusItem("keyword", "warning", `fallback keyword 사용 중: ${keyword}`);
    if (keyword) return statusItem("keyword", "success", `AI keyword success: ${keyword}`);
    return statusItem("keyword", "idle", "미실행");
  }

  function buildValidationSummary(state) {
    const s = state || {};
    const items = [];
    items.push(statusItem("API base URL", s.apiBaseUrl ? "success" : "warning", `${maskUrl(s.apiBaseUrl)} (${s.apiBaseUrlSource || "unknown"})`));
    items.push(statusItem("/api/health", s.apiHealth && s.apiHealth.status === "success" ? "success" : s.apiHealth && s.apiHealth.status === "error" ? "error" : s.apiHealth && s.apiHealth.status === "checking" ? "loading" : "idle", s.apiHealth && s.apiHealth.message));
    items.push(statusItem("data.go.kr diagnostics", s.dataPortalDiagnostic && s.dataPortalDiagnostic.status === "success" ? "success" : s.dataPortalDiagnostic && s.dataPortalDiagnostic.status === "error" ? "warning" : s.dataPortalDiagnostic && s.dataPortalDiagnostic.status === "checking" ? "loading" : "idle", s.dataPortalDiagnostic && s.dataPortalDiagnostic.message));
    items.push(keywordSummary(s));

    const candidates = s.datasetSearchResult && Array.isArray(s.datasetSearchResult.items) ? s.datasetSearchResult.items : [];
    const isFallbackSearch = !!(s.datasetSearchResult && (s.datasetSearchResult.is_offline_fallback || s.datasetSearchResult.source === "offline_fallback"));
    const fallbackSuffix = isFallbackSearch ? ` · offline fallback candidates${s.datasetSearchResult.reason_code ? ` (${s.datasetSearchResult.reason_code})` : ""}` : "";
    items.push(statusItem("dataset search", s.isDatasetSearchLoading ? "loading" : s.datasetSearchError ? "error" : s.datasetSearchResult ? "success" : "idle", s.isDatasetSearchLoading ? "loading" : s.datasetSearchError || `candidate count: ${candidates.length}${fallbackSuffix}${candidates[0] ? ` · 첫 후보: ${candidates[0].title || "제목 없음"}` : ""}`));
    items.push(statusItem("selected dataset", s.selectedDataset ? "success" : "idle", s.selectedDataset ? `${s.selectedDataset.title || "제목 없음"} · ${s.selectedDataset.provider || "provider 미상"} · ${s.selectedDataset.format || "format 미상"}` : "not selected"));
    const resources = s.datasetDetailResult && Array.isArray(s.datasetDetailResult.resources) ? s.datasetDetailResult.resources : [];
    items.push(statusItem("dataset detail", s.isDatasetDetailLoading ? "loading" : s.datasetDetailError ? "error" : s.datasetDetailResult ? "success" : "idle", s.datasetDetailError || `resource count: ${resources.length}`));

    const support = window.PublicDataDashboard.AnalysisHelpers && window.PublicDataDashboard.AnalysisHelpers.getResourceSupportState ? window.PublicDataDashboard.AnalysisHelpers.getResourceSupportState(s.selectedResource) : { isPreviewable: false, isVisualizable: false, unsupportedReason: "" };
    items.push(statusItem("selected resource", s.selectedResource ? (support.isPreviewable || support.isVisualizable ? "success" : "warning") : "idle", s.selectedResource ? `${s.selectedResource.format || "format 미상"} · preview ${support.isPreviewable ? "가능" : "제한"} · visualize ${support.isVisualizable ? "가능" : "제한"}${support.unsupportedReason ? ` · ${support.unsupportedReason}` : ""}` : "not selected"));

    const preview = s.resourcePreviewResult && s.resourcePreviewResult.preview;
    const meta = s.resourcePreviewResult && s.resourcePreviewResult.metadata ? s.resourcePreviewResult.metadata : {};
    const rows = preview && Array.isArray(preview.rows) ? preview.rows.length : 0;
    items.push(statusItem("resource preview", s.isResourcePreviewLoading ? "loading" : s.resourcePreviewError ? "error" : preview ? "success" : "idle", s.resourcePreviewError || (preview ? `${preview.kind || "unknown"} · rows ${rows} · bytes ${meta.bytes_read || 0} · ${meta.content_type || "content-type 미상"} · ${maskUrl(meta.source_url)}` : "미실행")));

    const v = s.visualizationResult || {};
    const table = v.table_data || {};
    const vMeta = v.metadata || {};
    items.push(statusItem("visualization", s.isVisualizationLoading || s.isResourceVisualizationLoading ? "loading" : s.visualizationError || s.resourceVisualizationError ? "error" : s.visualizationResult ? "success" : "idle", s.visualizationError || s.resourceVisualizationError || (s.visualizationResult ? `${vMeta.source_url ? "resource result" : "local upload result"} · chart ${v.chart_type || "미정"} · labels ${(v.labels || []).length} · datasets ${(v.datasets || []).length} · table rows ${(table.rows || []).length}` : "미실행")));

    const prompts = Array.isArray(s.additionalPrompts) ? s.additionalPrompts : [];
    items.push(statusItem("additional prompt", prompts.length ? "success" : "idle", `count: ${prompts.length}${prompts.length ? ` · latest: ${prompts[prompts.length - 1]}` : ""}`));
    return items;
  }

  function summarizeRequestHistory(history, now) {
    const current = now || Date.now();
    return (Array.isArray(history) ? history : []).slice(-10).map((item) => {
      const elapsed = item.elapsed_ms != null ? item.elapsed_ms : Math.max(0, current - (item.started_at_ms || current));
      const status = item.status === "pending" && elapsed > 10000 ? "long-pending" : item.status;
      return { ...item, status, elapsed_ms: elapsed, endpoint: maskUrl(item.endpoint || item.path || "") };
    });
  }

  window.PublicDataDashboard.ValidationHelpers = { buildValidationSummary, summarizeRequestHistory, maskUrl, mark };
})();
