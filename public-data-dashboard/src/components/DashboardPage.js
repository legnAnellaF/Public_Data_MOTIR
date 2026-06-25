(function () {
  window.PublicDataDashboard = window.PublicDataDashboard || {};

  function DashboardPage({
    mainPrompt,
    additionalPrompt,
    additionalPrompts,
    onAdditionalPromptChange,
    onAdditionalPromptSubmit,
    isKeywordLoading,
    keywordResult,
    keywordError,
    selectedDatasetFile,
    isVisualizationLoading,
    visualizationResult,
    visualizationError,
    onDatasetFileChange,
    onVisualizationSubmit,
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
        <span>${escapeHtml(createVisualizationTitle(mainPrompt, additionalPrompts))}</span>
      </div>
    `;

    const actions = document.createElement("div");
    actions.className = "header-actions";

    const newPromptButton = document.createElement("button");
    newPromptButton.className = "ghost-button";
    newPromptButton.type = "button";
    newPromptButton.textContent = "새 채팅";
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

      const keywordStatus = createKeywordStatusBlock();

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
        children: [promptBlock, note, keywordStatus, list],
      });
    }


    function createKeywordStatusBlock() {
      const wrapper = document.createElement("div");
      wrapper.className = `keyword-status ${keywordError ? "error" : ""}`.trim();

      const label = document.createElement("span");
      label.textContent = "백엔드 키워드 API";

      const message = document.createElement("p");
      message.textContent = getKeywordMessage();

      wrapper.append(label, message);
      return wrapper;
    }

    function getKeywordMessage() {
      if (isKeywordLoading) {
        return "키워드 분석 중...";
      }

      if (keywordError) {
        return `백엔드 API 연결 실패 또는 키워드 추출 실패: ${keywordError}`;
      }

      const keywords = formatKeywordResult(keywordResult);

      if (keywords) {
        return `추출 키워드: ${keywords}`;
      }

      return "키워드 추출 결과가 아직 없습니다. 백엔드가 실행 중이면 프롬포트 제출 후 자동으로 표시됩니다.";
    }

    function formatKeywordResult(result) {
      if (!result || typeof result !== "object") {
        return "";
      }

      if (typeof result.topic === "string" && result.topic.trim()) {
        return result.topic.trim();
      }

      if (Array.isArray(result.keywords)) {
        return result.keywords.filter(Boolean).join(" ").trim();
      }

      return "";
    }

    function createAdditionalPromptPanel() {
      const wrapper = document.createElement("div");
      wrapper.className = "additional-prompt-chat";

      const conversation = document.createElement("div");
      conversation.className = "additional-chat-thread conversation-panel";
      conversation.setAttribute("aria-live", "polite");

      conversation.append(
        ...createAdditionalPromptExchange(
          mainPrompt,
          "최초 프롬포트를 기준으로 분석 목차, 시각화 영역, 데이터 코멘트 초안을 구성했습니다."
        )
      );

      additionalPrompts.forEach((prompt) => {
        conversation.append(...createAdditionalPromptExchange(prompt));
      });

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

    function createAdditionalPromptExchange(prompt, replyText = createAdditionalPromptReply(prompt)) {
      const userBubble = document.createElement("div");
      userBubble.className = "chat-bubble user-bubble additional-user-bubble";
      userBubble.textContent = prompt;

      const botBubble = document.createElement("div");
      botBubble.className = "chat-bubble bot-bubble additional-bot-bubble";
      botBubble.textContent = replyText;

      return [userBubble, botBubble];
    }

    function createAdditionalPromptReply(prompt) {
      return `추가 요청 "${prompt}"을(를) 세션에 저장했습니다. 실제 데이터 재분석 응답은 추후 백엔드 API 연결 후 제공됩니다.`;
    }

    function createVisualizationPanel() {
      const wrapper = document.createElement("div");
      wrapper.className = "visualization-workspace";

      const uploadBox = document.createElement("div");
      uploadBox.className = "dataset-upload-box";

      const uploadCopy = document.createElement("div");
      uploadCopy.className = "dataset-upload-copy";

      const uploadTitle = document.createElement("p");
      uploadTitle.textContent = "분석할 데이터 파일 업로드";

      const uploadHint = document.createElement("span");
      uploadHint.textContent = "지원 형식: .csv, .xlsx, .xls";

      uploadCopy.append(uploadTitle, uploadHint);

      const fileLabel = document.createElement("label");
      fileLabel.className = "dataset-file-label";
      fileLabel.setAttribute("for", "dataset-file-input");
      fileLabel.textContent = "파일 선택";

      const fileInput = document.createElement("input");
      fileInput.id = "dataset-file-input";
      fileInput.type = "file";
      fileInput.accept = ".csv,.xlsx,.xls";
      fileInput.className = "sr-only";
      fileInput.addEventListener("change", () => {
        const file = fileInput.files && fileInput.files.length > 0 ? fileInput.files[0] : null;
        onDatasetFileChange(file);
      });

      const selectedFileText = document.createElement("p");
      selectedFileText.className = `selected-file-name ${selectedDatasetFile ? "" : "empty"}`.trim();
      selectedFileText.textContent = selectedDatasetFile
        ? `선택된 파일: ${selectedDatasetFile.name}`
        : "선택된 파일이 없습니다. CSV/XLSX/XLS 파일을 선택해 주세요.";

      const runButton = document.createElement("button");
      runButton.className = "primary-button visualization-run-button";
      runButton.type = "button";
      runButton.textContent = isVisualizationLoading ? "분석 중..." : "시각화 실행";
      runButton.disabled = !selectedDatasetFile || isVisualizationLoading;
      runButton.addEventListener("click", onVisualizationSubmit);

      uploadBox.append(uploadCopy, fileLabel, fileInput, selectedFileText, runButton);
      wrapper.append(uploadBox, createVisualizationResultBlock());

      return window.PublicDataDashboard.Panel({
        title: createVisualizationTitle(mainPrompt, additionalPrompts),
        children: wrapper,
        className: "visual-panel",
      });
    }

    function createVisualizationResultBlock() {
      const resultBox = document.createElement("div");
      resultBox.className = "visualization-result";
      resultBox.setAttribute("aria-live", "polite");

      if (isVisualizationLoading) {
        const message = document.createElement("p");
        message.className = "visualization-status loading";
        message.textContent = "데이터 시각화 분석 중...";
        resultBox.appendChild(message);
        return resultBox;
      }

      if (visualizationError) {
        const message = document.createElement("p");
        message.className = "visualization-status error";
        message.textContent = `데이터 시각화 실패: ${visualizationError}`;
        resultBox.appendChild(message);
        return resultBox;
      }

      if (!visualizationResult) {
        const empty = document.createElement("div");
        empty.className = "visualization-empty";
        empty.innerHTML = `
          <p>파일을 업로드하면 /api/visualize 분석 결과가 이 영역에 표시됩니다.</p>
          <span>외부 차트 라이브러리 없이 Vanilla JS와 CSS로 간단한 그래프/표를 렌더링합니다.</span>
        `;
        resultBox.appendChild(empty);
        return resultBox;
      }

      resultBox.append(
        createResultSummary(visualizationResult),
        createChartPreview(visualizationResult),
        createDatasetList(visualizationResult.datasets),
        createLabelList(visualizationResult.labels),
        createResultTable(visualizationResult.table_data),
        createPrecautionList(visualizationResult.startup_precautions)
      );
      return resultBox;
    }

    function createResultSummary(result) {
      const summary = document.createElement("div");
      summary.className = "visualization-card result-summary-card";
      summary.append(
        createMetaItem("차트 제목", result.chart_title || "제목 없음"),
        createMetaItem("차트 유형", result.chart_type || "유형 미정"),
        createMetaItem("선택 이유", result.strategy_reason || "시각화 전략 설명이 없습니다.")
      );
      return summary;
    }

    function createMetaItem(labelText, valueText) {
      const item = document.createElement("div");
      item.className = "result-meta-item";
      const label = document.createElement("span");
      label.textContent = labelText;
      const value = document.createElement("p");
      value.textContent = valueText;
      item.append(label, value);
      return item;
    }

    function createChartPreview(result) {
      const card = document.createElement("div");
      card.className = "visualization-card";
      const title = document.createElement("h3");
      title.textContent = "간단 시각화";
      card.appendChild(title);

      const labels = Array.isArray(result.labels) ? result.labels : [];
      const firstDataset = Array.isArray(result.datasets) ? result.datasets[0] : null;
      const data = firstDataset && Array.isArray(firstDataset.data) ? firstDataset.data : [];

      if (result.chart_type === "bar" && labels.length && data.length) {
        card.appendChild(createBarChart(labels, data));
      } else {
        const fallback = document.createElement("p");
        fallback.className = "muted-text compact";
        fallback.textContent = "line/pie 또는 기타 유형은 현재 요약, 라벨, 데이터셋, 표 중심으로 표시합니다.";
        card.appendChild(fallback);
      }
      return card;
    }

    function createBarChart(labels, data) {
      const chart = document.createElement("div");
      chart.className = "css-bar-chart";
      const numericValues = data.map((value) => Number(value)).filter((value) => Number.isFinite(value));
      const maxValue = Math.max(...numericValues, 1);

      labels.slice(0, 12).forEach((label, index) => {
        const value = Number(data[index]);
        const safeValue = Number.isFinite(value) ? value : 0;
        const row = document.createElement("div");
        row.className = "css-bar-row";
        const labelEl = document.createElement("span");
        labelEl.className = "css-bar-label";
        labelEl.textContent = String(label);
        const track = document.createElement("div");
        track.className = "css-bar-track";
        const bar = document.createElement("span");
        bar.className = "css-bar-fill";
        bar.style.width = `${Math.max(4, (safeValue / maxValue) * 100)}%`;
        const valueEl = document.createElement("span");
        valueEl.className = "css-bar-value";
        valueEl.textContent = String(data[index]);
        track.append(bar, valueEl);
        row.append(labelEl, track);
        chart.appendChild(row);
      });

      if (labels.length > 12) {
        const note = document.createElement("p");
        note.className = "partial-note";
        note.textContent = `막대그래프는 처음 12개 항목만 표시합니다. 전체 라벨 수: ${labels.length}개`;
        chart.appendChild(note);
      }
      return chart;
    }

    function createDatasetList(datasets) {
      const card = document.createElement("div");
      card.className = "visualization-card";
      const title = document.createElement("h3");
      title.textContent = "datasets";
      const list = document.createElement("ul");
      list.className = "result-data-list";
      (Array.isArray(datasets) ? datasets : []).forEach((dataset) => {
        const item = document.createElement("li");
        const data = Array.isArray(dataset.data) ? dataset.data : [];
        item.textContent = `${dataset.label || "데이터셋"}: ${data.slice(0, 12).join(", ")}${data.length > 12 ? " ..." : ""}`;
        list.appendChild(item);
      });
      if (!list.children.length) {
        const item = document.createElement("li");
        item.textContent = "표시할 datasets가 없습니다.";
        list.appendChild(item);
      }
      card.append(title, list);
      return card;
    }

    function createLabelList(labels) {
      const card = document.createElement("div");
      card.className = "visualization-card";
      const title = document.createElement("h3");
      title.textContent = "labels";
      const text = document.createElement("p");
      const safeLabels = Array.isArray(labels) ? labels : [];
      text.textContent = safeLabels.length ? safeLabels.slice(0, 20).join(", ") : "표시할 labels가 없습니다.";
      card.append(title, text);
      if (safeLabels.length > 20) {
        const note = document.createElement("p");
        note.className = "partial-note";
        note.textContent = `처음 20개 라벨만 표시합니다. 전체 라벨 수: ${safeLabels.length}개`;
        card.appendChild(note);
      }
      return card;
    }

    function createResultTable(tableData) {
      const card = document.createElement("div");
      card.className = "visualization-card table-card";
      const title = document.createElement("h3");
      title.textContent = "table_data";
      card.appendChild(title);

      const headers = tableData && Array.isArray(tableData.headers) ? tableData.headers : [];
      const rows = tableData && Array.isArray(tableData.rows) ? tableData.rows : [];
      if (!headers.length || !rows.length) {
        const empty = document.createElement("p");
        empty.className = "muted-text compact";
        empty.textContent = "표시할 table_data.headers 또는 table_data.rows가 없습니다.";
        card.appendChild(empty);
        return card;
      }

      const tableWrapper = document.createElement("div");
      tableWrapper.className = "result-table-wrapper";
      const table = document.createElement("table");
      table.className = "result-table";
      const thead = document.createElement("thead");
      const headRow = document.createElement("tr");
      headers.forEach((headerText) => {
        const th = document.createElement("th");
        th.textContent = String(headerText);
        headRow.appendChild(th);
      });
      thead.appendChild(headRow);

      const tbody = document.createElement("tbody");
      rows.slice(0, 15).forEach((row) => {
        const tr = document.createElement("tr");
        const cells = Array.isArray(row) ? row : headers.map((header) => row && row[header]);
        headers.forEach((_, index) => {
          const td = document.createElement("td");
          td.textContent = cells[index] == null ? "" : String(cells[index]);
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
      table.append(thead, tbody);
      tableWrapper.appendChild(table);
      card.appendChild(tableWrapper);

      if (rows.length > 15) {
        const note = document.createElement("p");
        note.className = "partial-note";
        note.textContent = `처음 15개 행만 일부만 표시합니다. 전체 행 수: ${rows.length}개`;
        card.appendChild(note);
      }
      return card;
    }

    function createPrecautionList(precautions) {
      const card = document.createElement("div");
      card.className = "visualization-card";
      const title = document.createElement("h3");
      title.textContent = "startup_precautions";
      const list = document.createElement("ul");
      list.className = "precaution-list";
      const items = Array.isArray(precautions) ? precautions : [];
      items.forEach((precaution) => {
        const li = document.createElement("li");
        li.textContent = String(precaution);
        list.appendChild(li);
      });
      if (!items.length) {
        const li = document.createElement("li");
        li.textContent = "표시할 창업 유의사항이 없습니다.";
        list.appendChild(li);
      }
      card.append(title, list);
      return card;
    }

    function createVisualizationTitle(prompt, prompts) {
      const latestPrompt = prompts.length > 0 ? prompts[prompts.length - 1] : prompt;
      const compactPrompt = latestPrompt.replace(/\s+/g, " ").trim();
      const description =
        compactPrompt.length > 28 ? `${compactPrompt.slice(0, 28)}...` : compactPrompt;

      return description ? `시각화 보드 - ${description}` : "시각화 보드";
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

      const keywordBubble = document.createElement("div");
      keywordBubble.className = `chat-bubble bot-bubble keyword-bubble ${keywordError ? "keyword-error" : ""}`.trim();
      keywordBubble.textContent = getKeywordMessage();

      const botBubbleSecond = document.createElement("div");
      botBubbleSecond.className = "chat-bubble bot-bubble muted-bubble";
      botBubbleSecond.textContent =
        "추후 이 영역에서는 그래프 해석, 데이터 경향, 종합 의견이 챗봇 형태로 출력됩니다.";

      wrapper.append(userBubble, botBubble, keywordBubble, botBubbleSecond);

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
