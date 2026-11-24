#!/usr/bin/env bash
# ============================================================
# C 엔진을 WebAssembly(WASI)로 컴파일 → mobile/engine/wildfire.wasm
#   휴대폰 앱(mobile/)이 이 파일을 내려받아 인터넷 없이 휴대폰 안에서 C 엔진을 실행한다.
#   C 코드는 한 줄도 바꾸지 않고 그대로 컴파일한다 (표준 C11 만 쓰기 때문에 가능).
#
# 필요한 것: wasi-sdk (WebAssembly 용 clang + 표준 C 라이브러리)
#   https://github.com/WebAssembly/wasi-sdk/releases 에서 받아 WASI_SDK 환경 변수로 위치를 알려 주거나,
#   이 스크립트가 tools/_wasi-sdk 에 자동으로 받는다. (Linux·macOS·WSL)
# 사용: bash tools/build_wasm.sh
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=24
if [ -z "${WASI_SDK:-}" ]; then
    WASI_SDK="tools/_wasi-sdk/wasi-sdk-${VERSION}.0-x86_64-linux"
    case "$(uname -s)" in
        Darwin) WASI_SDK="tools/_wasi-sdk/wasi-sdk-${VERSION}.0-$(uname -m)-macos" ;;
    esac
    if [ ! -x "$WASI_SDK/bin/clang" ]; then
        mkdir -p tools/_wasi-sdk
        NAME="$(basename "$WASI_SDK").tar.gz"
        echo "[받는 중] wasi-sdk ${VERSION} ($NAME)"
        curl -sSL -o "tools/_wasi-sdk/$NAME" \
            "https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-${VERSION}/$NAME"
        tar xzf "tools/_wasi-sdk/$NAME" -C tools/_wasi-sdk
    fi
fi

mkdir -p mobile/engine
"$WASI_SDK/bin/clang" --sysroot="$WASI_SDK/share/wasi-sysroot" --target=wasm32-wasip1 \
    -std=c11 -O2 -Wall -Wextra \
    -D_WASI_EMULATED_PROCESS_CLOCKS -lwasi-emulated-process-clocks \
    -Wl,-z,stack-size=1048576 \
    -I c_core/include c_core/src/*.c -lm \
    -o mobile/engine/wildfire.wasm
echo "[빌드 성공] mobile/engine/wildfire.wasm ($(wc -c < mobile/engine/wildfire.wasm) 바이트)"
