# Copies the addon into WoW's AddOns folder. Leaves the companion's live\ folder alone.
# In game, /reload picks up the changes.
param(
  [string]$AddOns = "C:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns"
)
$src = Join-Path $PSScriptRoot "..\addon\Cassette"
$dst = Join-Path $AddOns "Cassette"
robocopy $src $dst /E /XD live /NJH /NJS /NP /NDL | Out-Null
if ($LASTEXITCODE -ge 8) { throw "copy failed (robocopy code $LASTEXITCODE)" }
Write-Output "Cassette addon copied to $dst"
exit 0  # robocopy's 1-7 mean success
