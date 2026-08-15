# Publish the anla1 crate to crates.io.
#
#   powershell -ExecutionPolicy Bypass -File tools\release\publish-crate.ps1
#
# Why a script rather than `cargo login`: `cargo login` prompts with the input
# hidden, so a right-click paste gives no sign of whether anything arrived — and
# passing the token as a command-line argument instead would put it in the process
# list and in shell history. This asks for it in a normal prompt where paste works,
# shows a masked confirmation, and hands it to cargo through the environment of
# this process only.
#
# CARGO_REGISTRY_TOKEN is read by `cargo publish` directly, so `cargo login` is not
# used at all and nothing is written to ~/.cargo/credentials.toml.

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$rust = Join-Path $repo "rust"

Write-Host ""
Write-Host "  Publish anla1 to crates.io" -ForegroundColor Cyan
Write-Host "  --------------------------"

# --- 1. does it package, and is the tree clean --------------------------------

Push-Location $rust
try {
    Write-Host "  cargo publish --dry-run..."
    # Not `2>&1` into a variable. In Windows PowerShell 5.1 that wraps every stderr
    # line from a native program in an ErrorRecord, and cargo writes its ordinary
    # progress ("Updating crates.io index") to stderr — so with
    # $ErrorActionPreference = "Stop" the script died on a dry run that had
    # succeeded. The exit code is the thing to read; the output goes to a file so it
    # can still be quoted back on failure.
    $log = Join-Path $env:TEMP "anla-cargo-dryrun.log"
    $prior = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & cargo publish --dry-run 2>$log | Out-Null
    $dryCode = $LASTEXITCODE
    $ErrorActionPreference = $prior
    if ($dryCode -ne 0) {
        Write-Host "  FAILED" -ForegroundColor Red
        Get-Content $log -Tail 12 -ErrorAction SilentlyContinue
        Write-Host ""
        Write-Host "  If it complains about uncommitted changes, commit them first --"
        Write-Host "  a published crate should correspond to a commit that exists."
        exit 1
    }
    Write-Host "  passed" -ForegroundColor Green
    $packaged = Get-Content $log -ErrorAction SilentlyContinue |
                Select-String "Packaged" | Select-Object -First 1
    if ($packaged) { Write-Host ("  " + $packaged.ToString().Trim()) }

    # --- 2. the token ---------------------------------------------------------

    Write-Host ""
    Write-Host "  Get a token at https://crates.io/settings/tokens"
    Write-Host "  Scopes: tick " -NoNewline
    Write-Host "publish-new" -ForegroundColor Yellow -NoNewline
    Write-Host " -- anla1 does not exist yet, and"
    Write-Host "  publish-update alone will be refused with a 403 that says the token"
    Write-Host "  lacks permission. Leave the crate restriction empty, or list anla1."
    Write-Host ""
    Write-Host "  Paste it below -- right-click pastes in this window." -ForegroundColor Cyan
    Write-Host ""

    $token = Read-Host "  token"
    $token = $token.Trim()

    if ([string]::IsNullOrWhiteSpace($token)) {
        Write-Host "  nothing pasted." -ForegroundColor Red
        exit 1
    }
    if ($token.Length -lt 20) {
        Write-Host "  that is too short to be a crates.io token." -ForegroundColor Red
        exit 1
    }

    $masked = $token.Substring(0, 4) + ("." * 12) + $token.Substring($token.Length - 4)
    Write-Host ""
    Write-Host "  got $($token.Length) characters: $masked"

    # There is deliberately no preflight here, and the one that was here was wrong.
    #
    # It called /api/v1/me to prove the token was valid, got 403, and announced "the
    # token itself is not valid". crates.io tokens carry ENDPOINT scopes: a token
    # scoped to publish-new is not permitted to call /me, so that 403 meant the
    # token was correctly narrow -- the opposite of what the check reported. A
    # narrowly scoped token can, by design, do exactly one thing, which is why no
    # preflight can tell a good one from a bad one.
    #
    # The publish response already distinguishes them, in the registry's own words:
    #
    #   "this token does not have the required permissions"  -> valid token, wrong
    #                                                           scope
    #   "authentication failed" / 401                        -> wrong token
    #
    # So the diagnosis belongs after the attempt, reading what came back, rather
    # than before it, reading something that cannot answer.

    Write-Host ""
    Write-Host "  crates.io is permanent: a published version can be yanked but never" -ForegroundColor Yellow
    Write-Host "  deleted, and 0.1.1 can never be used again for this crate."
    $ok = Read-Host "  publish anla1 0.1.1? (yes/no)"
    if ($ok -ne "yes") {
        Write-Host "  stopped, nothing published."
        Remove-Variable token
        exit 0
    }

    # --- 3. publish -----------------------------------------------------------

    Write-Host ""
    $env:CARGO_REGISTRY_TOKEN = $token
    try {
        $prior = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & cargo publish
        $code = $LASTEXITCODE
        $ErrorActionPreference = $prior
    } finally {
        $env:CARGO_REGISTRY_TOKEN = $null
        Remove-Variable token -ErrorAction SilentlyContinue
    }

    if ($code -ne 0) {
        Write-Host ""
        Write-Host "  publish failed with exit $code." -ForegroundColor Red
        Write-Host ""
        Write-Host "  Read the registry's exact words above -- they separate the"
        Write-Host "  three cases, and nothing before the attempt can:"
        Write-Host ""
        Write-Host "  'this token does not have the required permissions'"
        Write-Host "     The token is VALID and recognised. Its scope is the problem."
        Write-Host "     Creating a crate that does not exist yet needs " -NoNewline
        Write-Host "publish-new" -ForegroundColor Yellow -NoNewline
        Write-Host "."
        Write-Host "     publish-update is not enough -- that only covers new versions"
        Write-Host "     of a crate you already own. On the token page the scope boxes"
        Write-Host "     start UNTICKED, so a token created by pressing Create straight"
        Write-Host "     away authenticates and is allowed to do nothing at all."
        Write-Host "     Leave 'Crates' empty, or list anla1 in it."
        Write-Host ""
        Write-Host "  'authentication failed' or 401"
        Write-Host "     The token itself is wrong: mistyped, revoked, or expired."
        Write-Host ""
        Write-Host "  'A verified email address is required'"
        Write-Host "     https://crates.io/settings/profile"
        Write-Host ""
        Write-Host "  'already uploaded'  0.1.0 is taken; crates.io never reuses one"
        exit $code
    }
} finally {
    Pop-Location
}

# --- 4. confirm it is actually there ------------------------------------------

Write-Host ""
Write-Host "  confirming on crates.io..." -NoNewline
Start-Sleep -Seconds 8
try {
    $headers = @{ "User-Agent" = "anla-release (kakon77777@gmail.com)" }
    $meta = Invoke-RestMethod -Uri "https://crates.io/api/v1/crates/anla1" -Headers $headers -TimeoutSec 30
    Write-Host " anla1 $($meta.crate.max_version) is live" -ForegroundColor Green
    Write-Host "  https://crates.io/crates/anla1"
    Write-Host ""
    Write-Host "  a stranger can now run:  cargo install anla1"
} catch {
    Write-Host " not visible yet" -ForegroundColor Yellow
    Write-Host "  the index can lag a minute; check https://crates.io/crates/anla1"
}
Write-Host ""
