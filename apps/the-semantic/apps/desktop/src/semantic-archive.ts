import { z } from 'zod';
import { ResearchRecordSchema } from '../../../packages/runtime/src/contracts.js';
import { read } from './client.js';
import { el, button, utc } from './dom.js';

/** Lists completed source records; the host opens their original editorial view. */
export function mountSemanticArchive(host: HTMLElement, reader: typeof read, openResearch?: (id: string) => void): () => void {
  let disposed = false; let generation = 0;
  host.append(el('p', 'Completed research · Newest first. Open a record in the Research tab to inspect its original evidence.', 'lead'));
  const notice = el('p', 'Reading retained research…', 'caption'); notice.setAttribute('role', 'status');
  const list = el('section');
  const refresh = button('Refresh research ↻', () => { void load(); }, 'refresh'); host.append(refresh, notice, list);
  async function load(): Promise<void> {
    const current = ++generation; refresh.disabled = true; notice.textContent = 'Reading retained research…'; list.replaceChildren();
    try {
      const result = z.object({ research: z.array(ResearchRecordSchema).max(100) }).strict().parse(await reader({ operation: 'research.list', order: 'newest' }));
      if (disposed || current !== generation) return;
      const records = result.research.filter(record => record.status === 'FINISHED').sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at) || a.research_id.localeCompare(b.research_id));
      notice.textContent = `${records.length} completed records · Newest first · Up to 100 source records · Read ${utc(new Date().toISOString())}`;
      if (!records.length) list.append(el('p', 'No completed research is available.', 'empty'));
      if (!openResearch) list.append(el('p', 'Opening the Research tab is unavailable in this host.', 'caption'));
      for (const record of records) {
        const row = button('', () => { if (!disposed) openResearch?.(record.research_id); }, 'semantic-source-row'); row.disabled = !openResearch;
        row.append(el('p', utc(record.created_at), 'eyebrow'), el('h3', record.title), el('p', record.question), el('span', 'Open in Research →', 'record-id')); list.append(row);
      }
    } catch { if (!disposed && current === generation) notice.textContent = 'Research unavailable. No sample records are substituted.'; }
    finally { if (!disposed && current === generation) refresh.disabled = false; }
  }
  void load(); return () => { disposed = true; generation++; };
}
