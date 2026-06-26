(function () {
  window.PublicDataDashboard = window.PublicDataDashboard || {};

  const DEFAULT_API_BASE_URL = "http://localhost:8000";
  const API_BASE_URL_OVERRIDE_KEY = "PUBLIC_DATA_API_BASE_URL";
  const DEFAULT_REQUEST_TIMEOUT_MS = 30000;
  const requestHistory = [];
  let nextRequestId = 1;

  function sanitizeEndpoint(path) {
    const text = String(path || "");
    try {
      const url = new URL(text, getApiBaseUrl());
      const sensitive = new Set(["key", "apikey", "api_key", "servicekey", "service_key", "token", "secret", "password"]);
      url.searchParams.forEach((value, key) => {
        if (sensitive.has(key.toLowerCase())) url.searchParams.set(key, "REDACTED");
      });
      return `${url.pathname}${url.search}`;
    } catch (error) {
      return text.split("?")[0];
    }
  }

  function rememberRequest(entry) {
    requestHistory.push(entry);
    while (requestHistory.length > 10) requestHistory.shift();
    return entry;
  }

  function getRequestHistory() {
    return requestHistory.map((item) => ({ ...item }));
  }

  function updateRequest(entry, patch) {
    Object.assign(entry, patch);
    return entry;
  }

  function normalizeApiBaseUrl(value) {
    const text = typeof value === "string" ? value.trim() : "";
    return text ? text.replace(/\/+$/, "") : "";
  }

  function getApiBaseUrl() {
    const windowOverride = normalizeApiBaseUrl(window.PUBLIC_DATA_API_BASE_URL);
    const storageOverride = normalizeApiBaseUrl(readStorageOverride());
    const baseUrl = windowOverride || storageOverride || DEFAULT_API_BASE_URL;

    return normalizeApiBaseUrl(baseUrl);
  }

  function getApiBaseUrlSource() {
    if (normalizeApiBaseUrl(window.PUBLIC_DATA_API_BASE_URL)) {
      return "window.PUBLIC_DATA_API_BASE_URL";
    }

    if (normalizeApiBaseUrl(readStorageOverride())) {
      return "localStorage.PUBLIC_DATA_API_BASE_URL";
    }

    return "default";
  }

  function setStoredApiBaseUrl(value) {
    const normalized = normalizeApiBaseUrl(value);
    try {
      if (normalized) {
        localStorage.setItem(API_BASE_URL_OVERRIDE_KEY, normalized);
      } else {
        localStorage.removeItem(API_BASE_URL_OVERRIDE_KEY);
      }
    } catch (error) {
      throw new Error("브라우저 저장소에 API base URL을 저장할 수 없습니다.");
    }
    console.info(`[PublicDataDashboard] API base URL set to: ${getApiBaseUrl()}`);
    return getApiBaseUrl();
  }

  function readStorageOverride() {
    try {
      const storedValue = localStorage.getItem(API_BASE_URL_OVERRIDE_KEY);
      return typeof storedValue === "string" ? storedValue.trim() : "";
    } catch (error) {
      return "";
    }
  }

  function toUserMessage(error, fallbackMessage) {
    if (!error) {
      return fallbackMessage;
    }

    if (typeof error === "string") {
      return error;
    }

    if (error.message) {
      return error.message;
    }

    return fallbackMessage;
  }

  function normalizeApiErrorPayload(payload, fallbackMessage) {
    if (!payload || typeof payload !== "object") {
      return fallbackMessage;
    }

    const detail = payload.detail;

    if (typeof detail === "string") {
      return detail;
    }

    if (detail && typeof detail === "object") {
      return detail.message || detail.detail || fallbackMessage;
    }

    return payload.message || fallbackMessage;
  }

  async function readJsonResponse(response, fallbackMessage) {
    const text = await response.text();

    if (!text) {
      return null;
    }

    try {
      return JSON.parse(text);
    } catch (error) {
      const apiError = new Error(fallbackMessage || "API 응답을 해석하지 못했습니다.");
      apiError.cause = error;
      throw apiError;
    }
  }

  async function requestJson(path, options) {
    const requestOptions = options || {};
    const fallbackMessage = requestOptions.fallbackMessage
      ? requestOptions.fallbackMessage
      : "API 요청 처리 중 오류가 발생했습니다.";
    const timeoutMs = Number(requestOptions.timeoutMs || DEFAULT_REQUEST_TIMEOUT_MS);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    const fetchOptions = { ...requestOptions, signal: controller.signal };
    delete fetchOptions.fallbackMessage;
    delete fetchOptions.timeoutMs;

    let response;
    const startedAtMs = Date.now();
    const historyEntry = rememberRequest({
      id: nextRequestId++,
      endpoint: sanitizeEndpoint(path),
      method: fetchOptions.method || "GET",
      status: "pending",
      started_at: new Date(startedAtMs).toISOString(),
      started_at_ms: startedAtMs,
      elapsed_ms: null,
      http_status: null,
      message: "요청 진행 중",
    });

    try {
      response = await fetch(`${getApiBaseUrl()}${path}`, fetchOptions);
      updateRequest(historyEntry, { http_status: response.status });
    } catch (error) {
      const elapsed = Date.now() - startedAtMs;
      if (error && error.name === "AbortError") {
        updateRequest(historyEntry, { status: "timeout", elapsed_ms: elapsed, message: "요청 시간이 초과되었습니다." });
        throw new Error("요청 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.");
      }
      const baseUrl = getApiBaseUrl();
      const message = `백엔드 API에 연결할 수 없습니다. API base URL과 배포 상태를 확인하세요. (${baseUrl}) ${toUserMessage(error, "네트워크 오류")}`;
      updateRequest(historyEntry, { status: "error", elapsed_ms: elapsed, message });
      throw new Error(message);
    } finally {
      clearTimeout(timeoutId);
    }

    const payload = await readJsonResponse(response, fallbackMessage);

    if (!response.ok) {
      const message = normalizeApiErrorPayload(payload, fallbackMessage);
      updateRequest(historyEntry, { status: "error", elapsed_ms: Date.now() - startedAtMs, http_status: response.status, message });
      throw new Error(message);
    }

    updateRequest(historyEntry, { status: "success", elapsed_ms: Date.now() - startedAtMs, http_status: response.status, message: "성공" });
    return payload;
  }

  function checkApiHealth() {
    return requestJson("/api/health", {
      method: "GET",
      fallbackMessage: "백엔드 상태 확인에 실패했습니다.",
    });
  }

  function checkDataPortalDiagnostics(query) {
    const params = new URLSearchParams();
    if (query) {
      params.set("query", query);
    }
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return requestJson(`/api/diagnostics/data-portal${suffix}`, {
      method: "GET",
      fallbackMessage: "data.go.kr 연결 진단에 실패했습니다.",
    });
  }

  function extractKeywords(prompt) {
    return requestJson("/api/keywords", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ prompt }),
      fallbackMessage: "키워드 추출에 실패했습니다.",
    });
  }

  function searchDatasets(keyword, options) {
    const searchOptions = options || {};

    return requestJson("/api/datasets/search", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        keyword,
        page: searchOptions.page || 1,
        per_page: searchOptions.perPage || searchOptions.per_page || 10,
      }),
      fallbackMessage: "공공데이터 후보 검색에 실패했습니다.",
    });
  }

  function fetchDatasetDetail(dataset) {
    const source = dataset && typeof dataset === "object" ? dataset : {};

    return requestJson("/api/datasets/detail", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        dataset_id: source.id || source.datasetId || null,
        url: source.url || source.detailUrl || source.link || null,
        raw: source.raw && typeof source.raw === "object" ? source.raw : source,
      }),
      fallbackMessage: "선택한 데이터셋 상세 조회에 실패했습니다.",
    });
  }

  function previewDatasetResource(resource, options) {
    const previewOptions = options || {};

    return requestJson("/api/datasets/resource/preview", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        resource: resource || {},
        max_rows: previewOptions.maxRows || previewOptions.max_rows || 10,
      }),
      fallbackMessage: "선택한 리소스 미리보기에 실패했습니다.",
    });
  }

  function visualizeDatasetResource(resource, query, coreKeyword, options) {
    const visualizeOptions = options || {};

    return requestJson("/api/datasets/resource/visualize", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        resource: resource || {},
        query: query || visualizeOptions.query || "",
        core_keyword: coreKeyword || visualizeOptions.coreKeyword || visualizeOptions.core_keyword || "",
      }),
      fallbackMessage: "선택한 리소스 시각화 API 호출에 실패했습니다.",
    });
  }

  function visualizeDataset(file, query, coreKeyword) {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("query", query || "");
    formData.append("core_keyword", coreKeyword || "");

    return requestJson("/api/visualize", {
      method: "POST",
      body: formData,
      fallbackMessage: "데이터 시각화 API 호출에 실패했습니다.",
    });
  }

  console.info(`[PublicDataDashboard] API base URL: ${getApiBaseUrl()} (${getApiBaseUrlSource()})`);

  window.PublicDataDashboard.Api = {
    DEFAULT_API_BASE_URL,
    API_BASE_URL_OVERRIDE_KEY,
    DEFAULT_REQUEST_TIMEOUT_MS,
    getApiBaseUrl,
    getApiBaseUrlSource,
    setStoredApiBaseUrl,
    checkApiHealth,
    checkDataPortalDiagnostics,
    extractKeywords,
    searchDatasets,
    fetchDatasetDetail,
    getDatasetDetail: fetchDatasetDetail,
    previewDatasetResource,
    visualizeDatasetResource,
    visualizeDataset,
    getRequestHistory,
  };
})();
