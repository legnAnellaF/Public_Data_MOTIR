(function () {
  window.PublicDataDashboard = window.PublicDataDashboard || {};

  const DEFAULT_API_BASE_URL = "http://localhost:8000";
  const API_BASE_URL_OVERRIDE_KEY = "PUBLIC_DATA_API_BASE_URL";
  const DEFAULT_REQUEST_TIMEOUT_MS = 30000;
  const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
  const MAX_VISUALIZE_ROWS = 1000;
  const CSV_SAMPLE_BYTES = 2 * 1024 * 1024;
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
    if (!error) return fallbackMessage;
    if (typeof error === "string") return error;
    if (error.reason_code) return mapReasonCodeToMessage(error.reason_code, error.message || fallbackMessage);
    if (error.message) return error.message;
    try {
      const text = JSON.stringify(error);
      return text && text !== "{}" ? text : fallbackMessage;
    } catch (jsonError) {
      return fallbackMessage;
    }
  }

  function mapReasonCodeToMessage(reasonCode, fallbackMessage) {
    const code = String(reasonCode || "").toUpperCase();
    if (code.includes("TOO_LARGE") || code.includes("PAYLOAD")) return "파일이 너무 큽니다. CSV는 일부 행만 샘플링하거나 더 작은 파일을 사용해 주세요.";
    if (code === "OPENAPI_SERVICE_KEY_MISSING") return "OpenAPI 호출에는 backend 환경변수 serviceKey가 필요합니다. 현재는 직접 업로드 또는 데모 흐름으로 진행할 수 있습니다.";
    if (code === "OPENAPI_AUTH_REQUIRED") return "공공데이터포털 활용신청 또는 인증키 확인이 필요합니다.";
    if (code === "OPENAPI_FETCH_FAILED") return "공공데이터포털 OpenAPI 호출이 실패했습니다. 직접 업로드 또는 오프라인 데모 흐름으로 계속할 수 있습니다.";
    if (code === "OPENAPI_XML_UNSUPPORTED") return "XML OpenAPI는 현재 범용 정규화를 지원하지 않습니다. JSON OpenAPI 또는 직접 업로드를 사용해 주세요.";
    return fallbackMessage || "요청 처리 중 오류가 발생했습니다.";
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
      return mapReasonCodeToMessage(detail.reason_code, detail.message || detail.detail || fallbackMessage);
    }

    return mapReasonCodeToMessage(payload.reason_code, payload.message || fallbackMessage);
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
      const hasFileConstructor = typeof File !== "undefined";
      const isLikelyLargeUpload = fetchOptions.body instanceof FormData && Array.from(fetchOptions.body.values()).some((value) => hasFileConstructor && value instanceof File && value.size > MAX_UPLOAD_BYTES);
      const message = isLikelyLargeUpload
        ? "파일이 너무 큽니다. CSV는 일부 행만 샘플링하고, XLS/XLSX는 더 작은 파일을 사용해 주세요."
        : `네트워크 또는 CORS 문제로 백엔드 API에 연결할 수 없습니다. API base URL과 배포 상태를 확인하세요. (${baseUrl}) ${toUserMessage(error, "네트워크 오류")}`;
      updateRequest(historyEntry, { status: "error", elapsed_ms: elapsed, message });
      throw new Error(message);
    } finally {
      clearTimeout(timeoutId);
    }

    const payload = await readJsonResponse(response, fallbackMessage);

    if (!response.ok) {
      const message = response.status === 413 ? "파일이 너무 큽니다. CSV는 일부 행만 샘플링하거나 더 작은 파일을 사용해 주세요." : normalizeApiErrorPayload(payload, fallbackMessage);
      updateRequest(historyEntry, { status: "error", elapsed_ms: Date.now() - startedAtMs, http_status: response.status, message });
      throw new Error(message);
    }

    const successMessage = payload && (payload.is_offline_fallback || payload.source === "offline_fallback")
      ? (payload.message || "offline fallback candidates")
      : "성공";
    updateRequest(historyEntry, { status: "success", elapsed_ms: Date.now() - startedAtMs, http_status: response.status, message: successMessage });
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

  function previewOpenApiResource(resource, options) {
    const previewOptions = options || {};
    return requestJson("/api/datasets/openapi/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dataset_id: previewOptions.datasetId || previewOptions.dataset_id || null,
        resource: resource || {},
        limit: previewOptions.limit || 100,
      }),
      fallbackMessage: "OpenAPI 미리보기에 실패했습니다.",
    });
  }

  function visualizeOpenApiResource(resource, query, coreKeyword, options) {
    const visualizeOptions = options || {};
    return requestJson("/api/datasets/openapi/visualize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dataset_id: visualizeOptions.datasetId || visualizeOptions.dataset_id || null,
        resource: resource || {},
        limit: visualizeOptions.limit || 100,
        query: query || visualizeOptions.query || "",
        core_keyword: coreKeyword || visualizeOptions.coreKeyword || visualizeOptions.core_keyword || "",
      }),
      fallbackMessage: "OpenAPI 시각화에 실패했습니다.",
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

  function isCsvFile(file) {
    const name = String(file && file.name || "").toLowerCase();
    const type = String(file && file.type || "").toLowerCase();
    return name.endsWith(".csv") || type.includes("csv");
  }

  async function sampleCsvFile(file) {
    const headBlob = file.slice(0, Math.min(file.size, CSV_SAMPLE_BYTES));
    const text = await headBlob.text();
    const lines = text.split(/\r?\n/);
    if (lines.length <= 1) return { file, isSampled: false, sampleRows: Math.max(0, lines.length - 1), message: "" };
    const sampledLines = lines.slice(0, MAX_VISUALIZE_ROWS + 1);
    const sampledText = sampledLines.join("\n");
    const sampledFile = new File([sampledText], file.name.replace(/\.csv$/i, "") + `.sample-${MAX_VISUALIZE_ROWS}.csv`, { type: "text/csv" });
    const isSampled = file.size > MAX_UPLOAD_BYTES || lines.length > MAX_VISUALIZE_ROWS + 1 || file.size > CSV_SAMPLE_BYTES;
    return {
      file: isSampled ? sampledFile : file,
      isSampled,
      sampleRows: Math.max(0, sampledLines.length - 1),
      message: isSampled ? `파일이 커서 header와 앞 ${Math.max(0, sampledLines.length - 1)}행만 샘플링하여 시각화합니다.` : "",
    };
  }

  async function prepareUploadFile(file) {
    if (!file) throw new Error("CSV/XLSX/XLS 파일을 먼저 선택해 주세요.");
    if (isCsvFile(file)) return sampleCsvFile(file);
    if (file.size > MAX_UPLOAD_BYTES) {
      throw new Error(`파일이 너무 큽니다. XLS/XLSX는 브라우저 샘플링을 지원하지 않으므로 ${(MAX_UPLOAD_BYTES / 1024 / 1024).toFixed(0)}MB 이하 파일 또는 CSV 샘플을 사용해 주세요.`);
    }
    return { file, isSampled: false, sampleRows: 0, message: "" };
  }

  async function visualizeDataset(file, query, coreKeyword) {
    const prepared = await prepareUploadFile(file);
    const formData = new FormData();
    formData.append("file", prepared.file);
    formData.append("query", query || "");
    formData.append("core_keyword", coreKeyword || "");

    if (prepared.isSampled) {
      formData.append("is_sampled", "true");
      formData.append("sample_rows", String(prepared.sampleRows || 0));
    }

    return requestJson("/api/visualize", {
      method: "POST",
      body: formData,
      fallbackMessage: "데이터 시각화 API 호출에 실패했습니다.",
    }).then((result) => {
      if (prepared.isSampled && result && typeof result === "object") {
        result.is_sampled = true;
        result.sample_rows = prepared.sampleRows || 0;
        result.sample_message = prepared.message;
        result.metadata = { ...(result.metadata || {}), source: "upload_sample", is_sampled: true, sample_rows: prepared.sampleRows || 0, original_file_size: file.size };
      }
      return result;
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
    previewOpenApiResource,
    visualizeOpenApiResource,
    visualizeDatasetResource,
    visualizeDataset,
    prepareUploadFile,
    sampleCsvFile,
    MAX_UPLOAD_BYTES,
    MAX_VISUALIZE_ROWS,
    CSV_SAMPLE_BYTES,
    getRequestHistory,
  };
})();
