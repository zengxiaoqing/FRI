<#
.SYNOPSIS
  PostToolUse hook — auto-formats changed files after Write/Edit tools.
  Non-blocking: never prevents agent from continuing.
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

$ext = [System.IO.Path]::GetExtension($filePath).TrimStart('.')

function Invoke-Formatter {
    param($Cmd, $Args, $Label)
    try {
        $null = Get-Command $Cmd -ErrorAction Stop
    } catch {
        return
    }
    & $Cmd @Args 2>$null
    Write-Warning "Harn: $Label formatted $filePath"
}

switch ($ext) {
    "py" {
        try {
            $null = Get-Command "ruff" -ErrorAction Stop
            Invoke-Formatter -Cmd "ruff" -Args @("format", "--quiet", $filePath) -Label "ruff"
        } catch {
            try {
                $null = Get-Command "black" -ErrorAction Stop
                Invoke-Formatter -Cmd "black" -Args @("--quiet", $filePath) -Label "black"
            } catch {
                # No formatter found
            }
        }
    }
    { $_ -in @("js", "ts", "jsx", "tsx", "json", "yaml", "yml", "md", "css", "html") } {
        try {
            $null = Get-Command "prettier" -ErrorAction Stop
            & prettier --write --log-level silent $filePath 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Warning "Harn: prettier formatted $filePath"
            }
        } catch {
            # prettier not found
        }
    }
    "rs" {
        try {
            $null = Get-Command "rustfmt" -ErrorAction Stop
            & rustfmt $filePath 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Warning "Harn: rustfmt formatted $filePath"
            }
        } catch {
            # rustfmt not found
        }
    }
    "go" {
        try {
            $null = Get-Command "gofmt" -ErrorAction Stop
            & gofmt -w $filePath 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Warning "Harn: gofmt formatted $filePath"
            }
        } catch {
            # gofmt not found
        }
    }
    { $_ -in @("sh", "bash", "zsh") } {
        # shfmt is less common on Windows — skip silently
        exit 0
    }
}

exit 0
