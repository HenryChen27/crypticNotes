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
    public GameWindow(string game, string data, string smoke, string title, string script) {
        root=Path.GetFullPath(game);profile=Path.GetFullPath(data);report=smoke;
        testScript=script;
        Directory.CreateDirectory(profile);
        Text=title;FormBorderStyle=FormBorderStyle.None;TopMost=true;
        BackColor=Color.FromArgb(24,36,48);ForeColor=Color.FromArgb(213,224,233);
        MinimumSize=new Size(480,304);StartPosition=FormStartPosition.CenterScreen;
        Rectangle area=Screen.PrimaryScreen.WorkingArea;
        int width=Math.Min(1160,Math.Min((int)(area.Width*.72),(int)(area.Height*.78*16/9)));
        ClientSize=new Size(width,(int)(width*1441.0/2559)+38);
        var bar=new Panel {Dock=DockStyle.Top,Height=26};
        var label=new Label {Text=title,Dock=DockStyle.Fill,TextAlign=ContentAlignment.MiddleLeft,Padding=new Padding(10,0,0,0)};
        var close=new Button {Text="×",Dock=DockStyle.Right,Width=34,FlatStyle=FlatStyle.Flat,TabStop=false};
        close.FlatAppearance.BorderSize=0;close.Click+=(s,e)=>Close();
        label.MouseDown+=(s,e)=>{if(e.Button==MouseButtons.Left){dragging=true;start=Cursor.Position;}};
        label.MouseMove+=(s,e)=>{if(dragging){Point next=Cursor.Position;Location=new Point(Left+next.X-start.X,Top+next.Y-start.Y);start=next;}};
        label.MouseUp+=(s,e)=>dragging=false;
        bar.Controls.Add(label);bar.Controls.Add(close);
        var grip=new Panel {Dock=DockStyle.Bottom,Height=12};
        grip.Paint+=(s,e)=>ControlPaint.DrawSizeGrip(e.Graphics,ForeColor,new Rectangle(grip.Width-12,0,12,12));
        grip.MouseDown+=(s,e)=>{if(e.Button==MouseButtons.Left){ReleaseCapture();SendMessage(Handle,0xA1,(IntPtr)17,IntPtr.Zero);}};
        view.Dock=DockStyle.Fill;Controls.Add(view);Controls.Add(bar);Controls.Add(grip);
        Shown+=async(s,e)=>await Initialize();
        save.Interval=1000;save.Tick+=async(s,e)=>await SaveAudio();
        FormClosed+=(s,e)=>{save.Stop();view.Dispose();};
        FormClosing+=async(s,e)=>{
            if(allowClose||view.CoreWebView2==null)return;
            e.Cancel=true;if(closing)return;closing=true;
            try {
                string result=await view.CoreWebView2.ExecuteScriptAsync("window.JellyfishSession ? JellyfishSession.beforeClose() : JSON.stringify({})");
                SaveStorage(new System.Web.Script.Serialization.JavaScriptSerializer().Deserialize<string>(result));
                allowClose=true;Close();
            } catch(Exception error){closing=false;MessageBox.Show(this,"保存未完成，请重试："+error.Message,"游戏存档");}
        };
    }
    [System.Runtime.InteropServices.DllImport("user32.dll")] static extern bool ReleaseCapture();
    [System.Runtime.InteropServices.DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr h,int m,IntPtr w,IntPtr l);
    async Task Initialize() {
        try {
            var environment=await CoreWebView2Environment.CreateAsync(null,Path.Combine(profile,"webview2"));
            await view.EnsureCoreWebView2Async(environment);
            var web=view.CoreWebView2;
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
                        File.WriteAllText(report,tested);if(!IsDisposed)Close();return;
                    }
                    string result=await web.ExecuteScriptAsync("({canvas:!!document.getElementById('gameCanvas'),matter:typeof Matter!=='undefined',width:innerWidth,height:innerHeight,storage:(()=>{try{localStorage.setItem('__nativeSmoke','yes');return localStorage.getItem('__nativeSmoke')==='yes'}catch(e){return false}})(),images:Object.keys(Loader.getAssets().images).length,audio:Object.keys(Loader.getAssets().audio).length,engine:'WebView2'})");
                    File.WriteAllText(report,result);Close();
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
class Program {
    [STAThread] static int Main(string[] args) {
        Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
        try{CoreWebView2Environment.GetAvailableBrowserVersionString();}catch(Exception){return 42;}
        if(Array.IndexOf(args,"--check-engine")>=0)return 0;
        Func<string,string,string> option=(name,fallback)=>{int i=Array.IndexOf(args,name);return i>=0&&i+1<args.Length?args[i+1]:fallback;};
        string root=option("--game-root",null),profile=option("--profile",null);
        if(root==null||profile==null||!File.Exists(Path.Combine(root,"index.html")))return 2;
        Application.Run(new GameWindow(root,profile,option("--smoke-report",null),option("--title","小游戏"),option("--test-script",null)));
        return Environment.ExitCode;
    }
}
