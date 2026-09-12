"""Bounded independent work items. The caller alone writes shared checkpoints."""
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED


def completed_items(items,compute,workers=1,*,on_error=None):
    if type(workers) is not int or not 1 <= workers <= 8:raise ValueError('Ein bis acht parallele Arbeitseinheiten erlaubt.')
    if workers==1:
        for index,item in enumerate(items):
            try: result=compute(item)
            except Exception as exc:
                if on_error: on_error(index,exc)
                raise
            yield index,result
        return
    iterator=iter(enumerate(items));running={};failure=None;exhausted=False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while running or not exhausted:
            while not exhausted and failure is None and len(running)<workers:
                try:index,item=next(iterator)
                except StopIteration:exhausted=True;break
                running[pool.submit(compute,item)]=index
            if not running:break
            done,_=wait(running,return_when=FIRST_COMPLETED)
            for future in done:
                index=running.pop(future)
                try:result=future.result()
                except Exception as exc:
                    if on_error: on_error(index,exc)
                    if failure is None:failure=exc
                    exhausted=True
                else:yield index,result
        if failure is not None:raise failure
