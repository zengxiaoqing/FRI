<#
.SYNOPSIS
  PreToolUse hook — blocks Write/Edit tools from creating files with secrets.
  Blocks (exit 2) on match; passes (exit 0) if clean.
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

$content = $payload.parameters.content
if (-not $content) {
    $content = $payload.parameters.new_string
}
if (-not $content -or $content -eq "null") {
    exit 0
}

$filePath = $payload.parameters.file_path

# Secret patterns — add project-specific patterns below
$patterns = @(
    # AWS access keys
    "AKIA[0-9A-Z]{16}",
    # Stripe API keys
    "sk_live_[0-9a-zA-Z]{24,}",
    "pk_live_[0-9a-zA-Z]{24,}",
    # GitHub personal access tokens
    "ghp_[0-9a-zA-Z]{36}",
    "github_pat_[0-9a-zA-Z]{22,}",
    # Generic API key patterns
    "api_key\s*=\s*['""][A-Za-z0-9_\-]{20,}['""]",
    "API_KEY\s*=\s*['""][A-Za-z0-9_\-]{20,}['""]",
    # Private key blocks
    "-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
    # Connection strings with embedded passwords
    "(mongodb|mysql|postgres|postgresql|redis)://[^:]+:[^@]+@",
    # JWT tokens
    "eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}",
    # Slack webhook URLs
    "hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+",
    # Generic password assignments
    "password\s*=\s*['""][^'""]{3,}['""]"
)

foreach ($pattern in $patterns) {
    if ($content -match $pattern) {
        Write-Warning "SECURITY BLOCKED: Secret pattern detected in $filePath"
        Write-Warning "  Pattern: $pattern"
        Write-Warning "  Use environment variables or a vault instead."
        exit 2
    }
}

exit 0
