"""Metrics from controller-owned gateway traces; no hidden grader text is exported."""
from collections import Counter
import json

TAXONOMY = ('MAX_TURNS','IDLE_LOOP','WRONG_VERIFY','BAD_EDIT','CONTEXT_OVERFLOW','REASONING','INFRA','TIMEOUT','REFUSAL')


def trace_metrics(path):
    requests=[]; chunks=[]; errors=[]; usages=[]; calls=[]; contents=[]; tool_results=[]
    if path.exists():
        for line in path.read_text().splitlines():
            try: event=json.loads(line)
            except ValueError: continue
            if event['kind']=='request':
                requests.append(event)
                tool_results.extend(m.get('content','') for m in event['payload'].get('messages',[]) if m.get('role')=='tool')
            elif event['kind']=='error': errors.append(event)
            elif event['kind']=='usage': usages.append(event['usage'])
            elif event['kind']=='response' and event.get('line','').startswith('data: {'):
                try: chunks.append((event['request_id'], json.loads(event['line'][6:])))
                except ValueError: pass
    by_call={}
    for request_id,chunk in chunks:
        for choice in chunk.get('choices',[]):
            delta=choice.get('delta',{})
            if delta.get('content'):contents.append(delta['content'])
            for call in delta.get('tool_calls',[]):
                key=(request_id,call.get('index',0)); item=by_call.setdefault(key,{'name':'','arguments':''})
                f=call.get('function',{})
                item['name']+=f.get('name','');item['arguments']+=f.get('arguments','')
    calls=list(by_call.values()); malformed=0
    for c in calls:
        try: json.loads(c['arguments'])
        except ValueError: malformed+=1
    repeated=max(Counter((c['name'],c['arguments']) for c in calls).values(),default=0)
    return {'requests':len(requests),'prompt_tokens':sum(u.get('prompt_tokens',0) for u in usages),
        'completion_tokens':sum(u.get('completion_tokens',0) for u in usages),
        'reasoning_tokens':sum(u.get('completion_tokens_details',{}).get('reasoning_tokens',0) for u in usages),
        'cost_usd':sum(u.get('cost',0) for u in usages),'accounted_requests':len(usages),
        'tool_calls':len(calls),'tools':dict(Counter(c['name'] for c in calls)),
        'malformed_calls':malformed,'max_identical_call_count':repeated,
        'tool_errors':sum('error' in str(v).lower() for v in set(map(str,tool_results))),
        'upstream_errors':[e.get('status') for e in errors],
        '_error_text':' '.join(str(e.get('detail','')) for e in errors),
        '_assistant_text':''.join(contents)}


def failure_tag(status, passed, metrics, max_requests):
    if passed:return None
    text=metrics.get('_error_text','').lower()
    if status=='timeout':return 'TIMEOUT'
    if 'context' in text and any(s in text for s in ('exceed','maximum','length')):return 'CONTEXT_OVERFLOW'
    if metrics.get('requests',0)>=max_requests:return 'MAX_TURNS'
    if metrics.get('max_identical_call_count',0)>=3:return 'IDLE_LOOP'
    if metrics.get('upstream_errors') or status in ('error','interrupted'):return 'INFRA'
    if metrics.get('malformed_calls') or metrics.get('tool_errors'):return 'BAD_EDIT'
    words=metrics.get('_assistant_text','').lower()
    if any(x in words for x in ('cannot assist','unable to help','i must refuse')):return 'REFUSAL'
    if any(x in words for x in ('verified','all tests pass','successfully completed')):return 'WRONG_VERIFY'
    return 'REASONING'
