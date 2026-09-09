"""Split independent analytical items without truncating any input."""
from llm_client import ContextBudgetError

def bounded_batches(items, build_prompts, params):
    if not items:
        return
    system,user=build_prompts(items)
    size=len(system.encode('utf-8'))+len(user.encode('utf-8'))+320+int(params.get('max_tokens',4000))
    limit=int(params.get('num_ctx',32768))
    max_items=int(params.get('batch_items',8))
    if max_items<1:
        raise ValueError('batch_items muss positiv sein.')
    if size<=limit and len(items)<=max_items:
        yield items,system,user
        return
    if len(items)==1:
        raise ContextBudgetError('Eine analytische Einheit überschreitet das Kontextbudget. num_ctx erhöhen oder Datenstruktur explizit verkleinern.')
    midpoint=len(items)//2
    yield from bounded_batches(items[:midpoint],build_prompts,params)
    yield from bounded_batches(items[midpoint:],build_prompts,params)
