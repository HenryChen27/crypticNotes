"""Launch the packaged GUI, not just its Python imports, on a macOS runner."""
import json
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
app=next((root/'dist-macos').glob('*.app'))
executable=app/'Contents/MacOS'/app.stem
report=root/'out/macos-startup.json'
report.parent.mkdir(parents=True,exist_ok=True)
report.unlink(missing_ok=True)
try:
    result=subprocess.run([str(executable),'--startup-smoke',str(report)],
                          capture_output=True,text=True,timeout=90)
    print(result.stdout)
    print(result.stderr)
    result.check_returncode()
    data=json.loads(report.read_text())
    assert data['visible'] and data['width']>0 and data['height']>0,data
    assert data['dialog_above_companion'] and data['dialog_accepts_mouse'],data
    print('Packaged GUI startup passed:',data)
finally:
    logs=Path.home()/'Library/Application Support/IdentityVMapAssistant/out/mapmatching'
    for name in ('ui_error.log','native_crash.log'):
        path=logs/name
        if path.exists():
            print(name,path.read_text(errors='replace')[-16000:])
