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

function Get-VhdDiskStrict {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)
    $Vhd = Get-VHD -Path $LiteralPath
    if (-not $Vhd.Attached) {
        $Vhd = Mount-VHD -Path $LiteralPath -PassThru
    }
    $Disk = $Vhd | Get-Disk
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
$Plan = [ordered]@{
    action = $Action
    work_directory = $WorkRoot
    vhdx_path = $ResolvedVhdx
    vhdx_exists = $Exists
    size_mib = $SizeMiB
    filesystem = "exFAT"
    physical_disk_selection = $false
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
foreach ($Command in @("Get-VHD", "Mount-VHD", "Dismount-VHD")) {
    if ($null -eq (Get-Command $Command -ErrorAction SilentlyContinue)) {
        throw "Required Hyper-V PowerShell command is unavailable: $Command"
    }
}

if ($Action -eq "Create") {
    if ($Exists) { throw "Create refuses an existing path: $ResolvedVhdx" }
    foreach ($Command in @("New-VHD", "Initialize-Disk", "New-Partition", "Format-Volume")) {
        if ($null -eq (Get-Command $Command -ErrorAction SilentlyContinue)) {
            throw "Required PowerShell command is unavailable: $Command"
        }
    }
    $Vhd = New-VHD -Path $ResolvedVhdx -Dynamic -SizeBytes ($SizeMiB * 1MB)
    $Disk = Mount-VHD -Path $Vhd.Path -PassThru | Get-Disk
    if ($null -eq $Disk -or $Disk.IsBoot -or $Disk.IsSystem -or $Disk.PartitionStyle -ne "RAW") {
        throw "New VHDX did not resolve to one safe RAW non-system disk."
    }
    $Initialized = Initialize-Disk -Number $Disk.Number -PartitionStyle GPT -PassThru
    $Partition = $Initialized | New-Partition -UseMaximumSize -AssignDriveLetter
    $Volume = $Partition | Format-Volume -FileSystem exFAT -NewFileSystemLabel "PARETODRIVE_TEST" -Confirm:$false
    if ($Volume.FileSystem -ine "exFAT") { throw "Post-format filesystem validation failed." }
    [ordered]@{
        status = "CREATED"
        vhdx_path = $ResolvedVhdx
        disk_number = $Disk.Number
        drive_letter = $Volume.DriveLetter
        filesystem = $Volume.FileSystem
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
    Dismount-VHD -Path $ResolvedVhdx
    [ordered]@{ status = "DETACHED"; vhdx_path = $ResolvedVhdx } | ConvertTo-Json -Depth 3
    exit 0
}

throw "Unsupported action: $Action"
