(function () {
  const appRoot = document.getElementById("app");
  const storageKey = "publicDataDashboardLoggedIn";
  const currentUserStorageKey = "publicDataDashboardCurrentUser";
  const usersStorageKey = "publicDataDashboardUsers";
  const promptHistoryStorageKey = "publicDataDashboardPromptHistory";
  const promptSessionsStorageKey = "publicDataDashboardPromptSessions";

  function getUserStorageKey(baseKey, userId) {
    return `${baseKey}:${encodeURIComponent(userId)}`;
  }

  function readStoredCurrentUser() {
    try {
      return localStorage.getItem(currentUserStorageKey) || "";
    } catch (error) {
      return "";
    }
  }

  function readStoredLogin() {
    try {
      return (
        localStorage.getItem(storageKey) === "true" &&
        Boolean(localStorage.getItem(currentUserStorageKey))
      );
    } catch (error) {
      return false;
    }
  }

  function writeStoredLogin(value, userId = "") {
    try {
      if (value) {
        localStorage.setItem(storageKey, "true");
        localStorage.setItem(currentUserStorageKey, userId);
      } else {
        localStorage.removeItem(storageKey);
        localStorage.removeItem(currentUserStorageKey);
      }
    } catch (error) {
      // 저장소 접근이 제한된 환경에서는 현재 세션 상태만 유지한다.
    }
  }

  function readStoredUsers() {
    try {
      const storedValue = localStorage.getItem(usersStorageKey);
      const parsedValue = storedValue ? JSON.parse(storedValue) : [];

      if (!Array.isArray(parsedValue)) {
        return [];
      }

      return parsedValue.filter((user) => user && user.userId && user.password);
    } catch (error) {
      return [];
    }
  }

  function writeStoredUsers(users) {
    try {
      localStorage.setItem(usersStorageKey, JSON.stringify(users));
    } catch (error) {
      // 저장소 접근이 제한된 환경에서는 현재 세션 상태만 유지한다.
    }
  }

  function readStoredPromptHistory(userId) {
    try {
      const storedValue = localStorage.getItem(
        getUserStorageKey(promptHistoryStorageKey, userId)
      );
      const parsedValue = storedValue ? JSON.parse(storedValue) : [];

      if (!Array.isArray(parsedValue)) {
        return [];
      }

      return parsedValue.filter((item) => item && item.id && item.text);
    } catch (error) {
      return [];
    }
  }

  function writeStoredPromptHistory(history, userId) {
    try {
      localStorage.setItem(
        getUserStorageKey(promptHistoryStorageKey, userId),
        JSON.stringify(history)
      );
    } catch (error) {
      // 저장소 접근이 제한된 환경에서는 현재 세션 상태만 유지한다.
    }
  }

  function readStoredPromptSessions(userId) {
    try {
      const storedValue = localStorage.getItem(
        getUserStorageKey(promptSessionsStorageKey, userId)
      );
      const parsedValue = storedValue ? JSON.parse(storedValue) : {};

      if (!parsedValue || typeof parsedValue !== "object" || Array.isArray(parsedValue)) {
        return {};
      }

      return Object.fromEntries(
        Object.entries(parsedValue).filter(
          ([prompt, session]) =>
            prompt &&
            session &&
            Array.isArray(session.additionalPrompts)
        )
      );
    } catch (error) {
      return {};
    }
  }

  function writeStoredPromptSessions(sessions, userId) {
    try {
      localStorage.setItem(
        getUserStorageKey(promptSessionsStorageKey, userId),
        JSON.stringify(sessions)
      );
    } catch (error) {
      // 저장소 접근이 제한된 환경에서는 현재 세션 상태만 유지한다.
    }
  }

  function createPromptHistoryItem(prompt) {
    return {
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      text: prompt,
      createdAt: new Date().toISOString(),
    };
  }

  function rememberPrompt(prompt) {
    const trimmedPrompt = prompt.trim();
    const historyWithoutDuplicate = state.promptHistory.filter(
      (item) => item.text !== trimmedPrompt
    );
    const nextHistory = [
      createPromptHistoryItem(trimmedPrompt),
      ...historyWithoutDuplicate,
    ].slice(0, 20);

    writeStoredPromptHistory(nextHistory, state.currentUserId);
    return nextHistory;
  }

  function movePromptHistoryToTop(prompt) {
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

    writeStoredPromptHistory(nextHistory, state.currentUserId);
    return nextHistory;
  }

  const storedLogin = readStoredLogin();
  const storedUserId = storedLogin ? readStoredCurrentUser() : "";
  const storedPromptHistory = storedUserId
    ? readStoredPromptHistory(storedUserId)
    : [];
  const storedPromptSessions = storedUserId
    ? readStoredPromptSessions(storedUserId)
    : {};
  const storedUsers = readStoredUsers();

  const state = {
    isLoggedIn: storedLogin,
    currentView: storedLogin ? "prompt" : "login",
    currentUserId: storedUserId,
    authNotice: "",
    mainPrompt: "",
    additionalPrompt: "",
    additionalPrompts: [],
    promptHistory: storedPromptHistory,
    promptSessions: storedPromptSessions,
    users: storedUsers,
  };

  function setState(nextState) {
    Object.assign(state, nextState);
    render();
  }

  function handleLogin(userId, password) {
    const matchedUser = state.users.find(
      (user) => user.userId === userId && user.password === password
    );

    if (!matchedUser) {
      return {
        ok: false,
        message: "회원가입한 아이디와 비밀번호를 입력해 주세요.",
      };
    }

    writeStoredLogin(true, userId);
    setState({
      isLoggedIn: true,
      currentUserId: userId,
      authNotice: "",
      currentView: "prompt",
      mainPrompt: "",
      additionalPrompt: "",
      additionalPrompts: [],
      promptHistory: readStoredPromptHistory(userId),
      promptSessions: readStoredPromptSessions(userId),
    });

    return { ok: true };
  }

  function handleSignup(userId, password) {
    const duplicatedUser = state.users.some((user) => user.userId === userId);

    if (duplicatedUser) {
      return {
        ok: false,
        message: "이미 가입된 아이디입니다.",
      };
    }

    const nextUsers = [...state.users, { userId, password }];

    writeStoredUsers(nextUsers);
    setState({
      users: nextUsers,
      currentView: "login",
      authNotice: "회원가입이 완료되었습니다. 가입한 계정으로 로그인해 주세요.",
    });

    return {
      ok: true,
      message: "회원가입이 완료되었습니다. 가입한 계정으로 로그인해 주세요.",
    };
  }

  function handleLogout() {
    writeStoredLogin(false);
    setState({
      isLoggedIn: false,
      currentView: "login",
      currentUserId: "",
      authNotice: "",
      mainPrompt: "",
      additionalPrompt: "",
      additionalPrompts: [],
      promptHistory: [],
      promptSessions: {},
    });
  }

  function handleMainPromptSubmit(prompt) {
    const trimmedPrompt = prompt.trim();
    const nextHistory = rememberPrompt(prompt);
    const savedSession = state.promptSessions[trimmedPrompt];

    setState({
      mainPrompt: trimmedPrompt,
      currentView: "dashboard",
      additionalPrompt: "",
      additionalPrompts: savedSession ? savedSession.additionalPrompts : [],
      promptHistory: nextHistory,
    });
  }

  function handlePromptHistorySelect(prompt) {
    const savedSession = state.promptSessions[prompt];

    setState({
      mainPrompt: prompt,
      currentView: "dashboard",
      additionalPrompt: "",
      additionalPrompts: savedSession ? savedSession.additionalPrompts : [],
    });
  }

  function handlePromptHistoryRemove(promptId) {
    const removedPrompt = state.promptHistory.find((item) => item.id === promptId);
    const nextHistory = state.promptHistory.filter((item) => item.id !== promptId);
    const nextPromptSessions = { ...state.promptSessions };

    if (removedPrompt) {
      delete nextPromptSessions[removedPrompt.text];
    }

    writeStoredPromptHistory(nextHistory, state.currentUserId);
    writeStoredPromptSessions(nextPromptSessions, state.currentUserId);
    setState({
      promptHistory: nextHistory,
      promptSessions: nextPromptSessions,
    });
  }

  function handleAdditionalPromptChange(value) {
    state.additionalPrompt = value;
  }

  function handleAdditionalPromptSubmit() {
    const prompt = state.additionalPrompt.trim();

    if (!prompt) {
      return;
    }

    const nextAdditionalPrompts = [...state.additionalPrompts, prompt];
    const nextHistory = movePromptHistoryToTop(state.mainPrompt);
    const nextPromptSessions = {
      ...state.promptSessions,
      [state.mainPrompt]: {
        additionalPrompts: nextAdditionalPrompts,
        updatedAt: new Date().toISOString(),
      },
    };

    writeStoredPromptSessions(nextPromptSessions, state.currentUserId);
    setState({
      additionalPrompt: "",
      additionalPrompts: nextAdditionalPrompts,
      promptHistory: nextHistory,
      promptSessions: nextPromptSessions,
    });
  }

  function render() {
    appRoot.replaceChildren();

    if (!state.isLoggedIn || state.currentView === "login") {
      appRoot.appendChild(
        window.PublicDataDashboard.LoginPage({
          mode: state.currentView === "signup" ? "signup" : "login",
          authNotice: state.authNotice,
          onLogin: handleLogin,
          onSignup: handleSignup,
          onShowSignup: () => setState({ currentView: "signup", authNotice: "" }),
          onShowLogin: () => setState({ currentView: "login", authNotice: "" }),
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
