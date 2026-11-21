# 一键启动群消息采集
# 流程: 开讲述人 -> 重启微信 -> 采集器自动登录并开始采集 -> 关讲述人
# 为什么要这样: 微信 4.1.8 只有在启动时检测到讲述人(无障碍客户端),
#               才会暴露完整控件树,采集器才能读消息;登录完成后讲述人就可以关掉。

$ErrorActionPreference = 'Continue'
$dir = 'F:\dev\wx-group-collector'
$py  = Join-Path $dir '.venv\Scripts\python.exe'
$log = Join-Path $dir 'logs\collector.log'

# 防止重复启动
$running = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*collector.py*' }
if ($running) {
    Write-Host '[!] 采集已经在运行了,不要重复启动。'
    Start-Sleep -Seconds 5
    exit 1
}

Write-Host '[1/5] 启动讲述人(微信启动瞬间需要,之后会自动关掉)...'
Start-Process narrator
Start-Sleep -Seconds 2

Write-Host '[2/5] 重启微信(约15秒,期间请不要动鼠标键盘)...'
Stop-Process -Name Weixin -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
Start-Process 'F:\Weixin\Weixin.exe'
Start-Sleep -Seconds 5

Write-Host '[3/5] 启动采集器和文件搬运工...'
# 滚动旧日志,便于后面判断本次连接结果
if (Test-Path $log) { Move-Item $log "$log.old" -Force }
# 采集器:控制台窗口直接实时显示(根 logger 统一格式,含 wx4py 日志);
# 完整日志同时写入 logs\collector.log(统一后 Tee 中转已无必要,且 PS 的
# 2>&1 会把 stderr 包装成错误记录污染日志,故弃用)
$proc = Start-Process -FilePath 'powershell.exe' `
    -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command',
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; & '$py' collector.py") `
    -WorkingDirectory $dir -PassThru
# 文件搬运工:后台隐藏运行,盯微信文件目录,新文件自动复制到 data\files\
Start-Process -FilePath $py -ArgumentList 'file_fetcher.py' `
    -WorkingDirectory $dir -WindowStyle Hidden
# 文件自动下载器:发现"文件 X 未下载"就右键点菜单"下载"
Start-Process -FilePath $py -ArgumentList 'file_clicker.py' `
    -WorkingDirectory $dir -WindowStyle Hidden
# 语音转写补录器:延迟回读语音气泡,把转写文字补记到 voice-transcripts-*.jsonl
Start-Process -FilePath $py -ArgumentList 'voice_transcriber.py' `
    -WorkingDirectory $dir -WindowStyle Hidden

Write-Host '[4/5] 等待连接微信(最长2分钟)...'
$ok = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 3
    if ($proc.HasExited) { break }
    if (Test-Path $log) {
        # 连接成功的日志只打在控制台,不进 log 文件;
        # 以"出现第一条群消息"作为成功信号
        $hits = Select-String -Path $log -Pattern 'INFO collector: \[' -Encoding UTF8
        if ($hits) { $ok = $true; break }
    }
}

Write-Host '[5/5] 关闭讲述人...'
Stop-Process -Name narrator -Force -ErrorAction SilentlyContinue

if ($ok) {
    Write-Host ''
    Write-Host '============================================'
    Write-Host '  采集已启动!弹出的新窗口里能看到实时消息。'
    Write-Host '  停止采集: 关闭那个新窗口(或在里面按 Ctrl+C)'
    Write-Host '  采集期间建议: 不锁屏、不在微信里切换其他聊天'
    Write-Host '============================================'
} elseif (-not $proc.HasExited) {
    # 群2分钟没新消息也算启动成功(进程活着)
    Write-Host '[?] 采集器在运行,但2分钟内群里没出现新消息。'
    Write-Host '    若黑窗口里已显示过"成功连接到微信"即正常。'
} else {
    Write-Host '[X] 连接失败: 请看弹出的采集器窗口里的报错信息。'
    Write-Host '    常见原因: 微信登录窗口在等手机确认,扫码后再运行一次本脚本。'
}
Start-Sleep -Seconds 6

