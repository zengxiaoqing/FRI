<#
.SYNOPSIS
  PostToolUse hook — logs tool calls to JSONL for debugging and analytics.
#>

$traceFile = ".claude\agent-trace.jsonl"
$maxLines = 5000
$keepLines = 2500

# Ensure directory exists
$dir = Split-Path $traceFile -Parent
if (-not (Test-Path $dir)) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

# Read payload from stdin
$stdin = @($input) -join "`n"
if (-not $stdin.Trim()) { $stdin = "{}" }
try {
    $payload = $stdin | ConvertFrom-Json
} catch {
    exit 0
}

$toolName = if ($payload.tool_name) { $payload.tool_name } else { "unknown" }
$exitCode = if ($null -ne $payload.exit_code) { $payload.exit_code } else { 0 }
$timestamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ"

# Append trace entry
$entry = "{""ts"":""$timestamp"",""tool"":""$toolName"",""exit"":$exitCode}"
Add-Content -Path $traceFile -Value $entry

# Log rotation: keep last $keepLines when exceeding $maxLines
if (Test-Path $traceFile) {
    $lineCount = (Get-Content $traceFile | Measure-Object -Line).Lines
    if ($lineCount -gt $maxLines) {
        $lines = Get-Content $traceFile
        $lines[-$keepLines..-1] | Set-Content $traceFile
    }
}

exit 0
