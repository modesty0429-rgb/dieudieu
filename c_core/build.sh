#!/bin/sh
# macOS / Linux 에서 확인용으로 빌드하는 스크립트 (과제 제출용 빌드는 build.bat 사용)
cd "$(dirname "$0")" || exit 1
mkdir -p bin
gcc -std=c11 -O2 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Iinclude src/*.c -lm -o bin/wildfire \
  && echo "[빌드 성공] bin/wildfire"
