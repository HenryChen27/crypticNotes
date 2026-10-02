"""Window-specific ScreenCaptureKit screenshots (macOS 14 or newer).

No desktop fallback: a missing window must never silently become wallpaper.
"""
from threading import Event


def await_callback(start, timeout=5):
    done=Event()
    result=[]
    def complete(value,error):
        result.append((value,error))
        done.set()
    start(complete)
    if not done.wait(timeout):
        raise TimeoutError('ScreenCaptureKit 截图响应超时，请重试')
    value,error=result[0]
    if error is not None:
        raise RuntimeError(str(error))
    if value is None:
        raise RuntimeError('ScreenCaptureKit 未返回图像或窗口列表')
    return value


def select_window(windows, window_id, pid):
    for window in windows:
        owner=window.owningApplication()
        if int(window.windowID()) == window_id and owner is not None and int(owner.processID()) == pid:
            return window
    raise RuntimeError('游戏窗口已切换或无法共享，请回到游戏后重新识别')


def capture_window(window_id,pid):
    import ScreenCaptureKit as SC
    if not hasattr(SC,'SCScreenshotManager'):
        raise RuntimeError('此截图版本需要 macOS 14 或更新版本')
    content=await_callback(SC.SCShareableContent.getShareableContentWithCompletionHandler_)
    window=select_window(content.windows(),window_id,pid)
    content_filter=SC.SCContentFilter.alloc().initWithDesktopIndependentWindow_(window)
    config=SC.SCStreamConfiguration.alloc().init()
    scale=float(content_filter.pointPixelScale())
    config.setWidth_(max(1,round(window.frame().size.width*scale)))
    config.setHeight_(max(1,round(window.frame().size.height*scale)))
    config.setShowsCursor_(False)
    config.setPixelFormat_(0x42475241)  # kCVPixelFormatType_32BGRA
    config.setIgnoreShadowsSingleWindow_(True)
    return await_callback(lambda callback:
        SC.SCScreenshotManager.captureImageWithFilter_configuration_completionHandler_(
            content_filter,config,callback))
