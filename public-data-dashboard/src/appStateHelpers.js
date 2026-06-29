(function () {
  window.PublicDataDashboard = window.PublicDataDashboard || {};

  function normalizeDatasetSearchResult(response, requestedKeyword) {
    const source = response && typeof response === "object" ? response : {};
    const items = Array.isArray(source.items) ? source.items : [];
    const query = typeof source.query === "string" && source.query.trim()
      ? source.query.trim()
      : String(requestedKeyword || "").trim();

    return {
      ...source,
      status: source.status || (items.length ? "success" : source.status),
      query,
      items,
      candidate_count: Number.isFinite(Number(source.candidate_count))
        ? Number(source.candidate_count)
        : items.length,
      first_candidate: source.first_candidate || items[0] || null,
    };
  }

  function hasRenderableDatasetCandidates(searchResult) {
    return Boolean(
      searchResult &&
      searchResult.status === "success" &&
      Array.isArray(searchResult.items) &&
      searchResult.items.length > 0
    );
  }

  window.PublicDataDashboard.AppStateHelpers = {
    normalizeDatasetSearchResult,
    hasRenderableDatasetCandidates,
  };
})();
