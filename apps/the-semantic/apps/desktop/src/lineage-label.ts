import type { NodeID } from './lineage-contracts.js';

function readableName(value: string): string {
  const terminal = value.split('/').filter(Boolean).at(-1) ?? value;
  const words = terminal.replace(/[_-]+/g, ' ').trim();
  return words ? words[0]!.toUpperCase() + words.slice(1) : value;
}

/** Formats source names for reading without changing their stored identity. */
export function lineageTitle(id: NodeID): string {
  const name = readableName(id.name);
  return id.column ? `${name} · ${readableName(id.column)}` : name;
}
