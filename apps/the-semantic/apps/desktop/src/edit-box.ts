import { el } from './dom.js';

/** Applies the shared document field style without changing persistence behavior. */
export function styleEditBox(field: HTMLInputElement | HTMLTextAreaElement, title = false): void {
  field.classList.add('edit-box');
  field.classList.toggle('edit-box-title', title);
}

/** Creates a labelled field for an explicit document edit. */
export function createEditBox(name: string, label: string, value: string): HTMLInputElement | HTMLTextAreaElement {
  const field = ['title', 'name', 'version', 'model'].includes(name) ? el('input') : el('textarea');
  field.name = name; field.value = value; field.setAttribute('aria-label', label);
  styleEditBox(field, name === 'title' || name === 'name');
  if (field.tagName === 'TEXTAREA') (field as HTMLTextAreaElement).rows = Math.min(24, Math.max(4, value.split('\n').length + Math.ceil(value.length / 90)));
  return field;
}
