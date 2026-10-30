"""Bounded event trace for requests that never reach the matching worker."""
import json
import threading
from datetime import datetime,timezone
from ..paths import DATA_ROOT
record_directory = DATA_ROOT/'failure-records'
_trace_lock=threading.Lock()
EVENT_LIMIT=2*1024*1024
HEALTH_LIMIT=512*1024


def trace(event,**fields):
    try:
        # Keyboard heartbeats must not evict capture/matching history.
        health=event=='keyboard_health'
        line=json.dumps(dict(time=datetime.now(timezone.utc).isoformat(),
            version='2026.09.24-display-guard',event=event,**fields),ensure_ascii=False)+'\n'
        with _trace_lock:
            folder=record_directory;folder.mkdir(parents=True,exist_ok=True)
            path=folder/('input-health.jsonl' if health else 'ui-events.jsonl')
            limit=HEALTH_LIMIT if health else EVENT_LIMIT
            if path.exists() and path.stat().st_size>limit:
                path.replace(path.with_name(path.stem+'.previous.jsonl'))
            with path.open('a',encoding='utf8') as f:f.write(line)
    except (OSError, TypeError, ValueError):
        pass


_crash_stream=None

def enable_crash_logging(role):
    """Keep native fault stacks, which cannot be caught by a Python exception handler."""
    global _crash_stream
    if _crash_stream is not None:return
    import faulthandler,os
    try:
        record_directory.mkdir(parents=True,exist_ok=True)
        path=record_directory/('native-'+role+'.log')
        if path.exists() and path.stat().st_size>1024*1024:path.replace(path.with_suffix('.previous.log'))
        _crash_stream=path.open('a',encoding='utf-8')
        _crash_stream.write('Process '+str(os.getpid())+' '+datetime.now(timezone.utc).isoformat()+'\n');_crash_stream.flush()
        faulthandler.enable(_crash_stream,all_threads=True)
    except (OSError,RuntimeError):pass
