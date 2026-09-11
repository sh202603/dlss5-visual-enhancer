<#
.SYNOPSIS
Neural Rendering, then RTX Video Super Resolution plus RTX Video HDR, as one script.

.DESCRIPTION
The two enhancers run in different workers, so the CLI has no single command for
them. This script chains the two commands:

  1. dlss5ve-cli video      Neural Rendering at the source size, SDR, into a stage folder
  2. dlss5ve-cli upscale-video   VSR to the target size and SDR-to-HDR10 conversion

Neural Rendering runs first because the Upscale pipeline accepts SDR sources only
and the NR worker processes 8-bit RGBA. Each stage is driven through --json, so a
file that fails in stage 1 is skipped in stage 2 instead of aborting the batch.

.PARAMETER InputPath
A video file, several files, or a folder (its supported files, name order).

.PARAMETER OutputDir
Where the final HDR files go. Stage-1 files are written to a "_nr_stage"
subfolder there and removed afterwards unless -KeepIntermediate is set.

.PARAMETER Scale
VSR scale factor for stage 2 (1 keeps the size and only de-noises), default 2.

.PARAMETER Codec
Codec for both stages; must support HDR (H.265, AV1, ProRes Proxy, plain or NVENC).

.PARAMETER NrArgs
Extra flags for the video command, e.g. @('--nr-style', 'Cinematic', '--nr-intensity', '1.2').

.PARAMETER UpscaleArgs
Extra flags for upscale-video, e.g. @('--vsr-quality', '3', '--hdr-peak-luminance', '800').

.EXAMPLE
.\examples\nr_vsr_hdr.ps1 D:\clips\scene.mp4 -OutputDir D:\hdr -Scale 2

.EXAMPLE
.\examples\nr_vsr_hdr.ps1 D:\clips -OutputDir D:\hdr -Codec AV1 -Container MKV -NrArgs @('--nr-style','Natural')
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0)][string[]]$InputPath,
    [Parameter(Mandatory)][string]$OutputDir,
    [double]$Scale = 2,
    [string]$Codec = 'H.265 (NVIDIA NVENC)',
    [ValidateSet('MP4', 'MKV', 'MOV')][string]$Container = 'MP4',
    [string]$Suffix = '_NR_VSR_HDR',
    [string[]]$NrArgs = @(),
    [string[]]$UpscaleArgs = @(),
    [switch]$KeepIntermediate,
    [string]$Cli = (Join-Path $PSScriptRoot '..\dlss5ve-cli.bat')
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

if (-not (Test-Path $Cli)) { throw "dlss5ve-cli.bat not found: $Cli" }
$Cli = (Resolve-Path $Cli).Path
New-Item -ItemType Directory -Force $OutputDir | Out-Null
$OutputDir = (Resolve-Path $OutputDir).Path
$stageDir = Join-Path $OutputDir '_nr_stage'
New-Item -ItemType Directory -Force $stageDir | Out-Null

function Invoke-Stage {
    param([string]$Name, [string[]]$Arguments)
    Write-Host "== $Name" -ForegroundColor Cyan
    Write-Host "   dlss5ve-cli $($Arguments -join ' ')"
    # stdout carries only the --json payload; progress and the summary stay on stderr.
    $json = & $Cli @Arguments | Out-String
    $code = $LASTEXITCODE
    if ([string]::IsNullOrWhiteSpace($json)) {
        throw "$Name produced no result (exit code $code); see the messages above."
    }
    $payload = $json | ConvertFrom-Json
    return [pscustomobject]@{ ExitCode = $code; Payload = $payload }
}

# --- stage 1: Neural Rendering at the source size, SDR (HDR Mode off), Copy naming
#     so that stage 2 sees the original base names.
$stage1 = Invoke-Stage 'Neural Rendering' (@(
    'video') + $InputPath + @(
    '--nr-scale', '1', '--no-hdr',
    '--codec', $Codec, '--container', 'MP4',
    '--rename', 'Copy',
    '--output-dir', $stageDir, '--json') + $NrArgs)
if ($stage1.ExitCode -eq 130) { throw 'Neural Rendering was cancelled.' }
$rendered = @($stage1.Payload.successes | ForEach-Object { $_.result.output_path })
foreach ($failure in $stage1.Payload.failures) {
    Write-Warning "Neural Rendering failed: $($failure.input_path): $(($failure.error -split "`n")[0])"
}
if ($rendered.Count -eq 0) { throw "Neural Rendering produced no output (exit code $($stage1.ExitCode))." }

# --- stage 2: VSR to the target size plus RTX Video HDR, on the stage-1 files only.
$stage2 = Invoke-Stage 'RTX Video Super Resolution + HDR' (@(
    'upscale-video') + $rendered + @(
    '--scale', $Scale.ToString([cultureinfo]::InvariantCulture), '--hdr',
    '--codec', $Codec, '--container', $Container,
    '--rename', 'Custom', '--suffix', $Suffix,
    '--output-dir', $OutputDir, '--json') + $UpscaleArgs)
foreach ($failure in $stage2.Payload.failures) {
    Write-Warning "Upscale failed: $($failure.input_path): $(($failure.error -split "`n")[0])"
}

if (-not $KeepIntermediate) {
    Remove-Item -Recurse -Force $stageDir
}

Write-Host "== Done" -ForegroundColor Cyan
foreach ($item in $stage2.Payload.successes) {
    $r = $item.result
    Write-Host "   $($r.output_path)  $($r.output_width)x$($r.output_height)  $($r.frames) frames"
}
$failed = $stage1.Payload.failures.Count + $stage2.Payload.failures.Count
if ($stage2.ExitCode -eq 130) { exit 130 }
exit ($(if ($failed -gt 0) { 1 } else { 0 }))
