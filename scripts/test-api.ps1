# Quick API smoke test for Windows PowerShell.
# Usage:
#   .\scripts\test-api.ps1
#   .\scripts\test-api.ps1 -Question "What are the engineering fees?"

param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$Question = "What are the admission requirements?"
)

Write-Host "GET $BaseUrl/health" -ForegroundColor Cyan
$health = Invoke-RestMethod -Uri "$BaseUrl/health" -Method GET
$health | ConvertTo-Json -Compress
Write-Host ""

Write-Host "POST $BaseUrl/chat" -ForegroundColor Cyan
$body = @{ question = $Question } | ConvertTo-Json -Compress
$chat = Invoke-RestMethod -Uri "$BaseUrl/chat" -Method POST -ContentType "application/json" -Body $body
$chat | ConvertTo-Json -Depth 5
