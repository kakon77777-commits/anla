# Publish the built wheel and sdist to PyPI.
#
#   powershell -ExecutionPolicy Bypass -File tools\release\publish-pypi.ps1
#
# Why a script rather than `twine upload`: twine's own password prompt is hidden,
# so a right-click paste gives no sign of whether anything arrived, and a token is
# ninety characters of base64 that nobody can retype. This asks for it in a normal
# prompt where paste works and shows a masked confirmation, then hands it to twine
# through the environment of this process only.
#
# The token is never written to disk, never passed as a command-line argument
# (which would put it in the process list), and the variable is cleared at the end.
# `Read-Host` input does not enter PowerShell history.

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$dist = Join-Path $repo "dist-release"

Write-Host ""
Write-Host "  Publish anla-archive to PyPI" -ForegroundColor Cyan
Write-Host "  ----------------------------"

# --- 1. the artefacts, and that they are the ones that were verified -----------

$files = @(
    (Join-Path $dist "anla_archive-0.1.0-py3-none-any.whl"),
    (Join-Path $dist "anla_archive-0.1.0.tar.gz")
)
foreach ($f in $files) {
    if (-not (Test-Path $f)) {
        Write-Host "  missing: $f" -ForegroundColor Red
        Write-Host "  rebuild with:  cd python; python -m build --outdir ..\dist-release"
        exit 1
    }
}

# Checked against the manifest that was written when these were verified, so an
# accidental rebuild between then and now cannot be published unnoticed.
$sums = Join-Path $dist "SHA256SUMS"
if (Test-Path $sums) {
    $expected = @{}
    Get-Content $sums | ForEach-Object {
        $parts = $_ -split '\s+\*?', 2
        if ($parts.Count -eq 2) { $expected[$parts[1].Trim()] = $parts[0].Trim() }
    }
    foreach ($f in $files) {
        $name = Split-Path -Leaf $f
        $have = (Get-FileHash -Algorithm SHA256 $f).Hash.ToLower()
        if ($expected.ContainsKey($name) -and $expected[$name] -ne $have) {
            Write-Host "  $name does not match SHA256SUMS." -ForegroundColor Red
            Write-Host "  These are not the files that were verified. Stopping."
            exit 1
        }
    }
    Write-Host "  checksums match SHA256SUMS" -ForegroundColor Green
}

Write-Host "  twine check..." -NoNewline
# stderr to a file rather than `2>&1` into a variable: PowerShell 5.1 turns a native
# program's stderr into ErrorRecords, which with $ErrorActionPreference = "Stop"
# aborts on output that was never an error. Read the exit code instead.
$checkLog = Join-Path $env:TEMP "anla-twine-check.log"
$prior = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& python -m twine check $files 2>$checkLog | Out-Null
$ErrorActionPreference = $prior
if ($LASTEXITCODE -ne 0) {
    Write-Host " FAILED" -ForegroundColor Red
    Get-Content $checkLog -Tail 5 -ErrorAction SilentlyContinue
    exit 1
}
Write-Host " passed" -ForegroundColor Green

# --- 2. the token -------------------------------------------------------------

Write-Host ""
Write-Host "  The distribution is anla-archive; the import packages stay anla/anla1."
Write-Host "  ('anla' itself is refused: too similar to ania/anta/anda/anna/nala.)"
Write-Host ""
Write-Host "  Get a token at https://pypi.org/manage/account/token/"
Write-Host "  First release of this name: scope must be " -NoNewline
Write-Host "Entire account" -ForegroundColor Yellow
Write-Host "  (a project-scoped token needs the project to exist already)."
Write-Host ""
Write-Host "  Paste it below -- right-click pastes in this window." -ForegroundColor Cyan
Write-Host ""

$token = Read-Host "  token"
$token = $token.Trim()

if ([string]::IsNullOrWhiteSpace($token)) {
    Write-Host "  nothing pasted." -ForegroundColor Red
    exit 1
}
if (-not $token.StartsWith("pypi-")) {
    # Caught here rather than by a 403 forty seconds later, and it is the usual
    # mistake: an account password where an API token belongs.
    Write-Host "  that does not look like a PyPI token -- they begin with 'pypi-'." -ForegroundColor Red
    Write-Host "  (a username and password will not work; PyPI requires a token)"
    exit 1
}

$masked = $token.Substring(0, 9) + ("." * 12) + $token.Substring($token.Length - 6)
Write-Host ""
Write-Host "  got $($token.Length) characters: $masked"
$ok = Read-Host "  upload anla-archive 0.1.0 to PyPI with this token? (yes/no)"
if ($ok -ne "yes") {
    Write-Host "  stopped, nothing uploaded."
    Remove-Variable token
    exit 0
}

# --- 3. upload ----------------------------------------------------------------

Write-Host ""
# Kept, not discarded. The first version of this printed a list of things the
# failure *might* have been and threw away the sentence PyPI had actually sent —
# which is the same mistake as publishing a number nobody can re-derive. `--verbose`
# because twine's default failure line is often shorter than the server's reason.
$uploadLog = Join-Path $env:TEMP "anla-twine-upload.log"
$env:TWINE_USERNAME = "__token__"
$env:TWINE_PASSWORD = $token
try {
    $prior = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & python -m twine upload --non-interactive --verbose $files 2>&1 |
        Tee-Object -FilePath $uploadLog
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prior
} finally {
    # This process only; nothing was written anywhere.
    $env:TWINE_PASSWORD = $null
    $env:TWINE_USERNAME = $null
    Remove-Variable token -ErrorAction SilentlyContinue
}

if ($code -ne 0) {
    Write-Host ""
    Write-Host "  upload failed with exit $code. What PyPI actually said:" -ForegroundColor Red
    Write-Host ""
    $said = Get-Content $uploadLog -ErrorAction SilentlyContinue |
            Where-Object { $_ -match "HTTPError|error|Error|refused|denied|403|400|401|429|Invalid|not allowed" } |
            Select-Object -Last 8
    if ($said) { $said | ForEach-Object { Write-Host "    $_" } }
    else { Get-Content $uploadLog -Tail 10 -ErrorAction SilentlyContinue |
           ForEach-Object { Write-Host "    $_" } }
    Write-Host ""
    Write-Host "  full log: $uploadLog"
    Write-Host ""
    Write-Host "  Common causes, in the order they actually happen:"
    Write-Host "    401/403  the token is wrong, or its scope does not cover a NEW"
    Write-Host "             project -- a first upload needs an 'Entire account' token"
    Write-Host "    403      the account has no verified email address yet"
    Write-Host "    400      that filename was already uploaded; PyPI never reuses one"
    exit $code
}

# --- 4. confirm it is actually there ------------------------------------------

Write-Host ""
Write-Host "  confirming on pypi.org..." -NoNewline
Start-Sleep -Seconds 5
try {
    $meta = Invoke-RestMethod -Uri "https://pypi.org/pypi/anla-archive/json" -TimeoutSec 30
    Write-Host " anla-archive $($meta.info.version) is live" -ForegroundColor Green
    Write-Host "  https://pypi.org/project/anla-archive/"
    Write-Host ""
    Write-Host "  a stranger can now run:  pip install anla-archive"
} catch {
    Write-Host " not visible yet" -ForegroundColor Yellow
    Write-Host "  the index can lag a minute; check https://pypi.org/project/anla-archive/"
}
Write-Host ""
