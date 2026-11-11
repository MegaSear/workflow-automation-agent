
param(
    [Parameter(Mandatory = $true)]
    [string]$ImageTag
)

$ErrorActionPreference = "Stop"

$env:IMAGE_TAG = $ImageTag

Write-Host "Pulling images with tag: $ImageTag"
docker compose -f docker-compose.prod.yml pull

if ($LASTEXITCODE -ne 0) {
    throw "Docker image pull failed"
}

Write-Host "Starting production stack"
docker compose -f docker-compose.prod.yml up -d

if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose deployment failed"
}

Write-Host "Deployment completed"
docker compose -f docker-compose.prod.yml ps
