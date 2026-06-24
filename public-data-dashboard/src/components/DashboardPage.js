(function () {
  window.PublicDataDashboard = window.PublicDataDashboard || {};

  function DashboardPage({
    mainPrompt,
    additionalPrompt,
    additionalPrompts,
    onAdditionalPromptChange,
    onAdditionalPromptSubmit,
    onNewPrompt,
    onLogout,
  }) {
    const page = document.createElement("main");
    page.className = "dashboard-page";

    const header = document.createElement("header");
    header.className = "app-header dashboard-header";
    header.innerHTML = `
      <div class="header-brand">
        <span class="brand-mark small" aria-hidden="true">D</span>
        <span>공공데이터 시각화</span>
      </div>
      <div class="dashboard-meta">
        <span class="status-dot" aria-hidden="true"></span>
        <span>${escapeHtml(mainPrompt)} 분석 보드</span>
      </div>
    `;

    const actions = document.createElement("div");
    actions.className = "header-actions";

    const newPromptButton = document.createElement("button");
    newPromptButton.className = "ghost-button";
    newPromptButton.type = "button";
    newPromptButton.textContent = "새 프롬포트";
    newPromptButton.addEventListener("click", onNewPrompt);

    const logoutButton = document.createElement("button");
    logoutButton.className = "ghost-button";
    logoutButton.type = "button";
    logoutButton.textContent = "로그아웃";
    logoutButton.addEventListener("click", onLogout);

    actions.append(newPromptButton, logoutButton);
    header.appendChild(actions);

    const layout = document.createElement("section");
    layout.className = "dashboard-layout";

    const leftColumn = document.createElement("div");
    leftColumn.className = "dashboard-column left-column";

    const rightColumn = document.createElement("div");
    rightColumn.className = "dashboard-column right-column";

    leftColumn.append(createOutlinePanel(mainPrompt), createAdditionalPromptPanel());
    rightColumn.append(createVisualizationPanel(), createCommentPanel(mainPrompt));
    layout.append(leftColumn, rightColumn);
    page.append(header, layout);

    function createOutlinePanel(prompt) {
      const promptBlock = document.createElement("div");
      promptBlock.className = "prompt-summary";

      const promptLabel = document.createElement("span");
      promptLabel.textContent = "최초 프롬포트";

      const promptText = document.createElement("p");
      promptText.textContent = prompt;

      promptBlock.append(promptLabel, promptText);

      const note = document.createElement("p");
      note.className = "muted-text";
      note.textContent = "추후 이 영역에는 입력 프롬포트 기반 자동 목차가 표시됩니다.";

      const list = document.createElement("ol");
      list.className = "outline-list";
      ["키워드 분석", "관련 공공데이터 탐색", "통계 데이터 시각화", "종합 의견"].forEach(
        (item) => {
          const li = document.createElement("li");
          li.textContent = item;
          list.appendChild(li);
        }
      );

      return window.PublicDataDashboard.Panel({
        title: "분석 목차",
        children: [promptBlock, note, list],
      });
    }

    function createAdditionalPromptPanel() {
      const wrapper = document.createElement("div");
      wrapper.className = "additional-prompt-chat";

      const conversation = document.createElement("div");
      conversation.className = "additional-chat-thread conversation-panel";
      conversation.setAttribute("aria-live", "polite");

      if (additionalPrompts.length === 0) {
        const empty = document.createElement("div");
        empty.className = "chat-empty-state";
        empty.textContent = "추가로 궁금한 점을 입력하면 이곳에 대화형 요청 기록이 표시됩니다.";
        conversation.appendChild(empty);
      } else {
        additionalPrompts.forEach((prompt) => {
          conversation.append(...createAdditionalPromptExchange(prompt));
        });
      }

      const form = document.createElement("form");
      form.className = "inline-composer chat-composer";

      const label = document.createElement("label");
      label.className = "sr-only";
      label.setAttribute("for", "additional-prompt");
      label.textContent = "추가 프롬포트";

      const textarea = document.createElement("textarea");
      textarea.id = "additional-prompt";
      textarea.rows = 3;
      textarea.value = additionalPrompt;
      textarea.placeholder = "예: 이 데이터에서 지역별 차이도 비교해줘";

      const button = document.createElement("button");
      button.className = "primary-button";
      button.type = "submit";
      button.textContent = "전송";
      button.disabled = additionalPrompt.trim().length === 0;

      form.append(label, textarea, button);

      textarea.addEventListener("input", () => {
        onAdditionalPromptChange(textarea.value);
        button.disabled = textarea.value.trim().length === 0;
      });

      textarea.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          if (textarea.value.trim()) {
            onAdditionalPromptSubmit();
          }
        }
      });

      form.addEventListener("submit", (event) => {
        event.preventDefault();
        onAdditionalPromptSubmit();
      });

      wrapper.append(conversation, form);

      return window.PublicDataDashboard.Panel({
        title: "추가 프롬포트 대화",
        children: wrapper,
        className: "conversation-panel-shell",
      });
    }

    function createAdditionalPromptExchange(prompt) {
      const userBubble = document.createElement("div");
      userBubble.className = "chat-bubble user-bubble additional-user-bubble";
      userBubble.textContent = prompt;

      const botBubble = document.createElement("div");
      botBubble.className = "chat-bubble bot-bubble additional-bot-bubble";
      botBubble.textContent = createAdditionalPromptReply(prompt);

      return [userBubble, botBubble];
    }

    function createAdditionalPromptReply(prompt) {
      return `추가 요청 "${prompt}"을(를) 세션에 저장했습니다. 실제 데이터 재분석 응답은 추후 백엔드 API 연결 후 제공됩니다.`;
    }

    function createVisualizationPanel() {
      const chart = document.createElement("div");
      chart.className = "chart-placeholder";

      const chartBars = document.createElement("div");
      chartBars.className = "chart-bars";

      [42, 68, 52, 86, 61, 74].forEach((height) => {
        const bar = document.createElement("span");
        bar.style.height = `${height}%`;
        chartBars.appendChild(bar);
      });

      const chartCopy = document.createElement("div");
      chartCopy.className = "placeholder-copy";
      chartCopy.innerHTML = `
        <p>추후 공공데이터 기반 그래프가 이 영역에 표시됩니다.</p>
        <span>막대그래프, 선그래프, 표, 지도 등 시각자료 출력 예정</span>
      `;

      chart.append(chartBars, chartCopy);

      return window.PublicDataDashboard.Panel({
        title: `시각화 보드: ${mainPrompt}`,
        children: chart,
        className: "visual-panel",
      });
    }

    function createCommentPanel(prompt) {
      const wrapper = document.createElement("div");
      wrapper.className = "comment-thread";

      const userBubble = document.createElement("div");
      userBubble.className = "chat-bubble user-bubble";
      userBubble.textContent = prompt;

      const botBubble = document.createElement("div");
      botBubble.className = "chat-bubble bot-bubble";
      botBubble.textContent =
        "입력한 프롬포트를 바탕으로 데이터 분석 코멘트가 이곳에 표시됩니다.";

      const botBubbleSecond = document.createElement("div");
      botBubbleSecond.className = "chat-bubble bot-bubble muted-bubble";
      botBubbleSecond.textContent =
        "추후 이 영역에서는 그래프 해석, 데이터 경향, 종합 의견이 챗봇 형태로 출력됩니다.";

      wrapper.append(userBubble, botBubble, botBubbleSecond);

      return window.PublicDataDashboard.Panel({
        title: "데이터 코멘트",
        children: wrapper,
      });
    }

    return page;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  window.PublicDataDashboard.DashboardPage = DashboardPage;
})();
