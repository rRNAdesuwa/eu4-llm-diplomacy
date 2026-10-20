# Pure Windows command-line token handling. This file never enumerates, starts,
# stops, or reads a game process. Original raw argument tokens stay in memory.
function Get-TestRestartArgumentTokens {
    param([AllowEmptyString()][string]$Arguments = '')
    if ($Arguments.IndexOfAny([char[]]"`r`n`0") -ge 0) { throw 'Invalid command-line framing.' }
    $tokens = [Collections.Generic.List[object]]::new()
    $offset = 0
    while ($offset -lt $Arguments.Length) {
        while ($offset -lt $Arguments.Length -and ($Arguments[$offset] -eq ' ' -or $Arguments[$offset] -eq "`t")) { $offset++ }
        if ($offset -ge $Arguments.Length) { break }
        $start = $offset
        $quoted = $false
        $decoded = [Text.StringBuilder]::new()
        while ($offset -lt $Arguments.Length) {
            $character = $Arguments[$offset]
            if (-not $quoted -and ($character -eq ' ' -or $character -eq "`t")) { break }
            if ($character -eq '\') {
                $slashes = 0
                while ($offset -lt $Arguments.Length -and $Arguments[$offset] -eq '\') { $slashes++; $offset++ }
                if ($offset -lt $Arguments.Length -and $Arguments[$offset] -eq '"') {
                    [void]$decoded.Append(('\' * [int][Math]::Floor($slashes / 2)))
                    if ($slashes % 2) { [void]$decoded.Append('"'); $offset++; continue }
                    # Even backslashes leave this quote to the normal quote rule.
                    $character = '"'
                } else { [void]$decoded.Append(('\' * $slashes)); continue }
            }
            if ($character -eq '"') {
                if ($quoted -and $offset + 1 -lt $Arguments.Length -and $Arguments[$offset + 1] -eq '"') {
                    [void]$decoded.Append('"'); $offset += 2; continue
                }
                $quoted = -not $quoted
                $offset++
                continue
            }
            [void]$decoded.Append($character)
            $offset++
        }
        if ($quoted) { throw 'Unbalanced launch-argument quotes; no arguments were changed.' }
        $tokens.Add([pscustomobject]@{ Raw = $Arguments.Substring($start, $offset - $start); Value = $decoded.ToString() })
    }
    return $tokens.ToArray()
}

function ConvertTo-TestRestartArguments {
    param([AllowEmptyString()][string]$Arguments = '',
          [Parameter(Mandatory = $true)][ValidatePattern('^llm_[A-Za-z0-9_-]+\.eu4$')][string]$SaveName)
    $tokens = @(Get-TestRestartArgumentTokens -Arguments $Arguments)
    $kept = [Collections.Generic.List[string]]::new()
    for ($index = 0; $index -lt $tokens.Count; $index++) {
        $value = $tokens[$index].Value
        if ($value -match '^(?i)--?continue=.*$' -or $value -match '^(?i)--?continuelastsave$') { continue }
        if ($value -match '^(?i)--?continue$') {
            if ($index + 1 -ge $tokens.Count -or $tokens[$index + 1].Value -match '^-') {
                throw 'An existing continue option has no unambiguous save argument.'
            }
            $index++
            continue
        }
        $kept.Add($tokens[$index].Raw)
    }
    $kept.Add('-continue=' + $SaveName)
    return [string]::Join(' ', $kept)
}
