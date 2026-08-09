from __future__ import annotations

import os
import sqlite3
import sys


def main() -> None:
    database, session = sys.argv[1], sys.argv[2]
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("BEGIN IMMEDIATE")
    connection.execute(
        "INSERT INTO scan_errors(scan_session_id,relative_path,operation,error_type,error_code,message) "
        "VALUES(?,?,?,?,?,?)",
        (session, "", "crash_probe", "SyntheticCrash", None, "must roll back"),
    )
    print("CRASH_TRANSACTION_READY", flush=True)
    os._exit(17)


if __name__ == "__main__":
    main()

