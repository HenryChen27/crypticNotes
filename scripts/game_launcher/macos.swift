import Cocoa
import WebKit

func option(_ name:String,_ fallback:String?=nil)->String? {
    let args=CommandLine.arguments
    if let i=args.firstIndex(of:name),i+1<args.count{return args[i+1]}
    return fallback
}
if CommandLine.arguments.contains("--check-engine"){exit(0)}
guard let game=option("--game-root"),let profilePath=option("--profile") else {exit(2)}
let root=URL(fileURLWithPath:game,isDirectory:true).standardizedFileURL
let profile=URL(fileURLWithPath:profilePath,isDirectory:true)
try FileManager.default.createDirectory(at:profile,withIntermediateDirectories:true)
final class GameWindow:NSWindow {
    override var canBecomeKey:Bool {true}
    override var canBecomeMain:Bool {true}
}
final class DragBar:NSView {
    override func mouseDown(with event:NSEvent){window?.performDrag(with:event)}
}
final class WindowControl:NSButton {
    var kind=0
    var inward=false
    override func draw(_ dirtyRect:NSRect){
        if isHighlighted {NSColor.white.withAlphaComponent(0.12).setFill();bounds.fill()}
        NSColor(red:0.83,green:0.88,blue:0.92,alpha:1).setStroke()
        let path=NSBezierPath();path.lineWidth=1.5
        let x=bounds.midX,y=bounds.midY
        func line(_ ax:CGFloat,_ ay:CGFloat,_ bx:CGFloat,_ by:CGFloat){path.move(to:NSPoint(x:ax,y:ay));path.line(to:NSPoint(x:bx,y:by))}
        if kind==0{line(x-6,y,x+6,y)}else if kind==2{line(x-5,y-5,x+5,y+5);line(x-5,y+5,x+5,y-5)}else{
            for sx in [CGFloat(-1),CGFloat(1)]{for sy in [CGFloat(-1),CGFloat(1)]{
                let a:CGFloat=inward ? 7:2,b:CGFloat=inward ? 2:7,d:CGFloat=inward ? 1:-1
                let tx=x+sx*b,ty=y+sy*b;line(x+sx*a,y+sy*a,tx,ty);line(tx,ty,tx+sx*d*4,ty);line(tx,ty,tx,ty+sy*d*4)
            }}
        };path.stroke()
    }
}
final class Host:NSObject,NSApplicationDelegate,WKNavigationDelegate,NSWindowDelegate,WKUIDelegate,WKScriptMessageHandler {
    var window:NSWindow!
    var view:WKWebView!
    var timer:Timer?
    var allowClose=false
    var closing=false
    var restoredFrame:NSRect?
    var statusItem:NSStatusItem!
    var saveDeadline:DispatchWorkItem?
    var commands:Timer?
    var lastCommand=""
    var fullButton:WindowControl!
    func publishState(_ hidden:Bool){web?.evaluateJavaScript("window.__jellyfishSetMuted&&window.__jellyfishSetMuted(\(hidden))",completionHandler:nil);try? "{\"hidden\":\(hidden)}".write(to:profile.appendingPathComponent("window-state.json"),atomically:true,encoding:.utf8)}
    func applicationDidFinishLaunching(_ notification:Notification){
        let config=WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        config.mediaTypesRequiringUserActionForPlayback=[]
        config.userContentController.add(self,name:"game")
        let hostAudio=Bundle.main.bundleURL.deletingLastPathComponent().appendingPathComponent("host-audio.js")
        if let source=try? String(contentsOf:hostAudio,encoding:.utf8){config.userContentController.addUserScript(WKUserScript(source:source,injectionTime:.atDocumentStart,forMainFrameOnly:true))}
        let bridge=Bundle.main.bundleURL.deletingLastPathComponent().appendingPathComponent("safe-exit.js")
        if let source=try? String(contentsOf:bridge,encoding:.utf8){
            config.userContentController.addUserScript(WKUserScript(source:"window.__jellyfishHostPost=m=>webkit.messageHandlers.game.postMessage(m);"+source,injectionTime:.atDocumentStart,forMainFrameOnly:true))
        }
        if let saved=try? String(contentsOf:profile.appendingPathComponent("local-storage.json"),encoding:.utf8),
           let encoded=try? JSONSerialization.data(withJSONObject:[saved]),let literal=String(data:encoded,encoding:.utf8){
            config.userContentController.addUserScript(WKUserScript(source:"try{Object.entries(JSON.parse(\(literal)[0])).forEach(([k,v])=>localStorage.setItem(k,v))}catch(e){}",injectionTime:.atDocumentStart,forMainFrameOnly:true))
        }
        if let audio=try? String(contentsOf:profile.appendingPathComponent("audio.json"),encoding:.utf8),
           let encoded=try? JSONSerialization.data(withJSONObject:[audio]),
           let literal=String(data:encoded,encoding:.utf8){
            config.userContentController.addUserScript(WKUserScript(source:"try{localStorage.setItem('jellyfish.audioSettings',\(literal)[0])}catch(e){}",injectionTime:.atDocumentStart,forMainFrameOnly:true))
        }
        let area=NSScreen.main!.visibleFrame
        let width=min(1160,min(area.width*0.72,area.height*0.78*16/9)),height=width*1441/2559+26
        window=GameWindow(contentRect:NSRect(x:0,y:0,width:width,height:height),styleMask:[.borderless,.resizable,.miniaturizable],backing:.buffered,defer:false)
        window.title=option("--title","小游戏")!;window.level = .floating
        window.collectionBehavior=[.canJoinAllSpaces,.fullScreenAuxiliary]
        window.minSize=NSSize(width:480,height:304);window.delegate=self;window.isReleasedWhenClosed=false
        window.isMovableByWindowBackground=true
        let content=window.contentView!
        view=WKWebView(frame:NSRect(x:0,y:0,width:width,height:height-26),configuration:config)
        view.autoresizingMask=[.width,.height];view.navigationDelegate=self;view.uiDelegate=self
        content.addSubview(view)
        let bar=DragBar(frame:NSRect(x:0,y:height-26,width:width,height:26))
        bar.autoresizingMask=[.width,.minYMargin];bar.wantsLayer=true
        bar.layer?.backgroundColor=NSColor(red:0.094,green:0.141,blue:0.188,alpha:1).cgColor
        let label=NSTextField(labelWithString:window.title)
        label.frame=NSRect(x:10,y:4,width:width-210,height:20);label.textColor = .white;label.isSelectable=false
        bar.addSubview(label)
        let button=WindowControl(frame:.zero);button.kind=2;button.target=self;button.action=#selector(close);button.setAccessibilityLabel("保存并关闭")
        button.frame=NSRect(x:width-34,y:0,width:34,height:26);button.autoresizingMask=[.minXMargin]
        button.isBordered=false;button.contentTintColor = .white;bar.addSubview(button);content.addSubview(bar)
        let full=WindowControl(frame:NSRect(x:width-68,y:0,width:34,height:26));full.kind=1;full.target=self;full.action=#selector(toggleSize);full.setAccessibilityLabel("全屏或恢复窗口");fullButton=full
        full.autoresizingMask=[.minXMargin];full.isBordered=false;bar.addSubview(full)
        let hide=WindowControl(frame:NSRect(x:width-102,y:0,width:34,height:26));hide.target=self;hide.action=#selector(hideWindow);hide.setAccessibilityLabel("隐藏窗口")
        hide.autoresizingMask=[.minXMargin];hide.isBordered=false;bar.addSubview(hide)
        statusItem=NSStatusBar.system.statusItem(withLength:NSStatusItem.variableLength);statusItem.button?.title="水母"
        let menu=NSMenu();menu.addItem(withTitle:"显示小游戏",action:#selector(showWindow),keyEquivalent:"").target=self
        menu.addItem(withTitle:"保存并退出",action:#selector(close),keyEquivalent:"").target=self;statusItem.menu=menu
        window.center();window.makeKeyAndOrderFront(nil);NSApp.activate(ignoringOtherApps:true)
        view.loadFileURL(root.appendingPathComponent("index.html"),allowingReadAccessTo:root)
        timer=Timer.scheduledTimer(withTimeInterval:1,repeats:true){[weak self] _ in self?.saveAudio()}
        publishState(false)
        commands=Timer.scheduledTimer(withTimeInterval:0.2,repeats:true){[weak self] _ in
            guard let self=self,let text=try? String(contentsOf:profile.appendingPathComponent("window-command.json"),encoding:.utf8),text != self.lastCommand else{return}
            self.lastCommand=text
            if let data=text.data(using:.utf8),let message=try? JSONSerialization.jsonObject(with:data) as? [String:Any],message["action"] as? String=="show"{self.showWindow()}
        }
    }
    @objc func close(){window.close()}
    @objc func hideWindow(){window.miniaturize(nil);publishState(true)}
    @objc func showWindow(){window.deminiaturize(nil);window.makeKeyAndOrderFront(nil);NSApp.activate(ignoringOtherApps:true);publishState(false)}
    @objc func toggleSize(){if let frame=restoredFrame{window.setFrame(frame,display:true);restoredFrame=nil;fullButton.inward=false}else{restoredFrame=window.frame;window.setFrame((window.screen ?? NSScreen.main!).frame,display:true);fullButton.inward=true};fullButton.needsDisplay=true}
    func windowDidMiniaturize(_ notification:Notification){publishState(true)}
    func windowDidDeminiaturize(_ notification:Notification){publishState(false)}
    func applicationShouldHandleReopen(_ sender:NSApplication,hasVisibleWindows flag:Bool)->Bool {showWindow();return true}
    func saveFailed(_ reason:String){saveDeadline?.cancel();closing=false;showWindow();let alert=NSAlert();alert.messageText="保存未完成，请重试";alert.informativeText=reason;alert.runModal()}
    func saveStorage(_ text:String)throws {
        guard text.utf8.count<1024*1024,let data=text.data(using:.utf8),
          let values=try JSONSerialization.jsonObject(with:data) as? [String:String],
          values.keys.allSatisfy({$0.hasPrefix("jellyfish.")}) else {throw NSError(domain:"GameSave",code:1,userInfo:[NSLocalizedDescriptionKey:"无效存档"])}
        try text.write(to:profile.appendingPathComponent("local-storage.json"),atomically:true,encoding:.utf8)
    }
    func userContentController(_ userContentController:WKUserContentController,didReceive message:WKScriptMessage){
        if message.frameInfo.isMainFrame,let url=message.frameInfo.request.url,url.isFileURL,url.standardizedFileURL.path.hasPrefix(root.path+"/"),
           let body=message.body as? [String:Any],body["type"] as? String=="safe-exit",closing {
            guard body["saved"] as? Bool == true,let text=body["json"] as? String else {saveFailed(body["reason"] as? String ?? "保存失败");return}
            do {try saveStorage(text);saveDeadline?.cancel();allowClose=true;close()}catch{saveFailed(error.localizedDescription)}
            return
        }
        guard message.frameInfo.isMainFrame,let url=message.frameInfo.request.url,url.isFileURL,
          url.standardizedFileURL.path.hasPrefix(root.path+"/"),
          let body=message.body as? [String:Any],body["type"] as? String=="save-storage",
          let id=body["id"] as? Int,let text=body["json"] as? String else{return}
        do {try saveStorage(text)
            view.evaluateJavaScript("JellyfishSaveAck(\(id),null)"){_,_ in
                if body["exit"] as? Bool == true {self.allowClose=true;self.close()}
            }
        }catch{
            let literal=(try? JSONSerialization.data(withJSONObject:[error.localizedDescription])).flatMap{String(data:$0,encoding:.utf8)} ?? "[\"保存失败\"]"
            view.evaluateJavaScript("JellyfishSaveAck(\(id),\(literal)[0])",completionHandler:nil)
        }
    }
    func windowShouldClose(_ sender:NSWindow)->Bool {
        if allowClose{return true};if closing{return false};closing=true
        let deadline=DispatchWorkItem{[weak self] in if self?.closing == true{self?.saveFailed("保存超时")}}
        saveDeadline=deadline;DispatchQueue.main.asyncAfter(deadline:.now()+10,execute:deadline)
        view.evaluateJavaScript("window.__jellyfishHostSave(1)"){_,error in if let error=error{self.saveFailed(error.localizedDescription)}}
        return false
    }
    func webViewDidClose(_ webView:WKWebView){close()}
    func saveAudio(){
        view.evaluateJavaScript("localStorage.getItem('jellyfish.audioSettings')"){result,error in
            if let text=result as? String,text.utf8.count<4096{try? text.write(to:profile.appendingPathComponent("audio.json"),atomically:true,encoding:.utf8)}
        }
    }
    func windowWillClose(_ notification:Notification){timer?.invalidate();commands?.invalidate();view.stopLoading();NSApp.terminate(nil)}
    func applicationShouldTerminateAfterLastWindowClosed(_ sender:NSApplication)->Bool {true}
    func webView(_ webView:WKWebView,decidePolicyFor navigationAction:WKNavigationAction,decisionHandler:@escaping(WKNavigationActionPolicy)->Void){
        if let url=navigationAction.request.url,url.isFileURL,url.standardizedFileURL.path.hasPrefix(root.path+"/"){decisionHandler(.allow)}else{decisionHandler(.cancel)}
    }
    func webView(_ webView:WKWebView,createWebViewWith configuration:WKWebViewConfiguration,for navigationAction:WKNavigationAction,windowFeatures:WKWindowFeatures)->WKWebView? {nil}
    func webView(_ webView:WKWebView,didFinish navigation:WKNavigation!){
        try? "ready".write(to:profile.appendingPathComponent("ready"),atomically:true,encoding:.utf8)
        if let report=option("--smoke-report"){
            DispatchQueue.main.asyncAfter(deadline:.now()+2.5){
                webView.evaluateJavaScript("JSON.stringify({canvas:!!document.getElementById('gameCanvas'),matter:typeof Matter!=='undefined',width:innerWidth,height:innerHeight,storage:(()=>{try{localStorage.setItem('__nativeSmoke','yes');return localStorage.getItem('__nativeSmoke')==='yes'}catch(e){return false}})(),images:Object.keys(Loader.getAssets().images).length,audio:Object.keys(Loader.getAssets().audio).length,engine:'WKWebView'})"){result,error in
                    if let text=result as? String{try? text.write(toFile:report,atomically:true,encoding:.utf8)}
                    self.close()
                }
            }
        }
    }
    func webView(_ webView:WKWebView,didFailProvisionalNavigation navigation:WKNavigation!,withError error:Error){
        try? error.localizedDescription.write(to:profile.appendingPathComponent("launcher-error.log"),atomically:true,encoding:.utf8)
        NSApp.terminate(nil)
    }
}
let app=NSApplication.shared;app.setActivationPolicy(.regular)
let host=Host();app.delegate=host;app.run()
