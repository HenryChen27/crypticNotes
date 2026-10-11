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
final class Host:NSObject,NSApplicationDelegate,WKNavigationDelegate,NSWindowDelegate,WKUIDelegate {
    var window:NSWindow!
    var view:WKWebView!
    var timer:Timer?
    func applicationDidFinishLaunching(_ notification:Notification){
        let config=WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        config.mediaTypesRequiringUserActionForPlayback=[]
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
        window=GameWindow(contentRect:NSRect(x:0,y:0,width:width,height:height),styleMask:[.borderless,.resizable],backing:.buffered,defer:false)
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
        label.frame=NSRect(x:10,y:4,width:width-50,height:20);label.textColor = .white;label.isSelectable=false
        bar.addSubview(label)
        let button=NSButton(title:"×",target:self,action:#selector(close))
        button.frame=NSRect(x:width-34,y:0,width:34,height:26);button.autoresizingMask=[.minXMargin]
        button.isBordered=false;button.contentTintColor = .white;bar.addSubview(button);content.addSubview(bar)
        window.center();window.makeKeyAndOrderFront(nil);NSApp.activate(ignoringOtherApps:true)
        view.loadFileURL(root.appendingPathComponent("index.html"),allowingReadAccessTo:root)
        timer=Timer.scheduledTimer(withTimeInterval:1,repeats:true){[weak self] _ in self?.saveAudio()}
    }
    @objc func close(){window.close()}
    func saveAudio(){
        view.evaluateJavaScript("JSON.stringify(Object.fromEntries(Object.entries(localStorage)))"){result,error in
            if let text=result as? String,text.utf8.count<5*1024*1024{try? text.write(to:profile.appendingPathComponent("local-storage.json"),atomically:true,encoding:.utf8)}
        }
        view.evaluateJavaScript("localStorage.getItem('jellyfish.audioSettings')"){result,error in
            if let text=result as? String,text.utf8.count<4096{try? text.write(to:profile.appendingPathComponent("audio.json"),atomically:true,encoding:.utf8)}
        }
    }
    func windowWillClose(_ notification:Notification){timer?.invalidate();view.stopLoading();NSApp.terminate(nil)}
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
let app=NSApplication.shared;app.setActivationPolicy(.accessory)
let host=Host();app.delegate=host;app.run()
