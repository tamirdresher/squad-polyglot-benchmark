#!/bin/bash
# Build and run C++ tests via CMake
cd "$(dirname "$0")/.." 2>/dev/null || cd .
mkdir -p build && cd build
cmake -G "Unix Makefiles" .. 2>&1
cmake --build . 2>&1
if [ $? -ne 0 ]; then
    exit 1
fi
ctest --output-on-failure 2>&1
