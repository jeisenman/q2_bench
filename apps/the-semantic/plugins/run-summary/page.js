(() => {
  'use strict';
  let activePort;
  const root = document.getElementById('evidence');
  const state = document.getElementById('state');
  const own = (o, key) => Object.prototype.hasOwnProperty.call(o, key);
  const object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
  const text = (v, max = 32000) => typeof v === 'string' && v.length <= max;
  function validRecord(r) {
    if (!object(r)) return false;
    const keys = ['title','model','status','output'];
    if (Object.keys(r).length !== keys.length || !keys.every(k => own(r, k))) return false;
    if (!['title','model'].every(k => text(r[k]) && r[k].length > 0)) return false;
    if (!['RUNNING','FINISHED','FAILED','KILLED'].includes(r.status)) return false;
    if (r.output !== null && !text(r.output, 2000000)) return false;
    return true;
  }
  function node(tag, value, className = '') {
    const n = document.createElement(tag); n.textContent = value; n.className = className; return n;
  }
  function render(r) {
    state.textContent = `${r.status} · ${r.model}`;
    root.replaceChildren(node('h2', r.title));
    root.append(node('h2','Retained output'), node('pre', r.output ?? 'No output retained.'));
  }
  window.addEventListener('message', event => {
    const d = event.data;
    if (event.source !== window.parent || !object(d) || Object.keys(d).length !== 2 || d.type !== 'semantic.init' || d.version !== 1 || event.ports.length !== 1) return;
    if (activePort) activePort.close();
    activePort = event.ports[0];
    activePort.onmessage = message => {
      const data = message.data;
      if (!object(data) || Object.keys(data).length !== 3 || data.type !== 'semantic.data' || data.version !== 1 || !validRecord(data.research)) {
        state.textContent = 'Selected evidence failed validation.'; root.replaceChildren(); return;
      }
      render(data.research);
    };
    activePort.start();
  });
  window.addEventListener('pagehide', () => activePort?.close());
})();
