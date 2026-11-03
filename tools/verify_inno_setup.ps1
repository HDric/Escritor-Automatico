[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$CompilerPath,

    [Parameter(Mandatory = $true)]
    [string]$RequiredVersion
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $CompilerPath -PathType Leaf)) {
    throw "No se encontró el compilador indicado: $CompilerPath"
}

$resolvedCompiler = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $CompilerPath).Path)
$uninstallKeyPath = 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1'
$verified = $false
$detected = @()

# Inno Setup is a 32-bit application even on 64-bit Windows. Its standard
# uninstall record is normally written to Registry32; Registry64 is checked
# as a compatibility fallback for custom installations.
foreach ($viewName in @('Registry32', 'Registry64')) {
    $baseKey = $null
    $uninstallKey = $null
    try {
        $view = [System.Enum]::Parse([Microsoft.Win32.RegistryView], $viewName)
        $baseKey = [Microsoft.Win32.RegistryKey]::OpenBaseKey(
            [Microsoft.Win32.RegistryHive]::LocalMachine,
            $view
        )
        $uninstallKey = $baseKey.OpenSubKey($uninstallKeyPath)
        if ($null -eq $uninstallKey) {
            continue
        }

        $displayVersion = [string]$uninstallKey.GetValue('DisplayVersion', '')
        $installLocation = [string]$uninstallKey.GetValue('InstallLocation', '')
        if (-not [string]::IsNullOrWhiteSpace($displayVersion)) {
            $detected += "$viewName=$displayVersion"
        }

        if ($displayVersion -ne $RequiredVersion) {
            continue
        }
        if ([string]::IsNullOrWhiteSpace($installLocation)) {
            continue
        }

        $registeredCompiler = [System.IO.Path]::GetFullPath(
            (Join-Path $installLocation 'ISCC.exe')
        )
        if (-not [string]::Equals(
            $registeredCompiler,
            $resolvedCompiler,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            continue
        }

        $verified = $true
        break
    }
    finally {
        if ($null -ne $uninstallKey) { $uninstallKey.Dispose() }
        if ($null -ne $baseKey) { $baseKey.Dispose() }
    }
}

if (-not $verified) {
    $detectedText = if ($detected.Count -gt 0) { $detected -join ', ' } else { 'no se encontró la entrada de desinstalación' }
    throw "No se pudo confirmar Inno Setup $RequiredVersion para el compilador '$resolvedCompiler'. Registro detectado: $detectedText."
}

Write-Host "Inno Setup validado: versión $RequiredVersion"
Write-Host "Compilador: $resolvedCompiler"
Write-Host 'La versión se comprobó mediante DisplayVersion e InstallLocation del registro de Windows.'
