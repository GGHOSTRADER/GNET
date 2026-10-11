[CmdletBinding()]
param([ValidateRange(3,20)][int]$Samples=5,[ValidateRange(100,30000)][int]$BudgetMs=2000)
$ErrorActionPreference='Stop'
$gnetRepo=Split-Path $PSScriptRoot -Parent
$gnetConfig=Get-Content -LiteralPath (Join-Path $gnetRepo '.artifacts/client-delivery-installed/client-config.json') -Raw | ConvertFrom-Json
$gnetOrigin='http://127.0.0.1:'+ $gnetConfig.port
$gnetRows=@()
foreach($gnetEndpoint in @('/api/config','/api/client-health','/api/transfer-status?offset=0&page_size=20','/api/client-inbox?offset=0&page_size=20')){
 for($gnetSample=1;$gnetSample -le $Samples;$gnetSample++){
  $gnetTimer=[Diagnostics.Stopwatch]::StartNew()
  $gnetFailure=$null
  try{$gnetResponse=Invoke-WebRequest -Uri ($gnetOrigin+$gnetEndpoint) -TimeoutSec 30; $gnetCode=[int]$gnetResponse.StatusCode}catch{$gnetFailure=$_.Exception.Message;$gnetCode=0}
  $gnetTimer.Stop()
  $gnetRows+=[pscustomobject][ordered]@{endpoint=$gnetEndpoint;sample=$gnetSample;duration_ms=[Math]::Round($gnetTimer.Elapsed.TotalMilliseconds,2);status=$gnetCode;error=$gnetFailure}
 }
}
$gnetSummary=@(foreach($gnetGroup in ($gnetRows | Group-Object endpoint)){
 $gnetTimes=@($gnetGroup.Group.duration_ms | Sort-Object)
 [pscustomobject][ordered]@{endpoint=$gnetGroup.Name;samples=$gnetTimes.Count;p50_ms=$gnetTimes[[Math]::Ceiling($gnetTimes.Count*.5)-1];p95_ms=$gnetTimes[[Math]::Ceiling($gnetTimes.Count*.95)-1];max_ms=$gnetTimes[-1]}
})
$gnetPassed=@($gnetRows | Where-Object {$_.error -or $_.status -ne 200 -or $_.duration_ms -gt $BudgetMs}).Count -eq 0
$gnetOutput=Join-Path $gnetRepo '.test_artifacts/installed-client-latency.json'
New-Item -ItemType Directory -Path (Split-Path $gnetOutput -Parent) -Force | Out-Null
[ordered]@{mode='installed-read-only-http';client_release_id=$gnetConfig.client_release_id;broker_release_id=$gnetConfig.broker_release_id;generated_at_utc=[DateTime]::UtcNow.ToString('o');budget_ms=$BudgetMs;passed=$gnetPassed;broker_jobs_submitted=$false;raw_market_data_read=$false;requests=$gnetRows;summary=$gnetSummary} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $gnetOutput -Encoding utf8
$gnetSummary | Format-Table
if(-not $gnetPassed){throw "Installed HTTP latency check failed; inspect $gnetOutput"}
Write-Output "Installed read-only latency passed: $gnetOutput"
