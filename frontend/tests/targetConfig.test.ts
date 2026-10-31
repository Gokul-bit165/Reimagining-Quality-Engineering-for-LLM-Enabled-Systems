import { describe, expect, it } from 'vitest';
import {
  TEMPLATE_PRESETS, emptyTargetForm, formFromConfig, hasTargetErrors, headerSecretNames, isAllowedSecretName, parseTemplate, splitPaths, toTargetConfig,
  validateTargetForm,
} from '../src/lib/targetConfig';

describe('request template', () => {
  it('accepts every preset and finds the placeholder', () => {
    for (const p of TEMPLATE_PRESETS) expect(parseTemplate(p.template).ok).toBe(true);
  });
  it('rejects bad JSON, scalars, and a template without {question}', () => {
    expect(parseTemplate('{oops')).toMatchObject({ ok: false });
    expect(parseTemplate('"hi"')).toMatchObject({ ok: false });
    expect(parseTemplate('{"q": "fixed"}')).toMatchObject({ ok: false, error: expect.stringContaining('{question}') });
    // the placeholder must be in a VALUE, not a key
    expect(parseTemplate('{"{question}": 1}')).toMatchObject({ ok: false });
  });
  it('treats an empty box as "use the default body"', () => {
    expect(parseTemplate('  ')).toEqual({ ok: true, value: null });
  });
});

describe('validateTargetForm', () => {
  it('flags a GET array template and bad paths', () => {
    const e = validateTargetForm({ ...emptyTargetForm(), method: 'GET', template: '["{question}"]', answerPath: 'a b', contextPaths: 'ok.path\nbad path!' });
    expect(e.template).toMatch(/flat/);
    expect(e.answerPath).toMatch(/not a valid path/);
    expect(e.contextPaths).toMatch(/bad path!/);
  });
  it('rejects credential headers that are not secret references and forbidden names', () => {
    const f = { ...emptyTargetForm(), headers: [
      { name: 'X-Auth', value: 'Bearer abc123' }, { name: 'Host', value: '${X}' }, { name: 'Accept', value: 'application/json' },
      { name: 'X-Key', value: '${QE_SECRET}' }, { name: 'Authorization', value: 'Bearer ${API_TOKEN}' }, { name: '', value: '' },
    ] };
    const e = validateTargetForm(f);
    expect(e.headers[0]).toMatch(/secret reference/);
    expect(e.headers[1]).toMatch(/not an allowed header/);
    expect(e.headers[2]).toBeUndefined();
    expect(e.headers[3]).toMatch(/reserved/);
    expect(e.headers[4]).toBeUndefined();
    expect(hasTargetErrors(e)).toBe(true);
  });
  it('a default form is valid', () => {
    expect(hasTargetErrors(validateTargetForm(emptyTargetForm()))).toBe(false);
  });
});

describe('conversion', () => {
  it('round-trips config <-> form and never carries secret values', () => {
    const cfg = { request_template: { messages: [{ role: 'user', content: '{question}' }] }, method: 'POST' as const, answer_path: 'choices.0.message.content',
      context_paths: ['sources.*.text', 'docs.0'], headers: { Authorization: 'Bearer ${API_TOKEN}' }, response_format: 'json' as const };
    const form = formFromConfig(cfg);
    expect(toTargetConfig(form)).toEqual(cfg);
    expect(headerSecretNames(form.headers)).toEqual(['API_TOKEN']);
  });
  it('splits context paths on lines and commas', () => {
    expect(splitPaths('a.b\n c.d , e.*')).toEqual(['a.b', 'c.d', 'e.*']);
  });
  it('mirrors the vault name rules', () => {
    expect(isAllowedSecretName('API_TOKEN')).toBe(true);
    for (const n of ['api_token', 'PATH', 'QE_X', 'HTTP_PROXY', '1X']) expect(isAllowedSecretName(n)).toBe(false);
  });
});
