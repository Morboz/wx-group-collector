# 采集状态自检:进程、微信、群聊窗口、最近消息时间
$dir = 'F:\dev\wx-group-collector'
$grp = '参见大王'
$today = Get-Date -Format 'yyyy-MM-dd'
$jsonl = Join-Path $dir "data\messages-$today.jsonl"

Write-Host "===== 采集状态自检 $(Get-Date -Format 'HH:mm:ss') ====="

# 注意:所有组件的 exe 路径都含 "wx-group-collector",必须匹配脚本名而非路径
$c = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'collector\.py\s*$' }
if ($c) { Write-Host '[OK] 采集器进程在运行' }
else    { Write-Host '[X] 采集器没在跑 —— 双击 start.bat 启动'; exit }

$f = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*file_fetcher*' }
if ($f) { Write-Host '[OK] 文件搬运工在运行(新文件自动复制到 data\files)' }
else    { Write-Host '[!] 文件搬运工没在跑 —— 群文件不会被自动复制,重跑 start.bat' }

$k = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*file_clicker*' }
if ($k) { Write-Host '[OK] 文件自动下载器在运行(未下载文件自动右键下载)' }
else    { Write-Host '[!] 文件自动下载器没在跑 —— 群文件需手动双击,重跑 start.bat' }

$t = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*voice_transcriber*' }
if ($t) { Write-Host '[OK] 语音转写补录器在运行(转写补记到 voice-transcripts-*.jsonl)' }
else    { Write-Host '[!] 语音转写补录器没在跑 —— 语音不会有转写文字,重跑 start.bat' }

if (Get-Process Weixin -ErrorAction SilentlyContinue) { Write-Host '[OK] 微信在运行' }
else { Write-Host '[X] 微信没开 —— 双击 start.bat 重新启动'; exit }

# 群聊窗口是采集的"眼睛",被关掉就收不到消息
# 用 EnumWindows 枚举所有顶层窗口(MainWindowTitle 每进程只报一个,会漏)
Add-Type -TypeDefinition @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class WinEnum {
    public delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    public static string titles = "";
    public static bool Callback(IntPtr h, IntPtr l) {
        var sb = new StringBuilder(256);
        GetWindowText(h, sb, 256);
        titles += sb.ToString() + "\n";
        return true;
    }
    public static string AllTitles() {
        titles = "";
        EnumWindows(Callback, IntPtr.Zero);
        return titles;
    }
}
"@ -ErrorAction SilentlyContinue
$allTitles = [WinEnum]::AllTitles()
$found = $allTitles -match [regex]::Escape($grp)
if ($found) { Write-Host "[OK] 群聊窗口在 ($grp)" }
else { Write-Host "[X] 群聊窗口($grp)被关了 —— 双击 stop.bat 再双击 start.bat 即可恢复" }

if (Test-Path $jsonl) {
    $lines = (Get-Content $jsonl | Measure-Object -Line).Lines
    $last = Get-Content $jsonl -Tail 1 -Encoding UTF8
    if ($last -match '"iso": "([^"]+)"') {
        $t = [datetime]::Parse($Matches[1])
        $age = [int]((Get-Date) - $t).TotalMinutes
        Write-Host "[i] 今天已记录 $lines 条,最后一条是 $age 分钟前"
        if ($age -gt 10 -and $found) { Write-Host '    (群里可能只是暂时没人说话)' }
    }
} else { Write-Host '[!] 今天的 jsonl 文件还没生成' }
Write-Host '====================================='
Start-Sleep -Seconds 6

