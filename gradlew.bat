@echo off
setlocal enabledelayedexpansion
rem F-Droid compliant script-only Gradle launcher (no binary gradle-wrapper.jar checked in).

set "GRADLE_VERSION=8.8"
if defined GRADLE_USER_HOME (
    set "USER_GRADLE_HOME=%GRADLE_USER_HOME%"
) else (
    set "USER_GRADLE_HOME=%USERPROFILE%\.gradle"
)

for /d %%D in ("%USER_GRADLE_HOME%\wrapper\dists\gradle-%GRADLE_VERSION%-bin\*") do (
    if exist "%%D\gradle-%GRADLE_VERSION%\bin\gradle.bat" (
        call "%%D\gradle-%GRADLE_VERSION%\bin\gradle.bat" %*
        exit /b !ERRORLEVEL!
    )
)

where gradle >nul 2>nul
if %ERRORLEVEL% equ 0 (
    call gradle %*
    exit /b !ERRORLEVEL!
)

echo Error: Gradle %GRADLE_VERSION% not found in %USER_GRADLE_HOME%\wrapper\dists or PATH. 1>&2
exit /b 1
