import { LineageGraphSchema, ExplanationSchema, nodePath, type NodeID, nodeKey } from './lineage-contracts.js';
import { boundedJSON, type ReadFetch } from './bounded-json.js';
/** Restricts the independently configured service to a credential-free loopback origin. */
export function lineageOrigin(raw='http://127.0.0.1:7420'):string {
  const url=new URL(raw);
  if(url.protocol!=='http:'||!['127.0.0.1','localhost','[::1]'].includes(url.hostname)||url.username||url.password||url.pathname!=='/'||url.search||url.hash)throw new Error('SEMANTIC_LINEAGE_URL must be an HTTP loopback origin.');
  return url.origin;
}
/** Reads the current graph or one exact node, without write/formal capabilities. */
export async function readLineage(request:{operation:'lineage.graph'}|{operation:'lineage.node';id:NodeID},base:string,fetcher?:ReadFetch):Promise<unknown> {
  const raw=await boundedJSON(base+(request.operation==='lineage.graph'?'/graph':nodePath(request.id)),fetcher);
  if(request.operation==='lineage.graph')return LineageGraphSchema.parse(raw);
  const result=ExplanationSchema.parse(raw);
  if(nodeKey(result.node.id)!==nodeKey(request.id))throw new Error('Lineage service returned another node.');
  return result;
}
/** Accepts only canonical preview graph/node paths with no query or extra route. */
export function lineageRequestFromPath(raw:string):{operation:'lineage.graph'}|{operation:'lineage.node';id:NodeID}{
  if(raw==='/graph')return{operation:'lineage.graph'};
  if(!raw.startsWith('/node/'))throw new Error('Unsupported lineage read.');
  const wire=decodeURIComponent(raw.slice(6));const parts=wire.split('#');const pair=parts[0]?.split('/');
  if(parts.length!==2||pair?.length!==2)throw new Error('Invalid encoded node identity.');
  const id={namespace:decodeURIComponent(pair[0]!),name:decodeURIComponent(pair[1]!),...(parts[1]?{column:decodeURIComponent(parts[1])}:{})};
  if(nodePath(id)!==raw)throw new Error('Noncanonical lineage path.');return{operation:'lineage.node',id};
}
