param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 18878
)

$ErrorActionPreference = 'Stop'
Write-Host "Minihelp V2: http://127.0.0.1:$Port/#/knowledge"
Write-Host 'Press Ctrl+C to stop.'
& python (Join-Path $PSScriptRoot 'preview_server.py') --port $Port
exit $LASTEXITCODE
