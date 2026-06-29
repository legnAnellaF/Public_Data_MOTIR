const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const analysisCode = fs.readFileSync('public-data-dashboard/src/analysisHelpers.js', 'utf8');
const validationCode = fs.readFileSync('public-data-dashboard/src/validationHelpers.js', 'utf8');
const appStateCode = fs.readFileSync('public-data-dashboard/src/appStateHelpers.js', 'utf8');
const context = { window: {}, URL };
vm.createContext(context);
vm.runInContext(analysisCode, context);
vm.runInContext(validationCode, context);
vm.runInContext(appStateCode, context);
const h = context.window.PublicDataDashboard.AnalysisHelpers;
const v = context.window.PublicDataDashboard.ValidationHelpers;
const a = context.window.PublicDataDashboard.AppStateHelpers;

const liveSearch = a.normalizeDatasetSearchResult({
  status: 'success',
  source: 'data_go_kr_live',
  candidate_count: 18,
  first_candidate: { title: '서울 첫 후보' },
  query: '서울 집값 부동산 실거래가',
  items: [{ title: '서울 부동산 실거래가', score: 89 }],
}, '서울 집값');
assert.strictEqual(liveSearch.query, '서울 집값 부동산 실거래가');
assert.strictEqual(liveSearch.items.length, 1);
assert(a.hasRenderableDatasetCandidates(liveSearch));
const fallbackSearch = a.normalizeDatasetSearchResult({
  status: 'success',
  source: 'offline_fallback',
  is_offline_fallback: true,
  reason_code: 'DATA_PORTAL_TIMEOUT',
  message: 'data.go.kr live 검색이 불안정해 데모 후보로 계속 진행합니다.',
  items: [{ title: '오프라인 서울 부동산 후보', format: 'CSV', provider: '데모', score: 70, match_reasons: ['fallback'] }],
}, '서울 집값');
assert.strictEqual(fallbackSearch.query, '서울 집값');
assert.strictEqual(fallbackSearch.candidate_count, 1);
assert(a.hasRenderableDatasetCandidates(fallbackSearch));
const keyword503FallbackSearch = a.normalizeDatasetSearchResult({ status: 'success', items: [{ title: 'fallback keyword result' }] }, '서울 집값');
assert(a.hasRenderableDatasetCandidates(keyword503FallbackSearch));
assert.strictEqual(keyword503FallbackSearch.first_candidate.title, 'fallback keyword result');
assert(!a.hasRenderableDatasetCandidates({ status: 'success', source: 'offline_fallback', is_offline_fallback: true, items: [] }));

assert(h.deriveFallbackKeyword('서울 부동산 가격 데이터 보여줘').includes('서울'));
assert(!['데이터', '보여줘'].includes(h.deriveFallbackKeyword('서울 부동산 가격 데이터 보여줘')));
const dataset = { title: '서울 부동산 실거래가', provider: '서울시', format: 'CSV' };
const resource = { name: '실거래 CSV', format: 'CSV', url: 'https://example.com/a.csv', is_previewable: true, is_visualizable: true };
const unsupportedResource = { name: '엑셀 파일', format: 'XLSX', url: 'https://example.com/a.xlsx', unsupported_reason: '원격 Excel은 직접 업로드 경로를 사용하세요.' };
const preview = { preview: { kind: 'table', headers: ['지역','가격'], rows: [['강남', '10'], ['마포', '7']] }, metadata: { content_type: 'text/csv', bytes_read: 128, source_url: 'https://example.com/a.csv?serviceKey=abc' } };
const visualization = { chart_type: 'bar', labels: ['강남','마포'], datasets: [{ label: '가격', data: [10, 7] }], table_data: { headers: ['지역','가격'], rows: [['강남', '10']] }, metadata: { source_url: 'https://example.com/a.csv?serviceKey=abc', resource_format: 'CSV', content_type: 'text/csv', bytes_read: 128 } };
const baseOutline = h.deriveAnalysisOutline({ prompt: '서울 부동산', keyword: '서울 부동산', dataset, resource });
const richerOutline = h.deriveAnalysisOutline({ prompt: '서울 부동산', keyword: '서울 부동산', dataset, resource, resourcePreview: preview, visualization, additionalPrompt: '강남만 비교' });
assert.notDeepStrictEqual(baseOutline, richerOutline);
const comments = h.deriveDataComment({ prompt: '서울 부동산', keyword: '서울 부동산', dataset, resource: unsupportedResource, resourcePreview: preview, visualization, additionalPrompt: '강남만 비교' }).join('\n');
assert(comments.includes('최대값'));
assert(comments.includes('preview'));
assert(comments.includes('강남만 비교'));
assert(comments.includes('원격 Excel'));
assert(comments.includes('source URL 확인됨'));
assert(comments.includes('형식 CSV'));
assert(comments.includes('content-type text/csv'));
assert(comments.includes('128 bytes 분석'));
const summary = v.buildValidationSummary({
  apiBaseUrl: 'https://codespace-8000.app.github.dev?token=abc', apiBaseUrlSource: 'localStorage',
  apiHealth: { status: 'success', message: 'ok' }, dataPortalDiagnostic: { status: 'error', message: 'DATA_PORTAL_NETWORK_ERROR' },
  keywordFallback: '서울 부동산', keywordError: 'AI 키워드 추출은 실패했지만 fallback으로 계속 진행합니다.',
  datasetSearchResult: { items: [dataset], source: 'offline_fallback', is_offline_fallback: true, reason_code: 'DATA_PORTAL_TIMEOUT' }, selectedDataset: dataset, datasetDetailResult: { resources: [resource] }, selectedResource: unsupportedResource,
  resourcePreviewResult: preview, visualizationResult: visualization, additionalPrompts: ['강남만 비교'],
});
assert(summary.some((item) => item.label === 'keyword' && item.status === 'warning'));
assert(summary.some((item) => item.label === 'dataset search' && item.details.includes('offline fallback candidates')));
assert(summary.some((item) => item.label === 'selected resource' && item.details.includes('원격 Excel')));
assert(summary.some((item) => item.label === 'resource preview' && item.details.includes('128')));
assert(summary.some((item) => item.label === 'visualization' && item.details.includes('resource result')));
assert(summary.some((item) => item.label === 'additional prompt' && item.details.includes('강남만 비교')));
const history = v.summarizeRequestHistory([
  { endpoint: '/api/health', method: 'GET', status: 'pending', started_at_ms: Date.now() - 11000 },
  { endpoint: '/api/visualize', method: 'POST', status: 'success', elapsed_ms: 120, http_status: 200 },
  { endpoint: '/api/keywords', method: 'POST', status: 'error', elapsed_ms: 50, http_status: 503 },
  { endpoint: '/api/datasets/search', method: 'POST', status: 'timeout', elapsed_ms: 30000 },
]);
assert(history.some((item) => item.status === 'long-pending'));
assert(history.some((item) => item.status === 'success'));
assert(history.some((item) => item.status === 'error'));
assert(history.some((item) => item.status === 'timeout'));
console.log('frontend analysis/validation helper checks passed');
const followUps = h.deriveFollowUpQuestions({ prompt: '서울 지역별 연도별 부동산', keyword: '서울 부동산 가격', dataset, resource, resourcePreview: preview, visualization });
assert(followUps.length >= 3 && followUps.length <= 5);
assert(followUps.some((q) => q.includes('지역별')));
assert(followUps.some((q) => q.includes('최대값') || q.includes('이상치')));
const unsupportedFollowUps = h.deriveFollowUpQuestions({ prompt: '서울 부동산', dataset, resource: unsupportedResource });
assert(unsupportedFollowUps.some((q) => q.includes('직접 파일 업로드')));
const report = h.buildReportSummaryMarkdown({ prompt: '서울 부동산', keyword: '서울 부동산 가격', dataset, resource: { ...resource, url: 'https://example.com/a.csv?serviceKey=abc&x=1&token=zzz' }, resourcePreview: preview, visualization, isDemoMode: true, additionalPrompt: '강남만 비교' });
assert(report.includes('데모 데이터 기반'));
assert(report.includes('최초 프롬프트'));
assert(report.includes('서울 부동산 가격'));
assert(report.includes('선택 데이터셋'));
assert(report.includes('주의사항'));
assert(report.includes('[REDACTED]'));
assert(!report.includes('abc'));
assert(!report.includes('zzz'));
const jsonReport = h.buildReportSummaryJson({ prompt: '서울 부동산', keyword: '서울 부동산 가격', dataset, resource: { ...resource, url: 'https://example.com/a.csv?apiKey=abc' }, resourcePreview: preview, visualization, isDemoMode: true });
assert.strictEqual(jsonReport.mode, 'offline-demo-fixture');
assert(!JSON.stringify(jsonReport).includes('abc'));
const changedFollowUps = h.deriveFollowUpQuestions({ prompt: '서울 부동산', keyword: '서울 부동산', dataset, resource, resourcePreview: preview, additionalPrompt: '연도별 추세' });
assert(changedFollowUps.some((q) => q.includes('최근 연도') || q.includes('연도별')));
console.log('frontend report/demo/follow-up helper checks passed');
