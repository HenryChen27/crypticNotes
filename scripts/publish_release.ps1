# Create (or refresh) the GitHub Release for the share repo's current commit.
#
# This file is deliberately ASCII-only. PowerShell 5.1 only reads a .ps1 as UTF-8
# when it carries a BOM, and a BOM is easy to lose on the next edit -- so the rule
# here is "no Chinese in this file at all". All the prose lives in
# scripts/release-notes.md, which is read explicitly with -Encoding UTF8.
#
# The tag is derived from the share repo's HEAD, so one source commit == one release.
# Re-running is idempotent: an existing release for that tag has its notes refreshed
# and its assets replaced only when their bytes actually differ.
#
# Usage:  powershell -File scripts/publish_release.ps1 [-Tag <tag>] [-Draft] [-DryRun]
#
# -DryRun renders the tag and the full release body from the local files and stops,
# without contacting GitHub. Use it to check the notes after editing release-notes.md.

[CmdletBinding()]
param(
    [string]$Tag = '',
    [switch]$Draft,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$Root  = Split-Path -Parent $PSScriptRoot                      # scripts\ -> repo root
$Share = Join-Path $Root 'release\crypticNotes'
$Notes = Join-Path $PSScriptRoot 'release-notes.md'
$Repo  = 'HenryChen27/crypticNotes'

# git writes UTF-8; without this, PowerShell decodes native-command output with the
# console code page (GBK here) and every Chinese commit subject turns into mojibake.
# The old value is restored on the way out so the shell that called us keeps whatever
# code page it expects -- the console encoding is shared between processes.
$savedEncoding = [Console]::OutputEncoding
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }


function Get-Git {
    param([string[]]$Arguments)
    $output = & git -C $Share @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw ("git " + ($Arguments -join ' ') + " failed with exit code $LASTEXITCODE")
    }
    return $output
}

function Get-MapCounts {
    # Counted straight out of the manifest, so the release notes can never drift from
    # the map library the way the hand-written "62 maps" line did. Only the numbers
    # are produced here -- the Chinese wording lives in release-notes.md, which keeps
    # this file ASCII-only.
    $floors = Get-Content (Join-Path $Root 'maps\floors.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $refs = @($floors.references)
    return @{
        TOTAL = $refs.Count
        HARD  = @($refs | Where-Object { $_.difficulty -eq 'hard' }).Count
        SOLO  = @($refs | Where-Object { $_.difficulty -eq 'nightmare' -and $_.mode -eq 'solo' }).Count
        DUO   = @($refs | Where-Object { $_.difficulty -eq 'nightmare' -and $_.mode -eq 'duo' }).Count
    }
}

function Get-Changelog {
    param([string]$Sha, [object[]]$Releases, [string]$SelfTag)
    $previous = $Releases |
        Where-Object { -not $_.draft -and $_.tag_name -ne $SelfTag } |
        Sort-Object created_at -Descending | Select-Object -First 1
    $lines = @()
    if ($previous -and $previous.target_commitish) {
        $lines = @(Get-Git @('log', '--no-merges', '--pretty=format:- %s',
                             "$($previous.target_commitish)..$Sha"))
    }
    if (-not $lines -or -not ($lines -join '').Trim()) {
        # No previous release (first publish), or the notes were asked for in a dry
        # run where the release list is not available: show recent history instead.
        $lines = @(Get-Git @('log', '-5', '--no-merges', '--pretty=format:- %s', $Sha))
    }
    $text = ($lines -join "`n").Trim()
    if (-not $text) { $text = '- See the source repository for the change history.' }
    return $text
}

function Get-ReleaseNotes {
    param([string]$Changelog)
    $lines = [System.IO.File]::ReadAllLines($Notes, [System.Text.Encoding]::UTF8)
    if ($lines.Count -eq 0) { throw "release notes are empty: $Notes" }
    # First line is the release title; everything after it is the body.
    $title = $lines[0].TrimStart('#', ' ')
    $body = ($lines[1..($lines.Count - 1)] -join "`n")
    $shasums = (Get-Content (Join-Path $Root 'release\SHA256SUMS.txt') -Raw -Encoding ASCII).Trim().Split(' ')[0]
    foreach ($pair in (Get-MapCounts).GetEnumerator()) {
        $body = $body.Replace('{{' + $pair.Key + '}}', $pair.Value)
    }
    return @{
        Title = $title
        Body  = $body.Replace('{{CHANGELOG}}', $Changelog).Replace('{{SHA256}}', $shasums)
    }
}

function Resolve-Tag {
    param([string]$Sha, [string]$Wanted)
    if ($Wanted) { return $Wanted }
    $stamp = (Get-Git @('log', '-1', '--format=%cd', '--date=format:%Y%m%d', $Sha) | Select-Object -First 1).Trim()
    return "desktop-update-$stamp-$($Sha.Substring(0, 7))"
}


function Invoke-Main {
    $sha = (Get-Git @('rev-parse', 'HEAD') | Select-Object -First 1).Trim()
    $Tag = Resolve-Tag -Sha $sha -Wanted $Tag
    Write-Output "tag       : $Tag"
    Write-Output "commit    : $sha"

    if ($DryRun) {
        # Renders everything that comes from local files -- title extraction, map
        # counts, SHA256, changelog formatting -- without touching the network.
        $preview = Get-ReleaseNotes -Changelog (Get-Changelog -Sha $sha -Releases @() -SelfTag $Tag)
        Write-Output "title     : $($preview.Title)"
        Write-Output '--- body ---'
        Write-Output $preview.Body
        Write-Output '--- end ---'
        return
    }

    # --- token (never printed) ---
    $raw = "protocol=https`nhost=github.com`n`n" | git credential fill
    if ($LASTEXITCODE -ne 0) { throw 'GitHub authentication unavailable (git credential fill failed)' }
    $secret = ($raw | Where-Object { $_.StartsWith('password=') } | Select-Object -First 1).Substring(9)
    $raw = $null
    $headers = @{
        Authorization = "Bearer $secret"
        'User-Agent'  = 'crypticNotes-release'
        Accept        = 'application/vnd.github+json'
    }
    $secret = $null

    $base = "https://api.github.com/repos/$Repo"
    $releases = @(Invoke-RestMethod -Uri "$base/releases" -Headers $headers)
    $entry = $releases | Where-Object { $_.tag_name -eq $Tag } | Select-Object -First 1

    $notes = Get-ReleaseNotes -Changelog (Get-Changelog -Sha $sha -Releases $releases -SelfTag $Tag)

    if ($entry) {
        Write-Output "release   : reusing existing release $($entry.id)"
        $payload = @{ name = $notes.Title; body = $notes.Body } | ConvertTo-Json -Depth 4
        $entry = Invoke-RestMethod -Method Patch -Uri "$base/releases/$($entry.id)" -Headers $headers `
            -ContentType 'application/json; charset=utf-8' `
            -Body ([System.Text.Encoding]::UTF8.GetBytes($payload))
    } else {
        $payload = @{
            tag_name         = $Tag
            target_commitish = $sha
            name             = $notes.Title
            body             = $notes.Body
            draft            = $true
        } | ConvertTo-Json -Depth 4
        $entry = Invoke-RestMethod -Method Post -Uri "$base/releases" -Headers $headers `
            -ContentType 'application/json; charset=utf-8' `
            -Body ([System.Text.Encoding]::UTF8.GetBytes($payload))
        Write-Output "release   : created draft $($entry.id)"
    }

    # --- assets ---
    $assets = @(
        @{ Name = 'IdentityVMapAssistant-Windows-x64.zip'; Path = (Join-Path $Root 'release\IdentityVMapAssistant-Windows-x64.zip') },
        @{ Name = 'SHA256SUMS.txt';                        Path = (Join-Path $Root 'release\SHA256SUMS.txt') }
    )
    foreach ($asset in $assets) {
        if (-not (Test-Path $asset.Path)) { throw "missing release asset: $($asset.Path)" }
        $local = Get-Item $asset.Path
        $digest = (Get-FileHash $asset.Path -Algorithm SHA256).Hash.ToLower()
        $existing = $entry.assets | Where-Object { $_.name -eq $asset.Name } | Select-Object -First 1
        if ($existing) {
            # Newer uploads carry a digest; older ones only report a size.
            $same = if ($existing.digest) { $existing.digest -eq "sha256:$digest" } else { $existing.size -eq $local.Length }
            if ($same) {
                Write-Output "asset     : $($asset.Name) unchanged, skipped"
                continue
            }
            Invoke-RestMethod -Method Delete -Uri "$base/releases/assets/$($existing.id)" -Headers $headers | Out-Null
            Write-Output "asset     : removed stale $($asset.Name)"
        }
        $uri = ($entry.upload_url -replace '\{.*$', '') + '?name=' + $asset.Name
        $uploaded = Invoke-RestMethod -Method Post -Uri $uri -Headers $headers `
            -ContentType 'application/octet-stream' -InFile $asset.Path -TimeoutSec 1800
        Write-Output ("asset     : uploaded {0} ({1:N1} MiB)" -f $uploaded.name, ($uploaded.size / 1MB))
    }

    if ($Draft) {
        Write-Output "result    : left as draft"
    } else {
        $published = Invoke-RestMethod -Method Patch -Uri "$base/releases/$($entry.id)" -Headers $headers `
            -ContentType 'application/json' -Body '{"draft":false}'
        Write-Output "result    : published $($published.html_url)"
    }
    $headers = $null
}

try {
    Invoke-Main
} finally {
    try { [Console]::OutputEncoding = $savedEncoding } catch { }
}
