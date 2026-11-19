/** Creates a text-only element. Service strings never enter HTML. */
export function el<K extends keyof HTMLElementTagNameMap>(tag: K, text = '', className = ''): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag); node.textContent = text; node.className = className; return node;
}
/** Formats an evidence timestamp explicitly in UTC. */
export function utc(value: string): string {
  return new Date(value).toISOString().replace('T', ' · ').replace(/\.\d{3}Z$/, ' UTC');
}
/** Creates a finite action button. */
export function button(label: string, action: () => void, className = ''): HTMLButtonElement {
  const node = el('button', label, className); node.type = 'button'; node.onclick = action; return node;
}
