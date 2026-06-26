(function () {
  const appRoot = document.getElementById("app");
  const usersStorageKey = "publicDataDashboardUsers";
  const currentUserStorageKey = "publicDataDashboardCurrentUser";
  const promptHistoryStorageKey = "publicDataDashboardPromptHistory";
  const promptSessionsStorageKey = "publicDataDashboardPromptSessions";

  function getUserStorageKey(baseKey, userId) {
    return `${baseKey}:${encodeURIComponent(userId)}`;
  }

  function readJsonStorage(key, fallbackValue) {
    try {
      const storedValue = localStorage.getItem(key);
      return storedValue ? JSON.parse(storedValue) : fallbackValue;
    } catch (error) {
      return fallbackValue;
    }
  }

  function writeJsonStorage(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (error) {
      // 저장소 접근이 제한된 환경에서는 현재 세션 상태만 유지한다.
    }
  }

  function readStoredCurrentUser() {
    try {
      return localStorage.getItem(currentUserStorageKey) || "";
    } catch (error) {
      return "";
    }
  }

  function writeStoredCurrentUser(userId) {
    try {
      if (userId) {
        localStorage.setItem(currentUserStorageKey, userId);
      } else {
        localStorage.removeItem(currentUserStorageKey);
      }
    } catch (error) {
      // 저장소 접근이 제한된 환경에서는 현재 세션 상태만 유지한다.
    }
  }

  function readStoredUsers() {
    const users = readJsonStorage(usersStorageKey, {});
    return users && typeof users === "object" && !Array.isArray(users) ? users : {};
  }

  function writeStoredUsers(users) {
    writeJsonStorage(usersStorageKey, users);
  }

  function readStoredPromptHistory(userId) {
    if (!userId) {
      return [];
    }

    const storedHistory = readJsonStorage(
      getUserStorageKey(promptHistoryStorageKey, userId),
      []
    );

    if (!Array.isArray(storedHistory)) {
      return [];
    }

    return storedHistory.filter((item) => item && item.id && item.text);
  }

  function writeStoredPromptHistory(history, userId) {
    if (!userId) {
      return;
    }

    writeJsonStorage(getUserStorageKey(promptHistoryStorageKey, userId), history);
  }

  function readStoredPromptSessions(userId) {
    if (!userId) {
      return {};
    }

    const sessions = readJsonStorage(
      getUserStorageKey(promptSessionsStorageKey, userId),
      {}
    );

    if (!sessions || typeof sessions !== "object" || Array.isArray(sessions)) {
      return {};
    }

    return Object.fromEntries(
      Object.entries(sessions).filter(
        ([prompt, session]) =>
          prompt && session && Array.isArray(session.additionalPrompts)
      )
    );
  }

  function writeStoredPromptSessions(sessions, userId) {
    if (!userId) {
      return;
    }

    writeJsonStorage(getUserStorageKey(promptSessionsStorageKey, userId), sessions);
  }

  function createPromptHistoryItem(prompt) {
    return {
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      text: prompt,
      createdAt: new Date().toISOString(),
    };
  }

  function rememberPrompt(prompt, userId) {
    const trimmedPrompt = prompt.trim();
    const historyWithoutDuplicate = state.promptHistory.filter(
      (item) => item.text !== trimmedPrompt
    );
    const nextHistory = [
      createPromptHistoryItem(trimmedPrompt),
      ...historyWithoutDuplicate,
    ].slice(0, 20);

    writeStoredPromptHistory(nextHistory, userId);
    return nextHistory;
  }

  function movePromptHistoryToTop(prompt, userId) {
    const trimmedPrompt = prompt.trim();
    const existingItem = state.promptHistory.find(
      (item) => item.text === trimmedPrompt
    );
    const historyWithoutPrompt = state.promptHistory.filter(
      (item) => item.text !== trimmedPrompt
    );
    const nextHistory = [
      {
        ...(existingItem || createPromptHistoryItem(trimmedPrompt)),
        text: trimmedPrompt,
        updatedAt: new Date().toISOString(),
      },
      ...historyWithoutPrompt,
    ].slice(0, 20);

    writeStoredPromptHistory(nextHistory, userId);
    return nextHistory;
  }

  function readPromptSession(prompt) {
    return state.promptSessions[prompt] || { additionalPrompts: [] };
  }

  function writePromptSession(prompt, additionalPrompts) {
    if (!state.currentUser || !prompt) {
      return state.promptSessions;
    }

    const nextSessions = {
      ...state.promptSessions,
      [prompt]: {
        additionalPrompts,
        updatedAt: new Date().toISOString(),
      },
    };

    writeStoredPromptSessions(nextSessions, state.currentUser);
    return nextSessions;
  }

  const storedUsers = readStoredUsers();
  const storedCurrentUser = readStoredCurrentUser();
  const hasStoredUser = Boolean(storedCurrentUser && storedUsers[storedCurrentUser]);
  const storedPromptHistory = hasStoredUser
    ? readStoredPromptHistory(storedCurrentUser)
    : [];
  const storedPromptSessions = hasStoredUser
    ? readStoredPromptSessions(storedCurrentUser)
    : {};

  const state = {
    users: storedUsers,
    currentUser: hasStoredUser ? storedCurrentUser : "",
    isLoggedIn: hasStoredUser,
    currentView: hasStoredUser ? "prompt" : "login",
    authMode: "login",
    authError: "",
    mainPrompt: "",
    additionalPrompt: "",
    additionalPrompts: [],
    promptHistory: storedPromptHistory,
    promptSessions: storedPromptSessions,
    isKeywordLoading: false,
    keywordResult: null,
    keywordError: "",
    isDatasetSearchLoading: false,
    datasetSearchResult: null,
    datasetSearchError: "",
    selectedDataset: null,
    isDatasetDetailLoading: false,
    datasetDetailResult: null,
    datasetDetailError: "",
    selectedResource: null,
    isResourcePreviewLoading: false,
    resourcePreviewResult: null,
    resourcePreviewError: "",
    isResourceVisualizationLoading: false,
    resourceVisualizationError: "",
    selectedDatasetFile: null,
    isVisualizationLoading: false,
    visualizationResult: null,
    visualizationError: "",
    apiHealth: { status: "idle", message: "아직 확인하지 않았습니다.", checkedAt: "" },
    dataPortalDiagnostic: { status: "idle", message: "아직 확인하지 않았습니다.", checkedAt: "" },
  };

  if (storedCurrentUser && !hasStoredUser) {
    writeStoredCurrentUser("");
  }

  function setState(nextState) {
    Object.assign(state, nextState);
    render();
  }


  function getConnectionFailureMessage(error, fallbackMessage) {
    const message = error && error.message ? error.message : fallbackMessage;
    if (message && message.includes("백엔드 API에 연결할 수 없습니다")) {
      return message;
    }
    return message || fallbackMessage;
  }

  function checkApiConnection() {
    if (!window.PublicDataDashboard.Api || !window.PublicDataDashboard.Api.checkApiHealth) {
      setState({
        apiHealth: {
          status: "error",
          message: "백엔드 API 클라이언트를 불러오지 못했습니다.",
          checkedAt: new Date().toISOString(),
        },
      });
      return;
    }

    setState({
      apiHealth: {
        status: "checking",
        message: "백엔드 /api/health 확인 중...",
        checkedAt: state.apiHealth.checkedAt || "",
      },
    });

    window.PublicDataDashboard.Api.checkApiHealth()
      .then((result) => {
        setState({
          apiHealth: {
            status: "success",
            message: `${result && result.app ? result.app : "API"} 연결 성공`,
            checkedAt: new Date().toISOString(),
          },
        });
      })
      .catch((error) => {
        setState({
          apiHealth: {
            status: "error",
            message: getConnectionFailureMessage(error, "백엔드 API에 연결할 수 없습니다. API base URL과 배포 상태를 확인하세요."),
            checkedAt: new Date().toISOString(),
          },
        });
      });
  }

  function checkDataPortalConnection() {
    if (!window.PublicDataDashboard.Api || !window.PublicDataDashboard.Api.checkDataPortalDiagnostics) {
      setState({
        dataPortalDiagnostic: {
          status: "error",
          message: "data.go.kr 진단 API 클라이언트를 불러오지 못했습니다.",
          checkedAt: new Date().toISOString(),
        },
      });
      return;
    }

    setState({
      dataPortalDiagnostic: {
        status: "checking",
        message: "data.go.kr 연결 확인 중...",
        checkedAt: state.dataPortalDiagnostic.checkedAt || "",
      },
    });

    window.PublicDataDashboard.Api.checkDataPortalDiagnostics(state.mainPrompt || "서울 부동산 가격")
      .then((result) => {
        const firstTitle = result && result.first_candidate && result.first_candidate.title ? ` · 첫 후보: ${result.first_candidate.title}` : "";
        setState({
          dataPortalDiagnostic: {
            status: result && result.status === "success" ? "success" : "error",
            message: result && result.status === "success"
              ? `후보 ${result.candidate_count || 0}건${firstTitle}`
              : `${result && result.reason_code ? result.reason_code : "DATA_PORTAL_ERROR"}: ${result && result.message ? result.message : "data.go.kr 연결 확인에 실패했습니다."}`,
            checkedAt: new Date().toISOString(),
          },
        });
      })
      .catch((error) => {
        setState({
          dataPortalDiagnostic: {
            status: "error",
            message: getConnectionFailureMessage(error, "data.go.kr 연결 확인에 실패했습니다."),
            checkedAt: new Date().toISOString(),
          },
        });
      });
  }

  function handleApiBaseUrlSave(value) {
    if (!window.PublicDataDashboard.Api || !window.PublicDataDashboard.Api.setStoredApiBaseUrl) {
      setState({
        apiHealth: {
          status: "error",
          message: "API base URL 설정 클라이언트를 불러오지 못했습니다.",
          checkedAt: new Date().toISOString(),
        },
      });
      return;
    }

    try {
      window.PublicDataDashboard.Api.setStoredApiBaseUrl(value);
    } catch (error) {
      setState({
        apiHealth: {
          status: "error",
          message: error && error.message ? error.message : "API base URL 저장에 실패했습니다.",
          checkedAt: new Date().toISOString(),
        },
      });
      return;
    }

    checkApiConnection();
  }

  function handleLogin(userId, password) {
    const trimmedUserId = userId.trim();
    const storedUser = state.users[trimmedUserId];

    if (!storedUser || storedUser.password !== password) {
      setState({
        authError: "아이디 또는 비밀번호가 올바르지 않습니다.",
      });
      return;
    }

    writeStoredCurrentUser(trimmedUserId);

    setState({
      currentUser: trimmedUserId,
      isLoggedIn: true,
      currentUserId: userId,
      authNotice: "",
      currentView: "prompt",
      authMode: "login",
      authError: "",
      mainPrompt: "",
      additionalPrompt: "",
      additionalPrompts: [],
      promptHistory: readStoredPromptHistory(trimmedUserId),
      promptSessions: readStoredPromptSessions(trimmedUserId),
      isKeywordLoading: false,
      keywordResult: null,
      keywordError: "",
      isDatasetSearchLoading: false,
      datasetSearchResult: null,
      datasetSearchError: "",
      selectedDataset: null,
      isDatasetDetailLoading: false,
      datasetDetailResult: null,
      datasetDetailError: "",
      selectedResource: null,
      isResourcePreviewLoading: false,
      resourcePreviewResult: null,
      resourcePreviewError: "",
      isResourceVisualizationLoading: false,
      resourceVisualizationError: "",
      selectedDatasetFile: null,
      isVisualizationLoading: false,
      visualizationResult: null,
      visualizationError: "",
    });

    return {
      ok: true,
      message: "회원가입이 완료되었습니다. 가입한 계정으로 로그인해 주세요.",
    };
  }

  function handleSignup(userId, password) {
    const trimmedUserId = userId.trim();

    if (state.users[trimmedUserId]) {
      setState({ authError: "이미 가입된 아이디입니다." });
      return;
    }

    const nextUsers = {
      ...state.users,
      [trimmedUserId]: {
        password,
        createdAt: new Date().toISOString(),
      },
    };

    writeStoredUsers(nextUsers);
    writeStoredCurrentUser(trimmedUserId);

    setState({
      users: nextUsers,
      currentUser: trimmedUserId,
      isLoggedIn: true,
      currentView: "prompt",
      authMode: "login",
      authError: "",
      mainPrompt: "",
      additionalPrompt: "",
      additionalPrompts: [],
      promptHistory: [],
      promptSessions: {},
      isKeywordLoading: false,
      keywordResult: null,
      keywordError: "",
      isDatasetSearchLoading: false,
      datasetSearchResult: null,
      datasetSearchError: "",
      selectedDataset: null,
      isDatasetDetailLoading: false,
      datasetDetailResult: null,
      datasetDetailError: "",
      selectedResource: null,
      isResourcePreviewLoading: false,
      resourcePreviewResult: null,
      resourcePreviewError: "",
      isResourceVisualizationLoading: false,
      resourceVisualizationError: "",
      selectedDatasetFile: null,
      isVisualizationLoading: false,
      visualizationResult: null,
      visualizationError: "",
    });
  }

  function handleAuthModeChange(authMode) {
    setState({ authMode, authError: "" });
  }

  function handleLogout() {
    writeStoredCurrentUser("");
    setState({
      currentUser: "",
      isLoggedIn: false,
      currentView: "login",
      authMode: "login",
      authError: "",
      mainPrompt: "",
      additionalPrompt: "",
      additionalPrompts: [],
      promptHistory: [],
      promptSessions: {},
      isKeywordLoading: false,
      keywordResult: null,
      keywordError: "",
      isDatasetSearchLoading: false,
      datasetSearchResult: null,
      datasetSearchError: "",
      selectedDataset: null,
      isDatasetDetailLoading: false,
      datasetDetailResult: null,
      datasetDetailError: "",
      selectedResource: null,
      isResourcePreviewLoading: false,
      resourcePreviewResult: null,
      resourcePreviewError: "",
      isResourceVisualizationLoading: false,
      resourceVisualizationError: "",
      selectedDatasetFile: null,
      isVisualizationLoading: false,
      visualizationResult: null,
      visualizationError: "",
    });
  }

  function requestKeywordExtraction(prompt) {
    if (!window.PublicDataDashboard.Api) {
      setState({
        isKeywordLoading: false,
        keywordResult: null,
        keywordError: "백엔드 API 클라이언트를 불러오지 못했습니다.",
      });
      return;
    }

    const requestedPrompt = prompt;

    window.PublicDataDashboard.Api.extractKeywords(prompt)
      .then((result) => {
        if (state.mainPrompt !== requestedPrompt || state.currentView !== "dashboard") {
          return;
        }

        setState({
          isKeywordLoading: false,
          keywordResult: result,
          keywordError: "",
        });

        requestDatasetSearch(getKeywordText(result) || requestedPrompt);
      })
      .catch((error) => {
        if (state.mainPrompt !== requestedPrompt || state.currentView !== "dashboard") {
          return;
        }

        setState({
          isKeywordLoading: false,
          keywordResult: null,
          keywordError: error && error.message
            ? error.message
            : "백엔드 API 연결 실패 또는 키워드 추출 실패",
        });

        requestDatasetSearch(requestedPrompt);
      })
      .finally(() => {
        if (state.mainPrompt === requestedPrompt && state.currentView === "dashboard" && state.isKeywordLoading) {
          setState({ isKeywordLoading: false });
        }
      });
  }

  function handleMainPromptSubmit(prompt) {
    const trimmedPrompt = prompt.trim();
    const nextHistory = rememberPrompt(trimmedPrompt, state.currentUser);
    const session = state.promptSessions[trimmedPrompt] || { additionalPrompts: [] };
    const nextSessions = state.promptSessions[trimmedPrompt]
      ? state.promptSessions
      : writePromptSession(trimmedPrompt, []);

    setState({
      mainPrompt: trimmedPrompt,
      currentView: "dashboard",
      additionalPrompt: "",
      additionalPrompts: session.additionalPrompts || [],
      promptHistory: nextHistory,
      promptSessions: nextSessions,
      isKeywordLoading: true,
      keywordResult: null,
      keywordError: "",
      isDatasetSearchLoading: false,
      datasetSearchResult: null,
      datasetSearchError: "",
      selectedDataset: null,
      isDatasetDetailLoading: false,
      datasetDetailResult: null,
      datasetDetailError: "",
      selectedResource: null,
      isResourcePreviewLoading: false,
      resourcePreviewResult: null,
      resourcePreviewError: "",
      isResourceVisualizationLoading: false,
      resourceVisualizationError: "",
      selectedDatasetFile: null,
      isVisualizationLoading: false,
      visualizationResult: null,
      visualizationError: "",
    });

    requestKeywordExtraction(trimmedPrompt);
  }

  function handlePromptHistorySelect(prompt) {
    const session = readPromptSession(prompt);

    setState({
      mainPrompt: prompt,
      currentView: "dashboard",
      additionalPrompt: "",
      additionalPrompts: session.additionalPrompts || [],
      isKeywordLoading: true,
      keywordResult: null,
      keywordError: "",
      isDatasetSearchLoading: false,
      datasetSearchResult: null,
      datasetSearchError: "",
      selectedDataset: null,
      isDatasetDetailLoading: false,
      datasetDetailResult: null,
      datasetDetailError: "",
      selectedResource: null,
      isResourcePreviewLoading: false,
      resourcePreviewResult: null,
      resourcePreviewError: "",
      isResourceVisualizationLoading: false,
      resourceVisualizationError: "",
      selectedDatasetFile: null,
      isVisualizationLoading: false,
      visualizationResult: null,
      visualizationError: "",
    });

    requestKeywordExtraction(prompt);
  }

  function handlePromptHistoryRemove(promptId) {
    const removedPrompt = state.promptHistory.find((item) => item.id === promptId);
    const nextHistory = state.promptHistory.filter((item) => item.id !== promptId);
    const nextSessions = { ...state.promptSessions };

    if (removedPrompt) {
      delete nextSessions[removedPrompt.text];
    }

    writeStoredPromptHistory(nextHistory, state.currentUser);
    writeStoredPromptSessions(nextSessions, state.currentUser);

    setState({
      promptHistory: nextHistory,
      promptSessions: nextSessions,
    });
  }

  function handleAdditionalPromptChange(value) {
    state.additionalPrompt = value;
  }

  function handleAdditionalPromptSubmit() {
    const prompt = state.additionalPrompt.trim();

    if (!prompt || !state.mainPrompt) {
      return;
    }

    const nextAdditionalPrompts = [...state.additionalPrompts, prompt];
    const nextHistory = movePromptHistoryToTop(state.mainPrompt, state.currentUser);
    const nextSessions = writePromptSession(state.mainPrompt, nextAdditionalPrompts);

    setState({
      additionalPrompt: "",
      additionalPrompts: nextAdditionalPrompts,
      promptHistory: nextHistory,
      promptSessions: nextSessions,
    });
  }

  function getKeywordText(result) {
    if (!result || typeof result !== "object") {
      return "";
    }

    if (typeof result.topic === "string") {
      return result.topic.trim();
    }

    if (Array.isArray(result.keywords)) {
      return result.keywords.filter(Boolean).join(" ").trim();
    }

    return "";
  }

  function requestDatasetSearch(keyword, options) {
    const trimmedKeyword = (keyword || "").trim();
    if (!trimmedKeyword) {
      setState({
        isDatasetSearchLoading: false,
        datasetSearchResult: null,
        datasetSearchError: "검색할 키워드를 입력해 주세요.",
        selectedDataset: null,
        isDatasetDetailLoading: false,
        datasetDetailResult: null,
        datasetDetailError: "",
        selectedResource: null,
        isResourcePreviewLoading: false,
        resourcePreviewResult: null,
        resourcePreviewError: "",
      });
      return;
    }

    if (!window.PublicDataDashboard.Api || !window.PublicDataDashboard.Api.searchDatasets) {
      setState({
        isDatasetSearchLoading: false,
        datasetSearchResult: null,
        datasetSearchError: "공공데이터 검색 API 클라이언트를 불러오지 못했습니다.",
        selectedDataset: null,
        isDatasetDetailLoading: false,
        datasetDetailResult: null,
        datasetDetailError: "",
        selectedResource: null,
        isResourcePreviewLoading: false,
        resourcePreviewResult: null,
        resourcePreviewError: "",
      });
      return;
    }

    const requestedKeyword = trimmedKeyword;
    setState({
      isDatasetSearchLoading: true,
      datasetSearchResult: null,
      datasetSearchError: "",
      selectedDataset: null,
      isDatasetDetailLoading: false,
      datasetDetailResult: null,
      datasetDetailError: "",
    });

    window.PublicDataDashboard.Api.searchDatasets(requestedKeyword, options || { page: 1, perPage: 10 })
      .then((result) => {
        if (state.currentView !== "dashboard" || requestedKeyword !== (result && result.query ? result.query : requestedKeyword)) {
          return;
        }

        setState({
          isDatasetSearchLoading: false,
          datasetSearchResult: result,
          datasetSearchError: "",
          selectedDataset: null,
          isDatasetDetailLoading: false,
          datasetDetailResult: null,
          datasetDetailError: "",
        });
      })
      .catch((error) => {
        if (state.currentView !== "dashboard") {
          return;
        }

        setState({
          isDatasetSearchLoading: false,
          datasetSearchResult: null,
          datasetSearchError: getConnectionFailureMessage(error, "공공데이터 후보 검색에 실패했습니다."),
          selectedDataset: null,
          isDatasetDetailLoading: false,
          datasetDetailResult: null,
          datasetDetailError: "",
        });
      })
      .finally(() => {
        if (state.currentView === "dashboard" && state.isDatasetSearchLoading) {
          setState({ isDatasetSearchLoading: false });
        }
      });
  }

  function handleDatasetSearchSubmit(keyword) {
    requestDatasetSearch(keyword || getCoreKeyword() || state.mainPrompt);
  }

  function handleDatasetSelect(dataset) {
    const selected = dataset || null;

    if (!selected) {
      setState({
        selectedDataset: null,
        isDatasetDetailLoading: false,
        datasetDetailResult: null,
        datasetDetailError: "",
        selectedResource: null,
        isResourcePreviewLoading: false,
        resourcePreviewResult: null,
        resourcePreviewError: "",
      });
      return;
    }

    setState({
      selectedDataset: selected,
      isDatasetDetailLoading: true,
      datasetDetailResult: null,
      datasetDetailError: "",
      selectedResource: null,
      isResourcePreviewLoading: false,
      resourcePreviewResult: null,
      resourcePreviewError: "",
    });

    if (!window.PublicDataDashboard.Api || !window.PublicDataDashboard.Api.fetchDatasetDetail) {
      setState({
        isDatasetDetailLoading: false,
        datasetDetailResult: null,
        datasetDetailError: "데이터셋 상세 API 클라이언트를 불러오지 못했습니다.",
      });
      return;
    }

    window.PublicDataDashboard.Api.fetchDatasetDetail(selected)
      .then((result) => {
        if (state.selectedDataset !== selected || state.currentView !== "dashboard") {
          return;
        }

        setState({
          isDatasetDetailLoading: false,
          datasetDetailResult: result,
          datasetDetailError: "",
        });
      })
      .catch((error) => {
        if (state.selectedDataset !== selected || state.currentView !== "dashboard") {
          return;
        }

        setState({
          isDatasetDetailLoading: false,
          datasetDetailResult: null,
          datasetDetailError: getConnectionFailureMessage(error, "선택한 데이터셋 상세 조회에 실패했습니다."),
        });
      })
      .finally(() => {
        if (state.selectedDataset === selected && state.currentView === "dashboard" && state.isDatasetDetailLoading) {
          setState({ isDatasetDetailLoading: false });
        }
      });
  }

  function handleResourcePreview(resource) {
    const selected = resource || null;

    if (!selected) {
      setState({
        selectedResource: null,
        isResourcePreviewLoading: false,
        resourcePreviewResult: null,
        resourcePreviewError: "미리보기할 리소스를 선택해 주세요.",
        resourceVisualizationError: "",
      });
      return;
    }

    if (!window.PublicDataDashboard.Api || !window.PublicDataDashboard.Api.previewDatasetResource) {
      setState({
        selectedResource: selected,
        isResourcePreviewLoading: false,
        resourcePreviewResult: null,
        resourcePreviewError: "리소스 미리보기 API 클라이언트를 불러오지 못했습니다.",
      });
      return;
    }

    setState({
      selectedResource: selected,
      isResourcePreviewLoading: true,
      resourcePreviewResult: null,
      resourcePreviewError: "",
    });

    window.PublicDataDashboard.Api.previewDatasetResource(selected, { maxRows: 10 })
      .then((result) => {
        if (state.selectedResource !== selected || state.currentView !== "dashboard") {
          return;
        }

        setState({
          isResourcePreviewLoading: false,
          resourcePreviewResult: result,
          resourcePreviewError: "",
        });
      })
      .catch((error) => {
        if (state.selectedResource !== selected || state.currentView !== "dashboard") {
          return;
        }

        setState({
          isResourcePreviewLoading: false,
          resourcePreviewResult: null,
          resourcePreviewError: getConnectionFailureMessage(error, "선택한 리소스 미리보기에 실패했습니다."),
        });
      })
      .finally(() => {
        if (state.selectedResource === selected && state.currentView === "dashboard" && state.isResourcePreviewLoading) {
          setState({ isResourcePreviewLoading: false });
        }
      });
  }

  function getCoreKeyword() {
    return getKeywordText(state.keywordResult);
  }

  function handleDatasetFileChange(file) {
    setState({
      selectedDatasetFile: file || null,
      isVisualizationLoading: false,
      visualizationResult: null,
      visualizationError: "",
    });
  }

  function handleResourceVisualization(resource) {
    const selected = resource || state.selectedResource || null;

    if (!selected) {
      setState({ resourceVisualizationError: "시각화할 리소스를 선택해 주세요." });
      return;
    }

    if (!window.PublicDataDashboard.Api || !window.PublicDataDashboard.Api.visualizeDatasetResource) {
      setState({
        isResourceVisualizationLoading: false,
        resourceVisualizationError: "리소스 시각화 API 클라이언트를 불러오지 못했습니다.",
      });
      return;
    }

    const requestedResource = selected;
    const requestedPrompt = state.mainPrompt;

    setState({
      selectedResource: selected,
      isResourceVisualizationLoading: true,
      resourceVisualizationError: "",
      isVisualizationLoading: false,
      visualizationResult: null,
      visualizationError: "",
    });

    window.PublicDataDashboard.Api.visualizeDatasetResource(selected, requestedPrompt, getCoreKeyword())
      .then((result) => {
        if (state.selectedResource !== requestedResource || state.currentView !== "dashboard") {
          return;
        }

        setState({
          isResourceVisualizationLoading: false,
          resourceVisualizationError: "",
          visualizationResult: result,
          visualizationError: "",
        });
      })
      .catch((error) => {
        if (state.selectedResource !== requestedResource || state.currentView !== "dashboard") {
          return;
        }

        setState({
          isResourceVisualizationLoading: false,
          resourceVisualizationError: getConnectionFailureMessage(error, "선택한 리소스 시각화에 실패했습니다."),
        });
      })
      .finally(() => {
        if (state.selectedResource === requestedResource && state.currentView === "dashboard" && state.isResourceVisualizationLoading) {
          setState({ isResourceVisualizationLoading: false });
        }
      });
  }

  function handleVisualizationSubmit() {
    const file = state.selectedDatasetFile;

    if (!file) {
      setState({ visualizationError: "CSV/XLSX/XLS 파일을 먼저 선택해 주세요." });
      return;
    }

    if (!window.PublicDataDashboard.Api) {
      setState({
        isVisualizationLoading: false,
        visualizationResult: null,
        visualizationError: "백엔드 API 클라이언트를 불러오지 못했습니다.",
      });
      return;
    }

    const requestedFile = file;
    const requestedPrompt = state.mainPrompt;

    setState({
      isVisualizationLoading: true,
      isResourceVisualizationLoading: false,
      resourceVisualizationError: "",
      visualizationResult: null,
      visualizationError: "",
    });

    window.PublicDataDashboard.Api.visualizeDataset(file, requestedPrompt, getCoreKeyword())
      .then((result) => {
        if (state.selectedDatasetFile !== requestedFile || state.currentView !== "dashboard") {
          return;
        }

        setState({
          isVisualizationLoading: false,
          visualizationResult: result,
          visualizationError: "",
        });
      })
      .catch((error) => {
        if (state.selectedDatasetFile !== requestedFile || state.currentView !== "dashboard") {
          return;
        }

        setState({
          isVisualizationLoading: false,
          visualizationResult: null,
          visualizationError: getConnectionFailureMessage(error, "데이터 시각화 API 호출에 실패했습니다."),
        });
      })
      .finally(() => {
        if (state.selectedDatasetFile === requestedFile && state.currentView === "dashboard" && state.isVisualizationLoading) {
          setState({ isVisualizationLoading: false });
        }
      });
  }

  function render() {
    appRoot.replaceChildren();

    if (!state.isLoggedIn || state.currentView === "login") {
      appRoot.appendChild(
        window.PublicDataDashboard.LoginPage({
          mode: state.authMode,
          errorMessage: state.authError,
          onLogin: handleLogin,
          onSignup: handleSignup,
          onShowLogin: () => handleAuthModeChange("login"),
          onShowSignup: () => handleAuthModeChange("signup"),
        })
      );
      return;
    }

    if (state.currentView === "prompt") {
      appRoot.appendChild(
        window.PublicDataDashboard.PromptPage({
          promptHistory: state.promptHistory,
          onSubmit: handleMainPromptSubmit,
          onHistorySelect: handlePromptHistorySelect,
          onHistoryRemove: handlePromptHistoryRemove,
          onLogout: handleLogout,
        })
      );
      return;
    }

    appRoot.appendChild(
      window.PublicDataDashboard.DashboardPage({
        mainPrompt: state.mainPrompt,
        additionalPrompt: state.additionalPrompt,
        additionalPrompts: state.additionalPrompts,
        onAdditionalPromptChange: handleAdditionalPromptChange,
        onAdditionalPromptSubmit: handleAdditionalPromptSubmit,
        isKeywordLoading: state.isKeywordLoading,
        keywordResult: state.keywordResult,
        keywordError: state.keywordError,
        isDatasetSearchLoading: state.isDatasetSearchLoading,
        datasetSearchResult: state.datasetSearchResult,
        datasetSearchError: state.datasetSearchError,
        selectedDataset: state.selectedDataset,
        isDatasetDetailLoading: state.isDatasetDetailLoading,
        datasetDetailResult: state.datasetDetailResult,
        datasetDetailError: state.datasetDetailError,
        selectedResource: state.selectedResource,
        isResourcePreviewLoading: state.isResourcePreviewLoading,
        resourcePreviewResult: state.resourcePreviewResult,
        resourcePreviewError: state.resourcePreviewError,
        isResourceVisualizationLoading: state.isResourceVisualizationLoading,
        resourceVisualizationError: state.resourceVisualizationError,
        onDatasetSearchSubmit: handleDatasetSearchSubmit,
        onDatasetSelect: handleDatasetSelect,
        onResourcePreview: handleResourcePreview,
        onResourceVisualization: handleResourceVisualization,
        selectedDatasetFile: state.selectedDatasetFile,
        isVisualizationLoading: state.isVisualizationLoading,
        visualizationResult: state.visualizationResult,
        visualizationError: state.visualizationError,
        onDatasetFileChange: handleDatasetFileChange,
        onVisualizationSubmit: handleVisualizationSubmit,
        apiBaseUrl: window.PublicDataDashboard.Api ? window.PublicDataDashboard.Api.getApiBaseUrl() : "",
        apiBaseUrlSource: window.PublicDataDashboard.Api && window.PublicDataDashboard.Api.getApiBaseUrlSource ? window.PublicDataDashboard.Api.getApiBaseUrlSource() : "unknown",
        apiHealth: state.apiHealth,
        dataPortalDiagnostic: state.dataPortalDiagnostic,
        onApiConnectionCheck: checkApiConnection,
        onDataPortalDiagnosticCheck: checkDataPortalConnection,
        onApiBaseUrlSave: handleApiBaseUrlSave,
        onNewPrompt: () => setState({
          currentView: "prompt",
          mainPrompt: "",
          isKeywordLoading: false,
          keywordResult: null,
          keywordError: "",
          isDatasetSearchLoading: false,
          datasetSearchResult: null,
          datasetSearchError: "",
          selectedDataset: null,
          isDatasetDetailLoading: false,
          datasetDetailResult: null,
          datasetDetailError: "",
          selectedDatasetFile: null,
          isVisualizationLoading: false,
          visualizationResult: null,
          visualizationError: "",
        }),
        onLogout: handleLogout,
      })
    );
  }

  render();
})();
