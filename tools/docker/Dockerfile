# Linux environment for cross-building afni-win with MinGW-w64 UCRT64 and
# running the result under wine. Used for local checks only; the reference
# Windows build is the MSYS2 UCRT64 CI job.
#
#   docker build -t afniwin-cross tools/docker
#   docker run --rm -it -v "$PWD:$PWD" -w "$PWD" afniwin-cross \
#     uv run --frozen python -m tools.build --tag AFNI_26.2.09 --work-dir /tmp/afni-win-build
#
# Run wine programs with stdin from /dev/null. Files created in the container
# belong to root; chown them back if the source tree is mounted.

FROM fedora:44

RUN dnf install -y -q \
      ucrt64-gcc ucrt64-gcc-c++ ucrt64-winpthreads ucrt64-zlib ucrt64-libgomp \
      binutils wine-core cmake make ninja-build python3 git which xz curl \
 && dnf clean all

ARG EXPAT_VERSION=2.7.1
RUN cd /opt \
 && curl -sSL "https://github.com/libexpat/libexpat/releases/download/R_${EXPAT_VERSION//./_}/expat-${EXPAT_VERSION}.tar.xz" | tar xJ \
 && cmake -S "expat-${EXPAT_VERSION}" -B expat-build \
      -DCMAKE_SYSTEM_NAME=Windows \
      -DCMAKE_C_COMPILER=x86_64-w64-mingw32ucrt-gcc \
      -DCMAKE_RC_COMPILER=x86_64-w64-mingw32ucrt-windres \
      -DCMAKE_INSTALL_PREFIX=/usr/x86_64-w64-mingw32ucrt/sys-root/mingw \
      -DEXPAT_BUILD_TOOLS=OFF -DEXPAT_BUILD_EXAMPLES=OFF -DEXPAT_BUILD_TESTS=OFF -DEXPAT_BUILD_DOCS=OFF \
 && cmake --build expat-build -j \
 && cmake --install expat-build \
 && rm -rf "expat-${EXPAT_VERSION}" expat-build

ARG BUSYBOX_SHA256=6e263d154d8548d1eb936f65d1d8312c80df31c45974e48d6335e4dcc0f4f34c
RUN mkdir -p /opt/busybox \
 && curl -sSL -o /opt/busybox/busybox64u.exe https://frippery.org/files/busybox/busybox64u.exe \
 && echo "${BUSYBOX_SHA256}  /opt/busybox/busybox64u.exe" | sha256sum -c -

RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

ENV WINEDEBUG=-all \
    WINEDLLOVERRIDES="winex11.drv=;winewayland.drv=;mscoree=;mshtml=" \
    WINEPATH="Z:\\usr\\x86_64-w64-mingw32ucrt\\sys-root\\mingw\\bin" \
    WINEPREFIX=/root/.wine \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN wine cmd /c exit 0 </dev/null || true \
 && git config --system --add safe.directory '*'
