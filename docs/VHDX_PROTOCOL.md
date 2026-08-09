# Disposable exFAT VHDX Protocol

The PowerShell harness in `tools/windows_exfat_vhdx.ps1` prints a plan unless `-Execute` is supplied.
Execution requires administrator privileges because Windows disk-image and formatting cmdlets do.
Administrator access is never requested for ordinary development or scanner tests.

The harness must reject:

- an existing VHDX path;
- a path outside the explicitly supplied working directory;
- sizes outside 256 MiB through 4 GiB;
- any disk not returned directly by mounting the newly created VHDX;
- a disk that is not RAW immediately before initialization;
- a volume whose post-format filesystem is not exFAT;
- an execution request without a separate explicit confirmation string.

Formatting is confined to the new VHDX disk number returned by `Mount-VHD -PassThru | Get-Disk`.
The script never enumerates candidate physical disks and never accepts a disk number from the user.

The scanner is invoked only after the VHDX is populated, manifested, and set read-only. VHDX
creation/population and removal are test tooling operations, not scanner runtime capabilities.
