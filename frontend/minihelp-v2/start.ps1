param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 18878
)

$ErrorActionPreference = 'Stop'
Write-Host "Minihelp V2: http://127.0.0.1:$Port/#/knowledge"
Write-Host 'Press Ctrl+C to stop.'
& python -m http.server $Port --bind 127.0.0.1 --directory $PSScriptRoot
exit $LASTEXITCODE
