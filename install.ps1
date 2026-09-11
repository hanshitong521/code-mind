<#
  install.ps1 — Engineering Control Plane 发布安装器（Peak v3 P0）

  安装流程（§6.2 / §27.4）：
      backup → verify hash → install → doctor
      任一步失败 → rollback

  用法：
    .\install.ps1                     # 安装到用户级 .cursor\skills（默认）
    .\install.ps1 -Force              # 覆盖已存在副本
    .\install.ps1 -Target project -ProjectPath D:\myproj
    .\install.ps1 -Copy               # 复制而非 junction
    .\install.ps1 -Doctor             # 只体检，不安装
    .\install.ps1 -Uninstall [-Force] # 卸载（含 legacy 清理）
    .\install.ps1 -Rollback           # 回滚到最近一次安装前快照
    .\install.ps1 -SkipHashVerify     # 紧急跳过哈希校验（不推荐）

  退出码：0=成功；1=失败（已自动 rollback）
#>
[CmdletBinding()]
param(
    [ValidateSet('user', 'project', 'both')]
    [string]$Target = 'user',
    [string]$ProjectPath = '',
    [switch]$Copy,
    [switch]$Force,
    [switch]$Uninstall,
    [switch]$Rollback,
    [switch]$Confirm,
    [switch]$Doctor,
    [switch]$SkipHashVerify,
    [string]$HarnessDir = '.cursor\skills'
)
$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# ── Python 解析（哈希校验需要）────────────────────────────────────
function Get-PythonExe {
    $cands = @(
        'C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe',
        'C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe'
    )
    foreach ($c in $cands) { if (Test-Path -LiteralPath $c) { return $c } }
    foreach ($n in @('python', 'python3')) {
        $cmd = Get-Command $n -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

# ── YAML 极简解析（只处理 deploy.bundle.yaml 的已知结构）──────────
function Get-DeployBundle {
    param([string]$BundlePath)
    if (-not (Test-Path -LiteralPath $BundlePath)) { throw "缺少 deploy.bundle.yaml: $BundlePath" }
    $lines = Get-Content -LiteralPath $BundlePath -Encoding UTF8
    $skills = [System.Collections.Generic.List[string]]::new()
    $legacy = [System.Collections.Generic.List[string]]::new()
    $installShared = $true
    $requireHash = $true
    $backupFirst = $true
    $section = ''
    foreach ($line in $lines) {
        if ($line -match '^\s*#') { continue }
        if ($line -match '^skills:\s*$') { $section = 'skills'; continue }
        if ($line -match '^legacy_skill_names:\s*$') { $section = 'legacy'; continue }
        if ($line -match '^install_shared:\s*(true|false)\s*$') { $installShared = ($Matches[1] -eq 'true'); continue }
        if ($line -match '^\s*require_hash_verify:\s*(true|false)\s*$') { $requireHash = ($Matches[1] -eq 'true'); continue }
        if ($line -match '^\s*backup_before_install:\s*(true|false)\s*$') { $backupFirst = ($Matches[1] -eq 'true'); continue }
        if ($line -match '^\s*-\s+(\S+)\s*$') {
            if ($section -eq 'skills') { $skills.Add($Matches[1]) }
            elseif ($section -eq 'legacy') { $legacy.Add($Matches[1]) }
            continue
        }
        if ($line -match '^[A-Za-z_][\w-]*:\s*') { $section = '' }
    }
    if ($skills.Count -eq 0) { throw 'deploy.bundle.yaml 中 skills 列表为空' }
    return @{
        Skills = $skills.ToArray(); LegacyNames = $legacy.ToArray()
        InstallShared = $installShared; RequireHash = $requireHash; BackupFirst = $backupFirst
    }
}

# ── 哈希校验：调用 build_release.py --check ────────────────────────
function Invoke-HashVerify {
    param([bool]$Required)
    $py = Get-PythonExe
    if (-not $py) {
        if ($Required) { throw '哈希校验需要 Python + PyYAML，但未找到可用解释器' }
        Write-Warning '未找到 Python，跳过哈希校验'
        return $true
    }
    $build = Join-Path $ScriptDir 'scripts\build_release.py'
    if (-not (Test-Path -LiteralPath $build)) {
        if ($Required) { throw "缺少 scripts\build_release.py" }
        Write-Warning '缺少 build_release.py，跳过哈希校验'
        return $true
    }
    $prev = Get-Location
    try {
        Set-Location $ScriptDir
        $null = & $py $build --check 2>&1
        return ($LASTEXITCODE -eq 0)
    } finally { Set-Location $prev }
}

function Link-Or-CopyItem {
    param([string]$Source, [string]$DestParent, [string]$Name, [bool]$UseCopy, [bool]$Overwrite, [switch]$Remove)
    $Dest = Join-Path $DestParent $Name
    if ($Remove) {
        if (-not (Test-Path -LiteralPath $Dest)) { Write-Host "[skip] $Dest"; return }
        $item = Get-Item -LiteralPath $Dest -Force
        if ($item.LinkType -eq 'Junction') { Remove-Item -LiteralPath $Dest -Force; Write-Host "[unlink] $Dest" }
        elseif ($Force) { Remove-Item -LiteralPath $Dest -Recurse -Force; Write-Host "[delete] $Dest" }
        else { Write-Warning "[physical] $Dest 用 -Force 删" }
        return
    }
    if (-not (Test-Path -LiteralPath $Source)) { throw "源不存在: $Source" }
    if (-not (Test-Path -LiteralPath $DestParent)) { New-Item -ItemType Directory -Path $DestParent -Force | Out-Null }
    if (Test-Path -LiteralPath $Dest) {
        if (-not $Overwrite) { Write-Warning "跳过（-Force 覆盖）: $Dest"; return }
        Remove-Item -LiteralPath $Dest -Recurse -Force
    }
    if ($UseCopy) { Copy-Item -LiteralPath $Source -Destination $Dest -Recurse -Force; Write-Host "[copy] $Dest" }
    else { New-Item -ItemType Junction -Path $Dest -Target $Source -Force | Out-Null; Write-Host "[junction] $Dest -> $Source" }
}

# ── 备份：把目标目录现有安装副本存到 .skill-rollback/<timestamp>/ ──
function New-InstallBackup {
    param([string[]]$TargetDirs, [string[]]$Names, [bool]$IncludeShared)
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backupRoot = Join-Path $ScriptDir ".skill-rollback\$stamp"
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    $manifest = [System.Collections.Generic.List[string]]::new()

    foreach ($Dir in $TargetDirs) {
        $parent = Split-Path -Parent $Dir
        foreach ($n in $Names) {
            $src = Join-Path $Dir $n
            if (-not (Test-Path -LiteralPath $src)) { continue }
            $item = Get-Item -LiteralPath $src -Force
            if ($item.LinkType -eq 'Junction') {
                $manifest.Add("junction|$src|$($item.Target)")
            } else {
                $dst = Join-Path $backupRoot ("$([IO.Path]::GetFileName($parent))__$n")
                Copy-Item -LiteralPath $src -Destination $dst -Recurse -Force
                $manifest.Add("copy|$src|$dst")
            }
        }
        if ($IncludeShared) {
            $shSrc = Join-Path $parent 'shared'
            if (Test-Path -LiteralPath $shSrc) {
                $shItem = Get-Item -LiteralPath $shSrc -Force
                if ($shItem.LinkType -eq 'Junction') {
                    $manifest.Add("junction|$shSrc|$($shItem.Target)")
                } else {
                    $shDst = Join-Path $backupRoot ("$([IO.Path]::GetFileName($parent))__shared")
                    Copy-Item -LiteralPath $shSrc -Destination $shDst -Recurse -Force
                    $manifest.Add("copy|$shSrc|$shDst")
                }
            }
        }
    }
    # 即使 0 项也要写出 manifest.txt，保证 rollback 可识别「快照为空」这一合法状态
    $lines = @($manifest)
    if ($lines.Count -eq 0) { $lines = @('# empty snapshot: 安装前目标目录无既有副本') }
    $lines | Set-Content (Join-Path $backupRoot 'manifest.txt') -Encoding UTF8
    Set-Content (Join-Path $ScriptDir '.skill-rollback\LATEST') $backupRoot -Encoding UTF8
    Write-Host "[backup] $backupRoot ($($manifest.Count) 项)"
    return $backupRoot
}
function Invoke-Rollback {
    param([string]$BackupRoot, [string[]]$TargetDirs, [string[]]$Names, [bool]$IncludeShared)
    if ([string]::IsNullOrWhiteSpace($BackupRoot)) {
        $latest = Join-Path $ScriptDir '.skill-rollback\LATEST'
        if (-not (Test-Path -LiteralPath $latest)) { Write-Warning '无可回滚快照'; return $false }
        $BackupRoot = (Get-Content -LiteralPath $latest -Raw).Trim()
    }
    if (-not (Test-Path -LiteralPath $BackupRoot)) { Write-Warning "快照不存在: $BackupRoot"; return $false }
    $mf = Join-Path $BackupRoot 'manifest.txt'
    if (-not (Test-Path -LiteralPath $mf)) { Write-Warning '快照缺 manifest.txt'; return $false }

    Write-Host "[rollback] 从 $BackupRoot 恢复"
    $restored = [System.Collections.Generic.HashSet[string]]::new()

    foreach ($line in (Get-Content -LiteralPath $mf -Encoding UTF8)) {
        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith('#')) { continue }
        $parts = $line.Split('|', 3)
        if ($parts.Count -lt 3) { continue }
        $kind, $dest, $src = $parts
        if (Test-Path -LiteralPath $dest) { Remove-Item -LiteralPath $dest -Recurse -Force -ErrorAction SilentlyContinue }
        if ($kind -eq 'junction') {
            New-Item -ItemType Junction -Path $dest -Target $src -Force | Out-Null
        } elseif (Test-Path -LiteralPath $src) {
            Copy-Item -LiteralPath $src -Destination $dest -Recurse -Force
        }
        $restored.Add($dest) | Out-Null
        Write-Host "  [restore] $dest"
    }

    # 关键：安装前不存在的项，回滚时要删掉（否则 rollback 不彻底）
    # 安全约束：只清理由本 bundle 声明的 skill 名；绝不递归删除 harness 根目录本身。
    if ($TargetDirs) {
        $expected = [System.Collections.Generic.List[string]]::new()
        foreach ($Dir in $TargetDirs) {
            foreach ($n in $Names) {
                # 只清理 skills 列表内的（不清理 legacy：它们可能是用户既有内容）
                if ($Bundle.Skills -contains $n) { $expected.Add((Join-Path $Dir $n)) }
            }
            if ($IncludeShared) { $expected.Add((Join-Path (Split-Path -Parent $Dir) 'shared')) }
            $expected.Add((Join-Path $Dir '.installed-version'))
        }
        foreach ($p in $expected) {
            if (-not $restored.Contains($p) -and (Test-Path -LiteralPath $p)) {
                Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue
                Write-Host "  [removed] $p（安装前不存在）"
            }
        }
    }
    Write-Host '[rollback] 完成'
    return $true
}

# ── Doctor：体检安装结果 ──────────────────────────────────────────
function Invoke-Doctor {
    param([string[]]$TargetDirs, [string[]]$Names, [bool]$IncludeShared, [bool]$Json)
    $issues = [System.Collections.Generic.List[string]]::new()
    $ok = 0
    foreach ($Dir in $TargetDirs) {
        foreach ($n in $Names) {
            $p = Join-Path $Dir $n
            if (-not (Test-Path -LiteralPath $p)) { $issues.Add("缺失: $p") }
            elseif (-not (Test-Path -LiteralPath (Join-Path $p 'SKILL.md'))) { $issues.Add("缺 SKILL.md: $p") }
            else { $ok++ }
        }
        if ($IncludeShared) {
            $sh = Join-Path (Split-Path -Parent $Dir) 'shared'
            if (-not (Test-Path -LiteralPath $sh)) { $issues.Add("缺失: $sh") }
            else { $ok++ }
        }
    }
    $py = Get-PythonExe
    if ($py) {
        $verify = Join-Path $ScriptDir 'scripts\verify_skill_drift.py'
        if (Test-Path -LiteralPath $verify) {
            $prev = Get-Location
            try {
                Set-Location $ScriptDir
                $null = & $py $verify 2>&1
                if ($LASTEXITCODE -ne 0) { $issues.Add('verify_skill_drift.py 报 DRIFT/MISSING/UNTRACKED') }
            } finally { Set-Location $prev }
        }
    } else { $issues.Add('未找到 Python，跳过哈希体检') }

    if ($Json) {
        @{ ok = ($issues.Count -eq 0); checked = $ok; issues = $issues.ToArray() } |
            ConvertTo-Json -Depth 4
    } else {
        Write-Host "[doctor] 通过项: $ok"
        if ($issues.Count -eq 0) { Write-Host '[doctor] 全部正常' }
        else { foreach ($i in $issues) { Write-Warning "[doctor] $i" } }
    }
    return ($issues.Count -eq 0)
}

# ══════════════════════════════════════════════════════════════════
$BundlePath = Join-Path $ScriptDir 'deploy.bundle.yaml'
$Bundle = Get-DeployBundle -BundlePath $BundlePath
if ([string]::IsNullOrWhiteSpace($ProjectPath)) { $ProjectPath = (Get-Location).Path }

# ── 安全推断：显式给了 -ProjectPath 但没给 -Target → 视为项目级 ──
# 原因：-ProjectPath 是项目意图的强信号。若仍按默认 Target=user 安装，
#       会静默写入用户级 .cursor\skills（曾导致误建 junction 的事故）。
$targetExplicit = $PSBoundParameters.ContainsKey('Target')
if (-not $targetExplicit -and $PSBoundParameters.ContainsKey('ProjectPath') -and $Target -eq 'user') {
    $Target = 'project'
    Write-Host "[target] 检测到 -ProjectPath 但未指定 -Target，自动按 project 级安装"
    Write-Host "[target] （如需用户级，请显式 -Target user）"
}

$UserSkills = Join-Path $env:USERPROFILE $HarnessDir
$ProjectSkills = Join-Path $ProjectPath $HarnessDir
function Get-TargetDirs([string]$c) {
    switch ($c) { 'user' { @($UserSkills) } 'project' { @($ProjectSkills) } 'both' { @($UserSkills, $ProjectSkills) } }
}
$TargetDirs = Get-TargetDirs $Target
$AllNames = @($Bundle.Skills) + @($Bundle.LegacyNames) | Select-Object -Unique

# ── 模式：Rollback ──
# 安全：Rollback 会删除「安装前不存在」的副本。若未显式指定 -ProjectPath，
#       默认 Target=user 会作用于用户级 .cursor\skills。为避免误删用户既有内容，
#       要求显式确认（-Confirm 或 -Force），否则拒绝执行。
if ($Rollback) {
    if ($Target -eq 'user' -and -not $Force -and -not $Confirm) {
        Write-Warning '拒绝执行：-Rollback 默认作用于用户级 .cursor\skills。'
        Write-Warning '若确认要回滚用户级安装，请加 -Confirm（或 -Force）；回滚项目级请用 -Target project -ProjectPath <path>。'
        exit 1
    }
    $okR = Invoke-Rollback -BackupRoot '' -TargetDirs $TargetDirs -Names $AllNames -IncludeShared $Bundle.InstallShared
    exit ($(if ($okR) { 0 } else { 1 }))
}

# ── 模式：Doctor ──
if ($Doctor) {
    $okD = Invoke-Doctor -TargetDirs $TargetDirs -Names $Bundle.Skills -IncludeShared $Bundle.InstallShared -Json:$false
    exit ($(if ($okD) { 0 } else { 1 }))
}

# ── 模式：Uninstall ──
if ($Uninstall) {
    foreach ($Dir in $TargetDirs) {
        foreach ($n in $AllNames) { Link-Or-CopyItem -DestParent $Dir -Name $n -Remove -Force:$Force }
        if ($Bundle.InstallShared) { Link-Or-CopyItem -DestParent (Split-Path -Parent $Dir) -Name 'shared' -Remove -Force:$Force }
        $vf = Join-Path $Dir '.installed-version'
        if (Test-Path $vf) { Remove-Item $vf -Force }
    }
    Write-Host 'Done (uninstall).'
    exit 0
}

# ── 模式：Install（backup → verify → install → doctor，失败即 rollback）──
$backupRoot = $null
try {
    if ($Bundle.BackupFirst) {
        $backupRoot = New-InstallBackup -TargetDirs $TargetDirs -Names $AllNames -IncludeShared $Bundle.InstallShared
    }

    if (-not $SkipHashVerify) {
        Write-Host '[verify] 校验 release 哈希…'
        $hashOk = Invoke-HashVerify -Required:$Bundle.RequireHash
        if (-not $hashOk) { throw '发布哈希校验未通过（run scripts/build_release.py 后重试）' }
        Write-Host '[verify] 哈希一致'
    } else {
        Write-Warning '已跳过哈希校验（-SkipHashVerify）'
    }

    $SourceRoot = Join-Path $ScriptDir 'skills'
    $SharedSource = Join-Path $ScriptDir 'shared'
    foreach ($Dir in $TargetDirs) {
        foreach ($Skill in $Bundle.Skills) {
            Link-Or-CopyItem -Source (Join-Path $SourceRoot $Skill) -DestParent $Dir -Name $Skill -UseCopy:$Copy -Overwrite:$Force
        }
        if ($Bundle.InstallShared -and (Test-Path $SharedSource)) {
            Link-Or-CopyItem -Source $SharedSource -DestParent (Split-Path -Parent $Dir) -Name 'shared' -UseCopy:$Copy -Overwrite:$Force
        }
        @("version: 3.0.0-bundle", "skills: $($Bundle.Skills -join ', ')", "installed: $(Get-Date -Format 'o')") |
            Set-Content (Join-Path $Dir '.installed-version') -Encoding UTF8
    }

    $ok = Invoke-Doctor -TargetDirs $TargetDirs -Names $Bundle.Skills -IncludeShared $Bundle.InstallShared -Json:$false
    if (-not $ok) { throw 'doctor 体检未通过' }

    Write-Host 'Done. /ai-design /ai-code /ai-debug /ai-requirement /ai-concise'
    exit 0
} catch {
    Write-Warning "安装失败: $($_.Exception.Message)"
    if ($backupRoot) {
        Invoke-Rollback -BackupRoot $backupRoot -TargetDirs $TargetDirs -Names $AllNames -IncludeShared $Bundle.InstallShared | Out-Null
    }
    exit 1
}
