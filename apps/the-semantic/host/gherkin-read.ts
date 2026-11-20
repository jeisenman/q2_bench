import { readGherkin } from '../apps/desktop/src/gherkin-source.js';
import { GherkinRequestSchema, GherkinListSchema, GherkinFeatureSchema, GherkinCapabilitiesSchema } from '../apps/desktop/src/gherkin-contracts.js';

/** One fixed-source host read; stdout contains validated public evidence only. */
async function main(): Promise<void> {
  let size = 0; const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) {
    const bytes = Buffer.from(chunk); size += bytes.length;
    if (size > 8192) throw new Error('Request exceeds limit.');
    chunks.push(bytes);
  }
  const request = GherkinRequestSchema.parse(JSON.parse(Buffer.concat(chunks).toString('utf8')));
  if (request.operation === 'gherkin.search' && request.mode === 'vector') {
    process.stdout.write(JSON.stringify({error:{code:'gherkin_vector_disabled',message:'Vector search is disabled.'}}) + '\n');
    process.exitCode = 1; return;
  }
  const value = await readGherkin(request);
  const schema = request.operation === 'gherkin.capabilities' ? GherkinCapabilitiesSchema : request.operation === 'gherkin.feature' ? GherkinFeatureSchema : GherkinListSchema;
  const encoded = JSON.stringify(schema.parse(value));
  if (Buffer.byteLength(encoded) > 2_097_152) throw new Error('Response exceeds limit.');
  process.stdout.write(encoded + '\n');
}
main().catch(() => {
  process.stdout.write(JSON.stringify({ error: { code: 'gherkin_unavailable', message: 'Committed Gherkin source could not be read within its size or time limit.' } }) + '\n');
  process.exitCode = 1;
});
