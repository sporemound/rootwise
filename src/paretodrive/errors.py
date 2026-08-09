"""Typed failures used at scanner trust boundaries."""


class ParetoDriveError(Exception):
    """Base error for expected audit-scanner failures."""


class VolumeIdentityError(ParetoDriveError):
    """The operating system could not establish a volume identity."""


class BoundaryViolation(ParetoDriveError):
    """A requested write violates the source/destination boundary."""


class ScanStateError(ParetoDriveError):
    """A scan-session state transition is invalid."""

