using System;
using System.IO;
using System.Drawing;
using System.Windows.Forms;
using System.Threading.Tasks;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

class GameWindow : Form {
    readonly WebView2 view = new WebView2();
    readonly string root, profile, report, testScript;
    readonly Timer save = new Timer();
    bool dragging; Point start;
    bool allowClose, closing;
    Rectangle restoredBounds;
    NotifyIcon tray;
    TaskCompletionSource<string> safeSave;
    string lastCommand;
    readonly Timer commands=new Timer();
    FormWindowState visibleState=FormWindowState.Normal;
    WindowControl sizeControl,hideControl,soundControl;
    bool muted;
    bool wasMinimized;
    DateTime? autoCloseAt;
    void ReadWindowCommands(){
        try{
            string path=Path.Combine(profile,"window-command.json");
            if(File.Exists(path)){
                string text=File.ReadAllText(path);
                if(text!=lastCommand){
                    var command=new System.Web.Script.Serialization.JavaScriptSerializer().Deserialize<System.Collections.Generic.Dictionary<string,object>>(text);
                    lastCommand=text;string action=Convert.ToString(command["action"]);
                    if(action=="show")RestoreGame();
                    else if(action=="safe-close"){autoCloseAt=null;Close();}
                    else if(action=="auto-hide"&&WindowState!=FormWindowState.Minimized){
                        visibleState=WindowState;autoCloseAt=DateTime.UtcNow.AddSeconds(5);WindowState=FormWindowState.Minimized;
                    }
                }
            }
        }catch(Exception){}
        if(autoCloseAt.HasValue&&DateTime.UtcNow>=autoCloseAt.Value&&WindowState==FormWindowState.Minimized&&!closing){autoCloseAt=null;Close();}
    }
    void SetMuted(bool value){muted=value;if(view.CoreWebView2!=null)view.CoreWebView2.IsMuted=value;if(soundControl!=null){soundControl.Muted=value;soundControl.Invalidate();}}
    FrameBar titleBar;
    bool ProbeControls(){
        sizeControl.PerformClick();bool expanded=WindowState==FormWindowState.Maximized&&sizeControl.Inward;
        sizeControl.PerformClick();bool restored=WindowState==FormWindowState.Normal&&!sizeControl.Inward;
        hideControl.PerformClick();bool hidden=WindowState==FormWindowState.Minimized&&ShowInTaskbar&&File.ReadAllText(Path.Combine(profile,"window-state.json")).Contains("true");
        bool hiddenMuted=muted&&view.CoreWebView2.IsMuted;RestoreGame();bool restoredSound=!muted&&!view.CoreWebView2.IsMuted;soundControl.PerformClick();bool manualMuted=muted&&view.CoreWebView2.IsMuted;soundControl.PerformClick();return expanded&&restored&&hidden&&hiddenMuted&&restoredSound&&manualMuted&&!muted&&!view.CoreWebView2.IsMuted&&WindowState==FormWindowState.Normal;
    }
    void PublishState(){try{File.WriteAllText(Path.Combine(profile,"window-state.json"),"{\"hidden\":"+(WindowState==FormWindowState.Minimized?"true":"false")+"}");}catch(Exception){}}
    void RestoreGame(){autoCloseAt=null;Show();WindowState=visibleState;SetMuted(false);Activate();PublishState();}
    public GameWindow(string game, string data, string smoke, string title, string script) {
        root=Path.GetFullPath(game);profile=Path.GetFullPath(data);report=smoke;
        testScript=script;
        Directory.CreateDirectory(profile);
        Text=title;FormBorderStyle=FormBorderStyle.None;TopMost=true;
        Icon=System.Drawing.Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        BackColor=Color.FromArgb(18,30,42);ForeColor=Color.FromArgb(213,224,233);
        Padding=new Padding(1);
        Font=new Font("Microsoft YaHei UI",9f);
        MinimumSize=new Size(480,304);StartPosition=FormStartPosition.CenterScreen;
        Rectangle area=Screen.PrimaryScreen.WorkingArea;
        int width=Math.Min(1160,Math.Min((int)(area.Width*.72),(int)(area.Height*.78*16/9)));
        ClientSize=new Size(width,(int)(width*1441.0/2559)+42);
        var bar=new FrameBar {Dock=DockStyle.Top,Height=36,Padding=new Padding(8,3,8,3)};
        titleBar=bar;
        var label=new Label {Text=title,Dock=DockStyle.Fill,BackColor=Color.Transparent,ForeColor=Color.FromArgb(182,203,219),TextAlign=ContentAlignment.MiddleLeft,Padding=new Padding(7,0,0,0)};
        var close=new WindowControl {Kind=2,AccessibleName="保存并关闭",Dock=DockStyle.Right,Width=34,TabStop=false};
        close.Click+=(s,e)=>Close();
        var full=new WindowControl {Kind=1,AccessibleName="全屏或恢复窗口",Dock=DockStyle.Right,Width=34,TabStop=false};
        sizeControl=full;
        full.Click+=(s,e)=>{if(WindowState==FormWindowState.Maximized){WindowState=FormWindowState.Normal;Bounds=restoredBounds;full.Inward=false;}else{restoredBounds=Bounds;WindowState=FormWindowState.Maximized;full.Inward=true;}full.Invalidate();};
        var hide=new WindowControl {Kind=0,AccessibleName="隐藏到任务栏",Dock=DockStyle.Right,Width=34,TabStop=false};
        soundControl=new WindowControl {Kind=3,AccessibleName="静音或恢复声音",Dock=DockStyle.Right,Width=34,TabStop=false};
        soundControl.Click+=(s,e)=>SetMuted(!muted);
        hideControl=hide;
        hide.Click+=(s,e)=>{visibleState=WindowState;WindowState=FormWindowState.Minimized;};
        ShowInTaskbar=true;
        Resize+=(s,e)=>{bool minimized=WindowState==FormWindowState.Minimized;if(!minimized){visibleState=WindowState;autoCloseAt=null;}if(minimized!=wasMinimized){wasMinimized=minimized;SetMuted(minimized);}PublishState();};
        tray=new NotifyIcon {Icon=Icon,Text=title,Visible=true};
        var menu=new ContextMenuStrip();menu.Items.Add("显示小游戏",null,(s,e)=>RestoreGame());menu.Items.Add("保存并退出",null,(s,e)=>Close());
        tray.ContextMenuStrip=menu;tray.DoubleClick+=(s,e)=>RestoreGame();
        commands.Interval=100;commands.Tick+=(s,e)=>ReadWindowCommands();
        Shown+=(s,e)=>{PublishState();commands.Start();};
        label.MouseDown+=(s,e)=>{if(e.Button==MouseButtons.Left){dragging=true;start=Cursor.Position;}};
        label.MouseMove+=(s,e)=>{if(dragging){Point next=Cursor.Position;Location=new Point(Left+next.X-start.X,Top+next.Y-start.Y);start=next;}};
        label.MouseUp+=(s,e)=>dragging=false;
        bar.Controls.Add(label);bar.Controls.Add(soundControl);bar.Controls.Add(hide);bar.Controls.Add(full);bar.Controls.Add(close);
        var grip=new Panel {Dock=DockStyle.Bottom,Height=4};
        grip.Paint+=(s,e)=>{using(var pen=new Pen(Color.FromArgb(70,103,125),1))e.Graphics.DrawLine(pen,grip.Width-24,2,grip.Width-10,2);};
        grip.MouseDown+=(s,e)=>{if(e.Button==MouseButtons.Left){ReleaseCapture();SendMessage(Handle,0xA1,(IntPtr)17,IntPtr.Zero);}};
        view.Dock=DockStyle.Fill;Controls.Add(view);Controls.Add(bar);Controls.Add(grip);
        Shown+=async(s,e)=>await Initialize();
        save.Interval=1000;save.Tick+=async(s,e)=>await SaveAudio();
        FormClosed+=(s,e)=>{save.Stop();commands.Stop();tray.Dispose();view.Dispose();};
        FormClosing+=async(s,e)=>{
            if(allowClose||view.CoreWebView2==null)return;
            e.Cancel=true;if(closing)return;closing=true;
            try {
                safeSave=new TaskCompletionSource<string>();
                await view.CoreWebView2.ExecuteScriptAsync("window.__jellyfishHostSave(1)");
                if(await Task.WhenAny(safeSave.Task,Task.Delay(10000))!=safeSave.Task)throw new Exception("保存超时");
                SaveStorage(await safeSave.Task);
                allowClose=true;Close();
            } catch(Exception error){closing=false;RestoreGame();MessageBox.Show(this,"保存未完成，请重试："+error.Message,"游戏存档");}
        };
    }
    [System.Runtime.InteropServices.DllImport("user32.dll")] static extern bool ReleaseCapture();
    [System.Runtime.InteropServices.DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr h,int m,IntPtr w,IntPtr l);
    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)] struct PhysicalRect {public int Left,Top,Right,Bottom;}
    [System.Runtime.InteropServices.DllImport("dwmapi.dll")] static extern int DwmGetWindowAttribute(IntPtr window,int attribute,out PhysicalRect rect,int size);
    async Task Initialize() {
        try {
            var environment=await CoreWebView2Environment.CreateAsync(null,Path.Combine(profile,"webview2"));
            await view.EnsureCoreWebView2Async(environment);
            var web=view.CoreWebView2;
            web.IsMuted=muted;
            await web.AddScriptToExecuteOnDocumentCreatedAsync("window.__jellyfishHostPost=m=>chrome.webview.postMessage(m);"+File.ReadAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"safe-exit.js")));
            web.WindowCloseRequested+=(s,e)=>Close();
            if(testScript!=null)await web.AddScriptToExecuteOnDocumentCreatedAsync("window.__JELLYFISH_TEST=true");
            var serializer=new System.Web.Script.Serialization.JavaScriptSerializer();
            string storage=Path.Combine(profile,"local-storage.json");
            if(File.Exists(storage)) {
                string literal=serializer.Serialize(File.ReadAllText(storage));
                await web.AddScriptToExecuteOnDocumentCreatedAsync("try{Object.entries(JSON.parse("+literal+")).forEach(([k,v])=>localStorage.setItem(k,v))}catch(e){}");
            }
            web.WebMessageReceived+=async(s,e)=>{
                if(!e.Source.StartsWith("https://minigame.local/",StringComparison.OrdinalIgnoreCase))return;
                try {
                    var message=serializer.Deserialize<System.Collections.Generic.Dictionary<string,object>>(e.WebMessageAsJson);
                    if(message.ContainsKey("type")&&(string)message["type"]=="safe-exit"){
                        if(safeSave!=null){if(Convert.ToBoolean(message["saved"]))safeSave.TrySetResult((string)message["json"]);else safeSave.TrySetException(new Exception(Convert.ToString(message["reason"])));}return;
                    }
                    if(!message.ContainsKey("type")||(string)message["type"]!="save-storage")return;
                    int id=Convert.ToInt32(message["id"]);
                    string saveError=null;
                    try { SaveStorage((string)message["json"]); }
                    catch(Exception error){saveError=error.Message;}
                    if(saveError!=null){await web.ExecuteScriptAsync("JellyfishSaveAck("+id+","+serializer.Serialize(saveError)+")");return;}
                    await web.ExecuteScriptAsync("JellyfishSaveAck("+id+",null)");
                    if(message.ContainsKey("exit")&&Convert.ToBoolean(message["exit"])) {allowClose=true;Close();}
                }catch(Exception error){File.WriteAllText(Path.Combine(profile,"launcher-error.log"),error.ToString());}
            };
            web.Settings.AreDevToolsEnabled=false;web.Settings.AreDefaultContextMenusEnabled=false;
            web.Settings.AreBrowserAcceleratorKeysEnabled=false;web.Settings.IsStatusBarEnabled=false;
            web.Settings.IsZoomControlEnabled=false;
            web.SetVirtualHostNameToFolderMapping("minigame.local",root,CoreWebView2HostResourceAccessKind.DenyCors);
            web.NewWindowRequested+=(s,e)=>e.Handled=true;web.DownloadStarting+=(s,e)=>e.Cancel=true;
            web.NavigationStarting+=(s,e)=>{if(!e.Uri.StartsWith("https://minigame.local/",StringComparison.OrdinalIgnoreCase))e.Cancel=true;};
            web.AddWebResourceRequestedFilter("*",CoreWebView2WebResourceContext.All);
            web.WebResourceRequested+=(s,e)=>{
                var uri=new Uri(e.Request.Uri);
                if(uri.Host!="minigame.local"&&uri.Scheme!="data"&&uri.Scheme!="blob")
                    e.Response=environment.CreateWebResourceResponse(new MemoryStream(),403,"Blocked","");
            };
            string audio=Path.Combine(profile,"audio.json");
            if(File.Exists(audio)) {
                string literal=new System.Web.Script.Serialization.JavaScriptSerializer().Serialize(File.ReadAllText(audio));
                await web.AddScriptToExecuteOnDocumentCreatedAsync("try{localStorage.setItem('jellyfish.audioSettings',"+literal+")}catch(e){}");
            }
            web.NavigationCompleted+=async(s,e)=>{
                if(!e.IsSuccess){Fail("游戏资源加载失败："+e.WebErrorStatus);return;}
                File.WriteAllText(Path.Combine(profile,"ready"),"ready");save.Start();
                if(report!=null){
                    await Task.Delay(2500);
                    if(testScript!=null){
                        string tested=await web.ExecuteScriptAsync(File.ReadAllText(testScript));
                        File.WriteAllText(report,tested);
                        if(!tested.Contains("\"waitForExit\":true")&&!IsDisposed)Close();return;
                    }
                    string result=await web.ExecuteScriptAsync("({canvas:!!document.getElementById('gameCanvas'),matter:typeof Matter!=='undefined',width:innerWidth,height:innerHeight,storage:(()=>{try{localStorage.setItem('__nativeSmoke','yes');return localStorage.getItem('__nativeSmoke')==='yes'}catch(e){return false}})(),images:Object.keys(Loader.getAssets().images).length,audio:Object.keys(Loader.getAssets().audio).length,engine:'WebView2'})");
                    var smoke=serializer.Deserialize<System.Collections.Generic.Dictionary<string,object>>(result);
                    smoke["windowControls"]=ProbeControls();
                    await Task.Delay(180);
                    PhysicalRect rect;
                    if(DwmGetWindowAttribute(Handle,9,out rect,16)!=0)throw new Exception("无法取得窗口截图边界");
                    using(var snapshot=new Bitmap(rect.Right-rect.Left,rect.Bottom-rect.Top)){
                        using(var graphics=Graphics.FromImage(snapshot))graphics.CopyFromScreen(new Point(rect.Left,rect.Top),Point.Empty,snapshot.Size);
                        snapshot.Save(Path.ChangeExtension(report,".png"),System.Drawing.Imaging.ImageFormat.Png);
                    }
                    using(var header=new Bitmap(titleBar.Width,titleBar.Height)){
                        titleBar.DrawToBitmap(header,new Rectangle(Point.Empty,header.Size));
                        header.Save(Path.Combine(Path.GetDirectoryName(report),"frame-bar-preview.png"),System.Drawing.Imaging.ImageFormat.Png);
                    }
                    File.WriteAllText(report,serializer.Serialize(smoke));Close();
                }
            };
            web.Navigate("https://minigame.local/index.html");
        }catch(Exception e){Fail(e.ToString());}
    }
    async Task SaveAudio() {
        if(view.CoreWebView2==null||IsDisposed)return;
        try{
            string result=await view.CoreWebView2.ExecuteScriptAsync("localStorage.getItem('jellyfish.audioSettings')");
            string audio=new System.Web.Script.Serialization.JavaScriptSerializer().Deserialize<string>(result);
            if(audio!=null&&audio.Length<4096)File.WriteAllText(Path.Combine(profile,"audio.json"),audio);
        }catch(Exception){}
    }
    void SaveStorage(string json) {
        if(json==null||json.Length>1024*1024)throw new Exception("存档过大");
        var data=new System.Web.Script.Serialization.JavaScriptSerializer().Deserialize<System.Collections.Generic.Dictionary<string,string>>(json);
        foreach(var key in data.Keys)if(!key.StartsWith("jellyfish."))throw new Exception("无效存档");
        string target=Path.Combine(profile,"local-storage.json"),temp=target+".tmp";
        File.WriteAllText(temp,json);
        if(File.Exists(target))File.Replace(temp,target,null);else File.Move(temp,target);
    }
    void Fail(string message){
        allowClose=true;
        File.WriteAllText(Path.Combine(profile,"launcher-error.log"),message);
        if(report==null)MessageBox.Show(this,"小游戏启动失败，详情已保存到 launcher-error.log。","小游戏");
        Environment.ExitCode=1;Close();
    }
}
class FrameBar:Panel {
    public FrameBar(){DoubleBuffered=true;}
    protected override void OnPaintBackground(PaintEventArgs e){
        using(var brush=new System.Drawing.Drawing2D.LinearGradientBrush(ClientRectangle,Color.FromArgb(34,52,67),Color.FromArgb(20,34,47),90f))e.Graphics.FillRectangle(brush,ClientRectangle);
        var random=new Random(23);
        using(var pen=new Pen(Color.FromArgb(10,205,222,235),1))for(int i=0;i<Width/3;i++){int x=random.Next(Math.Max(1,Width)),y=random.Next(Math.Max(1,Height));e.Graphics.DrawLine(pen,x,y,x+1,y);}
        using(var pen=new Pen(Color.FromArgb(47,72,90),1))e.Graphics.DrawLine(pen,0,Height-1,Width,Height-1);
    }
}
class WindowControl:Control {
    public int Kind;public bool Inward,Muted;
    bool hover;
    public WindowControl(){SetStyle(ControlStyles.SupportsTransparentBackColor|ControlStyles.UserPaint|ControlStyles.AllPaintingInWmPaint|ControlStyles.OptimizedDoubleBuffer,true);BackColor=Color.Transparent;ForeColor=Color.FromArgb(197,216,231);AccessibleRole=AccessibleRole.PushButton;}
    public void PerformClick(){OnClick(EventArgs.Empty);}
    protected override void OnMouseEnter(EventArgs e){hover=true;Invalidate();base.OnMouseEnter(e);}
    protected override void OnMouseLeave(EventArgs e){hover=false;Invalidate();base.OnMouseLeave(e);}
    protected override void OnPaint(PaintEventArgs e){
        e.Graphics.SmoothingMode=System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
        float x=Width/2f,y=Height/2f;
        using(var pen=new Pen(hover?(Kind==2?Color.FromArgb(237,140,149):Color.FromArgb(235,247,255)):ForeColor,1.5f)){
            if(Kind==0)e.Graphics.DrawLine(pen,x-6,y,x+6,y);
            else if(Kind==2){e.Graphics.DrawLine(pen,x-5,y-5,x+5,y+5);e.Graphics.DrawLine(pen,x-5,y+5,x+5,y-5);}
            else if(Kind==3){
                e.Graphics.DrawPolygon(pen,new[]{new PointF(x-8,y-3),new PointF(x-5,y-3),new PointF(x,y-6),new PointF(x,y+6),new PointF(x-5,y+3),new PointF(x-8,y+3)});
                if(Muted){e.Graphics.DrawLine(pen,x+3,y-3,x+8,y+3);e.Graphics.DrawLine(pen,x+3,y+3,x+8,y-3);}
                else{e.Graphics.DrawArc(pen,new RectangleF(x-2,y-5,9,10),-65,130);e.Graphics.DrawArc(pen,new RectangleF(x-2,y-8,14,16),-60,120);}
            }
            else foreach(int sx in new[]{-1,1})foreach(int sy in new[]{-1,1}){
                float a=Inward?7:2,b=Inward?2:7,tx=x+sx*b,ty=y+sy*b;
                e.Graphics.DrawLine(pen,x+sx*a,y+sy*a,tx,ty);
                float direction=Inward?1:-1;e.Graphics.DrawLine(pen,tx,ty,tx+sx*direction*4,ty);e.Graphics.DrawLine(pen,tx,ty,tx,ty+sy*direction*4);
            }
        }
    }
}
class Program {
    [STAThread] static int Main(string[] args) {
        Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
        try{CoreWebView2Environment.GetAvailableBrowserVersionString();}catch(Exception){return 42;}
        if(Array.IndexOf(args,"--check-engine")>=0)return 0;
        Func<string,string,string> option=(name,fallback)=>{int i=Array.IndexOf(args,name);return i>=0&&i+1<args.Length?args[i+1]:fallback;};
        string root=option("--game-root",null),profile=option("--profile",null);
        if(root==null||profile==null||!File.Exists(Path.Combine(root,"index.html")))return 2;
        try{Application.Run(new GameWindow(root,profile,option("--smoke-report",null),option("--title","小游戏"),option("--test-script",null)));}
        catch(Exception error){Directory.CreateDirectory(profile);File.WriteAllText(Path.Combine(profile,"launcher-error.log"),error.ToString());return 1;}
        return Environment.ExitCode;
    }
}
