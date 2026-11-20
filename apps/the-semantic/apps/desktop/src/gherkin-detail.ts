import { el, button } from './dom.js';

/** Indexes literal English headings for display; the complete source stays unchanged. */
export function appendGherkinSource(host: HTMLElement, text: string, prefix: string): void {
  const source = el('pre', '', 'gherkin-source'); source.tabIndex = 0;
  source.setAttribute('aria-label', 'Verbatim Gherkin source');
  const outline = el('details', '', 'gherkin-outline'); const links = el('div');
  let count = 0; let quoted: string | undefined; let pending = '';
  for (const line of text.split(/(?<=\n)/)) {
    const delimiter = /^\s*("""|```)/.exec(line)?.[1];
    const heading = !quoted && !delimiter && /^\s*(Feature|Rule|Background|Scenario(?: Outline| Template)?|Examples?)\s*:\s*(.*)/.exec(line);
    if (delimiter) quoted = quoted === delimiter ? undefined : quoted ?? delimiter;
    if (heading && count < 60) {
      source.append(document.createTextNode(pending)); pending = '';
      const target = el('span', line, 'gherkin-source-heading'); target.id = `${prefix}-line-${count++}`; target.tabIndex = -1;
      source.append(target);
      const jump = button(`${heading[1]}: ${heading[2]}`.trim(), () => { target.focus({ preventScroll: true }); target.scrollIntoView?.({ block: 'nearest' }); });
      links.append(jump);
    } else pending += line;
  }
  source.append(document.createTextNode(pending));
  if (count) {
    outline.append(el('summary', `Feature sections · ${count}${count === 60 ? ' shown (index limit)' : ''}`), links);
    host.append(outline);
  }
  host.append(source);
}
