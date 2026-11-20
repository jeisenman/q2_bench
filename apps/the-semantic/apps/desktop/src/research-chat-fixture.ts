import { button, el } from './dom.js';

const fixtureLabel = 'Illustrative fixture · Not the original research chat';

/** Creates a read-only example of a research question refinement chat. */
export function researchChatFixture(): HTMLElement {
  const stage = el('section', '', 'stage');
  stage.id = 'stage-chat';
  stage.append(el('p', '00 / CHAT THREAD', 'eyebrow'), el('h2', 'Chat thread'), el('p', fixtureLabel, 'caption'));
  const messages = (): HTMLElement => {
    const conversation = el('div', '', 'codex-thread');
    const items = [
    ['user', 'You', 'Do relationship managers who build more loan scenarios get better ROE?'],
    ['assistant', 'Codex', 'What group should we compare, and what would “better ROE” mean? Scenario work may be more common for larger or more complex relationships.'],
    ['user', 'You', 'Let’s stay within a relationship manager cohort. I want to compare booked loans and use realized ROE over the full life of each loan.'],
    ['assistant', 'Codex', 'We can define exposure as two or more distinct scenarios saved before booking versus exactly one. We should account for observable loan and borrower differences, plus manager cohort.'],
    ['user', 'You', 'Yes. Keep this as an association. Some loans may not have matured, and I have not chosen a client or time window yet.'],
    ['assistant', 'Codex', 'Draft question: Among booked loans in a selected client and booking window, is creating two or more distinct pre-booking scenarios, compared with one, associated with full-life realized ROE after adjustment for observable loan, borrower, and RM cohort differences? Unresolved: client, booking window, maturity rule, and available controls.'],
    ] as const;
    for (const [role, label, text] of items) {
      const message = el('article', '', `codex-message codex-message-${role}`);
      message.append(el('span', label, 'codex-message-label'), el('p', text, 'codex-bubble'));
      conversation.append(message);
    }
    return conversation;
  };

  const controls = el('div', '', 'research-chat-controls');
  const inline = messages();
  inline.id = 'research-chat-inline';
  inline.hidden = true;
  inline.prepend(el('p', fixtureLabel, 'caption'));
  const expand = button('Expand chat ▾', () => {
    inline.hidden = !inline.hidden;
    expand.textContent = inline.hidden ? 'Expand chat ▾' : 'Collapse chat ▴';
    expand.setAttribute('aria-expanded', String(!inline.hidden));
  });
  expand.setAttribute('aria-controls', inline.id);
  expand.setAttribute('aria-expanded', 'false');
  const open = el('a', 'Open chat thread');
  open.href = '#research-chat-example';
  open.addEventListener('click', (event) => {
    event.preventDefault();
    let dialog = stage.querySelector<HTMLDialogElement>('#research-chat-example');
    if (!dialog) {
      dialog = el('dialog', '', 'research-chat-dialog');
      dialog.id = 'research-chat-example';
      const heading = el('h2', 'Chat thread');
      heading.id = 'research-chat-dialog-heading';
      const caption = el('p', fixtureLabel, 'caption');
      caption.id = 'research-chat-dialog-caption';
      dialog.setAttribute('aria-labelledby', heading.id);
      dialog.setAttribute('aria-describedby', caption.id);
      dialog.append(heading, caption, messages());
      dialog.append(button('Close', () => dialog!.close()));
      stage.append(dialog);
    }
    dialog.showModal();
  });
  controls.append(open, expand);
  stage.append(controls, inline);
  return stage;
}
