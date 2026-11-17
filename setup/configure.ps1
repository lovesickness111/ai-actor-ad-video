# Masked key entry into local/secrets.env (never shown, never committed). -Only GROK_API_KEY asks just that key.
param([string[]]$Only)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$localDir = Join-Path $Root 'local'
New-Item -ItemType Directory -Path $localDir -Force | Out-Null
$file = Join-Path $localDir 'secrets.env'
$values = [ordered]@{}
if (Test-Path -LiteralPath $file) {
    foreach ($line in [IO.File]::ReadAllLines($file)) {
        if ($line -match '^([A-Z_][A-Z0-9_]*)=(.*)$') { $values[$matches[1]] = $matches[2] }
    }
}
$keys = [ordered]@{
    'GROK_API_KEY'     = 'xAI Grok - sinh video có diễn viên AI và giọng đọc cùng giọng nhân vật (console.x.ai > API keys)'
    'GEMINI_API_KEY'   = 'Google Gemini - ảnh nhân vật/khung cảnh, video Omni, giọng Gemini (aistudio.google.com > Get API key; cần gói trả phí cho video)'
    'GEMINI_TTS_MODEL' = 'Tên model Gemini TTS (không phải mật khẩu), chỉ cần khi dùng giọng Gemini; để trống nếu không dùng'
}
if ($Only) {
    $wanted = @($Only | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    foreach ($name in @($keys.Keys)) { if ($wanted -notcontains $name) { $keys.Remove($name) } }
}
Write-Host 'Dán từng key rồi nhấn Enter. Ký tự sẽ không hiện ra. Để trống và nhấn Enter nếu muốn giữ giá trị cũ hoặc bỏ qua.'
foreach ($name in $keys.Keys) {
    $status = if ($values[$name]) { 'đã lưu' } else { 'chưa có' }
    Write-Host ''
    Write-Host "$name [$status]"
    Write-Host "  $($keys[$name])"
    $secure = Read-Host -Prompt $name -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
        if ($plain.Length -gt 0) {
            if ($plain -match '[\r\n]') { throw 'Key must be one line.' }
            $values[$name] = $plain.Trim()
        }
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        $plain = $null
        $secure.Dispose()
    }
}
$lines = foreach ($entry in $values.GetEnumerator()) { $entry.Key + '=' + $entry.Value }
[IO.File]::WriteAllLines($file, [string[]]$lines, (New-Object Text.UTF8Encoding($false)))
Write-Host ''
foreach ($name in $keys.Keys) { Write-Host ("{0,-18} {1}" -f $name, $(if ($values[$name]) { 'đã lưu' } else { '-' })) }
Write-Host 'Đã lưu key trên máy này (không hiển thị). Không gửi file local/secrets.env cho người khác.'
