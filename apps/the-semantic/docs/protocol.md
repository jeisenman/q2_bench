# MVP protocol, version 1

Coordinator owns this contract. All JSON uses snake_case. All dates are UTC ISO
strings. API binds only to 127.0.0.1:5056. MLFLOW_TRACKING_URI defaults to
http://127.0.0.1:5055; MLFLOW_EXPERIMENT_NAME defaults to ra/the-semantic.
No extra application database. Native MLflow service is not modified.

## Agent

AgentDefinition has exactly these fields:

```json
{
  "id": "boundary-researcher",
  "version": "1",
  "name": "Boundary Researcher",
  "purpose": "Run one bounded research comparison.",
  "instructions": "Answer the research question using the supplied evidence.",
  "model": "gpt-5.6-sol",
  "allowed_tools": [],
  "page_plugin": "run-summary"
}
```

GET /health -> {status: "ok", tracking_uri, experiment_name} after MLflow read.
GET /api/research/v1/agents -> {agents: AgentRecord[]}.
POST /api/research/v1/agents with AgentDefinition -> AgentRecord.
GET /api/research/v1/agents/{id}?version=1 -> AgentRecord.
AgentRecord = AgentDefinition plus definition_digest and mlflow_run_id.
Same ID/version+same digest is idempotent; different content returns 409.
MVP requires allowed_tools empty and page_plugin run-summary. No fallback model.

The hypothesis/1 definition in agents/hypothesis uses this same contract, with
model gpt-6.1-sol and no tools. rc retrieves that exact version for drafting and
review. Its rubric readiness is not experiment acceptance. No new MCP tool or
persistent hypothesis-entity schema is introduced.

## Unaccepted research proposals

Saving a proposal is a storage operation. It does not require an agent, accept
an experiment, allocate an experiment/attempt, or invoke a model. Existing
research execution and its explicit acceptance checks stay separate.

POST /api/research/v1/proposals accepts exactly:

```json
{
  "title": "Loan scenario modeling and full-life realized ROE",
  "question": "Is scenario use associated with higher realized ROE?",
  "hypothesis": "The adjusted ROE difference is positive.",
  "plan": "Verify the data and comparison design before analysis.",
  "idempotency_key": "loan-scenario-realized-roe-proposal-v1"
}
```

All five fields are nonblank strings. Title is at most 1000 characters;
question, hypothesis and plan are each at most 16000; key is at most 128.
No execution fields are accepted. ProposalRecord has exactly proposal_id,
title, question, hypothesis, plan, status (always DRAFT), created_at, updated_at.
IDs use the existing identifier grammar; dates are UTC ISO strings.

GET /api/research/v1/proposals?order=newest|oldest -> {proposals: ProposalRecord[]}.
GET /api/research/v1/proposals/{proposal_id} -> ProposalRecord, or safe 404.
The separate proposal catalog has a 100-record limit. New saves return 201;
identical replays return 200 and Idempotent-Replayed: true. Changed content
under the same key returns 409. Proposals are immutable; revisions use a new key.

MLflow retains proposal.json in one run of kind proposal. An incomplete write
uses kind proposal_pending and stays hidden from reads until the full artifact
is written, its native storage run is terminated, and publication completes.
Identical replays recover pending publication without creating another run.
Native MLflow FINISHED describes storage completion; proposal status stays
DRAFT. A proposal is never evidence that scientific research was completed.

The desktop Proposals view uses finite list/get routes and a validated
proposals.save IPC mutation. Its form only saves drafts. Browser preview allows
only the corresponding fixed-origin proposal POST in addition to existing reads.
CLI and MCP expose proposal save/list/get through the same API contract.

## Accepted research specification

POST /api/research/v1/research accepts ResearchSpec:

```json
{
  "title": "A minimal research result",
  "question": "What is 2 + 2?",
  "hypothesis": "The answer is 4.",
  "plan": "Compute the sum and return a short answer.",
  "agent_id": "boundary-researcher",
  "agent_version": "1",
  "accepted": true,
  "max_runs": 1,
  "max_seconds": 90,
  "idempotency_key": "unique-per-request"
}
```

Create a root research run, nested experiment run and nested attempt run using
mlflow.parentRunId. Store immutable research/agent/plan artifacts and digest.
MVP permits max_runs=1 and max_seconds 1..300; reject unsupported requests.
Return ResearchRecord, including all three IDs and initial RUNNING status.
Same idempotency key+same spec returns the same record; changed spec returns 409.
Creation returns HTTP 201. An idempotent replay returns HTTP 200 with
Idempotent-Replayed: true. Clients execute the model only after a new HTTP 201.
One active execution is supported; reject concurrent new RUNNING research with
409. State and evidence remain in MLflow across API restarts. No auto replay.

ResearchRecord fields:
research_id, experiment_id, attempt_id, title, question, hypothesis, plan,
agent_id, agent_version, agent_definition_digest, model, page_plugin,
created_at, updated_at, status, max_runs, max_seconds, output (string or null),
metrics (object of finite numbers), trace_id (string or null), error (string or
null). Status is RUNNING, FINISHED, FAILED or KILLED. Never infer FINISHED from
missing evidence.

GET /api/research/v1/research?order=newest|oldest -> {research: ResearchRecord[]}.
GET /api/research/v1/research/{research_id} -> ResearchRecord.
POST /api/research/v1/research/{research_id}/complete accepts Completion:
attempt_id, status (FINISHED|FAILED|KILLED), output (string), metrics (finite
numeric values), sdk_events (array of event metadata), error (string or null).
Return updated ResearchRecord. Validate attempt ownership and terminal status.
Same completion is idempotent; conflicting completion is 409. Store SDK event
artifact and a native MLflow trace via its public tracing API, linked to IDs.
Artifacts must be saved before publishing FINISHED. Report incomplete writes.
Do not store raw Codex logs, credentials or private reasoning.

Error responses: {error: {code: string, message: string}}, appropriate 4xx/5xx.
Lists bounded to 100 entries for MVP; expose explicit limit if more are present.

## Rust executable

researcher-codex doctor: check API/MLflow and Codex executable presence.
researcher-codex agent put <agent.json>: POST definition, print AgentRecord JSON.
researcher-codex agents: list AgentRecords JSON.
researcher-codex list --order newest|oldest: list ResearchRecords JSON.
researcher-codex get <research_id>: get ResearchRecord JSON.
researcher-codex run --spec <spec.json>: create research, get exact pinned agent,
invoke Node runtime once, persist Completion, print terminal ResearchRecord.
Terminal FAILED or KILLED records are still printed but use a nonzero CLI exit.
An idempotent existing record must not cause model replay. Failed subprocesses
must persist FAILED/KILLED. Honor whole-run deadline, not only token generation.
SEMANTIC_API_URL defaults to http://127.0.0.1:5056; loopback only.

researcher-codex complete --model <model> --timeout-seconds <n>:
internal bridge; stdin JSON {instructions: string, input: string}; stdout JSON
BridgeResult {output: string, input_tokens: number, output_tokens: number,
duration_seconds: number, warning_count?: nonnegative integer}. New producers
include warning_count; absent legacy values mean zero. Only the source-pinned
informational "Under-development features enabled:" notice is permitted, and
the exact source-pinned notice that Code Mode is unavailable because its host
was explicitly disabled for this text-only bridge. Missing executables do not
qualify. Both require successful final output and usage. Rerouting, dropped events, policy
warnings and unknown warnings fail closed. Runtime retains provider_warning_count.
Failures return {error: {code,message}} with nonzero
exit. Use explicit CODEX_HOME (default ~/.codex), CODEX_BINARY (default the
validated installed packages/app-server-daemon/current/bin/codex beneath
CODEX_HOME), no shell sourcing or token extraction. Chat, doctor and experiments
share this resolver. Missing or invalid installed selection fails explicitly;
there is no fallback to a debug binary or another model.
Use codex exec --json --ephemeral --skip-git-repo-check --sandbox read-only in
an empty temporary work directory. Disable configured MCP servers, do not modify
user config. Reject observed tool use in this text-only MVP. Bound output,
redact provider errors, enforce timeout and child cleanup; no silent success.

researcher-codex mcp: official Rust MCP SDK, stdio; finite tools research_list,
research_get, agent_list, agent_get, research_run. Same API/client operations.
research_run requires accepted ResearchSpec and uses same execution path as CLI.
No stdout logs mixed into JSON-RPC. Q2_MCP_DEBUG=1 logs operation timing only.

## OpenAI Agents SDK runtime

Node entry packages/runtime/dist/main.js --request <request.json>.
Request {research_id, attempt_id, agent: AgentRecord, spec: ResearchSpec}.
SEMANTIC_CLI is the absolute built Rust executable used by its Model adapter.
Single Agent/Runner, maxTurns=1, retries=0. Pass agent instructions and actual
question/hypothesis/plan to Rust complete. Do not return a hard-coded test result.
Output Completion JSON on stdout, even on provider failure; no extra stdout logs.
SEMANTIC_DEADLINE_MS, when supplied by Rust, is an absolute Unix epoch timestamp
in milliseconds, not a remaining duration. The SDK uses the earlier of that
deadline and its specification budget. Fixture closure must cross this boundary.
SDK events contain event name, trace_id, span_id and type only, never credentials.
Use a custom local tracing processor; no OpenAI trace export credentials needed.
Provide actual token usage and duration metrics. Streaming, tools, handoffs and
retry loops are unsupported and must fail explicitly, not be simulated.

## Desktop and page plugin

apps/desktop: TypeScript Electron, editorial style named The Semantic. Live
Research and Agent Catalog views read API through finite validated preload IPC.
No generic URL/file/shell bridge. Default Research view shows newest first,
search and date sorting; opens exact record and five-stage provenance. Existing
mockup is a design reference, not imported production logic or fake live data.

GET /api/research/v1/page-plugins -> {plugins: PluginManifest[]}.
PluginManifest {id:"run-summary", version:"1", name, entry_path,
capabilities:["research.read"]}.
GET /plugins/run-summary/index.html and /plugins/run-summary/page.js serve the
trusted packaged page assets only. No arbitrary artifact HTML execution.
Render iframe sandbox="allow-scripts" on the separate HTTP origin, no same-origin
flag, Node, preload, credentials or direct API access. Parent sends a transferred
MessageChannel port with {type:"semantic.init", version:1}, then sends through
that port {type:"semantic.data", version:1, research: ResearchRecord}.
Child validates version/type and renders output and finite metric plot using
safe DOM/SVG. It cannot invoke execution. Unknown plugins are rejected.
Close ports/listeners when changing records. CSP explicitly limits frame origin.


## Semantic Layer desktop reads

The optional desktop adapter reuses the existing lineage-service JSON API.
Read requests add lineage.graph and lineage.node with an explicit NodeID object.
Only /graph and /node/{encoded identity} are mapped. The service origin is host
configuration SEMANTIC_LINEAGE_URL, default http://127.0.0.1:7420, restricted to
credential-free HTTP loopback origins. The renderer cannot supply an origin,
path, version override, formal operation or write operation. Full response
shapes, closed graph identities, timeout and byte limits are checked at reads.
Catalog and Graph use the same graph; displayed one-hop subsets retain edge
direction and explicit display caps. Existing coverage findings remain visible.

Help Center reads add help.list, help.search {query}, and help.article {id} for
the fixed public PrecisionLender HTTPS host. The corresponding knowledge.list,
knowledge.search {query}, and knowledge.article {id} operations read the configured
local export. The selected source is explicit; failures never choose another one.
Host-only SEMANTIC_ZENDESK_SNAPSHOT overrides the default ignored
var/zendesk-snapshot pointer. No renderer filesystem path or credential is accepted.

List responses contain articles, count and has_more. Articles contain numeric id,
title, url, updated_at, locale and inert plain text (or null). Snapshot responses
also include run_id, completed_at, article_count and chunk_count from the validated
producer manifest. An archive date is not live source freshness. Public article
links are validated before the main process opens them in the system browser;
other new windows and arbitrary navigation remain denied. The same finite reads
are proxied for browser development. No lineage/Zendesk MCP tools or execution
authorization are added by this desktop adapter.

## Versioned document editing

GET /api/research/v1/documents?kind=proposal|research|agent|sme&id=IDENTITY
returns {kind,id,version,content,updated_at}. Version zero is the original source.
GET /api/research/v1/documents/history with the same query returns {versions:[...]},
including the original source. POST /api/research/v1/documents takes exactly
{kind,id,base_version,content,idempotency_key}. A successful save publishes a new
numbered immutable snapshot. A stale base returns 409; an identical key and body
replays the saved response. The API uses its existing process serialization lock.
Proposal and research IDs retain their original run IDs. Agent IDs in this API
are MLflow definition run IDs; newer definitions resolve to the original document
anchor. SME IDs are stable JSON [namespace,name,column-or-empty] source identities.

Content is finite by kind: proposal has title/question/hypothesis/plan; research
adds nullable output; agent uses AgentDefinition; SME has text and nullable
source_commit. Agent changes require the same ID and a new version. Running
research is not editable. Source execution artifacts and agent pins remain
immutable; catalog and record reads expose the latest published document edits.
SME documents are explicitly local drafts, not approved upstream definitions.

Desktop reads add documents.get and documents.history with {kind,id}. The only
new write bridge is semantic.saveDocument, validated on both sides of preload.
Version history is inert text. Neither editing nor saving authorizes execution.

## Desktop research chat

GET /api/research/v1/chats?order=newest|oldest returns {chats:[ChatSummary]}.
POST /api/research/v1/chats takes {title,idempotency_key:UUID} and returns a
ChatRecord. GET /api/research/v1/chats/{chat_id} reads the durable snapshot.
POST /api/research/v1/chats/{chat_id}/messages takes exactly
{message,idempotency_key:UUID,base_version}. Each completed message pair increments
version once. Messages are bounded to 16,000 input characters and 100 retained
messages per chat. Exact replays return the stored pair without a provider call.

ChatRecord {chat_id,title,created_at,updated_at,version,messages}.
Each message is {id,role:user|assistant,text,created_at,proposal_id:null|ID,
tool:null|{name:proposal_prepare,status:completed}}. Only assistant messages attach
proposals. The strict runtime contract is packages/runtime/src/chats.ts.

The server invokes one fixed Rust native-auth completion per new user message.
The completion returns {message,proposal:null|{title,question,hypothesis,plan}}.
A proposed draft invokes proposal_prepare, persists a DRAFT, and publishes its ID
with the assistant message. Explicit requests and model-decided readiness both
permit drafting; client keyword matching does not decide readiness. Hypothesis
instructions, previous messages and bounded saved evidence are supplied context.

POST /api/research/v1/proposals/prepare takes ProposalInput and returns the saved
ProposalRecord. Rust MCP proposal_prepare calls the same route. Saving a draft
never allocates or accepts an experiment. Chat cannot invoke research_run.
Reservations prevent provider reruns after uncertain writes. Recovery returns a
saved completion or explicit failed assistant reply; provider diagnostics are
not retained. Independently saved draft evidence can remain in the catalog.

Desktop reads add chats.list/get; semantic.chat accepts only chats.create/send.
The host fixes origins, executable, model and deadlines. The chat POST deadline
is 200 seconds; native execution is bounded to 180 seconds. Reply animation is a
presentation of completed evidence. Modal saves use the existing documents API.

GET /api/research/v1/chats/{chat_id}/activity?key=UUID returns
{events:[{name,status,elapsed_ms}],done:boolean}. The key is the submitted message
idempotency UUID. This read uses bounded memory and can proceed during a turn.
Names are agent_get, research_list, proposal_list, codex_complete,
proposal_prepare, or chat_save; states are running, completed, or failed.
At most six operations are retained per turn and 256 recent turns per process.
Unknown keys return empty events and done:false; they do not authorize retries.
Assistant messages may include an activity array for restart persistence.
chat_save measures the initial conversation snapshot write; metadata publication
follows, and publication failures appear as failed in live activity. Only actual
operations produce events. No arguments, reasoning, or raw output are exposed.
Desktop reads include chats.activity; all other storage routes remain serialized.

## Historical conversation imports

GET /api/research/v1/transcripts returns {transcripts:[TranscriptSummary]};
GET /api/research/v1/transcripts/{id} returns
{transcript_id,imported_at,proposal_id,transcript}. The source object retains
source, thread_id, title, description, redactions:{}, and chronological items.
Items are public user/assistant text messages, tool_call records with call IDs,
names and inert argument strings, or matching tool_output strings/text blocks.
No analysis, system/developer messages, media or executable options are accepted.

POST /api/research/v1/transcripts takes exactly
{transcript,proposal_id:string|null,idempotency_key:UUID}. The optional proposal
must exist. Published imports are immutable; exact replay returns the same record
and conflicting key reuse returns 409. Pending imports stay hidden until their
artifact is persisted and one tag publishes the record. Limits: 100 imports,
1000 items, 1 MiB canonical UTF-8 source JSON, 256 KiB per text field, and one
matching output per call. No import or read invokes a provider.

The finite desktop read bridge adds transcripts.list/get. It has no import or
process operation. A Codex-tab transcript query selects one retained historical
record; its source identity must match the requested record. Live chat contracts
and versioned document saves retain their existing behavior.
