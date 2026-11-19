(() => {
  'use strict';
  let activePort;
  const root = document.getElementById('evidence');
  const state = document.getElementById('state');
  const own = (o, key) => Object.prototype.hasOwnProperty.call(o, key);
  const object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
  const text = (v, max = 32000) => typeof v === 'string' && v.length <= max;
  const id = v => text(v, 128) && /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/.test(v);
  function validRecord(r) {
    if (!object(r)) return false;
    const keys = ['research_id','experiment_id','attempt_id','title','question','hypothesis','plan','agent_id','agent_version',
      'agent_definition_digest','model','page_plugin','created_at','updated_at','status','max_runs','max_seconds','output','metrics','trace_id','error'];
    if (Object.keys(r).length !== keys.length || !keys.every(k => own(r, k))) return false;
    if (!['research_id','experiment_id','attempt_id','agent_id','agent_version'].every(k => id(r[k]))) return false;
    if (!['title','question','hypothesis','plan','model'].every(k => text(r[k]) && r[k].length > 0)) return false;
    if (!text(r.agent_definition_digest, 71) || !/^(sha256:)?[a-f0-9]{64}$/.test(r.agent_definition_digest)) return false;
    if (r.page_plugin !== 'run-summary' || !['RUNNING','FINISHED','FAILED','KILLED'].includes(r.status)) return false;
    if (!['created_at','updated_at'].every(k => text(r[k], 64) && /(?:Z|\+00:00)$/.test(r[k]) && Number.isFinite(Date.parse(r[k])))) return false;
    if (r.max_runs !== 1 || !Number.isInteger(r.max_seconds) || r.max_seconds < 1 || r.max_seconds > 300) return false;
    if (r.output !== null && !text(r.output, 2000000)) return false;
    if (r.error !== null && !text(r.error)) return false;
    if (r.trace_id !== null && !text(r.trace_id, 128)) return false;
    return object(r.metrics) && Object.keys(r.metrics).length <= 100 && Object.entries(r.metrics).every(([k,v]) => k.length <= 128 && typeof v === 'number' && Number.isFinite(v));
  }
  function node(tag, value, className = '') {
    const n = document.createElement(tag); n.textContent = value; n.className = className; return n;
  }
  function plot(r, keys, unit, title) {
    const entries = keys.filter(k => own(r.metrics, k)).map(k => [k, r.metrics[k]]);
    root.append(node('h2', title));
    if (!entries.length) { root.append(node('p', `No ${unit} measurements retained for this attempt.`, 'missing')); return; }
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', `0 0 720 ${entries.length * 36}`);
    svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', `${title} in ${unit}, attempt ${r.attempt_id}`);
    const max = Math.max(1, ...entries.map(([,value]) => value));
    entries.forEach(([key, value], index) => {
      const y = index * 36;
      const label = document.createElementNS(ns, 'text'); label.setAttribute('x','0'); label.setAttribute('y',String(y + 18));
      label.setAttribute('fill','#69685f'); label.setAttribute('font-size','11'); label.textContent = key;
      const bar = document.createElementNS(ns, 'rect'); bar.setAttribute('x','180'); bar.setAttribute('y',String(y + 4));
      bar.setAttribute('width', String(Math.max(0, value) / max * 350)); bar.setAttribute('height','20'); bar.setAttribute('fill','#9a4329');
      const number = document.createElementNS(ns, 'text'); number.setAttribute('x','545'); number.setAttribute('y',String(y + 18));
      number.setAttribute('font-size','11'); number.textContent = `${value} ${unit}`;
      svg.append(label, bar, number);
    });
    root.append(svg);
  }
  function render(r) {
    state.textContent = `${r.status} · ${r.model}`;
    root.replaceChildren(node('p', 'Research result', 'meta'));
    plot(r, ['duration_seconds','runtime_duration_seconds'], 'seconds', 'Duration');
    plot(r, ['input_tokens','output_tokens','total_tokens'], 'tokens', 'Token usage');
    root.append(node('h2','Retained output'), node('pre', r.output ?? 'No output retained.'));
    if (r.error) root.append(node('p',r.error,'missing'));
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
