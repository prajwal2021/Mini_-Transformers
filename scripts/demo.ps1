<#
Demo runner for the recorded video (follows docs/DEMO_SHOTLIST.md).

Each step clears nothing; it prints a title and the command, waits for Enter,
runs the command live, then waits for Enter before the next step. Read the
"what to say" lines from docs/DEMO_SHOTLIST.md on a second screen or your phone.

Usage (from the repository root, with bundle.zip unzipped into .\bundle):
    powershell -ExecutionPolicy Bypass -File scripts\demo.ps1
    powershell -ExecutionPolicy Bypass -File scripts\demo.ps1 -Start 5      # resume at step 5
    powershell -ExecutionPolicy Bypass -File scripts\demo.ps1 -SkipSampled  # drop the temperature step if running long
    powershell -ExecutionPolicy Bypass -File scripts\demo.ps1 -DryRun -NoPause  # print the commands only
#>
param(
    [string]$Bundle = "bundle",
    [int]$Start = 1,
    [switch]$SkipSampled,
    [switch]$DryRun,
    [switch]$NoPause
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# Prefer the project's virtual environment if there is one.
$python = "python"
if (Test-Path ".venv\Scripts\python.exe") { $python = ".venv\Scripts\python.exe" }

if (-not $DryRun -and -not (Test-Path (Join-Path $Bundle "pretrained"))) {
    Write-Host "Bundle not found at '$Bundle'. Unzip bundle.zip at the repository root first:" -ForegroundColor Red
    Write-Host "    Expand-Archive bundle.zip ." -ForegroundColor Red
    exit 1
}

$cat = "Passengers who arrive with a nervous cat should first"
$steps = @(
    @{ Title = "Verify the release files";              Args = @("scripts/make_bundle.py", "--verify", $Bundle) },
    @{ Title = "What is in the bundle";                  Show = (Join-Path $Bundle "CHECKPOINTS.md") },
    @{ Title = "Pretrained model: free text (greedy)";   Args = @("scripts/generate.py", "--bundle", "$Bundle/pretrained", "--prompt", $cat, "--max-new-tokens", "40") },
    @{ Title = "Pretrained model: sampled, T=0.8";       Args = @("scripts/generate.py", "--bundle", "$Bundle/pretrained", "--prompt", $cat, "--max-new-tokens", "40", "--temperature", "0.8", "--seed", "0"); Sampled = $true },
    @{ Title = "SUCCESS: a fine-tuned fact (sft_fixed3)"; Args = @("scripts/generate.py", "--bundle", "$Bundle/sft_fixed3", "--qa", "Who manages the pet lounge at Vellmar?") },
    @{ Title = "Same question, pre-specified SFT (sft_early_stopped)"; Args = @("scripts/generate.py", "--bundle", "$Bundle/sft_early_stopped", "--qa", "Who manages the pet lounge at Vellmar?") },
    @{ Title = "FAILURE: a novel question, all three models"; Args = @("scripts/generate.py", "--bundle-root", $Bundle, "--compare", "--qa", "What would it cost to bring my cat on the airship?") },
    @{ Title = "FAILURE: an entity not in the knowledge base"; Args = @("scripts/generate.py", "--bundle", "$Bundle/sft_fixed3", "--qa", "Who looks after the cargo pets on the Zephyrine?") },
    @{ Title = "Results: the report";                    Open = (Join-Path $Bundle "report/report.pdf") }
)

function Wait-Enter([string]$msg) {
    if ($NoPause) { return }
    Write-Host ""
    Write-Host $msg -ForegroundColor DarkGray -NoNewline
    [void][Console]::ReadLine()
}

function Format-Arg([string]$a) { if ($a -match '\s') { '"' + $a + '"' } else { $a } }

Clear-Host
Write-Host "Small Transformer LM - Aurelia Skyways Companion Animal Travel Desk" -ForegroundColor Cyan
Write-Host "12.4M-parameter decoder-only Transformer, built and trained from scratch, running on CPU" -ForegroundColor Cyan
Wait-Enter "[Enter to start]"

for ($i = $Start; $i -le $steps.Count; $i++) {
    $s = $steps[$i - 1]
    if ($SkipSampled -and $s.Sampled) { continue }

    Write-Host ""
    Write-Host ("=" * 78) -ForegroundColor DarkCyan
    Write-Host ("Step {0}/{1}: {2}" -f $i, $steps.Count, $s.Title) -ForegroundColor Yellow

    if ($s.Args) {
        $line = "python " + (($s.Args | ForEach-Object { Format-Arg $_ }) -join " ")
        Write-Host "> $line" -ForegroundColor Green
        Wait-Enter "[Enter to run]"
        if (-not $DryRun) {
            & $python @($s.Args)
            if ($LASTEXITCODE -ne 0) { Write-Host "(command exited with code $LASTEXITCODE)" -ForegroundColor Red }
        }
    } elseif ($s.Show) {
        Write-Host "> type $($s.Show)" -ForegroundColor Green
        Wait-Enter "[Enter to run]"
        if (-not $DryRun) { Get-Content $s.Show | Write-Host }
    } elseif ($s.Open) {
        Write-Host "> start $($s.Open)" -ForegroundColor Green
        Wait-Enter "[Enter to open]"
        if (-not $DryRun) {
            if (Test-Path $s.Open) { Start-Process $s.Open }
            else { Write-Host "Report not found at $($s.Open); open reports\integration\r11\report.pdf instead." -ForegroundColor Red }
        }
    }

    if ($i -lt $steps.Count) { Wait-Enter "[Enter for next step]" }
}

Write-Host ""
Write-Host "Demo complete." -ForegroundColor Cyan
