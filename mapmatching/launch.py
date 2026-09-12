"""Lightweight entry point: spawned matching workers do not import Qt."""
if __name__ == '__main__':
    import multiprocessing
    import sys
    import ctypes
    import subprocess
    from pathlib import Path
    import traceback
    multiprocessing.freeze_support()
    if '--admin' in sys.argv:
        sys.argv.remove('--admin')
        if not ctypes.windll.shell32.IsUserAnAdmin():
            shell=ctypes.windll.shell32.ShellExecuteW
            shell.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_int]
            shell.restype=ctypes.c_void_p
            root=Path(__file__).resolve().parents[1]
            args=sys.argv[1:] if getattr(sys,'frozen',False) else ['-m','mapmatching.launch',*sys.argv[1:]]
            result=shell(None,'runas',sys.executable,subprocess.list2cmdline(args),str(root),0)
            if not result or result<=32:
                ctypes.windll.user32.MessageBoxW(None,'管理员启动未完成。可重新双击启动，或使用普通权限启动。','加页手记',0x40)
            raise SystemExit(0 if result and result>32 else 1)
    try:
        if '--self-test' in sys.argv:
            from mapmatching.portable_check import run
            run(sys.argv[sys.argv.index('--self-test')+1])
            raise SystemExit(0)
        from mapmatching.ui import main
        main()
    except Exception:
        from mapmatching.paths import DATA_ROOT
        root=DATA_ROOT
        log=root/'out/mapmatching/ui_error.log'
        log.parent.mkdir(parents=True,exist_ok=True)
        log.parent.mkdir(parents=True,exist_ok=True)
        log.write_text(traceback.format_exc(),encoding='utf-8')
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,f'启动失败，详情已写入：\n{log}','加页手记',0x10)
        raise
