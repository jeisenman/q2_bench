const internalKey=/^(?:(?:research|experiment|attempt)(?:_run)?_id|(?:agent_)?(?:definition_)?digest|trace_id|(?:retained_)?metrics|(?:runtime_)?duration(?:_seconds|_ms)?|elapsed(?:_ms|_seconds)?|(?:input|output|total|cached|prompt|completion)_tokens|(?:token_)?usage|wall_time|latency(?:_ms|_seconds)?)$/i;
const internalLabel=/(?:research[ _-]*(?:run[ _-]*)?id|experiment[ _-]*(?:run[ _-]*)?id|attempt[ _-]*(?:run[ _-]*)?id|agent[ _-]*(?:definition[ _-]*)?digest|definition[ _-]*digest|trace[ _-]*id|(?:runtime[ _-]*)?duration[ _-]*(?:seconds|ms)|elapsed[ _-]*(?:ms|seconds)|(?:input|output|total|cached|prompt|completion)[ _-]*tokens|token[ _-]*usage|wall[ _-]*time|latency[ _-]*(?:ms|seconds)|retained[ _-]*metrics|["']?(?:metrics|usage|duration|elapsed|latency)["']?[*_\s]*[:=])/i;
const opaque=/\b(?:[a-f0-9]{32}|[a-f0-9]{64}|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})\b/gi;
const omitted='Internal execution metadata omitted.';
/** Project public chat text without changing the retained source evidence. */
export function chatDisplayText(text:string):string{
  function project(value:unknown):unknown{
    if(Array.isArray(value))return value.map(project);
    if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).filter(([key])=>!internalKey.test(key)).map(([key,item])=>[key,project(item)]));
    return typeof value==='string'?plain(value):value;
  }
  function plain(value:string):string{
    return value.split('\n').filter(line=>!internalLabel.test(line)&&!/^\s*(?:Wall time|Original token count|Output token count)\s*:/i.test(line)).join('\n').replace(opaque,'[internal reference]');
  }
  try{
    const parsed:unknown=JSON.parse(text);
    if(parsed&&typeof parsed==='object'){
      const result=project(parsed);if(JSON.stringify(result)===JSON.stringify(parsed))return text;const serialized=JSON.stringify(result,null,2);
      return serialized==='{}'||serialized==='[]'?omitted:serialized;
    }
  }catch{ /* Ordinary message text is not a JSON document. */ }
  const result=plain(text);return result.trim()?result:omitted;
}
