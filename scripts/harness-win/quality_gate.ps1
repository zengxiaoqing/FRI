<#
.SYNOPSIS
  Stop hook — quality gate. Blocks agent from completing if code is broken.
#>

# Read payload from stdin
$stdin = @($input) -join "`n"
if (-not $stdin.Trim()) { $stdin = "{}" }
try {
    $payload = $stdin | ConvertFrom-Json
} catch {
    $payload = @{}
}

$isActive = $payload.stop_hook_active
if ($isActive -eq $true -or $isActive -eq "true") {
    exit 0
}

# Session-aware temp file
$tempDir = if ($env:TMPDIR) { $env:TMPDIR } elseif ($env:TEMP) { $env:TEMP } else { "$env:USERPROFILE\AppData\Local\Temp" }
$logFile = Join-Path $tempDir "harn_gate_$([System.Diagnostics.Process]::GetCurrentProcess().Id).log"

Write-Warning "Harn: Running quality gate..."

function Run-Check {
    param($Cmd, $Args, $Label, $MissingMsg)
    try {
        $null = Get-Command $Cmd -ErrorAction Stop
    } catch {
        Write-Warning "QUALITY GATE BLOCKED: $MissingMsg"
        exit 2
    }

    $result = & $Cmd @Args 2>&1 | Out-String
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        Write-Warning "QUALITY GATE FAILED — $Label errors:"
        Write-Warning $result
        exit 2
    }
}

# Detect stack and run checker
if (Test-Path "tsconfig.json") {
    Run-Check -Cmd "npx" -Args @("tsc", "--noEmit") -Label "TypeScript" -MissingMsg "TypeScript detected but 'npx' not found. Install Node.js or remove tsconfig.json to skip."
} elseif (Test-Path "Cargo.toml") {
    Run-Check -Cmd "cargo" -Args @("check") -Label "Rust" -MissingMsg "Rust detected but 'cargo' not found."
} elseif (Test-Path "go.mod") {
    Run-Check -Cmd "go" -Args @("vet", "./...") -Label "Go" -MissingMsg "Go detected but 'go' not found."
} elseif (Test-Path "pyproject.toml") {
    Run-Check -Cmd "mypy" -Args @(".") -Label "Python type" -MissingMsg "Python detected but 'mypy' not found. Install mypy or remove pyproject.toml to skip."
} else {
    Write-Warning "Harn: No known stack detected. Add stack-specific checks to quality_gate.ps1."
}

Write-Warning "Harn: Quality gate passed."
exit 0
