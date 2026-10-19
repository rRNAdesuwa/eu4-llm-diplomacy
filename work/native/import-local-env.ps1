function Import-ProjectLocalEnv {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $configPath = Join-Path $ProjectRoot 'local.env'
    if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
        throw "Missing local.env. Copy local.env.example to local.env and configure it."
    }

    foreach ($rawLine in Get-Content -LiteralPath $configPath) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith('#')) { continue }
        $separator = $line.IndexOf('=')
        if ($separator -le 0) { throw "Invalid local.env entry: $rawLine" }
        $name = $line.Substring(0, $separator).Trim()
        $value = $line.Substring($separator + 1).Trim()
        if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
}

function Get-ProjectLocalValue {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $value = [Environment]::GetEnvironmentVariable($Name, 'Process')
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Missing $Name in local.env. Copy local.env.example to local.env and configure it."
    }
    return $value
}
