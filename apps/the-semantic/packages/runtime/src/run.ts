import { Agent, Runner, setTraceProcessors } from '@openai/agents';
import { BridgeFailure, RustModel } from './bridge.js';
import { RuntimeRequestSchema, type Completion, type SDKEvent } from './contracts.js';

/** Executes the accepted plan once and returns safe completion evidence. */
export async function execute(raw: unknown, cli: string): Promise<Completion> {
  const request = RuntimeRequestSchema.parse(raw);
  const events: SDKEvent[] = [];
  const add = (event: SDKEvent) => { if (events.length < 100) events.push(event); };
  setTraceProcessors([{
    async onTraceStart(t) { add({ event: 'trace.start', trace_id: t.traceId }); },
    async onTraceEnd(t) { add({ event: 'trace.end', trace_id: t.traceId }); },
    async onSpanStart(s) { add({ event: 'span.start', trace_id: s.traceId, span_id: s.spanId, type: s.spanData.type }); },
    async onSpanEnd(s) { add({ event: 'span.end', trace_id: s.traceId, span_id: s.spanId, type: s.spanData.type }); },
    async shutdown() {}, async forceFlush() {},
  }]);
  const start = Date.now();
  const inherited = process.env.SEMANTIC_DEADLINE_MS;
  if (inherited !== undefined && (!/^\d+$/.test(inherited) || !Number.isSafeInteger(Number(inherited)))) {
    throw new Error('SEMANTIC_DEADLINE_MS must be an absolute millisecond timestamp.');
  }
  const deadline = Math.min(start + request.spec.max_seconds * 1000, inherited === undefined ? Infinity : Number(inherited));
  let model: RustModel | undefined;
  try {
    model = new RustModel(cli, request.agent.model, deadline);
    const agent = new Agent({ name: request.agent.name, instructions: request.agent.instructions,
      model, tools: [], modelSettings: { retry: { maxRetries: 0 } } });
    const runner = new Runner({ workflowName: 'The Semantic accepted research', traceIncludeSensitiveData: false });
    const input = `Question:\n${request.spec.question}\n\nHypothesis:\n${request.spec.hypothesis}\n\nAccepted experiment plan:\n${request.spec.plan}`;
    const result = await runner.run(agent, input, { maxTurns: 1 });
    if (typeof result.finalOutput !== 'string') throw new BridgeFailure('SDK did not return text output.');
    return { attempt_id: request.attempt_id, status: 'FINISHED', output: result.finalOutput,
      metrics: { ...model.metrics, runtime_duration_seconds: (Date.now() - start) / 1000 }, sdk_events: events, error: null };
  } catch (error) {
    return { attempt_id: request.attempt_id, status: error instanceof BridgeFailure && error.killed ? 'KILLED' : 'FAILED',
      output: '', metrics: { ...model?.metrics, runtime_duration_seconds: (Date.now() - start) / 1000 }, sdk_events: events,
      error: error instanceof BridgeFailure ? error.message : 'OpenAI Agents SDK execution failed.' };
  }
}
