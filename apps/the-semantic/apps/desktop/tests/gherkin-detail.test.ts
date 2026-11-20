import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { appendGherkinSource } from '../src/gherkin-detail.js';

test('literal section index preserves BOM, comments, whitespace, docstrings and examples', () => {
  const dom = new JSDOM('<section></section>'); Object.assign(globalThis, { document: dom.window.document });
  const host = document.querySelector('section')!;
  const text = '\uFEFF@tag\r\nFeature: Retained purpose\r\n  As a lender\r\n  I want evidence\r\n  # original comment\r\n\r\n  Background: Setup\r\n    Given a record\r\n  Scenario Outline: Detail\r\n    When a value changes\r\n    Then the source stays literal\r\n    """\r\n    Scenario: Not a heading inside a docstring\r\n    """\r\n    Examples:\r\n      | value |\r\n      | <x>   |\r\n';
  appendGherkinSource(host, text, 'fixture');
  assert.equal(host.querySelector('pre')!.textContent, text);
  assert.deepEqual([...host.querySelectorAll('.gherkin-outline button')].map(n => n.textContent), ['Feature: Retained purpose','Background: Setup','Scenario Outline: Detail','Examples:']);
  assert.equal(host.querySelectorAll('x').length, 0);
  (host.querySelector('.gherkin-outline button') as HTMLButtonElement).click();
  assert.equal(document.activeElement, host.querySelector('.gherkin-source-heading'));
  dom.window.close();
});

test('heading index is bounded while the entire source remains inspectable', () => {
  const dom = new JSDOM('<section></section>'); Object.assign(globalThis, { document: dom.window.document });
  const text = Array.from({length:75}, (_, i) => `Scenario: Item ${i}\n  Given original text\n`).join('');
  const host = document.querySelector('section')!; appendGherkinSource(host, text, 'bounded');
  assert.equal(host.querySelectorAll('.gherkin-outline button').length, 60);
  assert.equal(host.querySelector('pre')!.textContent, text);
  assert.match(host.querySelector('summary')!.textContent!, /index limit/); dom.window.close();
});
