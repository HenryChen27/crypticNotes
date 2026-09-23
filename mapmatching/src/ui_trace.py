"""Bounded event trace for requests that never reach the matching worker."""
import json
from datetime import datetime,timezone
from ..paths import DATA_ROOT


def trace(event,**fields):
    try:
        folder=DATA_ROOT/'failure-records';folder.mkdir(parents=True,exist_ok=True)
        path=folder/'ui-events.jsonl'
        if path.exists() and path.stat().st_size>128*1024:
            lines=path.read_text(encoding='utf8').splitlines()[-200:]
            path.write_text('\n'.join(lines)+'\n',encoding='utf8')
        with path.open('a',encoding='utf8') as f:
            f.write(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(),
                version='2026.09.23-input',event=event,**fields),ensure_ascii=False)+'\n')
    except OSError:
        pass
