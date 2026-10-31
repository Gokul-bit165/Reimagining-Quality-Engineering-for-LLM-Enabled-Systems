import { describe, expect, it } from 'vitest';
import { looksBinary, parseAnswerable, parseCsv, parseQaCsv, parseQaJsonl, parseQaText } from '../src/lib/parsers';
import { clearLayout, loadLayout, saveLayout } from '../src/lib/layoutStorage';
import { parseRoute, projectHref } from '../src/lib/route';

describe('parseCsv', () => {
  it('handles quotes, escaped quotes, commas and newlines inside fields', () => {
    expect(parseCsv('a,b\n"x, y","he said ""hi"""\n"l1\nl2",z')).toEqual([
      ['a', 'b'], ['x, y', 'he said "hi"'], ['l1\nl2', 'z'],
    ]);
  });
});

describe('Q&A parsing', () => {
  it('reads a headed CSV', () => {
    const r = parseQaCsv('question,reference_answer\nWhat?,That\nNo ref,');
    expect(r.rows).toEqual([{ question: 'What?', reference_answer: 'That' }, { question: 'No ref' }]);
  });
  it('treats a headerless CSV as question[,answer]', () => {
    expect(parseQaCsv('Q1,A1').rows).toEqual([{ question: 'Q1', reference_answer: 'A1' }]);
  });
  it('reports malformed JSONL lines instead of failing', () => {
    const r = parseQaJsonl('{"question":"a","expected":"b"}\nnot json\n{"foo":1}');
    expect(r.rows).toEqual([{ question: 'a', reference_answer: 'b' }]);
    expect(r.errors).toHaveLength(2);
  });
  it('sniffs the format', () => {
    expect(parseQaText('{"question":"q"}').rows).toHaveLength(1);
    expect(parseQaText('question\nq1\nq2', 'x.csv').rows).toHaveLength(2);
  });
  it('flags binary content such as a real PDF', () => {
    expect(looksBinary('%PDF-1.7 ...')).toBe(true);
    expect(looksBinary('plain text here')).toBe(false);
  });
});

describe('layout storage', () => {
  it('round-trips positions per key and ignores corrupt data', () => {
    saveLayout('p1', { a: { x: 1, y: 2 } });
    expect(loadLayout('p1')).toEqual({ a: { x: 1, y: 2 } });
    expect(loadLayout('other')).toEqual({});
    window.localStorage.setItem('qe.canvas.layout.v1:bad', '{oops');
    expect(loadLayout('bad')).toEqual({});
    clearLayout('p1');
    expect(loadLayout('p1')).toEqual({});
  });
});

describe('routes', () => {
  it('defaults to the connect flow', () => {
    expect(parseRoute('')).toEqual({ name: 'connect' });
    expect(parseRoute('#connect')).toEqual({ name: 'connect' });
  });
  it('parses project steps and evaluation ids', () => {
    expect(parseRoute('#p/abc/results/ev1')).toEqual({ name: 'project', projectId: 'abc', step: 'results', evalId: 'ev1' });
    expect(parseRoute('#p/abc')).toEqual({ name: 'project', projectId: 'abc', step: 'understand', evalId: null });
    expect(projectHref('abc', 'run', 'ev1')).toBe('#p/abc/run/ev1');
  });
  it('accepts path-style project links', () => {
    expect(parseRoute('#/projects/prj-1/results')).toEqual({ name: 'project', projectId: 'prj-1', step: 'results', evalId: null });
    expect(parseRoute('#some/weird/path')).toEqual({ name: 'notfound', hash: 'some/weird/path' });
  });
  it('treats removed legacy routes as not found', () => {
    expect(parseRoute('#new')).toEqual({ name: 'notfound', hash: 'new' });
    expect(parseRoute('#bench')).toEqual({ name: 'notfound', hash: 'bench' });
  });
});

describe('answerable column', () => {
  it('parses CSV answerable as tri-state: true, false, and blank = unknown', () => {
    const r = parseQaCsv('question,reference_answer,answerable\nQ1,A1,true\nQ2,,false\nQ3,A3,\nQ4,,maybe');
    expect(r.errors).toEqual([]);
    expect(r.rows).toEqual([
      { question: 'Q1', reference_answer: 'A1', answerable: true },
      { question: 'Q2', answerable: false },
      { question: 'Q3', reference_answer: 'A3' },
      { question: 'Q4' },
    ]);
  });
  it('parses JSONL booleans and strings, and drops a reference on a not-answerable row with a note', () => {
    const r = parseQaJsonl('{"question":"Q1","answerable":false,"reference_answer":"x"}\n{"question":"Q2","answerable":"yes"}\n{"question":"Q3"}');
    expect(r.rows).toEqual([{ question: 'Q1', answerable: false }, { question: 'Q2', answerable: true }, { question: 'Q3' }]);
    expect(r.errors.join(' ')).toMatch(/Line 1.*not answerable.*dropped/);
  });
  it('maps values explicitly', () => {
    expect(parseAnswerable('No')).toBe(false);
    expect(parseAnswerable(1)).toBe(true);
    expect(parseAnswerable('')).toBeNull();
  });
});
