param(
    [Parameter(Mandatory = $true)]
    [string]$PiHost,

    [string]$PiUser = "pi",

    [string]$RemoteDir = "~/classroom-neurofeedback-pi",

    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

$runtimeRoot = $PSScriptRoot
$tempDir = Join-Path $env:TEMP ("pi-deploy-" + [guid]::NewGuid().ToString("N"))
$bundleRoot = Join-Path $tempDir "bundle"

New-Item -ItemType Directory -Force -Path $bundleRoot | Out-Null

$pathsToCopy = @(
    "requirements.txt",
    "stream_unicorn_lsl.py",
    "unicorn_capi_stream.py",
    "vendor/unicorn_pi_zero_w_lib"
)

foreach ($relativePath in $pathsToCopy) {
    $sourcePath = Join-Path $runtimeRoot $relativePath
    $destinationPath = Join-Path $bundleRoot $relativePath
    $destinationParent = Split-Path -Parent $destinationPath

    if (-not (Test-Path $sourcePath)) {
        throw "Missing required path: $sourcePath"
    }

    New-Item -ItemType Directory -Force -Path $destinationParent | Out-Null
    Copy-Item -Path $sourcePath -Destination $destinationPath -Recurse -Force
}

try {
    Write-Host "Creating remote directory on $PiUser@$PiHost ..."
    ssh "$PiUser@$PiHost" "mkdir -p $RemoteDir"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create remote directory on the Pi."
    }

    Write-Host "Copying Pi runtime bundle to ${PiUser}@${PiHost}:$RemoteDir ..."
    $uploadItems = @(
        (Join-Path $bundleRoot "requirements.txt"),
        (Join-Path $bundleRoot "stream_unicorn_lsl.py"),
        (Join-Path $bundleRoot "unicorn_capi_stream.py"),
        (Join-Path $bundleRoot "vendor")
    )
    scp -r $uploadItems "${PiUser}@${PiHost}:$RemoteDir/"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to copy files to the Pi."
    }

    if (-not $SkipInstall) {
        $installCommand = @'
set -e

if ! find /usr /usr/local -name 'liblsl.so*' 2>/dev/null | grep -q liblsl; then
  arch=$(uname -m)
  tmpdir=$(mktemp -d)
  case "$arch" in
    aarch64)
      liblsl_url="https://github.com/sccn/liblsl/releases/download/v1.17.5/liblsl-1.17.5-jammy_arm64.tar.gz"
      ;;
    armv7l|armv6l|arm*)
      liblsl_url="https://github.com/sccn/liblsl/releases/download/v1.17.5/liblsl-1.17.5-jammy_arm.tar.gz"
      ;;
    *)
      echo "Unsupported Pi architecture for automated liblsl install: $arch" >&2
      exit 1
      ;;
  esac

  curl -L "$liblsl_url" -o "$tmpdir/liblsl.tar.gz"
  mkdir -p "$tmpdir/extract"
  tar -xzf "$tmpdir/liblsl.tar.gz" -C "$tmpdir/extract"
  sudo mkdir -p /usr/local/lib
  find "$tmpdir/extract" -name 'liblsl.so*' -type f -exec sudo cp -f {} /usr/local/lib/ \;
  if [ ! -e /usr/local/lib/liblsl.so ]; then
    first_lib=$(find /usr/local/lib -maxdepth 1 -name 'liblsl.so*' | sort | head -n 1)
    if [ -n "$first_lib" ]; then
      sudo ln -sf "$first_lib" /usr/local/lib/liblsl.so
    fi
  fi
  sudo ldconfig
  rm -rf "$tmpdir"
fi

cd __REMOTE_DIR__
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
'@
        $installCommand = $installCommand.Replace("__REMOTE_DIR__", $RemoteDir)
        Write-Host "Installing Python dependencies on the Pi ..."
        ssh "$PiUser@$PiHost" $installCommand
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install runtime dependencies on the Pi."
        }
    }

    Write-Host ""
    Write-Host "Deploy complete."
    Write-Host "Check Unicorn library:"
    Write-Host "ssh $PiUser@$PiHost `"ls '$RemoteDir/vendor/unicorn_pi_zero_w_lib'`""
    Write-Host "Check liblsl:"
    Write-Host "ssh $PiUser@$PiHost `"find /usr /usr/local -name 'liblsl.so*' 2>/dev/null`""
    Write-Host "Start Unicorn -> LSL:"
    Write-Host "ssh $PiUser@$PiHost `"cd $RemoteDir && . .venv/bin/activate && python3 stream_unicorn_lsl.py --lsl-name Unicorn --single-channel --channel-name 'EEG 1'`""
}
finally {
    if (Test-Path $tempDir) {
        Remove-Item -Path $tempDir -Recurse -Force
    }
}
