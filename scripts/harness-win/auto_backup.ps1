<#
.SYNOPSIS
  Stop hook — auto-commit and push all changes to GitHub.
  Non-blocking: never prevents agent from stopping.
#>

$RepoDir = Get-Location
Set-Location $RepoDir

# Check if git repo
try {
    $null = git rev-parse --git-dir 2>$null
    if ($LASTEXITCODE -ne 0) { throw }
} catch {
    Write-Warning "Harn: not a git repo, backup skipped"
    exit 0
}

# Stage all changes
git add -A 2>$null

# Nothing to commit? Done
git diff --cached --quiet 2>$null
if ($LASTEXITCODE -eq 0) {
    exit 0
}

# Commit with timestamp
$timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
git commit -m "backup: auto-save ${timestamp}" 2>$null

# Push to remote (non-blocking)
git push 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Harn: push failed (network ok, manual push later)"
}

exit 0
