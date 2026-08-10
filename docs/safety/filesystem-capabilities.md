# Filesystem Capabilities

## Portable baseline

Audit.1 uses directory enumeration and non-following metadata calls. It records logical bytes,
timestamps, type, depth, and available attributes. It makes no assumptions about stable inode/file
IDs, ACLs, hardlinks, sparse allocation, alternate data streams, or journals.

## Windows

Volume identity is the volume GUID path returned by `GetVolumeNameForVolumeMountPointW`, after the
mount root is resolved with `GetVolumePathNameW`. Filesystem type comes from
`GetVolumeInformationW`. Before enumeration, the scanner opens and retains handles for the source
root and every queued path component with `FILE_FLAG_OPEN_REPARSE_POINT`, rejects reparse points,
verifies the final handle's volume-GUID path, and denies delete sharing while `os.scandir` runs.
An API failure is a hard
boundary failure; drive-letter or string-prefix comparison is not a fallback.

## POSIX

Volume identity combines the device number from `stat` with the resolved mount point. Filesystem
type is best-effort descriptive data from `/proc/mounts`; inability to resolve the identity itself
is fatal. Traversal opens each component descriptor-relative with `O_NOFOLLOW`, verifies `st_dev`,
and enumerates the final directory descriptor. Literal POSIX backslashes remain filename data.
This is not an exFAT acceptance claim.

## exFAT

Missing NTFS features are recorded as unavailable, never negative evidence. No USN journal, MFT,
ACL, alternate-stream, or stable NTFS identifier assumption is permitted. Disposable Windows
exFAT VHDX testing remains a mandatory uncompleted release gate.
