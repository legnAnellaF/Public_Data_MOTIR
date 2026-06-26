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
    isDatasetSearchLoading,
    datasetSearchResult,
    datasetSearchError,
    selectedDataset,
    isDatasetDetailLoading,
    datasetDetailResult,
    datasetDetailError,
    selectedResource,
    isResourcePreviewLoading,
    resourcePreviewResult,
    resourcePreviewError,
    isResourceVisualizationLoading,
    resourceVisualizationError,
    onDatasetSearchSubmit,
    onDatasetSelect,
    onResourcePreview,
    onResourceVisualization,
    selectedDatasetFile,
    isVisualizationLoading,
    visualizationResult,
    visualizationError,
    onDatasetFileChange,
    onVisualizationSubmit,
    apiBaseUrl,
    apiBaseUrlSource,
    apiHealth,
    onApiConnectionCheck,
    onApiBaseUrlSave,
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

    leftColumn.append(createApiConnectionPanel(), createOutlinePanel(mainPrompt), createAdditionalPromptPanel());
    rightColumn.append(createDatasetSearchPanel(), createVisualizationPanel(), createCommentPanel(mainPrompt));
    layout.append(leftColumn, rightColumn);
    page.append(header, layout);


    function createApiConnectionPanel() {
      const wrapper = document.createElement("div");
      wrapper.className = "api-connection-panel";

      const baseLabel = document.createElement("p");
      baseLabel.className = "api-base-url";
      baseLabel.textContent = `현재 API base URL: ${apiBaseUrl || "설정 없음"}`;

      const source = document.createElement("p");
      source.className = "muted-text compact";
      source.textContent = `설정 출처: ${apiBaseUrlSource || "unknown"}`;

      const status = document.createElement("p");
      const health = apiHealth && typeof apiHealth === "object" ? apiHealth : {};
      status.className = `api-health-status ${health.status || "idle"}`;
      status.textContent = getApiHealthMessage(health);

      const actions = document.createElement("div");
      actions.className = "api-connection-actions";

      const checkButton = document.createElement("button");
      checkButton.type = "button";
      checkButton.className = "ghost-button";
      checkButton.textContent = health.status === "checking" ? "확인 중..." : "API 연결 다시 확인";
      checkButton.disabled = health.status === "checking";
      checkButton.addEventListener("click", () => onApiConnectionCheck());

      actions.appendChild(checkButton);

      const form = document.createElement("form");
      form.className = "api-base-url-form";
      const input = document.createElement("input");
      input.type = "url";
      input.placeholder = "https://YOUR-BACKEND-URL";
      input.value = apiBaseUrl || "";
      input.setAttribute("aria-label", "Backend API base URL");
      const saveButton = document.createElement("button");
      saveButton.type = "submit";
      saveButton.className = "primary-button";
      saveButton.textContent = "URL 적용";
      form.append(input, saveButton);
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        onApiBaseUrlSave(input.value);
      });

      const hint = document.createElement("p");
      hint.className = "muted-text compact";
      hint.textContent = "백엔드 URL만 입력하세요. API key나 secret은 프론트엔드에 저장하지 않습니다.";

      wrapper.append(baseLabel, source, status, actions, form, hint);
      return window.PublicDataDashboard.Panel({
        title: "API 연결 상태",
        children: wrapper,
        className: "api-connection-shell",
      });
    }

    function getApiHealthMessage(health) {
      if (health.status === "success") {
        return `/api/health 성공: ${health.message || "연결됨"}`;
      }
      if (health.status === "error") {
        return `/api/health 실패: ${health.message || "백엔드 API에 연결할 수 없습니다. API base URL과 배포 상태를 확인하세요."}`;
      }
      if (health.status === "checking") {
        return health.message || "/api/health 확인 중...";
      }
      return "/api/health 미확인: 버튼을 눌러 연결 상태를 확인하세요.";
    }

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

    function createDatasetSearchPanel() {
      const wrapper = document.createElement("div");
      wrapper.className = "dataset-search-section";

      const intro = document.createElement("p");
      intro.className = "muted-text compact";
      intro.textContent = "키워드 기반 공공데이터포털 데이터셋 후보를 검색합니다. 이번 단계에서는 후보 표시와 선택만 지원합니다.";

      const form = document.createElement("form");
      form.className = "dataset-search-form";

      const input = document.createElement("input");
      input.type = "search";
      input.value = getDatasetSearchQuery();
      input.placeholder = "예: 서울 빈집";
      input.setAttribute("aria-label", "공공데이터 검색 키워드");

      const button = document.createElement("button");
      button.type = "submit";
      button.className = "primary-button";
      button.textContent = isDatasetSearchLoading ? "검색 중..." : "후보 검색";
      button.disabled = isDatasetSearchLoading;

      form.append(input, button);
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        onDatasetSearchSubmit(input.value);
      });

      wrapper.append(intro, form, createDatasetSearchResultBlock());

      return window.PublicDataDashboard.Panel({
        title: "공공데이터 후보",
        children: wrapper,
        className: "dataset-search-panel",
      });
    }

    function getDatasetSearchQuery() {
      if (datasetSearchResult && typeof datasetSearchResult.query === "string") {
        return datasetSearchResult.query;
      }

      const keywordText = formatKeywordResult(keywordResult);
      return keywordText || mainPrompt || "";
    }

    function createDatasetSearchResultBlock() {
      const resultBox = document.createElement("div");
      resultBox.className = "dataset-search-results";
      resultBox.setAttribute("aria-live", "polite");

      if (isDatasetSearchLoading) {
        resultBox.appendChild(createDatasetStatus("loading", "공공데이터 후보를 검색 중입니다..."));
        return resultBox;
      }

      if (datasetSearchError) {
        resultBox.appendChild(createDatasetStatus("error", `공공데이터 후보 검색 실패: ${datasetSearchError}`));
        return resultBox;
      }

      const items = datasetSearchResult && Array.isArray(datasetSearchResult.items)
        ? datasetSearchResult.items
        : [];

      if (!datasetSearchResult) {
        resultBox.appendChild(createDatasetStatus("empty", "키워드 추출 후 자동 검색을 시도하거나 직접 검색어를 입력해 후보를 확인할 수 있습니다."));
        return resultBox;
      }

      if (!items.length) {
        resultBox.appendChild(createDatasetStatus("empty", "검색된 공공데이터 후보가 없습니다. 다른 키워드로 다시 검색해 보세요."));
        return resultBox;
      }

      const list = document.createElement("div");
      list.className = "dataset-candidate-list";
      items.forEach((item) => list.appendChild(createDatasetCandidateCard(item)));
      resultBox.appendChild(list);

      if (selectedDataset) {
        const notice = document.createElement("p");
        notice.className = "selected-dataset-notice";
        notice.textContent = "실제 다운로드 및 자동 시각화 연결은 후속 작업입니다.";
        resultBox.appendChild(notice);
        resultBox.appendChild(createSelectedDatasetDetailBlock());
      }

      return resultBox;
    }


    function createSelectedDatasetDetailBlock() {
      const section = document.createElement("section");
      section.className = "selected-dataset-detail-section";

      const title = document.createElement("h3");
      title.textContent = "선택한 데이터셋 상세";
      section.appendChild(title);

      if (isDatasetDetailLoading) {
        section.appendChild(createDatasetStatus("loading", "선택한 데이터셋 상세 metadata와 리소스 후보를 조회 중입니다..."));
        return section;
      }

      if (datasetDetailError) {
        section.appendChild(createDatasetStatus("error", `선택한 데이터셋 상세 조회 실패: ${datasetDetailError}`));
        return section;
      }

      if (!datasetDetailResult) {
        section.appendChild(createDatasetStatus("empty", "데이터셋을 선택하면 상세 metadata와 다운로드/API 링크 후보가 표시됩니다."));
        return section;
      }

      const detail = datasetDetailResult.dataset && typeof datasetDetailResult.dataset === "object"
        ? datasetDetailResult.dataset
        : selectedDataset || {};
      const resources = Array.isArray(datasetDetailResult.resources) ? datasetDetailResult.resources : [];

      section.append(createDatasetDetailCard(detail), createResourceCandidateBlock(resources));
      return section;
    }

    function createDatasetDetailCard(detail) {
      const card = document.createElement("article");
      card.className = "dataset-detail-card";

      const heading = document.createElement("h4");
      heading.textContent = detail.title || "제목 없는 데이터셋";

      const description = document.createElement("p");
      description.className = "dataset-description";
      description.textContent = detail.description || "설명이 제공되지 않았습니다.";

      const meta = document.createElement("dl");
      meta.className = "dataset-detail-meta-grid";
      appendDatasetMeta(meta, "제공기관", detail.provider || "미상");
      appendDatasetMeta(meta, "형식", detail.format || "형식 미정");
      appendDatasetMeta(meta, "업데이트", detail.updated_at || "날짜 없음");
      appendDatasetMeta(meta, "분류", detail.category || "미분류");

      card.append(heading, description, meta);
      if (detail.url) {
        const link = document.createElement("a");
        link.className = "dataset-detail-link";
        link.href = detail.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = "상세 페이지 새 탭에서 열기";
        card.appendChild(link);
      }
      return card;
    }

    function createResourceCandidateBlock(resources) {
      const wrapper = document.createElement("div");
      wrapper.className = "resource-candidate-section";

      const heading = document.createElement("h4");
      heading.textContent = "다운로드/API 링크 후보";
      wrapper.appendChild(heading);

      if (!resources.length) {
        wrapper.appendChild(createDatasetStatus("empty", "표시할 다운로드/API 링크 후보가 없습니다. 실제 endpoint 연결은 후속 작업에서 보강합니다."));
        return wrapper;
      }

      const list = document.createElement("div");
      list.className = "resource-candidate-list";
      resources.forEach((resource) => list.appendChild(createResourceCandidateCard(resource)));
      wrapper.appendChild(list);
      wrapper.appendChild(createResourcePreviewBlock());
      return wrapper;
    }

    function createResourceCandidateCard(resource) {
      const item = resource && typeof resource === "object" ? resource : {};
      const card = document.createElement("article");
      card.className = "resource-candidate-card";

      const header = document.createElement("div");
      header.className = "resource-card-header";
      const title = document.createElement("h5");
      title.textContent = item.name || "리소스 후보";
      const format = document.createElement("span");
      format.className = "dataset-format-badge";
      format.textContent = item.format || "unknown";
      header.append(title, format);

      const description = document.createElement("p");
      description.className = "dataset-description";
      description.textContent = item.description || "설명이 제공되지 않았습니다.";

      const flags = document.createElement("p");
      flags.className = "resource-flags";
      flags.textContent = `${item.is_downloadable ? "다운로드 후보" : "다운로드 여부 미확정"} · ${item.is_api ? "API 후보" : "파일/링크 후보"}`;

      card.append(header, description, flags);
      if (item.url) {
        const previewButton = document.createElement("button");
        previewButton.type = "button";
        previewButton.className = isSameResource(item, selectedResource) ? "primary-button" : "ghost-button";
        previewButton.textContent = isSameResource(item, selectedResource) && isResourcePreviewLoading ? "미리보기 중..." : "미리보기";
        previewButton.disabled = isResourcePreviewLoading || !isPreviewableResource(item);
        previewButton.addEventListener("click", () => onResourcePreview(item));
        card.appendChild(previewButton);

        const visualizeButton = document.createElement("button");
        visualizeButton.type = "button";
        visualizeButton.className = "resource-visualize-button ghost-button";
        const isSelectedForVisualization = isSameResource(item, selectedResource) && isResourceVisualizationLoading;
        visualizeButton.textContent = isSelectedForVisualization ? "선택한 리소스를 분석 중..." : "이 리소스로 시각화";
        visualizeButton.disabled = isResourceVisualizationLoading || !isVisualizableResource(item);
        visualizeButton.addEventListener("click", () => onResourceVisualization(item));
        card.appendChild(visualizeButton);

        if (!isPreviewableResource(item)) {
          const hint = document.createElement("p");
          hint.className = "resource-preview-hint";
          hint.textContent = "원격 미리보기/자동 분석은 CSV/TSV/JSON만 지원합니다. 원격 Excel은 아직 자동 분석하지 않으며 직접 파일 업로드를 사용하세요.";
          card.appendChild(hint);
        }

        const link = document.createElement("a");
        link.className = "dataset-detail-link resource-url-link";
        link.href = item.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = "URL 새 탭에서 열기";
        card.appendChild(link);
      }
      return card;
    }


    function createResourcePreviewBlock() {
      const block = document.createElement("section");
      block.className = "resource-preview-card";

      const title = document.createElement("h4");
      title.textContent = "선택 리소스 미리보기";
      const scope = document.createElement("p");
      scope.className = "muted-text compact";
      scope.textContent = "미리보기는 소량만 가져옵니다. 전체 분석은 사용자가 ‘이 리소스로 시각화’를 명시적으로 눌렀을 때만 실행됩니다.";
      block.append(title, scope);

      if (isResourceVisualizationLoading) {
        block.appendChild(createDatasetStatus("loading", "선택한 리소스를 분석 중..."));
      }

      if (resourceVisualizationError) {
        block.appendChild(createDatasetStatus("error", `리소스 시각화 실패: ${resourceVisualizationError}`));
      }

      if (isResourcePreviewLoading) {
        block.appendChild(createDatasetStatus("loading", "선택한 resource URL을 안전하게 검사하고 미리보기를 가져오는 중입니다..."));
        return block;
      }

      if (resourcePreviewError) {
        block.appendChild(createDatasetStatus("error", `리소스 미리보기 실패: ${resourcePreviewError}`));
        return block;
      }

      if (!resourcePreviewResult || !resourcePreviewResult.preview) {
        block.appendChild(createDatasetStatus("empty", "리소스 후보의 미리보기 버튼을 누르면 CSV/TSV/JSON 일부가 여기에 표시됩니다."));
        return block;
      }

      const meta = resourcePreviewResult.metadata && typeof resourcePreviewResult.metadata === "object"
        ? resourcePreviewResult.metadata
        : {};
      const metaText = document.createElement("p");
      metaText.className = "resource-preview-meta";
      metaText.textContent = `content-type: ${meta.content_type || "unknown"} · bytes read: ${meta.bytes_read || 0}`;
      block.appendChild(metaText);

      if (resourcePreviewResult.preview.kind === "table") {
        block.appendChild(createResourcePreviewTable(resourcePreviewResult.preview));
      } else if (resourcePreviewResult.preview.kind === "json") {
        const pre = document.createElement("pre");
        pre.className = "resource-json-preview";
        pre.textContent = JSON.stringify(resourcePreviewResult.preview.data, null, 2);
        block.appendChild(pre);
      } else {
        block.appendChild(createDatasetStatus("empty", resourcePreviewResult.preview.message || "표시 가능한 preview가 없습니다."));
      }

      const message = document.createElement("p");
      message.className = "resource-preview-hint";
      message.textContent = resourcePreviewResult.preview.message || "소량 preview만 표시합니다.";
      block.appendChild(message);

      if (selectedResource && isVisualizableResource(selectedResource)) {
        const visualizeButton = document.createElement("button");
        visualizeButton.type = "button";
        visualizeButton.className = "primary-button resource-visualize-button";
        visualizeButton.textContent = isResourceVisualizationLoading ? "선택한 리소스를 분석 중..." : "이 리소스로 시각화";
        visualizeButton.disabled = isResourceVisualizationLoading;
        visualizeButton.addEventListener("click", () => onResourceVisualization(selectedResource));
        block.appendChild(visualizeButton);
      }
      return block;
    }

    function createResourcePreviewTable(preview) {
      const tableWrapper = document.createElement("div");
      tableWrapper.className = "resource-preview-table-wrap";
      const table = document.createElement("table");
      table.className = "resource-preview-table";
      const thead = document.createElement("thead");
      const headRow = document.createElement("tr");
      (Array.isArray(preview.headers) ? preview.headers : []).forEach((header) => {
        const th = document.createElement("th");
        th.textContent = String(header || "");
        headRow.appendChild(th);
      });
      thead.appendChild(headRow);
      const tbody = document.createElement("tbody");
      (Array.isArray(preview.rows) ? preview.rows : []).slice(0, 20).forEach((row) => {
        const tr = document.createElement("tr");
        (Array.isArray(row) ? row : []).forEach((cell) => {
          const td = document.createElement("td");
          td.textContent = String(cell == null ? "" : cell);
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
      table.append(thead, tbody);
      tableWrapper.appendChild(table);
      return tableWrapper;
    }

    function createDatasetStatus(type, text) {
      const message = document.createElement("p");
      message.className = `dataset-search-status ${type}`;
      message.textContent = text;
      return message;
    }

    function createDatasetCandidateCard(item) {
      const dataset = item && typeof item === "object" ? item : {};
      const isSelected = isSameDataset(dataset, selectedDataset);
      const card = document.createElement("article");
      card.className = `dataset-candidate-card ${isSelected ? "selected" : ""}`.trim();

      const header = document.createElement("div");
      header.className = "dataset-card-header";
      const title = document.createElement("h3");
      title.textContent = dataset.title || "제목 없는 데이터셋";
      const format = document.createElement("span");
      format.className = "dataset-format-badge";
      format.textContent = dataset.format || "형식 미정";
      header.append(title, format);

      const description = document.createElement("p");
      description.className = "dataset-description";
      description.textContent = summarizeText(dataset.description || "설명이 제공되지 않았습니다.", 150);

      const meta = document.createElement("dl");
      meta.className = "dataset-meta-grid";
      appendDatasetMeta(meta, "제공기관", dataset.provider || "미상");
      appendDatasetMeta(meta, "분류", dataset.category || "미분류");
      appendDatasetMeta(meta, "업데이트", dataset.updated_at || "날짜 없음");

      const actions = document.createElement("div");
      actions.className = "dataset-card-actions";
      if (dataset.url) {
        const link = document.createElement("a");
        link.className = "dataset-detail-link";
        link.href = dataset.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = "상세 보기";
        actions.appendChild(link);
      }

      const selectButton = document.createElement("button");
      selectButton.type = "button";
      selectButton.className = isSelected ? "primary-button" : "ghost-button";
      selectButton.textContent = isSelected ? "선택됨" : "선택";
      selectButton.addEventListener("click", () => onDatasetSelect(dataset));
      actions.appendChild(selectButton);

      card.append(header, description, meta, actions);
      return card;
    }

    function isPreviewableResource(resource) {
      const item = resource && typeof resource === "object" ? resource : {};
      const format = String(item.format || "").toUpperCase();
      const url = String(item.url || "").toLowerCase().split("?")[0];
      return Boolean(item.url) && (format.includes("CSV") || format.includes("TSV") || format.includes("JSON") || url.endsWith(".csv") || url.endsWith(".tsv") || url.endsWith(".json"));
    }

    function isVisualizableResource(resource) {
      return isPreviewableResource(resource);
    }

    function isSameResource(left, right) {
      if (!left || !right) {
        return false;
      }
      return (left.url && right.url && left.url === right.url) || (left.name === right.name && left.format === right.format);
    }

    function appendDatasetMeta(parent, labelText, valueText) {
      const label = document.createElement("dt");
      label.textContent = labelText;
      const value = document.createElement("dd");
      value.textContent = valueText;
      parent.append(label, value);
    }

    function summarizeText(value, maxLength) {
      const text = String(value || "").replace(/\s+/g, " ").trim();
      return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
    }

    function isSameDataset(left, right) {
      if (!left || !right) {
        return false;
      }
      if (left.id && right.id) {
        return left.id === right.id;
      }
      return left.title === right.title && left.url === right.url;
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

      if (isVisualizationLoading || isResourceVisualizationLoading) {
        const message = document.createElement("p");
        message.className = "visualization-status loading";
        message.textContent = isResourceVisualizationLoading ? "선택한 리소스를 분석 중..." : "데이터 시각화 분석 중...";
        resultBox.appendChild(message);
        return resultBox;
      }

      if (resourceVisualizationError) {
        const message = document.createElement("p");
        message.className = "visualization-status error";
        message.textContent = `리소스 시각화 실패: ${resourceVisualizationError}`;
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
          <p>파일 업로드 또는 명시적으로 선택한 리소스 분석 결과가 이 영역에 표시됩니다.</p>
          <span>외부 차트 라이브러리 없이 Vanilla JS와 CSS로 간단한 그래프/표를 렌더링합니다.</span>
        `;
        resultBox.appendChild(empty);
        return resultBox;
      }

      const safeResult = normalizeVisualizationResult(visualizationResult);
      const warning = createIncompleteResultNotice(safeResult);
      if (warning) {
        resultBox.appendChild(warning);
      }

      resultBox.append(
        createResultSummary(safeResult),
        createChartPreview(safeResult),
        createDatasetList(safeResult.datasets),
        createLabelList(safeResult.labels),
        createResultTable(safeResult.table_data),
        createPrecautionList(safeResult.startup_precautions)
      );
      return resultBox;
    }

    function normalizeVisualizationResult(result) {
      const source = result && typeof result === "object" ? result : {};
      const labels = Array.isArray(source.labels) ? source.labels : [];
      const datasets = Array.isArray(source.datasets)
        ? source.datasets.map((dataset) => {
            const safeDataset = dataset && typeof dataset === "object" ? dataset : {};
            return {
              label: typeof safeDataset.label === "string" && safeDataset.label.trim()
                ? safeDataset.label
                : "데이터셋",
              data: Array.isArray(safeDataset.data) ? safeDataset.data : [],
            };
          })
        : [];
      const tableSource = source.table_data && typeof source.table_data === "object" ? source.table_data : {};
      const precautions = Array.isArray(source.startup_precautions)
        ? source.startup_precautions.filter((item) => typeof item === "string" && item.trim())
        : [];

      return {
        status: source.status,
        chart_type: source.chart_type,
        chart_title: source.chart_title,
        strategy_reason: source.strategy_reason,
        labels,
        datasets,
        table_data: {
          headers: Array.isArray(tableSource.headers) ? tableSource.headers : [],
          rows: Array.isArray(tableSource.rows) ? tableSource.rows : [],
        },
        startup_precautions: precautions,
        isIncomplete:
          source.status !== "success" ||
          !Array.isArray(source.labels) ||
          !Array.isArray(source.datasets) ||
          datasets.length === 0 ||
          datasets.some((dataset) => !Array.isArray(dataset.data) || dataset.data.some((value) => !isRenderableDataValue(value))) ||
          !source.table_data ||
          !Array.isArray(tableSource.headers) ||
          !Array.isArray(tableSource.rows) ||
          !Array.isArray(source.startup_precautions) ||
          source.startup_precautions.some((item) => typeof item !== "string"),
      };
    }

    function isRenderableDataValue(value) {
      if (value == null || value === "") {
        return false;
      }
      return Number.isFinite(Number(value));
    }

    function createIncompleteResultNotice(result) {
      if (!result.isIncomplete) {
        return null;
      }

      const notice = document.createElement("p");
      notice.className = "visualization-status warning";
      notice.textContent = "표시 가능한 데이터가 제한적입니다. 일부 결과만 표시됩니다.";
      return notice;
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
      const numericData = data.map((value) => Number(value)).map((value) => (Number.isFinite(value) ? value : 0));

      if (result.chart_type === "bar" && labels.length && numericData.length) {
        card.appendChild(createBarChart(labels, numericData));
      } else {
        const fallback = document.createElement("p");
        fallback.className = "muted-text compact";
        fallback.textContent = labels.length && data.length
          ? "line/pie 또는 기타 유형은 현재 요약, 라벨, 데이터셋, 표 중심으로 표시합니다."
          : "표시 가능한 데이터가 제한적입니다. 요약/표시 가능한 항목만 보여줍니다.";
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
        const preview = data.slice(0, 12).map((value) => value == null || value === "" ? "(빈 값)" : String(value));
        item.textContent = `${dataset.label || "데이터셋"}: ${preview.join(", ")}${data.length > 12 ? " ..." : ""}`;
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
