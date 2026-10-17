package org.rootwise.android.core.model

/**
 * Structured exceptions matching upstream `src/rootwise/errors.py`.
 */
open class RootwiseException(message: String, cause: Throwable? = null) : RuntimeException(message, cause)

open class BoundaryViolationException(message: String, cause: Throwable? = null) : RootwiseException(message, cause)

class VolumeIdentityException(message: String, cause: Throwable? = null) : BoundaryViolationException(message, cause)

class ScanStateException(message: String, cause: Throwable? = null) : RootwiseException(message, cause)

class ResourceLimitExceededException(message: String, cause: Throwable? = null) : RootwiseException(message, cause)

class VolumeUnmountedException(
    val relativePath: String,
    message: String,
    cause: Throwable? = null
) : RootwiseException(message, cause)
