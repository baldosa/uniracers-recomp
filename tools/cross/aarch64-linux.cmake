# Cross toolchain: aarch64 Linux via Zig (zig cc/c++), static musl by default.
# Builds the arm64 port on an x86-64 host to check it under qemu-aarch64.
# The renderer loads GL at run time (gl_core), so a static check build links an
# empty stub for OpenGL::GL; GL headers are architecture-neutral (GLINC = any
# dir with GL/gl.h, e.g. /usr/include from libgl-dev):
#   tools/cross/zig-cc -c -x c /dev/null -o stub.o && tools/cross/zig-ar rcs libGLstub.a stub.o
#   cmake -S . -B build-arm64 -G Ninja -DCMAKE_BUILD_TYPE=Release \
#     -DCMAKE_TOOLCHAIN_FILE=tools/cross/aarch64-linux.cmake -DSDL_UNIX_CONSOLE_BUILD=ON \
#     -DOPENGL_INCLUDE_DIR=$GLINC -DOPENGL_GLX_INCLUDE_DIR=$GLINC \
#     -DOPENGL_opengl_LIBRARY=$PWD/libGLstub.a -DOPENGL_glx_LIBRARY=$PWD/libGLstub.a
#   cmake --build build-arm64
#   BIN=$PWD/tools/cross/run-arm64.sh tools/routes.sh runs/arm64 baselines/snes9x
# A Raspberry Pi build for play is native on the Pi (README), so SDL finds its
# real display and audio stack.
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)
set(CMAKE_C_COMPILER ${CMAKE_CURRENT_LIST_DIR}/zig-cc)
set(CMAKE_CXX_COMPILER ${CMAKE_CURRENT_LIST_DIR}/zig-c++)
set(CMAKE_AR ${CMAKE_CURRENT_LIST_DIR}/zig-ar CACHE FILEPATH "")
set(CMAKE_RANLIB ${CMAKE_CURRENT_LIST_DIR}/zig-ranlib CACHE FILEPATH "")
set(CMAKE_EXE_LINKER_FLAGS_INIT "-static")
set(CMAKE_CROSSCOMPILING_EMULATOR qemu-aarch64)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
