const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const analysisCode = fs.readFileSync('public-data-dashboard/src/analysisHelpers.js', 'utf8');
const validationCode = fs.readFileSync('public-data-dashboard/src/validationHelpers.js', 'utf8');
const context = { window: {}, URL };
vm.createContext(context);
vm.runInContext(analysisCode, context);
vm.runInContext(validationCode, context);
const h = context.window.PublicDataDashboard.AnalysisHelpers;
const v = context.window.PublicDataDashboard.ValidationHelpers;
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
  datasetSearchResult: { items: [dataset] }, selectedDataset: dataset, datasetDetailResult: { resources: [resource] }, selectedResource: unsupportedResource,
  resourcePreviewResult: preview, visualizationResult: visualization, additionalPrompts: ['강남만 비교'],
});
assert(summary.some((item) => item.label === 'keyword' && item.status === 'warning'));
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
