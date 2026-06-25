(function () {
  window.PublicDataDashboard = window.PublicDataDashboard || {};

  const DEFAULT_API_BASE_URL = "http://localhost:8000";
  const API_BASE_URL_OVERRIDE_KEY = "PUBLIC_DATA_API_BASE_URL";

  function getApiBaseUrl() {
    const windowOverride = typeof window.PUBLIC_DATA_API_BASE_URL === "string"
      ? window.PUBLIC_DATA_API_BASE_URL.trim()
      : "";
    const storageOverride = readStorageOverride();
    const baseUrl = windowOverride || storageOverride || DEFAULT_API_BASE_URL;

    return baseUrl.replace(/\/+$/, "");
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
    const fallbackMessage = options && options.fallbackMessage
      ? options.fallbackMessage
      : "API 요청 처리 중 오류가 발생했습니다.";

    let response;

    try {
      response = await fetch(`${getApiBaseUrl()}${path}`, options);
    } catch (error) {
      throw new Error(`백엔드 API 연결 실패: ${toUserMessage(error, "네트워크 오류")}`);
    }

    const payload = await readJsonResponse(response, fallbackMessage);

    if (!response.ok) {
      throw new Error(normalizeApiErrorPayload(payload, fallbackMessage));
    }

    return payload;
  }

  function checkApiHealth() {
    return requestJson("/api/health", {
      method: "GET",
      fallbackMessage: "백엔드 상태 확인에 실패했습니다.",
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

  window.PublicDataDashboard.Api = {
    DEFAULT_API_BASE_URL,
    API_BASE_URL_OVERRIDE_KEY,
    getApiBaseUrl,
    checkApiHealth,
    extractKeywords,
    searchDatasets,
    fetchDatasetDetail,
    getDatasetDetail: fetchDatasetDetail,
    previewDatasetResource,
    visualizeDataset,
  };
})();
