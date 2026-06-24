(function () {
  const appRoot = document.getElementById("app");
  const usersStorageKey = "publicDataDashboardUsers";
  const currentUserStorageKey = "publicDataDashboardCurrentUser";
  const promptHistoryStorageKey = "publicDataDashboardPromptHistory";
  const promptSessionsStorageKey = "publicDataDashboardPromptSessions";

  function getUserStorageKey(baseKey, userId) {
    return `${baseKey}:${userId}`;
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

    return sessions && typeof sessions === "object" && !Array.isArray(sessions)
      ? sessions
      : {};
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
  };

  if (storedCurrentUser && !hasStoredUser) {
    writeStoredCurrentUser("");
  }

  function setState(nextState) {
    Object.assign(state, nextState);
    render();
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
      currentView: "prompt",
      authMode: "login",
      authError: "",
      mainPrompt: "",
      additionalPrompt: "",
      additionalPrompts: [],
      promptHistory: readStoredPromptHistory(trimmedUserId),
      promptSessions: readStoredPromptSessions(trimmedUserId),
    });
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
    });
  }

  function handlePromptHistorySelect(prompt) {
    const session = readPromptSession(prompt);

    setState({
      mainPrompt: prompt,
      currentView: "dashboard",
      additionalPrompt: "",
      additionalPrompts: session.additionalPrompts || [],
    });
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
    const nextSessions = writePromptSession(state.mainPrompt, nextAdditionalPrompts);

    setState({
      additionalPrompt: "",
      additionalPrompts: nextAdditionalPrompts,
      promptSessions: nextSessions,
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
        onNewPrompt: () => setState({ currentView: "prompt", mainPrompt: "" }),
        onLogout: handleLogout,
      })
    );
  }

  render();
})();
