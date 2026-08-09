# Security Review

Two read-only reviews were performed during development. The pre-change repository was empty and
had no findings. The post-implementation review found six boundary issues. Source traversal
substitution, same-volume/different-root resume mixing, and POSIX backslash reinterpretation were
fixed and independently revalidated against the revised source.

Exclusive output creation now rejects pre-existing final links and files. SQLite revalidates its
opened target before application writes and pre-authorizes its durable rollback-journal path.
Canonical export validates application identity, integrity, foreign keys, frontier exhaustion, and
row/error counts within one transaction.

## Residual assumptions

The approved destination directory is an operator-controlled trust boundary. A same-privilege actor
who can concurrently rename its intermediate path components or coherently rewrite the inventory
database is outside the audit.2 attacker model; such an actor can redirect or forge local state and
can always deny service. These races remain relevant if that assumption changes, in which case
handle-relative output creation and an authenticated immutable snapshot become required.

SQLite uses `DELETE` rollback journaling with `FULL` synchronization. This restores durable recovery
semantics after an early experiment with an in-memory journal; crash/power-loss recovery is designed
but has not been acceptance tested. exFAT, OS-enforced read-only, independent build, and hostile
destination-directory tests remain unperformed.
