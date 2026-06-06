<#
.SYNOPSIS
  Stop hook — reminds to release if commits exist since last tag.
  Non-blocking: warns but always exits 0.
#>

# Get last tag
$lastTag = ""
try {
    $lastTag = git describe --tags --abbrev=0 2>$null
} catch {
    # No tags
}

if (-not $lastTag) {
    # No tags at all — first release
    try {
        $commitCount = git rev-list --count HEAD 2>$null
        if ($commitCount -gt 3) {
            Write-Warning "HARNESS NOTE: ${commitCount} commits, no release tag yet. Create a release: git tag v0.1.0 && git push --tags"
        }
    } catch {
        # Not a git repo or other error
    }
} else {
    try {
        $newCommits = git rev-list "${lastTag}..HEAD" --count 2>$null
        if ($newCommits -gt 0) {
            Write-Warning "HARNESS NOTE: ${newCommits} commit(s) since ${lastTag}. Time to tag a release: git tag vX.Y.Z && git push --tags"
        }
    } catch {
        # Error
    }
}

exit 0
