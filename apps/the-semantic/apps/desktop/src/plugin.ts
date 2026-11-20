import { ResearchRecordSchema, PluginManifestSchema, type ResearchRecord } from '../../../packages/runtime/src/contracts.js';
import { chatDisplayText } from './chat-display.js';

/** Mounts one isolated page and releases its previous evidence capability. */
export function mountPlugin(host: HTMLElement, rawManifest: unknown, rawRecord: ResearchRecord): () => void {
  const manifest = PluginManifestSchema.parse(rawManifest);
  const research = ResearchRecordSchema.parse(rawRecord);
  const iframe = document.createElement('iframe');
  iframe.title = `${manifest.name}: selected run evidence`;
  iframe.setAttribute('sandbox', 'allow-scripts');
  iframe.referrerPolicy = 'no-referrer';
  iframe.setAttribute('credentialless', '');
  iframe.src = `http://127.0.0.1:5056${manifest.entry_path}`;
  const channel = new MessageChannel();
  let disposed = false;
  iframe.addEventListener('load', () => {
    if (disposed) return;
    iframe.contentWindow?.postMessage({ type: 'semantic.init', version: 1 }, '*', [channel.port2]);
      channel.port1.postMessage({ type: 'semantic.data', version: 1, research: {
        title: chatDisplayText(research.title), model: research.model, status: research.status,
        output: research.output === null ? null : chatDisplayText(research.output),
      } });
  }, { once: true });
  host.replaceChildren(iframe);
  return () => { disposed = true; channel.port1.close(); channel.port2.close(); iframe.remove(); };
}
