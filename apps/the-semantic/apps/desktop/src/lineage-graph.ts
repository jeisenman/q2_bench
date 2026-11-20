import { nodeKey, type LineageGraph, type LineageNode, type LineageEdge, type NodeID } from './lineage-contracts.js';
export interface Neighborhood { nodes:LineageNode[];edges:LineageEdge[];candidateNodes:number;candidateEdges:number }
/** Selects declared incident edges only, in source order, with explicit display limits. */
export function neighborhood(graph:LineageGraph, selected:NodeID, maxNodes=40, maxEdges=80):Neighborhood {
  if(!Number.isInteger(maxNodes)||maxNodes<1||!Number.isInteger(maxEdges)||maxEdges<1)throw new Error('Graph display limits must be positive integers.');
  const key=nodeKey(selected);const center=graph.nodes.find(n=>nodeKey(n.id)===key);
  if(!center)throw new Error('Selected node is absent from the current graph.');
  const incident=graph.edges.filter(e=>nodeKey(e.source)===key||nodeKey(e.target)===key);
  const candidates=new Set([key]);for(const edge of incident){candidates.add(nodeKey(edge.source));candidates.add(nodeKey(edge.target));}
  const nodes=[center,...graph.nodes.filter(n=>nodeKey(n.id)!==key&&candidates.has(nodeKey(n.id)))].slice(0,maxNodes);
  const shown=new Set(nodes.map(n=>nodeKey(n.id)));
  return {nodes,edges:incident.filter(e=>shown.has(nodeKey(e.source))&&shown.has(nodeKey(e.target))).slice(0,maxEdges),candidateNodes:candidates.size,candidateEdges:incident.length};
}
