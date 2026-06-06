<#
.SYNOPSIS
  PostToolUse hook — auto-stage changed files after Write/Edit.
  Works with auto_backup.ps1 (Stop hook) for full backup cycle.
#>

# Read payload from stdin
$stdin = @($input) -join "`n"
if (-not $stdin.Trim()) { $stdin = "{}" }
try {
    $payload = $stdin | ConvertFrom-Json
} catch {
    exit 0
}

$toolName = $payload.tool_name
if ($toolName -ne "Write" -and $toolName -ne "Edit") {
    exit 0
}

$filePath = $payload.parameters.file_path
if (-not $filePath -or -not (Test-Path $filePath)) {
    exit 0
}

git add $filePath 2>$null
exit 0
