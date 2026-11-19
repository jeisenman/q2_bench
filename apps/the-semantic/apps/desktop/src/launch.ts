/** Parses the sole supported deep link flag without accepting arbitrary URLs. */
export function researchSessionArgument(args: string[]): string | undefined {
  const positions = args.flatMap((arg, index) => arg === '--research-session' ? [index] : []);
  if (!positions.length) return undefined;
  if (positions.length !== 1) throw new Error('Supply --research-session once.');
  const value = args[positions[0]! + 1];
  if (!value || !/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/.test(value)) throw new Error('--research-session requires a valid session ID.');
  return value;
}

/** Validates Electron single-instance metadata, which avoids reordered argv. */
export function forwardedResearchSession(value: unknown): string | undefined {
  if (typeof value !== 'object' || value === null || Array.isArray(value) || Object.keys(value).length !== 1 || !('research_session' in value)) {
    throw new Error('Invalid session forwarding metadata.');
  }
  if (value.research_session === null) return undefined;
  if (typeof value.research_session !== 'string' || !/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/.test(value.research_session)) {
    throw new Error('Invalid forwarded session ID.');
  }
  return value.research_session;
}
