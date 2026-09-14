@echo off
setlocal enabledelayedexpansion

:: Script to build multi-arch Docker image and push to Docker Hub
:: Requires Docker CLI with buildx and a Docker Hub access token stored in dockerhub_credentials.txt

set "SCRIPT_DIR=%~dp0"
set "IMAGE_NAME=migruiz/pv-solar-api:latest"
set "DOCKERFILE_DIR=%SCRIPT_DIR%"
set "CREDENTIALS_FILE=%SCRIPT_DIR%dockerhub_credentials.txt"

if not exist "%CREDENTIALS_FILE%" (
    echo [ERROR] Credentials file not found at "%CREDENTIALS_FILE%".
    echo Create the file with the format: username:token
    exit /b 1
)

for /f "usebackq tokens=1,2 delims=:" %%a in ("%CREDENTIALS_FILE%") do (
    set "DOCKERHUB_USERNAME=%%a"
    set "DOCKERHUB_TOKEN=%%b"
    goto :after_credentials
)

:after_credentials
if not defined DOCKERHUB_USERNAME (
    echo [ERROR] Docker Hub username missing in credentials file.
    exit /b 1
)

if not defined DOCKERHUB_TOKEN (
    echo [ERROR] Docker Hub token missing in credentials file.
    exit /b 1
)

where docker >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker CLI not found in PATH.
    exit /b 1
)

echo [INFO] Authenticating to Docker Hub...
:: No space before the pipe: cmd would send it as part of the token
echo %DOCKERHUB_TOKEN%| docker login --username %DOCKERHUB_USERNAME% --password-stdin
if errorlevel 1 (
    echo [ERROR] Docker login failed.
    exit /b 1
)

echo [INFO] Building multi-arch image %IMAGE_NAME% (amd64 + arm64)...
docker buildx build --platform linux/amd64,linux/arm64 --file "%DOCKERFILE_DIR%Dockerfile" --tag %IMAGE_NAME% --push %DOCKERFILE_DIR%
set "BUILD_STATUS=%ERRORLEVEL%"

docker logout >nul 2>&1

if not "%BUILD_STATUS%"=="0" (
    echo [ERROR] Docker buildx build/push failed.
    exit /b %BUILD_STATUS%
)

echo [INFO] Multi-arch image %IMAGE_NAME% pushed successfully.
exit /b 0
