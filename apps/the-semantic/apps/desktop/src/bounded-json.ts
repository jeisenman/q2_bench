export type ReadFetch = (url: string, init?: RequestInit) => Promise<Response>;
/** Reads bounded JSON with no credentials, redirect, or unbounded response body. */
export async function boundedJSON(url:string, fetcher:ReadFetch=fetch, maximum=32_000_000):Promise<unknown> {
  const response=await fetcher(url,{method:'GET',signal:AbortSignal.timeout(15000),credentials:'omit',redirect:'error'});
  if(!response.ok)throw new Error(`Evidence service returned HTTP ${response.status}.`);
  if(Number(response.headers.get('content-length')??0)>maximum) { await response.body?.cancel();throw new Error('Evidence response exceeds the permitted size.'); }
  const reader=response.body?.getReader();if(!reader)throw new Error('Evidence service returned no body.');
  let size=0;const chunks:Uint8Array[]=[];
  try {while(true){const {value,done}=await reader.read();if(done)break;size+=value.length;if(size>maximum)throw new Error('Evidence response exceeds the permitted size.');chunks.push(value);}}
  finally{await reader.cancel();}
  const bytes=new Uint8Array(size);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
  return JSON.parse(new TextDecoder().decode(bytes));
}
