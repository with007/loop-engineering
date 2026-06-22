param([string]$url)

$file = $url -replace '^taskrunner://open/\?file=', ''
$file = [System.Uri]::UnescapeDataString($file)

if (Test-Path $file) {
    $winPath = $file -replace '/', '\'
    Start-Process explorer -ArgumentList "/select,$winPath"
}
