# Squad Polyglot Benchmark Runner
# Runs copilot --yolo --agent squad on each exercise, tests, retries on failure
param(
    [string]$Language = "python",
    [string]$BaseDir = $PSScriptRoot,
    [switch]$NoAgent,       # Skip --agent squad for faster runs
    [int]$MaxExercises = 0, # 0 = all
    [string]$StartFrom = "" # Resume from this exercise name
)

$ErrorActionPreference = "Continue"
$benchmarkDir = Join-Path $BaseDir "benchmark-$Language"
$resultsDir = Join-Path $BaseDir "results" $Language
New-Item -ItemType Directory -Force -Path $resultsDir | Out-Null

# For C++, use subst to avoid Windows path length issues with MSVC
if ($Language -eq "cpp") {
    subst B: $BaseDir 2>$null
    $benchmarkDir = "B:\benchmark-$Language"
}

$timestamp = Get-Date -Format "yyyy-MM-dd-HH-mm-ss"
$logFile = Join-Path $resultsDir "run-$timestamp.log"

function Write-Log($msg) {
    $ts = Get-Date -Format "HH:mm:ss"
    $line = "[$ts] $msg"
    Write-Host $line
    Add-Content -Path $logFile -Value $line
}

function Get-TestCommand($lang, $exerciseDir) {
    switch ($lang) {
        "python" { return "python -m pytest *_test.py -x -q 2>&1" }
        "go"     { return "go test ./... 2>&1" }
        "javascript" { return "npx jest --no-coverage 2>&1" }
        "java"   { return "gradle test 2>&1" }
        "rust"   { return "cargo test 2>&1" }
        "cpp"    { return "cmake -B build . 2>&1; cmake --build build 2>&1; cd build; ctest 2>&1" }
    }
}

function Enable-AllTests($lang, $exerciseDir) {
    if ($lang -eq "javascript") {
        Get-ChildItem $exerciseDir -Filter "*.spec.js" | ForEach-Object {
            $content = Get-Content $_.FullName -Raw
            $content = $content -replace '\bxtest\(', 'test('
            $content = $content -replace '\bxit\(', 'it('
            Set-Content $_.FullName $content
        }
    }
    if ($lang -eq "python") {
        Get-ChildItem $exerciseDir -Filter "*_test.py" | ForEach-Object {
            $content = Get-Content $_.FullName -Raw
            $content = $content -replace '@unittest\.skip\([^)]*\)', ''
            $content = $content -replace 'unittest\.skip\([^)]*\)', ''
            Set-Content $_.FullName $content
        }
    }
    if ($lang -eq "java") {
        Get-ChildItem $exerciseDir -Recurse -Filter "*.java" | Where-Object { $_.Name -match "Test" } | ForEach-Object {
            $content = Get-Content $_.FullName -Raw
            $content = $content -replace '@Disabled\([^)]*\)\s*\r?\n', ''
            $content = $content -replace 'import org\.junit\.jupiter\.api\.Disabled;\s*\r?\n', ''
            Set-Content $_.FullName $content
        }
    }
    if ($lang -eq "rust") {
        Get-ChildItem $exerciseDir -Filter "*.rs" -Recurse | ForEach-Object {
            $content = Get-Content $_.FullName -Raw
            $content = $content -replace '#\[ignore\]', ''
            Set-Content $_.FullName $content
        }
    }
}

function Run-Tests($lang, $exerciseDir) {
    Push-Location $exerciseDir
    try {
        switch ($lang) {
            "python" {
                $testFile = (Get-ChildItem -Filter "*_test.py" | Select-Object -First 1).Name
                if ($testFile) {
                    $output = python -m pytest $testFile -x -q 2>&1 | Out-String
                } else {
                    $output = "No test file found"
                }
            }
            "go" {
                $output = go test ./... 2>&1 | Out-String
            }
            "javascript" {
                if (-not (Test-Path "node_modules")) {
                    npm install --silent 2>&1 | Out-Null
                }
                $output = npx jest --no-coverage 2>&1 | Out-String
            }
            "java" {
                $output = .\gradlew.bat test 2>&1 | Out-String
            }
            "rust" {
                $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "User") + ";" + $env:PATH
                $output = cargo test 2>&1 | Out-String
            }
            "cpp" {
                $vsBase = "C:\Program Files\Microsoft Visual Studio\2022\Enterprise"
                $vsCmake = "$vsBase\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
                $vcvars = "$vsBase\VC\Auxiliary\Build\vcvars64.bat"
                Remove-Item -Recurse -Force build -ErrorAction SilentlyContinue
                $cwd = (Get-Location).Path
                $output = & $env:ComSpec /c "call `"$vcvars`" >nul 2>&1 && cd /d `"$cwd`" && `"$vsCmake`" -G Ninja -B build . >nul 2>&1 && `"$vsCmake`" --build build 2>&1 && cd build && ctest --output-on-failure 2>&1" | Out-String
            }
        }
        $passed = $LASTEXITCODE -eq 0
        return @{ passed = $passed; output = $output }
    } finally {
        Pop-Location
    }
}

function Build-Prompt($lang, $exerciseDir, $exerciseName) {
    $instructions = ""
    $docsPath = Join-Path $exerciseDir ".docs" "instructions.md"
    if (Test-Path $docsPath) {
        $instructions = Get-Content $docsPath -Raw -Encoding utf8
    }
    
    # Find the implementation file
    $implFile = switch ($lang) {
        "python"     { Get-ChildItem $exerciseDir -Filter "*.py" | Where-Object { $_.Name -notmatch "test" } | Select-Object -First 1 }
        "go"         { Get-ChildItem $exerciseDir -Filter "*.go" | Where-Object { $_.Name -notmatch "test" } | Select-Object -First 1 }
        "javascript" { Get-ChildItem $exerciseDir -Filter "*.js" | Where-Object { $_.Name -notmatch "spec" } | Select-Object -First 1 }
        "java"       { Get-ChildItem $exerciseDir -Recurse -Filter "*.java" | Where-Object { $_.Name -notmatch "Test" } | Select-Object -First 1 }
        "rust"       { Join-Path $exerciseDir "src" "lib.rs" | Get-Item -ErrorAction SilentlyContinue }
        "cpp"        { Get-ChildItem $exerciseDir -Filter "*.cpp" | Where-Object { $_.Name -notmatch "test" } | Select-Object -First 1 }
    }
    
    $starterCode = ""
    if ($implFile -and (Test-Path $implFile.FullName)) {
        $starterCode = Get-Content $implFile.FullName -Raw -Encoding utf8
    }

    $prompt = @"
Implement the solution for the '$exerciseName' exercise.

## Instructions
$instructions

## Current code in $($implFile.Name):
``````
$starterCode
``````

Requirements:
- Edit ONLY $($implFile.Name) in the current directory
- Implement all required functions/classes
- Use only standard library unless imports already exist
- Don't change function signatures or class names
- Make all unit tests pass
"@
    return $prompt
}

function Build-RetryPrompt($lang, $exerciseDir, $exerciseName, $testOutput) {
    $implFile = switch ($lang) {
        "python"     { Get-ChildItem $exerciseDir -Filter "*.py" | Where-Object { $_.Name -notmatch "test" } | Select-Object -First 1 }
        "go"         { Get-ChildItem $exerciseDir -Filter "*.go" | Where-Object { $_.Name -notmatch "test" } | Select-Object -First 1 }
        "javascript" { Get-ChildItem $exerciseDir -Filter "*.js" | Where-Object { $_.Name -notmatch "spec" } | Select-Object -First 1 }
        "java"       { Get-ChildItem $exerciseDir -Recurse -Filter "*.java" | Where-Object { $_.Name -notmatch "Test" } | Select-Object -First 1 }
        "rust"       { Join-Path $exerciseDir "src" "lib.rs" | Get-Item -ErrorAction SilentlyContinue }
        "cpp"        { Get-ChildItem $exerciseDir -Filter "*.cpp" | Where-Object { $_.Name -notmatch "test" } | Select-Object -First 1 }
    }
    
    $currentCode = ""
    if ($implFile -and (Test-Path $implFile.FullName)) {
        $currentCode = Get-Content $implFile.FullName -Raw -Encoding utf8
    }

    # Truncate test output to avoid prompt bloat
    $truncated = $testOutput
    if ($testOutput.Length -gt 3000) {
        $truncated = $testOutput.Substring(0, 3000) + "`n... (truncated)"
    }

    return @"
The tests for '$exerciseName' are failing. Fix the implementation in $($implFile.Name).

## Test failures:
``````
$truncated
``````

## Current code in $($implFile.Name):
``````
$currentCode
``````

Fix the code to make all tests pass. Edit ONLY $($implFile.Name).
"@
}

# --- Main ---
Write-Log "=== Squad Polyglot Benchmark - $Language ==="
Write-Log "Benchmark dir: $benchmarkDir"
Write-Log "Agent mode: $(if ($NoAgent) { 'copilot --yolo' } else { 'copilot --yolo --agent squad' })"

# Get exercise list
$exercises = Get-ChildItem $benchmarkDir -Directory | 
    Where-Object { $_.Name -notmatch '^\.' } |
    Sort-Object Name

if ($StartFrom) {
    $idx = ($exercises | ForEach-Object { $_.Name }).IndexOf($StartFrom)
    if ($idx -ge 0) {
        $exercises = $exercises[$idx..($exercises.Count-1)]
        Write-Log "Resuming from: $StartFrom"
    }
}

if ($MaxExercises -gt 0) {
    $exercises = $exercises | Select-Object -First $MaxExercises
}

Write-Log "Exercises to run: $($exercises.Count)"

$results = @()
$passCount1 = 0
$passCount2 = 0
$totalCount = 0

foreach ($ex in $exercises) {
    $totalCount++
    $exerciseName = $ex.Name
    $exerciseDir = $ex.FullName
    
    Write-Log "--- [$totalCount/$($exercises.Count)] $exerciseName ---"
    
    # Enable all tests (remove skip/xtest/ignore markers)
    Enable-AllTests $Language $exerciseDir
    
    # Build prompt
    $prompt = Build-Prompt $Language $exerciseDir $exerciseName
    
    # Save prompt for debugging
    $promptFile = Join-Path $resultsDir "$exerciseName-prompt.txt"
    Set-Content $promptFile $prompt -Encoding utf8
    
    # Attempt 1
    Write-Log "  Attempt 1..."
    $startTime = Get-Date
    
    $copilotArgs = @("--yolo", "-p", $prompt)
    if (-not $NoAgent) {
        $copilotArgs = @("--yolo", "--agent", "squad", "-p", $prompt)
    }
    
    # Run copilot pointing at the exercise directory
    Push-Location $exerciseDir
    try {
        $copilotOutput = & copilot @copilotArgs 2>&1 | Out-String
    } finally {
        Pop-Location
    }
    
    $elapsed1 = ((Get-Date) - $startTime).TotalSeconds
    Write-Log "  Copilot finished in $([math]::Round($elapsed1))s"
    
    # Run tests
    $testResult = Run-Tests $Language $exerciseDir
    
    if ($testResult.passed) {
        Write-Log "  PASS (attempt 1)"
        $passCount1++
        $passCount2++
        $results += @{
            exercise = $exerciseName
            pass_1 = $true
            pass_2 = $true
            time_1 = $elapsed1
            time_2 = 0
        }
    } else {
        Write-Log "  FAIL (attempt 1) - retrying..."
        
        # Attempt 2 with test error feedback
        $retryPrompt = Build-RetryPrompt $Language $exerciseDir $exerciseName $testResult.output
        $retryPromptFile = Join-Path $resultsDir "$exerciseName-retry-prompt.txt"
        Set-Content $retryPromptFile $retryPrompt -Encoding utf8
        
        $startTime2 = Get-Date
        
        $copilotArgs2 = @("--yolo", "-p", $retryPrompt)
        if (-not $NoAgent) {
            $copilotArgs2 = @("--yolo", "--agent", "squad", "-p", $retryPrompt)
        }
        
        Push-Location $exerciseDir
        try {
            $copilotOutput2 = & copilot @copilotArgs2 2>&1 | Out-String
        } finally {
            Pop-Location
        }
        
        $elapsed2 = ((Get-Date) - $startTime2).TotalSeconds
        Write-Log "  Attempt 2 finished in $([math]::Round($elapsed2))s"
        
        $testResult2 = Run-Tests $Language $exerciseDir
        
        if ($testResult2.passed) {
            Write-Log "  PASS (attempt 2)"
            $passCount2++
            $results += @{
                exercise = $exerciseName
                pass_1 = $false
                pass_2 = $true
                time_1 = $elapsed1
                time_2 = $elapsed2
            }
        } else {
            Write-Log "  FAIL (both attempts)"
            $results += @{
                exercise = $exerciseName
                pass_1 = $false
                pass_2 = $false
                time_1 = $elapsed1
                time_2 = $elapsed2
            }
        }
    }
    
    # Save running results
    $summary = @{
        language = $Language
        total = $totalCount
        pass_1 = $passCount1
        pass_2 = $passCount2
        rate_1 = [math]::Round(($passCount1 / $totalCount) * 100, 1)
        rate_2 = [math]::Round(($passCount2 / $totalCount) * 100, 1)
        exercises = $results
    }
    $summary | ConvertTo-Json -Depth 3 | Set-Content (Join-Path $resultsDir "results.json") -Encoding utf8
    
    Write-Log "  Running totals: $passCount1/$totalCount ($(([math]::Round(($passCount1/$totalCount)*100,1)))%) attempt1, $passCount2/$totalCount ($(([math]::Round(($passCount2/$totalCount)*100,1)))%) attempt2"
}

Write-Log ""
Write-Log "=== FINAL RESULTS ==="
Write-Log "Language: $Language"
Write-Log "Total exercises: $totalCount"
Write-Log "Pass rate (attempt 1): $passCount1/$totalCount = $(([math]::Round(($passCount1/$totalCount)*100,1)))%"
Write-Log "Pass rate (attempt 2): $passCount2/$totalCount = $(([math]::Round(($passCount2/$totalCount)*100,1)))%"
Write-Log "Results saved to: $resultsDir"
