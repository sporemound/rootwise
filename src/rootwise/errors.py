"""Typed failures used at scanner trust boundaries."""


class RootwiseError(Exception):
    """Base error for expected audit-scanner failures."""


class VolumeIdentityError(RootwiseError):
    """The operating system could not establish a volume identity."""


class BoundaryViolation(RootwiseError):
    """A requested write violates the source/destination boundary."""


class ScanStateError(RootwiseError):
    """A scan-session state transition is invalid."""


class ResourceLimitExceeded(RootwiseError):
    """A configured resource boundary requested a clean scanner stop."""
