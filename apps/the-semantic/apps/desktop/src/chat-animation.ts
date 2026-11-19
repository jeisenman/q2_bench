/** Reveals a completed reply in bounded steps, without changing its evidence. */
export function revealReply(host: HTMLElement, text: string, finished: () => void): () => void {
  const win = host.ownerDocument.defaultView!;
  const chunks = Math.min(75, Math.max(1, Math.ceil(text.length / 24)));
  const step = Math.ceil(text.length / chunks);
  let offset = 0; let canceled = false; let timer: number | undefined;
  host.textContent = '';
  function tick(): void {
    if (canceled) return;
    offset = Math.min(text.length, offset + step); host.textContent = text.slice(0, offset);
    if (offset === text.length) { finished(); return; }
    timer = win.setTimeout(tick, 16);
  }
  tick();
  return () => { canceled = true; if (timer !== undefined) win.clearTimeout(timer); };
}
