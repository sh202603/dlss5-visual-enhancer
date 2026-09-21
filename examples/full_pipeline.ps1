<#
.SYNOPSIS
RTX Video Upscale, then DLSS Frame Generation, then DLSS 5 Neural Rendering, as one script.

.DESCRIPTION
The three enhancers run through different NGX bridges and hold the render slot
one at a time, so the CLI has no single command for them. This script chains the
three commands in the order requested in upstream issue #64 (Full Process
Pipeline), feeding each stage the files the previous stage produced:

  1. dlss5ve-cli upscale-video   RTX Video Super Resolution to the target size
  2. dlss5ve-cli interpolate     DLSS Frame Generation to the target frame rate
  3. dlss5ve-cli video           Neural Rendering at that size (--nr-scale 1)

Why this order. Super Resolution is trained on camera detail, so it works on the
original pixels rather than on frames another model has already sharpened, and it
accepts SDR sources only. Frame Generation then estimates motion at the final
resolution. Neural Rendering runs last so that every delivered frame, generated
ones included, is enhanced the same way.

What it costs. Each stage decodes and re-encodes, so quality loss accumulates
across three encodes; -EncodingQuality defaults to Max for that reason.
Intermediates are written at the upscaled size and, after stage 2, at the higher
frame rate, so the stage folders can be several times the size of the source.

A note on bit depth. One DLSS Frame Generation session carries a single depth
for its input and its output, and HDR Mode picks it, so a 10-bit source with
HDR off (or an 8-bit source with -Hdr) cannot stay on the GPU-resident path:
the processing layer stages those frames through system memory to convert
them. The render is correct either way, only slower, and this script says so
before the stage runs rather than leaving it to be discovered afterwards.

A note on frame rates. Frame Interpolation checks its own output against the
exact target rational, and Matroska's millisecond timestamps cannot carry
59.94 or 119.88 closely enough to pass, so this script refuses those two rates
with an MKV codec (H.265, AV1, and FFV1) before rendering anything. H.264 (MP4)
and both ProRes profiles (MOV) take them, and every rate works in MKV up to
29.97.

Each stage is driven through --json, so a file that fails in one stage is
dropped from the next instead of aborting the batch. Stages can be skipped;
whichever stage runs last writes to -OutputDir with the -Suffix name, and the
earlier ones write into stage folders that are removed unless -KeepIntermediate
is set.

.PARAMETER InputPath
A video file, several files, or a folder (its supported files, name order).
Only the first stage takes folders; later stages receive explicit file lists.

.PARAMETER OutputDir
Where the final files go. Stage folders "_stage1_upscale" and
"_stage2_interpolate" are created inside it and removed afterwards unless
-KeepIntermediate is set.

.PARAMETER Scale
RTX VSR scale factor for stage 1, at least 1 (1 keeps the size and only
enhances). Default 2.

.PARAMETER Fps
Target frame rate for stage 2. Default 60.

.PARAMETER Codec
Codec for every stage. The container follows the codec (H.264 gives MP4,
H.265, AV1 and FFV1 give MKV, ProRes Proxy and ProRes HQ give MOV). ProRes HQ
and FFV1 Lossless RGB 10-bit ignore -EncodingQuality.

.PARAMETER EncodingQuality
Encoding quality for every stage. Max by default because the material is
encoded three times.

.PARAMETER Hdr
Convert SDR to HDR10 with RTX Video HDR in stage 1 and keep 10-bit through
stages 2 and 3. Requires a 10-bit codec (H.265, AV1, ProRes Proxy, ProRes HQ, or FFV1).

.PARAMETER UpscaleArgs
Extra flags for upscale-video, e.g. @('--vsr-quality', '3').

.PARAMETER InterpolateArgs
Extra flags for interpolate, e.g. @('--engine', 'Cascade').

.PARAMETER NrArgs
Extra flags for the video command, e.g. @('--nr-style', 'Cinematic', '--nr-passes', '2').

.EXAMPLE
.\examples\full_pipeline.ps1 D:\clips\scene.mp4 -OutputDir D:\out

.EXAMPLE
.\examples\full_pipeline.ps1 D:\clips -OutputDir D:\out -Scale 2 -Fps 120 -NrArgs @('--nr-style','Natural')

.EXAMPLE
.\examples\full_pipeline.ps1 D:\clips -OutputDir D:\out -Hdr -Codec 'AV1 (NVIDIA NVENC)'

.EXAMPLE
.\examples\full_pipeline.ps1 D:\uhd -OutputDir D:\out -SkipUpscale -Fps 60
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0)][string[]]$InputPath,
    [Parameter(Mandatory)][string]$OutputDir,
    [double]$Scale = 2,
    [ValidateSet('23.976', '25', '29.97', '30', '50', '59.94', '60', '90', '119.88',
                 '120', '144', '165', '180', '240', '360', '480')]
    [string]$Fps = '60',
    [ValidateSet('H.264', 'H.264 (NVIDIA NVENC)', 'H.265', 'H.265 (NVIDIA NVENC)',
                 'AV1', 'AV1 (NVIDIA NVENC)', 'ProRes Proxy', 'ProRes HQ',
                 'FFV1 Lossless RGB 10-bit')]
    [string]$Codec = 'H.265 (NVIDIA NVENC)',
    [ValidateSet('Auto (Default)', 'Max', 'Best', 'Good')]
    [string]$EncodingQuality = 'Max',
    [string]$Suffix = '_PIPELINE',
    [switch]$Hdr,
    [switch]$SkipUpscale,
    [switch]$SkipInterpolate,
    [switch]$SkipEnhance,
    [string[]]$UpscaleArgs = @(),
    [string[]]$InterpolateArgs = @(),
    [string[]]$NrArgs = @(),
    [switch]$KeepIntermediate,
    [string]$Cli = (Join-Path $PSScriptRoot '..\dlss5ve-cli.bat'),
    [string]$Ffprobe = (Join-Path $PSScriptRoot '..\bin\ffmpeg\bin\ffprobe.exe')
)

$ErrorActionPreference = 'Stop'
# The CLI signals partial failures with exit code 1, which this script reads from
# $LASTEXITCODE. Keep PowerShell from turning that into a terminating error.
$PSNativeCommandUseErrorActionPreference = $false
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$HDR_CODECS = @('H.265', 'H.265 (NVIDIA NVENC)', 'AV1', 'AV1 (NVIDIA NVENC)', 'ProRes Proxy',
                'ProRes HQ', 'FFV1 Lossless RGB 10-bit')
if ($Hdr -and $Codec -notin $HDR_CODECS) {
    throw "HDR needs one of: $($HDR_CODECS -join ', '). -Codec is '$Codec'."
}
if ($Scale -lt 1) {
    throw "-Scale must be at least 1; RTX Video Super Resolution never reduces the size."
}
if ($SkipUpscale -and $SkipInterpolate -and $SkipEnhance) {
    throw 'All three stages are skipped; nothing to do.'
}
# Frame Interpolation verifies its own output against the exact target rational.
# Matroska keeps millisecond timestamps, which cannot carry 59.94 or 119.88
# closely enough for that check, so those two rates always fail in an MKV
# however long the render took. Refuse the combination up front.
$container = switch -Regex ($Codec) {
    '^H\.264' { 'MP4'; break }
    '^ProRes' { 'MOV'; break }
    default   { 'MKV' }
}
if (-not $SkipInterpolate -and $container -eq 'MKV' -and $Fps -in @('59.94', '119.88')) {
    throw ("-Fps $Fps cannot be verified in an MKV output: Matroska stores millisecond " +
           "timestamps and Frame Interpolation checks its result against the exact rate. " +
           "Use -Codec 'H.264 (NVIDIA NVENC)' (MP4) or -Codec 'ProRes Proxy' (MOV), " +
           "or an integer rate such as -Fps 60.")
}
if (-not (Test-Path $Cli)) { throw "dlss5ve-cli.bat not found: $Cli" }
$Cli = (Resolve-Path $Cli).Path
New-Item -ItemType Directory -Force $OutputDir | Out-Null
$OutputDir = (Resolve-Path $OutputDir).Path

$hdrFlag = if ($Hdr) { @('--hdr') } else { @('--no-hdr') }

# Stage table. Extra carries the flags that belong to this command only; the
# codec, quality, naming, and output directory are added per run below.
$stages = @()
if (-not $SkipUpscale) {
    $stages += [pscustomobject]@{
        Name    = 'RTX Video Super Resolution'
        Command = 'upscale-video'
        Folder  = '_stage1_upscale'
        Extra   = @('--scale', $Scale.ToString([cultureinfo]::InvariantCulture)) + $hdrFlag + $UpscaleArgs
    }
}
if (-not $SkipInterpolate) {
    $stages += [pscustomobject]@{
        Name    = 'DLSS Frame Generation'
        Command = 'interpolate'
        Folder  = '_stage2_interpolate'
        Extra   = @('--fps', $Fps) + $hdrFlag + $InterpolateArgs
    }
}
if (-not $SkipEnhance) {
    $stages += [pscustomobject]@{
        Name    = 'Neural Rendering'
        Command = 'video'
        Folder  = '_stage3_enhance'
        # The size is already final; Neural Rendering must not resize again.
        Extra   = @('--nr-scale', '1') + $hdrFlag + $NrArgs
    }
}

function Format-Command {
    # Quote the arguments that carry spaces so the echoed line can be pasted back.
    param([string[]]$Arguments)
    return ($Arguments | ForEach-Object { if ($_ -match '\s') { "'$_'" } else { $_ } }) -join ' '
}

function Invoke-Stage {
    # The caller prints the "== name" header, so that any advisory note for the
    # stage appears under it and above the command line.
    param([string]$Name, [string[]]$Arguments)
    Write-Host "   dlss5ve-cli $(Format-Command $Arguments)"
    # stdout carries only the --json payload; progress and the summary stay on stderr.
    $json = & $Cli @Arguments | Out-String
    $code = $LASTEXITCODE
    if ([string]::IsNullOrWhiteSpace($json)) {
        throw "$Name produced no result (exit code $code); see the messages above."
    }
    return [pscustomobject]@{ ExitCode = $code; Payload = ($json | ConvertFrom-Json) }
}

function Get-VideoBitDepth {
    # 0 when the depth cannot be read; the caller then says nothing.
    param([string]$Path)
    if (-not (Test-Path $Ffprobe) -or -not (Test-Path -PathType Leaf $Path)) { return 0 }
    try {
        $pixelFormat = & $Ffprobe -v error -select_streams v:0 -show_entries stream=pix_fmt `
            -of csv=p=0 -- $Path 2>$null | Select-Object -First 1
    } catch {
        return 0
    }
    if (-not $pixelFormat) { return 0 }
    if ($pixelFormat -match '(\d{2})(le|be)$') { return [int]$Matches[1] }
    return 8
}

function Write-DepthNote {
    # One DLSSG session carries a single depth for input and output, and HDR Mode
    # picks it. When the source disagrees, the processing layer stages the frames
    # through system memory to convert them, which is correct but slower than the
    # GPU-resident path. Saying so before the stage beats wondering afterwards.
    param([string[]]$Files)
    $mismatched = @($Files | Where-Object {
        $depth = Get-VideoBitDepth $_
        $depth -gt 0 -and (($depth -gt 8) -ne [bool]$Hdr)
    })
    if ($mismatched.Count -eq 0) { return }
    $state = if ($Hdr) { '8-bit while -Hdr asks for 10-bit output' } else { '10-bit while HDR is off' }
    Write-Host "   note: $($mismatched.Count) file(s) are $state, so this stage stages through" -ForegroundColor Yellow
    Write-Host "         system memory instead of staying on the GPU. The result is the same." -ForegroundColor Yellow
}

function Format-Result {
    param([object]$Result)
    $parts = @()
    if ($Result.PSObject.Properties['output_width']) {
        $parts += "$($Result.output_width)x$($Result.output_height)"
    }
    if ($Result.PSObject.Properties['output_frames']) {
        $parts += "$($Result.output_frames) frames ($($Result.generated_frames) generated)"
    } elseif ($Result.PSObject.Properties['frames']) {
        $parts += "$($Result.frames) frames"
    }
    return ($parts -join '  ')
}

$stageDirs = @()
$current = $InputPath
$failedCount = 0
$lastPayload = $null
$completed = $false

try {
    for ($i = 0; $i -lt $stages.Count; $i++) {
        $stage = $stages[$i]
        $isLast = ($i -eq $stages.Count - 1)
        if ($isLast) {
            $destination = $OutputDir
            # Only the final file carries the pipeline suffix; the stage files keep
            # the source names so that each stage can find them by name.
            $naming = @('--rename', 'Custom', '--suffix', $Suffix)
        } else {
            $destination = Join-Path $OutputDir $stage.Folder
            New-Item -ItemType Directory -Force $destination | Out-Null
            $stageDirs += $destination
            $naming = @('--rename', 'Copy')
        }

        $arguments = @($stage.Command) + $current + $stage.Extra + @(
            '--codec', $Codec,
            '--encoding-quality', $EncodingQuality,
            '--output-dir', $destination, '--json') + $naming
        Write-Host "== $($stage.Name)" -ForegroundColor Cyan
        # Only Frame Generation cares about the source depth; the other two
        # stages convert whatever they are given without changing transport.
        if ($stage.Command -eq 'interpolate') { Write-DepthNote $current }
        $run = Invoke-Stage $stage.Name $arguments
        $lastPayload = $run.Payload

        foreach ($failure in @($run.Payload.failures)) {
            $failedCount++
            Write-Warning "$($stage.Name) failed: $($failure.input_path): $(($failure.error -split "`n")[0])"
        }
        if ($run.ExitCode -eq 130) {
            Write-Warning "$($stage.Name) was cancelled; stopping. Finished intermediates are kept."
            exit 130
        }
        $produced = @(@($run.Payload.successes) | ForEach-Object { $_.result.output_path })
        if ($produced.Count -eq 0) {
            throw "$($stage.Name) produced no output (exit code $($run.ExitCode))."
        }
        $current = $produced
    }
    $completed = $true
} finally {
    # A finished run drops its stage folders. An interrupted one keeps whatever
    # it managed to render, because that work is worth resuming from, but still
    # removes the folders it never wrote into.
    foreach ($dir in $stageDirs) {
        if (-not (Test-Path $dir)) { continue }
        $keep = $KeepIntermediate -or (-not $completed -and @(Get-ChildItem -File $dir).Count -gt 0)
        if (-not $keep) { Remove-Item -Recurse -Force $dir }
    }
}

Write-Host '== Done' -ForegroundColor Cyan
foreach ($item in @($lastPayload.successes)) {
    Write-Host "   $($item.result.output_path)  $(Format-Result $item.result)"
}
exit ($(if ($failedCount -gt 0) { 1 } else { 0 }))
