"""Bounded independent analysis items with durable checkpoints and live status."""
from parallel_items import completed_items
from managed_ollama import workers
from progress_events import update_progress
from runtime_context import require_messages
from runtime_support import PartCheckpoint


def analyze_items(items, compute, params, module, unit):
    """Items contain key, system, user, texts. Compute receives one immutable item.

    Each worker owns a separate checkpoint object/file; only this coordinator
    assembles results. No nested parallel pools or shared checkpoint writes.
    """
    count = workers(params)
    keys = [item['key'] for item in items]
    if len(set(keys)) != len(keys):
        raise ValueError('Arbeitseinheiten benötigen eindeutige Schlüssel.')
    update_progress(completed=0, total=len(items), unit=unit, reused=0, failed=0,
                    failure_kind='', context_blocked=False)
    # Inspect every actual prompt before any new inference for this module.
    for item in items:
        require_messages([{'content': item['system']}, {'content': item['user']}], params)

    def work(item):
        checkpoint = PartCheckpoint(module, params)
        inputs = {key: item[key] for key in ('system', 'user', 'texts')}
        result = checkpoint.run(item['key'], inputs, lambda: compute(item))
        return result, checkpoint.hits

    failed = 0
    def on_error(index, exc):
        nonlocal failed
        from runtime_context import ContextBudgetError
        failed += 1
        # Never copy exception strings or study identifiers into live status.
        update_progress(failed=failed, failure_kind=(
            'context' if isinstance(exc, ContextBudgetError) else 'analysis'))

    ordered = [None] * len(items)
    done = reused = 0
    for index, (result, hits) in completed_items(items, work, count, on_error=on_error):
        ordered[index] = result
        done += 1
        reused += hits
        update_progress(completed=done, reused=reused)
    return ordered
