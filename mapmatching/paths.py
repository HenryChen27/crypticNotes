"""Runtime roots.

Settings and logs use DATA_ROOT when frozen. The map library remains under
ROOT/maps so packaged and source builds share one editable library layout.
"""
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FROZEN=bool(getattr(sys,'frozen',False))
if FROZEN and sys.platform == 'darwin':
    DATA_ROOT=Path.home()/'Library/Application Support/IdentityVMapAssistant'
elif FROZEN:
    DATA_ROOT=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'IdentityVMapAssistant'
else:
    DATA_ROOT=ROOT
