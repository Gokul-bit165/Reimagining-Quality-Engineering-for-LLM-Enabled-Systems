import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * End-to-end test of the guided flow with a route-mocked API.
 * The fixtures live only in this test file; the shipped UI contains no mock data.
 */

const PROJECT_READY = {
  id: 'p1', repo_url: 'https://github.com/acme/support-rag', branch: 'main', state: 'ready', error: null, created_at: '2026-01-01T00:00:00Z',
  analysis: {
    framework: 'LangChain', language: 'Python', entrypoints: ['app/main.py'], retriever: 'VectorStoreRetriever (k=4)', vector_store: 'Chroma',
    llm_providers: ['openai'], prompts: ['prompts/system.txt'], doc_sources: ['docs/'], env_vars: ['OPENAI_API_KEY'], chunking: 'RecursiveCharacterTextSplitter 500/50',
    risk_flags: [
      { id: 'inj', title: 'User text concatenated into system prompt', evidence_file: 'app/chain.py', line: 42 },
      { id: 'cite', title: 'No citation check on answers', evidence_file: 'app/answer.py', line: 17 },
    ],
    execution_mode: 'static_only',
  },
  inputs: {},
};

const metric = (value: number, lo: number, hi: number, n: number) => ({ value, ci_low: lo, ci_high: hi, n, note: null });

const EVAL_DONE = {
  id: 'e1', project_id: 'p1', state: 'done', progress: { done: 12, total: 12 }, error: null, synthetic: true,
  metrics: {},
  scorecard: {
    accuracy: metric(0.72, 0.55, 0.85, 12), grounding: metric(0.64, 0.45, 0.8, 12), completeness: metric(0.7, 0.52, 0.84, 12),
    safety: metric(0.9, 0.7, 0.97, 8), consistency: metric(0.81, 0.62, 0.92, 12),
    security: { value: null, ci_low: null, ci_high: null, n: 0, note: 'No security probes ran in static-only mode' },
  },
  failure_taxonomy: {
    'QE-FAB': { name: 'Fabricated or wrong claims', count: 2, examples: [] },
    'QE-RET': { name: 'Retrieval miss', count: 1, examples: [] },
  },
  decision: { verdict: 'INSUFFICIENT_EVIDENCE', status: 'pending_review', reasons: ['Only 12 items measured; intervals are too wide to decide.', 'Code was not executed.'] },
  items: [
    { id: 'i1', question: 'What is the refund window?', reference_answer: '30 days', answer: 'Refunds are possible within 90 days.', contexts: ['Refunds are accepted within 30 days of purchase.'],
      scores: { faithfulness: 0.1 }, passed: false, failure_reason: 'Answer contradicts retrieved context', failure_class: 'QE-FAB', source: 'user' },
    { id: 'i2', question: 'Who is the CEO?', reference_answer: null, answer: 'Jane Doe', contexts: [], scores: {}, passed: false, failure_reason: 'No relevant passage retrieved', failure_class: 'QE-RET', source: 'generated' },
    { id: 'i3', question: 'How do I reset my password?', reference_answer: 'Use the reset link.', answer: 'Use the reset link.', contexts: ['Use the reset link on the login page.'], scores: { faithfulness: 1 }, passed: true, failure_reason: null, source: 'user' },
  ],
};

async function mockApi(page: Page, opts: { evalPolls?: number } = {}) {
  let evalReads = 0;
  const seen: string[] = [];
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    seen.push(`${req.method()} ${path}`);
    if (path === '/api/projects' && req.method() === 'POST') {
      const body = req.postDataJSON();
      return body.authorized === true ? json(route, { id: 'p1', state: 'cloning' }, 202) : json(route, { detail: 'authorization required' }, 400);
    }
    if (path === '/api/projects') return json(route, []);
    if (path === '/api/projects/p1') return json(route, PROJECT_READY);
    if (path === '/api/projects/p1/suggested-inputs') {
      return json(route, { qa_pairs: [{ question: 'What is the refund window?', reference_answer: '30 days' }], risk_focus: ['faithfulness'] });
    }
    if (path === '/api/projects/p1/inputs') return json(route, { ok: true });
    if (path === '/api/projects/p1/secrets') return json(route, { ok: true });
    if (path === '/api/evaluations' && req.method() === 'POST') return json(route, { id: 'e1', state: 'queued' }, 202);
    if (path === '/api/evaluations' && req.method() === 'GET') {
      return json(route, [{ id: 'e1', project_id: 'p1', state: evalReads > (opts.evalPolls ?? 2) ? 'done' : 'running', progress: { done: 12, total: 12 }, synthetic: true, verdict: null, status: null, created: 100 }]);
    }
    if (path === '/api/evaluations/e1/signoff') return json(route, { ok: true });
    if (path === '/api/evaluations/e1') {
      evalReads += 1;
      const polls = opts.evalPolls ?? 2;
      if (evalReads <= polls) {
        return json(route, { ...EVAL_DONE, state: 'running', progress: { done: evalReads * 3, total: 12 }, items: [], decision: null, scorecard: {} });
      }
      return json(route, EVAL_DONE);
    }
    if (path === '/api/evaluations/e1/monitoring-plan') return json(route, { alerts: ['grounding below 0.6'], cadence: 'weekly' });
    if (path.startsWith('/api/')) return json(route, []);
    return route.continue();
  });
  return seen;
}

test('guided flow: connect, understand, inputs, run, results, operate', async ({ page }) => {
  const seen = await mockApi(page);
  await page.goto('/');

  // Landing is the connect flow, with demo pages clearly labelled.
  await expect(page.getByRole('heading', { name: 'Connect your RAG app' })).toBeVisible();
  await expect(page.locator('#primary-nav')).not.toContainText(/SYNTHETIC|DEMO/);
  await expect(page.getByText('demo / benchmark page')).toHaveCount(0);

  // Authorization is mandatory.
  await page.locator('#repo').fill('https://github.com/acme/support-rag');
  await page.getByTestId('analyze').click();
  await expect(page.getByText(/must confirm you are allowed/)).toBeVisible();
  await page.getByTestId('authorized').check();
  await page.screenshot({ path: 'e2e-screenshots/flow-1-connect-1440.png' });
  await page.getByTestId('analyze').click();

  // Step 2: understand
  await expect(page).toHaveURL(/#p\/p1\/understand/);
  await expect(page.getByTestId('execution-mode')).toContainText('analysed but NOT executed');
  await expect(page.getByText('app/chain.py:42')).toBeVisible();
  await page.screenshot({ path: 'e2e-screenshots/flow-2-understand-1440.png', fullPage: true });

  // Step 3: inputs with one-click suggestions
  await page.getByTestId('to-inputs').click();
  await page.getByTestId('use-suggested').click();
  await expect(page.getByTestId('qa-count')).toHaveText('1 question loaded');
  await page.getByLabel('Upload .txt / .md files').setInputFiles({ name: 'policy.md', mimeType: 'text/markdown', buffer: Buffer.from('# Refunds\n30 days.') });
  await expect(page.getByText(/policy.md/)).toBeVisible();
  await page.getByLabel('OPENAI_API_KEY').fill('sk-test-not-real');
  await page.screenshot({ path: 'e2e-screenshots/flow-3-inputs-1440.png', fullPage: true });
  const secretBody = page.waitForRequest((r) => r.url().endsWith('/api/projects/p1/secrets'));
  await page.getByTestId('save-inputs').click();
  expect((await secretBody).postDataJSON()).toEqual({ values: { OPENAI_API_KEY: 'sk-test-not-real' } });

  // Step 4: run with live progress
  await expect(page).toHaveURL(/#p\/p1\/run/);
  await page.getByTestId('start-eval').click();
  await expect(page).toHaveURL(/#p\/p1\/run\/e1/);
  await expect(page.getByTestId('eval-progress')).toContainText('of 12');
  await page.screenshot({ path: 'e2e-screenshots/flow-4-run-1440.png' });
  await page.getByTestId('to-results').click({ timeout: 15_000 });

  // Step 5: results
  await expect(page.getByTestId('synthetic-badge').first()).toBeVisible();
  await expect(page.getByTestId('verdict')).toContainText('INSUFFICIENT EVIDENCE');
  await expect(page.getByTestId('verdict')).toContainText('PENDING HUMAN REVIEW');
  await expect(page.getByTestId('metric-grounding')).toContainText('95% CI 45.0% to 80.0% · n=12');
  await expect(page.getByTestId('metric-security')).toContainText('Not measured');
  await page.getByTestId('eval-item').first().getByRole('button').click();
  await expect(page.getByText('Answer contradicts retrieved context').first()).toBeVisible();
  await expect(page.getByText('Refunds are accepted within 30 days of purchase.')).toBeVisible();
  await page.screenshot({ path: 'e2e-screenshots/flow-5-results-1440.png', fullPage: true });

  // Human sign-off
  const signoff = page.waitForRequest((r) => r.url().endsWith('/signoff'));
  await page.locator('#so-name').fill('A. Reviewer');
  await page.locator('#so-why').fill('Needs a real endpoint run first.');
  await page.getByRole('button', { name: 'Record sign-off' }).click();
  expect((await signoff).postDataJSON()).toMatchObject({ reviewer: 'A. Reviewer', decision: 'approve' });
  await page.goto('/#p/p1/results');
  await expect(page.getByTestId('verdict')).toBeVisible();
  await page.goto('/#/projects/p1/results');
  await expect(page.getByTestId('verdict')).toBeVisible();

  // Step 6: operate
  await page.getByTestId('to-operate').click();
  await page.getByRole('button', { name: 'Generate monitoring plan' }).click();
  await expect(page.getByTestId('monitoring-plan')).toContainText('grounding below 0.6');
  await page.screenshot({ path: 'e2e-screenshots/flow-6-operate-1440.png', fullPage: true });

  expect(seen.some((s) => s === 'POST /api/evaluations')).toBe(true);
});

test('mobile 390: flow screens are usable without horizontal scroll', async ({ page }) => {
  await mockApi(page, { evalPolls: 0 });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/#connect');
  await page.screenshot({ path: 'e2e-screenshots/flow-1-connect-390.png' });
  for (const [hash, name] of [['#p/p1/understand', 'understand'], ['#p/p1/inputs', 'inputs'], ['#p/p1/results/e1', 'results']] as const) {
    await page.goto(`/${hash}`);
    await page.waitForLoadState('networkidle');
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, `${name} overflows horizontally`).toBeLessThanOrEqual(0);
    await page.screenshot({ path: `e2e-screenshots/flow-${name}-390.png`, fullPage: true });
  }
  await page.getByRole('button', { name: 'Menu' }).click();
  await expect(page.getByRole('complementary', { name: 'Primary' })).toBeVisible();
  await page.screenshot({ path: 'e2e-screenshots/nav-open-390.png' });
});

test('backend 404 shows a clear message instead of crashing', async ({ page }) => {
  await page.route('**/api/projects/**', (route) => route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"Not Found"}' }));
  await page.route('**/api/projects', (route) => route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"Not Found"}' }));
  await page.route('**/api/{runs,benchmarks,taxonomy,config}', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
  await page.goto('/#p/nope/understand');
  await expect(page.getByRole('alert')).toContainText('Not found (404)');
});

test('canvas: nodes drag, positions persist per project, reset restores layout', async ({ page }) => {
  await mockApi(page, { evalPolls: 0 });
  await page.goto('/#p/p1/results/e1');
  const node = page.locator('.react-flow__node').first();
  await expect(node).toBeVisible();
  await page.locator('.flow-surface').scrollIntoViewIfNeeded();
  await page.screenshot({ path: 'e2e-screenshots/canvas-before-drag-1440.png' });
  const before = await node.boundingBox();
  expect(before).not.toBeNull();

  const cx = before!.x + before!.width / 2;
  const cy = before!.y + before!.height / 2;
  await page.mouse.move(cx, cy);
  await page.mouse.down();
  await page.mouse.move(cx + 20, cy + 40, { steps: 5 });
  await page.mouse.move(cx + 40, cy + 140, { steps: 10 });
  await page.waitForTimeout(150);
  await page.mouse.up();
  await page.waitForTimeout(150);
  const after = await node.boundingBox();
  expect(Math.round(after!.y - before!.y)).toBeGreaterThan(100);

  const stored = await page.evaluate(() => window.localStorage.getItem('qe.canvas.layout.v1:project:p1'));
  expect(stored).not.toBeNull();
  const layout = JSON.parse(stored!);
  expect(layout.analyse.y).toBeGreaterThan(50);
  await page.screenshot({ path: 'e2e-screenshots/canvas-after-drag-1440.png' });

  // Edges follow: edge paths still exist for all links.
  await expect(page.locator('.react-flow__edge')).toHaveCount(4);

  // Persisted across reload
  const flowY = (loc: ReturnType<Page['locator']>) => loc.evaluate((el) => Number(/translate\(([-\d.]+)px,\s*([-\d.]+)px\)/.exec((el as HTMLElement).style.transform)![2]));
  const yBeforeReload = await flowY(page.locator('.react-flow__node').first());
  expect(yBeforeReload).toBeGreaterThan(50);
  await page.reload();
  await expect(page.locator('.react-flow__node').first()).toBeVisible();
  expect(Math.abs((await flowY(page.locator('.react-flow__node').first())) - yBeforeReload)).toBeLessThan(2);
  // A different project starts from the default layout.
  expect(await page.evaluate(() => window.localStorage.getItem('qe.canvas.layout.v1:project:other'))).toBeNull();

  // Keyboard: focus node and move with arrow keys
  const first = page.locator('.react-flow__node').first();
  await first.focus();
  const kb0 = await flowY(first);
  await page.keyboard.press('Enter');
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('ArrowDown');
  await expect.poll(() => flowY(first)).toBeGreaterThan(kb0);

  // Reset
  await page.getByTestId('reset-layout').click();
  const stored2 = await page.evaluate(() => window.localStorage.getItem('qe.canvas.layout.v1:project:p1'));
  expect(stored2).toBeNull();
  await expect.poll(() => flowY(page.locator('.react-flow__node').first())).toBe(0);
});

test('canvas at 390 width is pannable and zoomable', async ({ page }) => {
  await mockApi(page, { evalPolls: 0 });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/#p/p1/results/e1');
  await expect(page.locator('.react-flow__node').first()).toBeVisible();
  const vp = page.locator('.react-flow__viewport');
  const t0 = await vp.getAttribute('style');
  await page.getByRole('button', { name: 'zoom in' }).click();
  const t1 = await vp.getAttribute('style');
  expect(t1).not.toBe(t0);
  await page.locator('.flow-surface').scrollIntoViewIfNeeded();
  await page.screenshot({ path: 'e2e-screenshots/canvas-390.png' });
});
