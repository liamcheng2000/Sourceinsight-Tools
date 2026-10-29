param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectFolder,

    [string]$SourceRoot = "CtrlSW",

    [string]$SIProjectName = "",

    [string]$Config = "Debug",

    [string]$SIVersion = "4.00.0150"
)

$ErrorActionPreference = "Stop"

$TrunkDir = [IO.Path]::GetFullPath((Split-Path -Parent $MyInvocation.MyCommand.Path))
$ProjectDir = Join-Path $TrunkDir $ProjectFolder
$BuildDir = Join-Path $ProjectDir $Config

if (-not (Test-Path -LiteralPath $ProjectDir -PathType Container)) {
    throw "Project directory not found: $ProjectDir"
}

if (-not (Test-Path -LiteralPath $BuildDir -PathType Container)) {
    throw "Build directory not found: $BuildDir"
}

# SourceRoot may be relative to trunk or an absolute path.
if ([IO.Path]::IsPathRooted($SourceRoot)) {
    $SourceRootDir = [IO.Path]::GetFullPath($SourceRoot)
}
else {
    $SourceRootDir = [IO.Path]::GetFullPath((Join-Path $TrunkDir $SourceRoot))
}

if (-not (Test-Path -LiteralPath $SourceRootDir -PathType Container)) {
    throw "Source root not found: $SourceRootDir"
}

if ([string]::IsNullOrWhiteSpace($SIProjectName)) {
    $name = $ProjectFolder
    if ($name.StartsWith("Prj_", [StringComparison]::OrdinalIgnoreCase)) {
        $name = $name.Substring(4)
    }
    $SIProjectName = "SI_" + $name
}

$subdirFiles = @(
    Get-ChildItem -LiteralPath $BuildDir -Recurse -Filter "subdir.mk" -File -ErrorAction SilentlyContinue
)

if ($subdirFiles.Count -eq 0) {
    throw "No subdir.mk found. Build the project once first."
}

function Normalize-BuildPath {
    param(
        [string]$RawPath,
        [string]$BaseDir
    )

    if ([string]::IsNullOrWhiteSpace($RawPath)) {
        return $null
    }

    $p = $RawPath.Trim()
    $p = $p.TrimEnd('\').Trim()
    $p = $p.Trim('"')
    $p = $p -replace '\\ ', ' '

    if ([string]::IsNullOrWhiteSpace($p)) {
        return $null
    }

    if ($p -match '\$\(') {
        return $null
    }

    try {
        if ([IO.Path]::IsPathRooted($p)) {
            return [IO.Path]::GetFullPath($p)
        }
        return [IO.Path]::GetFullPath((Join-Path $BaseDir $p))
    }
    catch {
        return $null
    }
}

# ------------------------------------------------------------
# 1. Actual translation units from CDT-generated subdir.mk
# ------------------------------------------------------------

$sourceExtensions = @(".c", ".cc", ".cpp", ".cxx", ".s", ".asm")
$sourceVars = @(
    "C_SRCS",
    "CPP_SRCS",
    "CXX_SRCS",
    "CC_SRCS",
    "ASM_SRCS",
    "S_UPPER_SRCS"
)

$sources = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)

foreach ($mk in $subdirFiles) {
    $capturing = $false

    foreach ($line in Get-Content -LiteralPath $mk.FullName) {
        $trim = $line.Trim()

        if (-not $capturing) {
            foreach ($var in $sourceVars) {
                if ($trim -match ("^" + [regex]::Escape($var) + "\s*\+=")) {
                    $capturing = $true
                    $rhs = ($trim -replace ("^" + [regex]::Escape($var) + "\s*\+="), "").Trim()

                    if ($rhs) {
                        $candidate = Normalize-BuildPath -RawPath $rhs -BaseDir $BuildDir
                        if ($candidate) {
                            $ext = [IO.Path]::GetExtension($candidate).ToLowerInvariant()
                            if (($sourceExtensions -contains $ext) -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
                                [void]$sources.Add($candidate)
                            }
                        }
                    }

                    if (-not $trim.EndsWith("\")) {
                        $capturing = $false
                    }
                    break
                }
            }
        }
        else {
            if (-not $trim) {
                $capturing = $false
                continue
            }

            $candidate = Normalize-BuildPath -RawPath $trim -BaseDir $BuildDir
            if ($candidate) {
                $ext = [IO.Path]::GetExtension($candidate).ToLowerInvariant()
                if (($sourceExtensions -contains $ext) -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
                    [void]$sources.Add($candidate)
                }
            }

            if (-not $trim.EndsWith("\")) {
                $capturing = $false
            }
        }
    }
}

# ------------------------------------------------------------
# 2. Actual headers from GCC-generated dependency (*.d) files
# ------------------------------------------------------------

$headerExtensions = @(".h", ".hh", ".hpp", ".hxx", ".inc", ".inl")
$headers = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)

$depFiles = @(
    Get-ChildItem -LiteralPath $BuildDir -Recurse -Filter "*.d" -File -ErrorAction SilentlyContinue
)

foreach ($dep in $depFiles) {
    $raw = Get-Content -LiteralPath $dep.FullName -Raw

    # Join make continuation lines.
    $raw = $raw -replace "\\\r?\n", " "

    # GCC dependency target is normally before the first ": ".
    $match = [regex]::Match($raw, ':\s+')
    if (-not $match.Success) {
        continue
    }

    $depsText = $raw.Substring($match.Index + $match.Length)

    # Protect escaped spaces before tokenization.
    $placeholder = "__SI_ESCAPED_SPACE__"
    $depsText = $depsText -replace "\\ ", $placeholder

    foreach ($token0 in ($depsText -split "\s+")) {
        $token = $token0.Replace($placeholder, " ").Trim()
        if (-not $token) {
            continue
        }

        $candidate = Normalize-BuildPath -RawPath $token -BaseDir $BuildDir
        if (-not $candidate) {
            continue
        }

        $ext = [IO.Path]::GetExtension($candidate).ToLowerInvariant()
        if (($headerExtensions -contains $ext) -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            [void]$headers.Add($candidate)
        }
    }
}

# ------------------------------------------------------------
# 3. Keep files under SourceRoot and convert to Source Insight paths
# ------------------------------------------------------------

$rootPrefix = $SourceRootDir.TrimEnd('\') + '\'

$inside = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
$outside = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)

foreach ($file in @($sources) + @($headers)) {
    if ($file.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        $relative = $file.Substring($rootPrefix.Length)
        $relative = $relative.Replace('/', '\')
        [void]$inside.Add($relative)
    }
    else {
        [void]$outside.Add($file)
    }
}

$sortedFiles = @($inside | Sort-Object)

# ------------------------------------------------------------
# 4. Write Source Insight file list
# ------------------------------------------------------------

$OutputFile = Join-Path $TrunkDir ($SIProjectName + "_filelist.txt")
$OutsideFile = Join-Path $TrunkDir ($SIProjectName + "_outside_root.txt")

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("; Source Insight Project File List")
$lines.Add("; Project Name: $SIProjectName")
$lines.Add("; Generated by Source Insight $SIVersion at $timestamp")
$lines.Add("; Version=$SIVersion")
$lines.Add(";")
$lines.Add("; Each line should contain either a file name, a wildcard, or a sub-directory name.")
$lines.Add("; File paths are relative to the project source root directory.")
$lines.Add(";")
$lines.Add(";")

foreach ($file in $sortedFiles) {
    $lines.Add($file)
}

$lines | Set-Content -LiteralPath $OutputFile -Encoding UTF8

if ($outside.Count -gt 0) {
    @(
        "; Files used by the build but outside the selected Source Insight source root:"
        "; Source root: $SourceRootDir"
        "; These files are NOT written into the Source Insight file list."
        ";"
    ) + @($outside | Sort-Object) |
        Set-Content -LiteralPath $OutsideFile -Encoding UTF8
}
elseif (Test-Path -LiteralPath $OutsideFile) {
    Remove-Item -LiteralPath $OutsideFile -Force
}

Write-Host ""
Write-Host "============================================================"
Write-Host " Source Insight file list generated"
Write-Host "============================================================"
Write-Host "Xilinx project : $ProjectFolder"
Write-Host "Build config   : $Config"
Write-Host "SI project     : $SIProjectName"
Write-Host "Source root    : $SourceRootDir"
Write-Host "Source files   : $($sources.Count)"
Write-Host "Header files   : $($headers.Count)"
Write-Host "SI file count  : $($sortedFiles.Count)"
Write-Host "Outside root   : $($outside.Count)"
Write-Host ""
Write-Host "Output:"
Write-Host "  $OutputFile"

if ($outside.Count -gt 0) {
    Write-Host ""
    Write-Host "Files outside SourceRoot were skipped:"
    Write-Host "  $OutsideFile"
}

Write-Host ""
