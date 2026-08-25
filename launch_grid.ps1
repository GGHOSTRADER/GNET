# Launch the complete GNET pipeline in one Windows Terminal window.

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $root "launch.ps1") -Grid
exit $LASTEXITCODE
