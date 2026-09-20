Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

python scripts/reconstruct_source.py --output corresponding-source --archive artifacts/Update-P5-Edit-Aja-Source.zip

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
