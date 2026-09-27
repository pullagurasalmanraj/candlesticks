[CmdletBinding()]
param(
    [ValidateSet("local", "azure")]
    [string]$Target = "local",

    [string]$AzureBaseUrl = "https://candlesticks-india.southafricanorth.cloudapp.azure.com",

    [switch]$Restart
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envPath = Join-Path $repoRoot ".env"

if (-not (Test-Path -LiteralPath $envPath)) {
    throw "Missing $envPath. Create it with the required Upstox credentials before switching environments."
}

function Set-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Key,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value
    )

    $lines = @(Get-Content -LiteralPath $Path)
    $updated = New-Object System.Collections.Generic.List[string]
    $found = $false

    foreach ($line in $lines) {
        if ($line -match ("^" + [regex]::Escape($Key) + "=")) {
            $updated.Add("$Key=$Value")
            $found = $true
        }
        else {
            $updated.Add($line)
        }
    }

    if (-not $found) {
        $updated.Add("$Key=$Value")
    }

    $utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($Path, $updated, $utf8WithoutBom)
}

$azureBase = $AzureBaseUrl.TrimEnd("/")
$redirectUri = if ($Target -eq "local") {
    "http://localhost/"
}
else {
    "$azureBase/"
}

# Compose services communicate with Redis by service name. Host tools such as
# RedisInsight continue to use 127.0.0.1:6380.
Set-DotEnvValue -Path $envPath -Key "UPSTOX_REDIRECT_URI" -Value $redirectUri
Set-DotEnvValue -Path $envPath -Key "DOCKER_REDIS_URL" -Value "redis://:linux123@redis:6379/0"
Set-DotEnvValue -Path $envPath -Key "REDIS_URL" -Value "redis://:linux123@127.0.0.1:6380/0"
Set-DotEnvValue -Path $envPath -Key "VITE_WS_URL" -Value ""

Write-Host "Environment prepared for: $Target"
Write-Host "Upstox redirect URI: $redirectUri"

if ($Restart) {
    Push-Location $repoRoot
    try {
        docker compose up -d --build --force-recreate backend wsserver frontend nginx
        if ($LASTEXITCODE -ne 0) {
            throw "Docker Compose failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "Configuration only. Add -Restart to rebuild and recreate the application services."
}

if ($Target -eq "local") {
    Write-Host "Next: set the Upstox developer-console redirect URI to http://localhost/"
    Write-Host "Then open http://localhost/auth/login"
    Write-Host "RedisInsight: 127.0.0.1:6380, database 0 (no SSH tunnel required)."
}
else {
    Write-Host "Next: ensure the Upstox developer-console redirect URI exactly matches $redirectUri"
}
