import { z } from 'zod';
import { SessionSummarySchema, SessionRecordSchema, type SessionSummary, type SessionRecord } from '../../../packages/runtime/src/sessions.js';
import { read } from './client.js';
import { el, button, utc } from './dom.js';
import { chatDisplayText } from './chat-display.js';

/** Applies a display-only credential filter as a second boundary after API normalization. */
export function safeSessionText(value: string): string {
  return chatDisplayText(value.replace(/\bBearer\s+[^\s,;]+/gi, 'Bearer [REDACTED]')
    .replace(/\b(?:AKIA|ASIA)[A-Z0-9]{16}\b/g, '[REDACTED]')
    .replace(/\b(https?:\/\/)[^\s/@:]+:[^\s/@]+@/gi, '$1[REDACTED]@')
    .replace(/\b(?:sk|ghp|gho|github_pat)[-_][A-Za-z0-9_-]{12,}\b/g, '[REDACTED]')
    .replace(/\b((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|token|client[_-]?secret|aws[_-]?secret[_-]?access[_-]?key|authorization)["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)/gi, '$1[REDACTED]'));
}
interface Options { selectedID?: string; onSelect?: (id: string | undefined) => void; onConnection?: (message: string) => void }
/** Mounts read-only native session snapshots. Disposing invalidates pending reads. */
export function mountSessions(host: HTMLElement, options: Options = {}, reader: typeof read = read): () => void {
  let disposed = false; let generation = 0; let selectedID = options.selectedID;
  let sessions: SessionSummary[] = []; let selected: SessionRecord | undefined; let snapshotAt: string | undefined;
  const intro = el('section', '', 'intro');
  intro.append(el('p', '03 / RESEARCH SESSIONS', 'eyebrow'), el('h1', 'Follow the\nconversation.'),
    el('p', 'Native Codex sessions saved in MLflow. Read retained messages and tool status. Refresh to read new evidence from an active session.', 'lead'));
  const controls = el('div', '', 'session-controls');
  const freshness = el('p', 'Reading saved sessions…', 'caption'); freshness.setAttribute('aria-live', 'polite');
  const error = el('div'); error.setAttribute('role', 'status');
  const grid = el('div', '', 'session-grid'); const list = el('section', '', 'session-list');
  list.setAttribute('aria-label', 'Saved research sessions');
  const detail = el('section', '', 'session-detail'); detail.setAttribute('aria-label', 'Selected research session');
  const refresh = button('Refresh sessions ↻', () => { void load(); }, 'refresh');
  controls.append(refresh, freshness); grid.append(list, detail); host.append(intro, controls, error, grid);
  function fail(message: string): void {
    error.replaceChildren(el('p', message, 'error'));
    freshness.textContent = snapshotAt ? `STALE SNAPSHOT · Last successful read ${utc(snapshotAt)}. Counts are not live.` : 'No successful session snapshot is available.';
    options.onConnection?.('○ SESSION READ FAILED · RETAINED SNAPSHOT ONLY');
  }
  function renderList(): void {
    list.replaceChildren(el('div', `${sessions.length} SAVED SESSIONS`, 'rule-title'));
    if (!sessions.length) list.append(el('p', 'No native research sessions are saved. Start researcher-codex chat to create one before the first prompt.', 'empty'));
    for (const session of sessions) {
      const row = button('', () => {
        if (selectedID !== session.session_id) selected = undefined;
        selectedID = session.session_id; options.onSelect?.(selectedID); renderList(); renderDetail(); void load();
      }, `session-row${session.session_id === selectedID ? ' selected' : ''}`);
      row.append(el('p', `${session.status} · ${safeSessionText(session.model)}`, 'eyebrow'),
        el('h3', safeSessionText(session.title || 'Native research session')),
        el('p', utc(session.created_at), 'caption'),
        el('p', `${session.message_count} messages · ${session.event_count} events`, 'caption')); list.append(row);
    }
  }
  function metadata(parent: HTMLElement, label: string, value: string): void {
    const field = el('div'); field.append(el('h4', label), el('code', safeSessionText(value))); parent.append(field);
  }
  function renderDetail(): void {
    detail.replaceChildren(); delete detail.dataset.sessionId;
    if (!selected) {
      detail.append(el('h2', selectedID ? 'Session unavailable.' : 'Select a session.'),
        el('p', selectedID ? 'The requested session could not be read. Refresh to try the exact ID again.' : 'Open a saved session to read its messages, status and trace.')); return;
    }
    const r = selected; detail.dataset.sessionId = r.session_id;
    detail.append(el('p', `${r.status} · SNAPSHOT`, 'eyebrow'), el('h2', safeSessionText(r.title || 'Native research session')),
      el('p', `${r.message_count} saved messages · ${r.event_count} retained events`, 'session-counts'));
    if (r.status === 'ACTIVE') detail.append(el('p', 'The native session is active. Refresh to read new events. No model call is made by this view.', 'session-notice'));
    if (r.error || r.status === 'FAILED') detail.append(el('p', chatDisplayText(safeSessionText(r.error ?? 'The native session failed without a saved diagnostic.')), 'error'));
    const info = el('div', '', 'session-metadata');
    for (const [label, value] of [['Coordinator model', r.model], ['Created', utc(r.created_at)], ['Updated', utc(r.updated_at)],
      ['Working directory', r.cwd], ['Codex home', r.codex_home], ['Codex executable', r.codex_binary], ['Trace evidence', r.trace_id ? 'Retained' : 'Not retained'],
      ['Exit code', r.exit_code === null ? 'Not recorded' : String(r.exit_code)]]) metadata(info, label!, value!);
    detail.append(info, el('h3', 'Retained conversation'));
    if (!r.events.length) detail.append(el('p', r.status === 'ACTIVE' ? 'The session was saved before the first prompt. No events have been retained yet.' : 'No normalized events were retained. Message capture is not confirmed.', 'empty'));
    const timeline = el('div', '', 'session-timeline');
    for (const event of r.events) {
      const article = el('article', '', `session-event ${event.kind}`);
      article.append(el('p', `${event.kind.replaceAll('_', ' ').toUpperCase()} · ${utc(event.at)}`, 'eyebrow'));
      if (event.kind === 'tool') article.append(el('p', `${safeSessionText(event.tool_name ?? 'Unnamed tool')} · ${safeSessionText(event.status ?? 'Status not retained')}`, 'pre-line'));
      else if (event.text !== null) article.append(el('p', chatDisplayText(safeSessionText(event.text)), 'pre-line'));
      else article.append(el('p', chatDisplayText(safeSessionText(event.status ?? 'Metadata event; no message text retained.')), 'caption'));
      timeline.append(article);
    }
    detail.append(timeline, el('p', 'This view shows normalized saved evidence. Private reasoning, tool arguments and tool results are not available. Agent delegation is not implemented.', 'caption'));
  }
  async function load(): Promise<void> {
    const current = ++generation; refresh.disabled = true; freshness.textContent = 'Reading saved session evidence…'; error.replaceChildren();
    try {
      const listing = z.object({ sessions: z.array(SessionSummarySchema).max(100) }).strict().parse(await reader({ operation: 'sessions.list', order: 'newest' }));
      let record: SessionRecord | undefined;
      if (selectedID) record = SessionRecordSchema.parse(await reader({ operation: 'sessions.get', id: selectedID }));
      if (record && record.session_id !== selectedID) throw new Error('Session identity does not match the requested record.');
      if (disposed || current !== generation) return;
      sessions = listing.sessions; selected = record; snapshotAt = new Date().toISOString();
      if (record) sessions = sessions.map(s => s.session_id === record!.session_id ? SessionSummarySchema.parse(Object.fromEntries(Object.entries(record!).filter(([key]) => key !== 'events'))) : s);
      renderList(); renderDetail();
      freshness.textContent = `SNAPSHOT READ ${utc(snapshotAt)} · Refresh to read updates. Counts are not live.`;
      options.onConnection?.('● CONNECTED · SAVED NATIVE SESSION EVIDENCE');
    } catch {
      if (disposed || current !== generation) return;
      renderList(); renderDetail(); fail('Cannot read the saved session evidence. The service may be unavailable or returned an invalid record. Refresh to retry.');
    } finally { if (!disposed && current === generation) refresh.disabled = false; }
  }
  renderList(); renderDetail(); void load();
  return () => { disposed = true; generation++; };
}
