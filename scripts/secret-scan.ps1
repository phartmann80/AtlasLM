param(
  [switch]$History
)

$ErrorActionPreference = "Stop"

function Test-AllowedPath {
  param([string]$Path)
  $Path -notmatch '(^|/)(\.env|\.env\.|node_modules|\.next|dist|__pycache__|screenshots)/' -and
  $Path -notmatch '(package-lock\.json|tsconfig\.tsbuildinfo)$'
}

$patterns = @(
  'AKIA[0-9A-Z]{16}',
  '-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----',
  'gh[pousr]_[A-Za-z0-9_]{20,}',
  'sk-[A-Za-z0-9]{20,}',
  'Bearer\s+[A-Za-z0-9._-]{40,}',
  'postgres(ql)?://[^\s"'']+:[^\s"'']+@',
  'eyJhbGciOiJ[A-Za-z0-9_-]{20,}'
)

$hits = @()
$tracked = git ls-files | Where-Object { Test-AllowedPath $_ }
foreach ($file in $tracked) {
  if (Test-Path -LiteralPath $file) {
    $content = Get-Content -LiteralPath $file -Raw -ErrorAction SilentlyContinue
    foreach ($pattern in $patterns) {
      if ($content -match $pattern) {
        $hits += $file
        break
      }
    }
  }
}

$historyHits = @()
if ($History) {
  $commits = git rev-list --all
  $commitBatches = @()
  for ($i = 0; $i -lt $commits.Count; $i += 20) {
    $end = [Math]::Min($i + 19, $commits.Count - 1)
    $commitBatches += ,($commits[$i..$end])
  }
  foreach ($commitBatch in $commitBatches) {
    foreach ($pattern in $patterns) {
      $grepArgs = @("grep", "-I", "-l", "-E", "-e", $pattern) + $commitBatch + @("--", ".")
      $matches = & git @grepArgs 2>$null
      foreach ($match in $matches) {
        $path = ($match -replace '^[^:]+:', '')
        if (Test-AllowedPath $path) {
          $commit = ($match -replace ':.*$', '')
          $historyHits += ("{0} {1}" -f $commit.Substring(0, 12), $path)
        }
      }
    }
  }
}

$hits = $hits | Sort-Object -Unique
$historyHits = $historyHits | Sort-Object -Unique
if ($hits.Count -gt 0 -or $historyHits.Count -gt 0) {
  $hits | ForEach-Object { Write-Output "secret-scan: REVIEW $_" }
  $historyHits | ForEach-Object { Write-Output "secret-scan: REVIEW history $_" }
  exit 1
}
Write-Output "secret-scan: PASS"
