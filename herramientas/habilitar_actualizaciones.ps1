param($Carpeta)

# Se auto-eleva a administrador si hace falta, pasando la carpeta como
# argumento de proceso (nunca como texto embebido), asi cualquier enie o
# tilde en la ruta ("dmunoz", etc.) llega intacta sin depender de que
# cmd.exe adivine el codepage.
$esAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)

if (-not $esAdmin) {
    Start-Process powershell -Verb RunAs -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", "$PSCommandPath", "-Carpeta", "$Carpeta"
    )
    exit
}

Add-Type -AssemblyName System.Windows.Forms

try {
    Add-MpPreference -ExclusionPath $Carpeta -ErrorAction Stop
    [System.Windows.Forms.MessageBox]::Show(
        "Listo. Se agrego la excepcion de seguridad para Bitacora Diaria.`n`n" +
        "Ahora abre la app y dale a Actualizar si te lo ofrece.",
        "Bitacora Diaria",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    ) | Out-Null
} catch {
    [System.Windows.Forms.MessageBox]::Show(
        "No se pudo agregar la excepcion: $($_.Exception.Message)",
        "Bitacora Diaria",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
}
