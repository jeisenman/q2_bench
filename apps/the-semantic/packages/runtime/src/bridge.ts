import { spawn } from 'node:child_process';
import { isAbsolute } from 'node:path';
import { z } from 'zod';
import { Usage, type Model, type ModelRequest, type ModelResponse } from '@openai/agents';

const BridgeResult = z.object({
  output: z.string().max(2_000_000), input_tokens: z.number().int().nonnegative(),
  output_tokens: z.number().int().nonnegative(), duration_seconds: z.number().finite().nonnegative(),
  warning_count: z.number().int().nonnegative().optional().default(0),
}).strict();
const BridgeError = z.object({ error: z.object({ code: z.string().max(128), message: z.string().max(2000) }).strict() }).strict();
/** A safe adapter failure suitable for the completion record. */
export class BridgeFailure extends Error {
  constructor(message: string, readonly killed = false) { super(message); }
}
/** Runs one text-only model call through the Rust authentication boundary. */
export class RustModel implements Model {
  calls = 0;
  metrics: Record<string, number> = {};
  constructor(private readonly cli: string, private readonly model: string, private readonly deadline: number) {
    if (!isAbsolute(cli)) throw new BridgeFailure('SEMANTIC_CLI must be an absolute executable path.');
  }
  async getResponse(request: ModelRequest): Promise<ModelResponse> {
    if (++this.calls !== 1) throw new BridgeFailure('Only one model call is supported.');
    if (request.tools.length || request.handoffs.length || request.previousResponseId || request.conversationId) {
      throw new BridgeFailure('Tools, handoffs and conversation continuation are unsupported.');
    }
    const remaining = this.deadline - Date.now();
    if (remaining <= 0) throw new BridgeFailure('Research deadline expired.', true);
    const payload = JSON.stringify({
      instructions: request.systemInstructions ?? '',
      input: typeof request.input === 'string' ? request.input : JSON.stringify(request.input),
    });
    const raw = await this.invoke(payload, remaining, request.signal);
    let value: unknown;
    try { value = JSON.parse(raw); } catch { throw new BridgeFailure('Rust bridge returned invalid JSON.'); }
    const result = BridgeResult.safeParse(value);
    if (!result.success) throw new BridgeFailure('Rust bridge returned invalid completion evidence.');
    const v = result.data;
    this.metrics = { input_tokens: v.input_tokens, output_tokens: v.output_tokens,
      total_tokens: v.input_tokens + v.output_tokens, duration_seconds: v.duration_seconds, provider_warning_count: v.warning_count, sdk_model_calls: this.calls };
    return { usage: new Usage({ requests: 1, inputTokens: v.input_tokens, outputTokens: v.output_tokens,
      totalTokens: v.input_tokens + v.output_tokens }),
    output: [{ type: 'message', role: 'assistant', status: 'completed', content: [{ type: 'output_text', text: v.output }] }] };
  }
  private invoke(payload: string, remaining: number, signal?: AbortSignal): Promise<string> {
    return new Promise((resolve, reject) => {
      const child = spawn(this.cli, ['complete', '--model', this.model, '--timeout-seconds', String(Math.max(1, Math.floor(remaining / 1000)))],
        { stdio: ['pipe', 'pipe', 'pipe'], signal });
      let output = ''; let timedOut = false; let oversized = false;
      const timer = setTimeout(() => { timedOut = true; child.kill('SIGKILL'); }, remaining);
      child.stdout.on('data', (chunk: Buffer) => {
        if (Buffer.byteLength(output) + chunk.length > 2_100_000) { oversized = true; child.kill('SIGKILL'); }
        else output += chunk.toString('utf8');
      });
      child.stderr.resume(); // Provider diagnostics must not enter retained SDK evidence.
      child.stdin.on('error', () => {});
      child.on('error', () => { clearTimeout(timer); reject(new BridgeFailure('Rust bridge could not start or was aborted.', signal?.aborted)); });
      child.on('close', code => {
        clearTimeout(timer);
        if (timedOut || signal?.aborted) return reject(new BridgeFailure('Research deadline expired.', true));
        if (oversized) return reject(new BridgeFailure('Rust bridge output exceeded the supported size.'));
        if (code !== 0) {
          let failure: z.infer<typeof BridgeError> | undefined;
          try { failure = BridgeError.parse(JSON.parse(output)); } catch { /* Do not retain unvalidated child output. */ }
          const errCode = failure?.error.code ?? 'bridge_failed';
          // Only the typed bridge error is retained; never raw stderr.
          return reject(new BridgeFailure(failure ? `${errCode}: ${failure.error.message}` : 'Rust bridge failed without a valid error.', /timeout|deadline|killed/i.test(errCode)));
        }
        resolve(output);
      });
      child.stdin.end(payload);
    });
  }
  async *getStreamedResponse(_request: ModelRequest): AsyncIterable<never> {
    throw new BridgeFailure('Streaming is unsupported.');
  }
}
