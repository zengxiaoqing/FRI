<#
.SYNOPSIS
  SessionStart hook — validates MCP server configurations at session start.
  Non-blocking: reports status, never prevents session start.
#>

$settingsFile = ".claude\settings.json"
if (-not (Test-Path $settingsFile)) {
    exit 0
}

try {
    $settings = Get-Content $settingsFile -Raw | ConvertFrom-Json
} catch {
    exit 0
}

$mcpServers = $settings.mcpServers
if (-not $mcpServers) {
    exit 0
}

$mcpCount = ($mcpServers.PSObject.Properties | Measure-Object).Count
if ($mcpCount -eq 0) {
    exit 0
}

Write-Warning "Harn: Checking ${mcpCount} MCP server(s)..."

$pass = 0
$fail = 0

foreach ($server in $mcpServers.PSObject.Properties) {
    $name = $server.Name
    $config = $server.Value
    $mcpCmd = $config.command

    if (-not $mcpCmd) {
        Write-Warning "  SKIP: $name — no command configured"
        continue
    }

    $cmdExists = $false
    try {
        $null = Get-Command $mcpCmd -ErrorAction Stop
        $cmdExists = $true
    } catch {
        $cmdExists = $false
    }

    if ($cmdExists) {
        Write-Warning "  OK: $name ($mcpCmd)"
        $pass++
    } else {
        Write-Warning "  WARN: $name — '$mcpCmd' not found in PATH"
        $fail++
    }
}

Write-Warning "Harn: MCP check done — ${pass} ok, ${fail} warn, $($mcpCount - $pass - $fail) skipped."

exit 0
