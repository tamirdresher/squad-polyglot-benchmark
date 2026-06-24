#!/bin/bash
# Run JavaScript tests via npm/jest
cd "$(dirname "$0")/.." 2>/dev/null || cd .

# Enable all tests (Exercism uses xtest for skipped tests)
sed -i 's/\bxtest(/test(/g' *.spec.js 2>/dev/null || true
sed -i 's/\bxit(/it(/g' *.spec.js 2>/dev/null || true
sed -i "s/test\.skip(/test(/g" *.spec.js 2>/dev/null || true

npm install --silent 2>/dev/null
npx jest --no-coverage 2>&1
