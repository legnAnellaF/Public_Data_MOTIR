(function () {
  window.PublicDataDashboard = window.PublicDataDashboard || {};

  function PromptPage({
    promptHistory = [],
    onSubmit,
    onHistorySelect,
    onHistoryRemove,
    onLogout,
  }) {
    const page = document.createElement("main");
    page.className = "prompt-page";

    const header = document.createElement("header");
    header.className = "app-header";
    header.innerHTML = `
      <div class="header-brand">
        <span class="brand-mark small" aria-hidden="true">D</span>
        <span>공공데이터 시각화</span>
      </div>
    `;

    const logoutButton = document.createElement("button");
    logoutButton.className = "ghost-button";
    logoutButton.type = "button";
    logoutButton.textContent = "로그아웃";
    logoutButton.addEventListener("click", onLogout);
    header.appendChild(logoutButton);

    const workspace = document.createElement("div");
    workspace.className = "prompt-workspace";

    const sidebar = createPromptHistorySidebar();

    const content = document.createElement("section");
    content.className = "prompt-content";

    const title = document.createElement("h1");
    title.textContent = "어떤 공공데이터를 시각화할까요?";

    const form = document.createElement("form");
    form.className = "prompt-composer";

    const label = document.createElement("label");
    label.className = "sr-only";
    label.setAttribute("for", "main-prompt");
    label.textContent = "프롬포트";

    const textarea = document.createElement("textarea");
    textarea.id = "main-prompt";
    textarea.rows = 4;
    textarea.placeholder = "분석하고 싶은 공공데이터 주제를 입력하세요";

    const footer = document.createElement("div");
    footer.className = "composer-footer";

    const error = document.createElement("p");
    error.className = "form-error compact";
    error.setAttribute("role", "alert");

    const button = document.createElement("button");
    button.className = "primary-button";
    button.type = "submit";
    button.textContent = "전송";
    button.disabled = true;

    footer.append(error, button);
    form.append(label, textarea, footer);
    content.append(title, form);
    workspace.append(sidebar, content);
    page.append(header, workspace);

    function createPromptHistorySidebar() {
      const sidebar = document.createElement("aside");
      sidebar.className = "prompt-sidebar";

      const heading = document.createElement("h2");
      heading.textContent = "채팅 기록";

      const list = document.createElement("ul");
      list.className = "prompt-history-list";

      if (promptHistory.length === 0) {
        const empty = document.createElement("li");
        empty.className = "prompt-history-empty";
        empty.textContent = "저장된 프롬포트가 없습니다.";
        list.appendChild(empty);
      } else {
        promptHistory.forEach((historyItem) => {
          const item = document.createElement("li");
          item.className = "prompt-history-item";

          const selectButton = document.createElement("button");
          selectButton.className = "prompt-history-select";
          selectButton.type = "button";
          selectButton.textContent = historyItem.text;
          selectButton.title = historyItem.text;
          selectButton.addEventListener("click", () => {
            onHistorySelect(historyItem.text);
          });

          const removeButton = document.createElement("button");
          removeButton.className = "prompt-history-remove";
          removeButton.type = "button";
          removeButton.textContent = "삭제";
          removeButton.setAttribute(
            "aria-label",
            `${historyItem.text} 프롬포트 삭제`
          );
          removeButton.addEventListener("click", () => {
            onHistoryRemove(historyItem.id);
          });

          item.append(selectButton, removeButton);
          list.appendChild(item);
        });
      }

      sidebar.append(heading, list);
      return sidebar;
    }

    function submitPrompt() {
      const prompt = textarea.value.trim();

      if (!prompt) {
        error.textContent = "프롬포트를 입력해 주세요.";
        button.disabled = true;
        return;
      }

      error.textContent = "";
      onSubmit(prompt);
    }

    textarea.addEventListener("input", () => {
      const hasValue = textarea.value.trim().length > 0;
      button.disabled = !hasValue;

      if (hasValue) {
        error.textContent = "";
      }
    });

    textarea.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        submitPrompt();
      }
    });

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      submitPrompt();
    });

    return page;
  }

  window.PublicDataDashboard.PromptPage = PromptPage;
})();
