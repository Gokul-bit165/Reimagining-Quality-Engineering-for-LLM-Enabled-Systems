import { expect, test, type Page, type Route } from '@playwright/test';
import {
  CALIBRATION_RECORD, CAMPAIGN_DONE, CAMPAIGN_LIST, CAMPAIGN_RUNNING, EVENTS, JUDGE_STATUS, LLM_MISSING, LLM_STATUS, PLAN, POLICY_TEMPLATE, PROJECT,
} from '../tests/fixtures/campaign';

/**
 * Campaign flow with a route-mocked API. Fixtures live in tests/fixtures only: the shipped UI has no mock data.
 */

const CID = CAMPAIGN_DONE.id;
const REPORT_HTML = '<!doctype html><title>QA report</title><h1>QA report for Chunk 512 vs 1024</h1>';

interface MockOptions { runningPolls?: number; llm?: typeof LLM_STATUS | typeof LLM_MISSING; bundleConflict?: boolean }

async function mockApi(page: Page, opts: MockOptions = {}) {
  const seen: { method: string; path: string; body: unknown }[] = [];
  const signed: Record<string, { reviewer: string; decision: string; rationale: string }> = {};
  let campaignReads = 0;
  const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

  const campaignNow = () => {
    campaignReads += 1;
    if (campaignReads <= (opts.runningPolls ?? 0)) return { ...CAMPAIGN_RUNNING, progress: { done: campaignReads * 20, total: 144 } };
    const c = structuredClone(CAMPAIGN_DONE);
    for (const [label, so] of Object.entries(signed)) {
      c.results[label].decision = { ...c.results[label].decision!, status: so.decision.startsWith('approve') ? 'approved' : 'rejected', signoff: so };
    }
    return c;
  };

  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname;
    const method = req.method();
    seen.push({ method, path, body: method === 'POST' ? req.postDataJSON() : undefined });

    if (path === '/api/projects') return json(route, [PROJECT]);
    if (path === '/api/projects/p1') return json(route, PROJECT);
    if (path === '/api/projects/p1/inputs') return json(route, { ok: true });
    if (path === '/api/policy/template') return json(route, POLICY_TEMPLATE);
    if (path === '/api/llm/status') return json(route, opts.llm ?? LLM_STATUS);
    if (path === '/api/judge/status') return json(route, JUDGE_STATUS);
    if (path === '/api/judge/calibration') return json(route, { latest: null, records: [] });
    if (path === '/api/judge/calibrate') return json(route, CALIBRATION_RECORD);
    if (path === '/api/evaluations') return json(route, []);

    if (path === '/api/campaigns' && method === 'POST') return json(route, { id: CID, state: 'queued' }, 202);
    if (path === '/api/campaigns') return json(route, CAMPAIGN_LIST);
    if (path === `/api/campaigns/${CID}/plan`) return json(route, PLAN);
    if (path === `/api/campaigns/${CID}/events`) return json(route, EVENTS);
    if (path === `/api/campaigns/${CID}/signoff`) {
      const body = req.postDataJSON() as { target_label: string; reviewer: string; decision: string; rationale: string };
      signed[body.target_label] = { reviewer: body.reviewer, decision: body.decision, rationale: body.rationale };
      return json(route, { id: CID, target_label: body.target_label, decision: {} });
    }
    if (path === `/api/campaigns/${CID}/qa-report`) {
      return route.fulfill({ status: 200, contentType: 'text/html', body: REPORT_HTML });
    }
    if (path === `/api/campaigns/${CID}/evidence-bundle`) {
      return opts.bundleConflict
        ? json(route, { detail: 'a secret value was found in evidence.json: bundle withheld' }, 409)
        : route.fulfill({ status: 200, contentType: 'application/zip', body: 'PK', headers: { 'content-disposition': `attachment; filename="evidence-bundle-${CID}.zip"` } });
    }
    if (path === `/api/campaigns/${CID}`) return json(route, campaignNow());
    if (path.startsWith('/api/')) return json(route, []);
    return route.continue();
  });
  return seen;
}

const SHOTS = 'e2e-screenshots';
/** The app scrolls inside .shell__scroll; for full-height screenshots let the page grow instead. */
const GROW = 'html,body,#root{height:auto!important;overflow:visible!important}.shell,.shell__main,.shell__scroll{height:auto!important;overflow:visible!important}';

test('campaign flow: create with two targets, watch it run, compare, open the report, sign off', async ({ page }) => {
  const seen = await mockApi(page, { runningPolls: 2 });
  await page.goto('/#p/p1/campaign');

  // Work areas sit beside the six wizard steps, which stay intact.
  await expect(page).toHaveTitle('acme/support-rag · Test campaign · qe');
  for (const k of ['understand', 'inputs', 'run', 'results', 'operate']) await expect(page.getByTestId(`step-${k}`)).toBeVisible();
  await expect(page.getByTestId('tool-campaign')).toHaveAttribute('aria-current', 'page');

  // The list shows this project's campaign only.
  await expect(page.getByTestId(`campaign-${CID}`)).toContainText('Chunk 512 vs 1024');
  await expect(page.getByTestId('campaign-cmp-99999999')).toHaveCount(0);

  // Create: two targets with metadata, example policy.
  await page.getByTestId('new-campaign').click();
  await expect(page.getByTestId('campaign-form')).toBeVisible();
  await expect(page.getByTestId('start-campaign')).toBeDisabled();
  await page.locator('#cf-name').fill('Chunk 512 vs 1024');

  const t0 = page.getByTestId('target-0');
  await t0.getByLabel('Label').fill('Chunk 512');
  await t0.getByRole('button', { name: 'Add a setting' }).click();
  await t0.getByLabel('Setting name 1 for target 1').fill('chunk_size');
  await t0.getByLabel('Setting value 1 for target 1').fill('512');

  await page.getByTestId('add-target').click();
  const t1 = page.getByTestId('target-1');
  await t1.getByLabel('Label').fill('Chunk 1024');
  await t1.getByRole('button', { name: 'Add a setting' }).click();
  await t1.getByLabel('Setting name 1 for target 2').fill('chunk_size');
  await t1.getByLabel('Setting value 1 for target 2').fill('1024');

  await page.getByTestId('use-example-policy').locator('input').check();
  await expect(page.getByTestId('start-campaign')).toBeEnabled();

  // A bad plan file shows exactly what is wrong; a good one is accepted.
  await page.getByTestId('cf-plan-file').setInputFiles({ name: 'bad.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify({ cases: [{ id: 'a', question: '' }] })) });
  await expect(page.getByTestId('plan-errors')).toContainText('cases[0] has an empty "question"');
  await page.getByTestId('cf-plan-file').setInputFiles({ name: 'ok.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify({ cases: [{ id: 'a', question: 'Refund window?' }] })) });
  await expect(page.getByTestId('plan-ok')).toContainText('1 case ready to import');
  await page.getByRole('button', { name: 'Remove plan' }).click();

  await page.getByTestId('start-campaign').click();
  const create = seen.find((s) => s.method === 'POST' && s.path === '/api/campaigns')!;
  expect(create.body).toMatchObject({
    project_id: 'p1', name: 'Chunk 512 vs 1024', use_example_policy: true, repeats: 3, include_security: true,
    targets: [
      { label: 'Chunk 512', kind: 'endpoint', metadata: { chunk_size: 512 } },
      { label: 'Chunk 1024', kind: 'endpoint', metadata: { chunk_size: 1024 } },
    ],
  });
  expect(create.body).not.toHaveProperty('policy');
  expect(create.body).not.toHaveProperty('plan');

  // Live tracker: 9 stages, running, then done.
  await expect(page).toHaveURL(new RegExp(`#p/p1/campaign/${CID}`));
  await expect(page.getByTestId('stage-tracker')).toBeVisible();
  await expect(page.getByTestId('stage-execution')).toHaveAttribute('data-status', 'running');
  await expect(page.locator('[data-testid^="stage-"][data-status]')).toHaveCount(9);
  await expect(page.getByTestId('campaign-progress')).toContainText('of 144 calls');
  await page.getByTestId('ctab-progress').click();
  await expect(page.getByTestId('campaign-state')).toHaveText('DONE', { timeout: 15_000 });

  // Comparison: side-by-side with intervals, pairwise table, honest recommendation.
  await page.getByTestId('ctab-compare').click();
  await expect(page.getByTestId('cell-overall_pass_rate-Chunk 512')).toContainText('62.0% (45.0% to 77.0%)');
  await expect(page.getByTestId('cell-overall_pass_rate-Chunk 1024')).toContainText('n_roots = 24');
  await expect(page.getByTestId('pair-overall_pass_rate')).toHaveAttribute('data-outcome', 'NO_SIGNIFICANT_DIFFERENCE');
  await expect(page.getByTestId('multiplicity-caution')).toContainText('Bonferroni');
  await expect(page.getByTestId('rec-none')).toContainText('No target is established as better.');
  await expect(page.getByTestId('rec-winner')).toHaveCount(0);

  // Reports: HTML opens in a new tab, bundle explains verify-bundle.
  await expect(page.getByTestId('report-actions')).toContainText('qe verify-bundle');
  const popupPromise = page.waitForEvent('popup');
  await page.getByTestId('report-open-html').click();
  const popup = await popupPromise;
  await expect(popup.locator('h1')).toHaveText('QA report for Chunk 512 vs 1024');
  await popup.close();
  const dl = page.waitForEvent('download');
  await page.getByTestId('report-bundle').click();
  expect((await dl).suggestedFilename()).toBe(`evidence-bundle-${CID}.zip`);

  // Audit trail with the ledger badge.
  await page.getByTestId('ctab-audit').click();
  await expect(page.getByTestId('ledger-badge')).toHaveText('LEDGER VERIFIED');

  // Sign off one target.
  await page.getByTestId('ctab-review').click();
  await page.getByTestId('reviewer-name').fill('Dana Reviewer');
  await page.getByTestId('signoff-form-Chunk 512').getByLabel('Rationale').fill('Evidence is thin but fine for staging.');
  await page.getByTestId('record-signoff-Chunk 512').click();
  await expect(page.getByTestId('signed-Chunk 512')).toContainText('APPROVED');
  await expect(page.getByTestId('signoff-form-Chunk 1024')).toBeVisible();
  const so = seen.find((s) => s.path === `/api/campaigns/${CID}/signoff`)!;
  expect(so.body).toEqual({ reviewer: 'Dana Reviewer', decision: 'approve', rationale: 'Evidence is thin but fine for staging.', target_label: 'Chunk 512' });
});

test('bundle withheld because a secret was found is explained, not hidden', async ({ page }) => {
  await mockApi(page, { bundleConflict: true });
  await page.goto(`/#p/p1/campaign/${CID}`);
  await page.getByTestId('report-bundle').click();
  await expect(page.getByTestId('report-error')).toContainText('withheld because a secret was found');
  await expect(page.getByTestId('report-error')).toContainText('Nothing was exported');
});

test('generation is disabled with the reason when no language model is configured', async ({ page }) => {
  await mockApi(page, { llm: LLM_MISSING });
  await page.goto('/#p/p1/campaign/new');
  await expect(page.getByTestId('cf-generate')).toBeDisabled();
  await expect(page.getByTestId('cf-generate-reason')).toContainText('QE_LLM_MODEL');
  await expect(page.getByTestId('cf-generate-reason')).toContainText('names only');
});

test('judge calibration: paste labelled items, see the record', async ({ page }) => {
  await mockApi(page);
  await page.goto('/#p/p1/judge');
  await expect(page.getByTestId('judge-independence')).toHaveText('INDEPENDENT');
  await expect(page.getByTestId('judge-stale')).toBeVisible();
  const items = [
    '{"question":"Refund window?","reference":"30 days","answer":"90 days","label":"incorrect"}',
    '{"question":"Refund window?","reference":"30 days","answer":"30 days","label":"correct"}',
    '{"question":"Ship to Mars?","reference":"No","answer":"Yes","label":"incorrect"}',
  ].join('\n');
  await page.locator('#cal-paste').fill(items);
  await expect(page.getByTestId('calibration-parse')).toContainText('3 valid items');
  await page.getByTestId('calibrate-run').click();
  await expect(page.getByTestId('calibration-record')).toContainText('66.7%');
  await expect(page.getByTestId('calibration-record')).toContainText('9.0% to 99.0%');
});

for (const [name, width, height] of [['1440', 1440, 900], ['390', 390, 844]] as const) {
  test(`screenshots at ${name}px: campaign create, detail, coverage, judge, execution`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await mockApi(page);
    await page.addInitScript((css) => {
      document.addEventListener('DOMContentLoaded', () => { const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st); });
    }, GROW);

    await page.goto('/#p/p1/campaign/new');
    await page.getByTestId('target-0').getByLabel('Label').fill('Chunk 512');
    await page.getByTestId('add-target').click();
    await page.getByTestId('target-1').getByLabel('Label').fill('Chunk 1024');
    await page.getByTestId('target-1').getByLabel('Bare model').check();
    await expect(page.getByTestId('target-editor')).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/campaign-create-${name}.png`, fullPage: true });

    await page.goto(`/#p/p1/campaign/${CID}`);
    await expect(page.getByTestId('comparison')).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/campaign-detail-compare-${name}.png`, fullPage: true });

    await page.getByTestId('ctab-progress').click();
    await expect(page.getByTestId('stage-tracker')).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/campaign-detail-stages-${name}.png`, fullPage: true });

    await page.getByTestId('ctab-plan').click();
    await expect(page.getByTestId('coverage-matrix')).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/campaign-coverage-${name}.png`, fullPage: true });

    await page.getByTestId('ctab-results').click();
    await expect(page.getByTestId('target-results')).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/campaign-results-${name}.png`, fullPage: true });

    await page.goto('/#p/p1/judge');
    await expect(page.getByTestId('judge-status')).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/judge-panel-${name}.png`, fullPage: true });

    await page.goto('/#p/p1/understand');
    await expect(page.getByTestId('execution-panel')).toBeVisible();
    await expect(page.getByTestId('runtime-state')).toBeVisible();
    await page.getByTestId('execution-panel').scrollIntoViewIfNeeded();
    await page.getByTestId('execution-panel').screenshot({ path: `${SHOTS}/execution-panel-${name}.png` });

    // No horizontal page overflow at this width (tables scroll inside their own wrapper).
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
}
