<#
.SYNOPSIS
  Stop hook — context budget monitor. Warns when session context approaches limits.
  Non-blocking: warns via stderr but always exits 0.
#>

$traceFile = ".claude\agent-trace.jsonl"
$warnThreshold = 150
$criticalThreshold = 250

if (-not (Test-Path $traceFile)) {
    exit 0
}

$toolCount = (Get-Content $traceFile | Measure-Object -Line).Lines

# Get top tools from last 50 entries
$recentLines = Get-Content $traceFile -Tail 50
$toolCounts = @{}
foreach ($line in $recentLines) {
    try {
        $entry = $line | ConvertFrom-Json
        $tool = $entry.tool
        if ($tool) {
            $toolCounts[$tool] = ($toolCounts[$tool] -or 0) + 1
        }
    } catch {
        continue
    }
}

$topTools = $toolCounts.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 3
$topToolsStr = ($topTools | ForEach-Object { "$($_.Name) ($($_.Value))" }) -join " "

if ($toolCount -gt $criticalThreshold) {
    Write-Warning "CONTEXT WARNING: ${toolCount} tool calls in session — near context limit."
    Write-Warning "  Action: compact, checkpoint, or start new session for complex subtasks."
    Write-Warning "  Top tools: $topToolsStr"
} elseif ($toolCount -gt $warnThreshold) {
    Write-Warning "CONTEXT NOTE: ${toolCount} tool calls so far."
    Write-Warning "  Top tools: $topToolsStr"
}

exit 0
