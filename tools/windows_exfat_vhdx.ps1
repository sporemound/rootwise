[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$WorkDirectory,

    [Parameter(Mandatory = $true)]
    [string]$VhdxPath,

    [ValidateSet("Plan", "Create", "SetReadOnly", "Detach")]
    [string]$Action = "Plan",

    [ValidateRange(256, 4096)]
    [int]$SizeMiB = 512,

    [string]$Confirmation = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Resolve-ExistingDirectory {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)
    if (-not (Test-Path -LiteralPath $LiteralPath -PathType Container)) {
        throw "Directory does not exist: $LiteralPath"
    }
    return (Resolve-Path -LiteralPath $LiteralPath).Path
}

function Assert-Administrator {
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $Principal = [Security.Principal.WindowsPrincipal]::new($Identity)
    if (-not $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "This VHDX test action requires an elevated PowerShell session."
    }
}

function Test-HyperVBackend {
    return ($null -ne (Get-Command "Get-VHD" -ErrorAction SilentlyContinue) -and
        $null -ne (Get-Command "New-VHD" -ErrorAction SilentlyContinue) -and
        $null -ne (Get-Command "Mount-VHD" -ErrorAction SilentlyContinue) -and
        $null -ne (Get-Command "Dismount-VHD" -ErrorAction SilentlyContinue))
}

function Assert-StorageBackend {
    foreach ($Command in @("Get-DiskImage", "Mount-DiskImage", "Dismount-DiskImage", "diskpart.exe")) {
        if ($null -eq (Get-Command $Command -ErrorAction SilentlyContinue)) {
            throw "Required Windows Home VHDX command is unavailable: $Command"
        }
    }
}

function Invoke-DiskPartCreate {
    param(
        [Parameter(Mandatory = $true)][string]$LiteralPath,
        [Parameter(Mandatory = $true)][int]$MaximumMiB
    )
    if (Test-Path -LiteralPath $LiteralPath) {
        throw "DiskPart creation refuses an existing path: $LiteralPath"
    }
    $DiskPart = (Get-Command "diskpart.exe" -ErrorAction Stop).Source
    $StartInfo = [Diagnostics.ProcessStartInfo]::new()
    $StartInfo.FileName = $DiskPart
    $StartInfo.UseShellExecute = $false
    $StartInfo.RedirectStandardInput = $true
    $StartInfo.RedirectStandardOutput = $true
    $StartInfo.RedirectStandardError = $true
    $Process = [Diagnostics.Process]::new()
    $Process.StartInfo = $StartInfo
    if (-not $Process.Start()) { throw "Unable to start DiskPart." }
    $Process.StandardInput.WriteLine("create vdisk file=`"$LiteralPath`" maximum=$MaximumMiB type=expandable")
    $Process.StandardInput.WriteLine("exit")
    $Process.StandardInput.Close()
    $Output = $Process.StandardOutput.ReadToEnd()
    $ErrorOutput = $Process.StandardError.ReadToEnd()
    $Process.WaitForExit()
    if ($Process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $LiteralPath -PathType Leaf)) {
        throw "DiskPart did not create the requested VHDX (exit $($Process.ExitCode)). stdout: $Output stderr: $ErrorOutput"
    }
}

function Get-VhdDiskStrict {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)
    if (Test-HyperVBackend) {
        $Vhd = Get-VHD -Path $LiteralPath
        if (-not $Vhd.Attached) {
            $Vhd = Mount-VHD -Path $LiteralPath -PassThru
        }
        $Disk = $Vhd | Get-Disk
    }
    else {
        Assert-StorageBackend
        $Image = Get-DiskImage -ImagePath $LiteralPath -ErrorAction Stop
        if (-not $Image.Attached) {
            $Image = Mount-DiskImage -ImagePath $LiteralPath -PassThru
        }
        $Disk = $Image | Get-Disk
    }
    if ($null -eq $Disk -or $Disk.IsBoot -or $Disk.IsSystem) {
        throw "The named VHDX did not resolve to one non-system virtual disk."
    }
    return $Disk
}

$WorkRoot = Resolve-ExistingDirectory -LiteralPath $WorkDirectory
$VhdParentInput = Split-Path -Parent $VhdxPath
$VhdName = Split-Path -Leaf $VhdxPath
$VhdParent = Resolve-ExistingDirectory -LiteralPath $VhdParentInput
$ResolvedVhdx = [IO.Path]::GetFullPath((Join-Path $VhdParent $VhdName))
$RootPrefix = $WorkRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if (-not $ResolvedVhdx.StartsWith($RootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "VHDX path must remain inside the explicit work directory."
}
if ([IO.Path]::GetExtension($ResolvedVhdx) -ine ".vhdx") {
    throw "VHDX path must use the .vhdx extension."
}

$Exists = Test-Path -LiteralPath $ResolvedVhdx -PathType Leaf
$Backend = if (Test-HyperVBackend) { "hyper_v" } else { "storage_diskpart" }
$Plan = [ordered]@{
    action = $Action
    work_directory = $WorkRoot
    vhdx_path = $ResolvedVhdx
    vhdx_exists = $Exists
    size_mib = $SizeMiB
    filesystem = "exFAT"
    physical_disk_selection = $false
    backend = $Backend
    requires_administrator = ($Action -ne "Plan")
    confirmation_required = "CREATE-DISPOSABLE-EXFAT-VHDX"
}

if ($Action -eq "Plan") {
    $Plan | ConvertTo-Json -Depth 3
    exit 0
}

if ($Confirmation -cne "CREATE-DISPOSABLE-EXFAT-VHDX") {
    throw "Execution requires -Confirmation CREATE-DISPOSABLE-EXFAT-VHDX"
}
Assert-Administrator
if ($Backend -eq "storage_diskpart") {
    Assert-StorageBackend
}

if ($Action -eq "Create") {
    if ($Exists) { throw "Create refuses an existing path: $ResolvedVhdx" }
    $CreateCommands = @("Initialize-Disk", "New-Partition", "Format-Volume")
    if ($Backend -eq "hyper_v") { $CreateCommands += "New-VHD" }
    foreach ($Command in $CreateCommands) {
        if ($null -eq (Get-Command $Command -ErrorAction SilentlyContinue)) {
            throw "Required PowerShell command is unavailable: $Command"
        }
    }
    if ($Backend -eq "hyper_v") {
        $Vhd = New-VHD -Path $ResolvedVhdx -Dynamic -SizeBytes ($SizeMiB * 1MB)
        $Disk = Mount-VHD -Path $Vhd.Path -PassThru | Get-Disk
    }
    else {
        Invoke-DiskPartCreate -LiteralPath $ResolvedVhdx -MaximumMiB $SizeMiB
        $Disk = Mount-DiskImage -ImagePath $ResolvedVhdx -PassThru | Get-Disk
    }
    if ($null -eq $Disk -or $Disk.IsBoot -or $Disk.IsSystem -or $Disk.PartitionStyle -ne "RAW") {
        throw "New VHDX did not resolve to one safe RAW non-system disk."
    }
    $Initialized = Initialize-Disk -Number $Disk.Number -PartitionStyle GPT -PassThru
    $Partition = $Initialized | New-Partition -UseMaximumSize -AssignDriveLetter
    $Volume = $Partition | Format-Volume -FileSystem exFAT -NewFileSystemLabel "ROOTWISE_TEST" -Confirm:$false
    if ($Volume.FileSystem -ine "exFAT") { throw "Post-format filesystem validation failed." }
    [ordered]@{
        status = "CREATED"
        vhdx_path = $ResolvedVhdx
        disk_number = $Disk.Number
        drive_letter = $Volume.DriveLetter
        filesystem = $Volume.FileSystem
        backend = $Backend
        next_action = "Populate the deterministic corpus, then run SetReadOnly."
    } | ConvertTo-Json -Depth 3
    exit 0
}

if (-not $Exists) { throw "$Action requires an existing VHDX: $ResolvedVhdx" }
if ($Action -eq "SetReadOnly") {
    $Disk = Get-VhdDiskStrict -LiteralPath $ResolvedVhdx
    Set-Disk -Number $Disk.Number -IsReadOnly $true
    $Verified = Get-Disk -Number $Disk.Number
    if (-not $Verified.IsReadOnly) { throw "Read-only enforcement validation failed." }
    [ordered]@{ status = "READ_ONLY"; vhdx_path = $ResolvedVhdx; disk_number = $Disk.Number } |
        ConvertTo-Json -Depth 3
    exit 0
}

if ($Action -eq "Detach") {
    if ($Backend -eq "hyper_v") {
        Dismount-VHD -Path $ResolvedVhdx
    }
    else {
        Dismount-DiskImage -ImagePath $ResolvedVhdx
    }
    [ordered]@{ status = "DETACHED"; vhdx_path = $ResolvedVhdx } | ConvertTo-Json -Depth 3
    exit 0
}

throw "Unsupported action: $Action"
