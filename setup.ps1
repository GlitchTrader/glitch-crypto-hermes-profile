$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw 'Python 3.12 or newer is required.'
}

if (-not (Test-Path (Join-Path $root '.env'))) {
    Copy-Item (Join-Path $root '.env.EXAMPLE') (Join-Path $root '.env')
    Write-Host 'Created .env from .env.EXAMPLE. Configure the paired gateway tokens before using commands.'
}

& $python.Source (Join-Path $root 'scripts\verify_distribution.py')
& $python.Source -m unittest discover -s tests -p 'test_*.py'

Write-Host 'Glitch Crypto profile verified.'
Write-Host 'No scheduled trading job is installed by GC-001; use the interactive profile and deterministic slash commands.'
