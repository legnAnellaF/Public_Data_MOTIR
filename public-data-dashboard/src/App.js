(function () {
  const appRoot = document.getElementById("app");
  const storageKey = "publicDataDashboardLoggedIn";
  const promptHistoryStorageKey = "publicDataDashboardPromptHistory";

  function readStoredLogin() {
    try {
      return localStorage.getItem(storageKey) === "true";
    } catch (error) {
      return false;
    }
  }

  function writeStoredLogin(value) {
    try {
      if (value) {
        localStorage.setItem(storageKey, "true");
      } else {
        localStorage.removeItem(storageKey);
      }
    } catch (error) {
      // 저장소 접근이 제한된 환경에서는 현재 세션 상태만 유지한다.
    }
  }

  function readStoredPromptHistory() {
    try {
      const storedValue = localStorage.getItem(promptHistoryStorageKey);
      const parsedValue = storedValue ? JSON.parse(storedValue) : [];

      if (!Array.isArray(parsedValue)) {
        return [];
      }

      return parsedValue.filter((item) => item && item.id && item.text);
    } catch (error) {
      return [];
    }
  }

  function writeStoredPromptHistory(history) {
    try {
      localStorage.setItem(promptHistoryStorageKey, JSON.stringify(history));
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

    writeStoredPromptHistory(nextHistory);
    return nextHistory;
  }

  const storedLogin = readStoredLogin();
  const storedPromptHistory = readStoredPromptHistory();

  const state = {
    isLoggedIn: storedLogin,
    currentView: storedLogin ? "prompt" : "login",
    mainPrompt: "",
    additionalPrompt: "",
    additionalPrompts: [],
    promptHistory: storedPromptHistory,
  };

  function setState(nextState) {
    Object.assign(state, nextState);
    render();
  }

  function handleLogin() {
    writeStoredLogin(true);
    setState({
      isLoggedIn: true,
      currentView: "prompt",
    });
  }

  function handleLogout() {
    writeStoredLogin(false);
    setState({
      isLoggedIn: false,
      currentView: "login",
      mainPrompt: "",
      additionalPrompt: "",
      additionalPrompts: [],
    });
  }

  function handleMainPromptSubmit(prompt) {
    const nextHistory = rememberPrompt(prompt);

    setState({
      mainPrompt: prompt,
      currentView: "dashboard",
      additionalPrompt: "",
      additionalPrompts: [],
      promptHistory: nextHistory,
    });
  }

  function handlePromptHistorySelect(prompt) {
    setState({
      mainPrompt: prompt,
      currentView: "dashboard",
      additionalPrompt: "",
      additionalPrompts: [],
    });
  }

  function handlePromptHistoryRemove(promptId) {
    const nextHistory = state.promptHistory.filter((item) => item.id !== promptId);

    writeStoredPromptHistory(nextHistory);
    setState({
      promptHistory: nextHistory,
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

    setState({
      additionalPrompt: "",
      additionalPrompts: [...state.additionalPrompts, prompt],
    });
  }

  function render() {
    appRoot.replaceChildren();

    if (!state.isLoggedIn || state.currentView === "login") {
      appRoot.appendChild(
        window.PublicDataDashboard.LoginPage({
          onLogin: handleLogin,
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
