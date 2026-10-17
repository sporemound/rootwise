#!/usr/bin/env sh
# F-Droid compliant script-only Gradle launcher (no binary gradle-wrapper.jar checked in).
set -eu

GRADLE_VERSION="8.8"
USER_GRADLE_HOME="${GRADLE_USER_HOME:-$HOME/.gradle}"

if command -v gradle >/dev/null 2>&1; then
    exec gradle "$@"
fi

for candidate in "$USER_GRADLE_HOME"/wrapper/dists/gradle-"$GRADLE_VERSION"-bin/*/gradle-"$GRADLE_VERSION"/bin/gradle; do
    if [ -x "$candidate" ]; then
        exec "$candidate" "$@"
    fi
done

echo "Error: Gradle $GRADLE_VERSION not found on PATH or in $USER_GRADLE_HOME/wrapper/dists." >&2
exit 1
