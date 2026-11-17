# Creates .venv in the repository and installs requirements.txt. Checks ffmpeg (installs it with winget when missing).
# No API call, no key needed. Safe to run again.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Find-Python {
    foreach ($cmd in @('py -3.11', 'py -3.12', 'python')) {
        $parts = @($cmd -split ' ')
        $extra = @($parts | Select-Object -Skip 1)
        try {
            $v = & $parts[0] @extra -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -eq 0 -and [version]$v -ge [version]'3.10') { return ,$parts }
        } catch { }
    }
    return $null
}

if (!(Test-Path '.venv/Scripts/python.exe')) {
    $py = Find-Python
    if (!$py) {
        Write-Host 'Chưa có Python 3.10+. Đang cài Python 3.11 bằng winget...'
        winget install -e --id Python.Python.3.11 --accept-source-agreements --accept-package-agreements
        $py = Find-Python
        if (!$py) { throw 'Không tìm thấy Python sau khi cài. Đóng cửa sổ, mở lại rồi bấm đúp 1-Cai-dat.cmd.' }
    }
    Write-Host 'Tạo môi trường .venv ...'
    $extra = @($py | Select-Object -Skip 1)
    & $py[0] @extra -m venv .venv
}
# pip cache and temp files stay inside the repository (drive C may be nearly full)
New-Item -ItemType Directory -Path 'local/tmp' -Force | Out-Null
$env:PIP_NO_CACHE_DIR = '1'; $env:TMP = (Resolve-Path 'local/tmp').Path; $env:TEMP = $env:TMP
& .venv/Scripts/python.exe -m pip install --upgrade pip --quiet
& .venv/Scripts/python.exe -m pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) { throw 'pip install thất bại.' }

if (!(Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host 'Chưa có ffmpeg. Đang cài bằng winget (Gyan.FFmpeg)...'
    winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
    Write-Host 'Nếu 3-Kiem-tra.cmd vẫn báo thiếu ffmpeg: đóng cửa sổ và mở lại (PATH mới cần cửa sổ mới).'
}
New-Item -ItemType Directory -Path 'local', 'projects' -Force | Out-Null
Write-Host 'Cài đặt xong.'
