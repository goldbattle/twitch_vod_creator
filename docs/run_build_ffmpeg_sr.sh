#!/bin/bash

# Script to build ffmpeg with libtensorflow support and set up super resolution models
# Based on: https://video.stackexchange.com/a/38059
# All output goes to thirdparty/ directory, nothing installed globally
#
# Usage:
#   ./run_build_ffmpeg_sr.sh          # Build with CPU version of TensorFlow (default)
#   ./run_build_ffmpeg_sr.sh --gpu    # Build with GPU version of TensorFlow
#
# Prerequisites for NVENC/NVDEC (optional but recommended):
# - NVIDIA drivers installed
# - NVIDIA Video Codec SDK headers (for hardware encoding/decoding)
#   If not available, configure will disable these features automatically
#
# Prerequisites for GPU version:
# - CUDA and cuDNN installed with versions compatible with TensorFlow 2.18.0
# - GPU version may have compatibility issues - CPU version is recommended for stability
#
# Note: Some configure flags may fail if optional libraries are missing.
# The script will continue and those features will simply be disabled.

set -e  # Exit on error

# Parse command line arguments
TENSORFLOW_TYPE="cpu"  # Default to CPU version for stability
if [ "$1" = "--gpu" ] || [ "$1" = "-gpu" ]; then
    TENSORFLOW_TYPE="gpu"
    echo "GPU version requested - ensure CUDA/cuDNN versions are compatible with TensorFlow 2.18.0"
fi

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
THIRDPARTY_DIR="${SCRIPT_DIR}/thirdparty"
OUTPUT_DIR="${THIRDPARTY_DIR}/ffmpeg-sr"

# Versions
VERSION_FFMPEG="8.0"
VERSION_LIBTENSORFLOW="2.18.0"

# Create temporary directory for building
# TEMP_DIR=$(mktemp -d)
TEMP_DIR="${THIRDPARTY_DIR}/ffmpeg-sr-build"
# trap "rm -rf $TEMP_DIR" EXIT

echo "=========================================="
echo "Building ffmpeg with libtensorflow support"
echo "=========================================="
echo "Temporary build directory: $TEMP_DIR"
echo "Output directory: $OUTPUT_DIR"
echo ""

# Check for required tools
echo "Checking for required tools..."
for cmd in curl tar python3 git make; do
    if ! command -v $cmd &> /dev/null; then
        echo "Error: $cmd is not installed"
        exit 1
    fi
done

# Check for CUDA installation (required for NVENC/NVDEC and TensorFlow GPU)
echo "Checking for CUDA installation..."
CUDA_FOUND=false

# Check for CUDA in common locations
if [ -d "/usr/local/cuda" ] || [ -d "/opt/cuda" ]; then
    CUDA_FOUND=true
    echo "✓ CUDA found in standard location"
elif [ -f "/usr/lib/libcuda.so" ] || [ -f "/usr/lib64/libcuda.so" ]; then
    CUDA_FOUND=true
    echo "✓ CUDA libraries found"
elif command -v nvcc &> /dev/null; then
    CUDA_FOUND=true
    echo "✓ CUDA compiler (nvcc) found"
fi

if [ "$CUDA_FOUND" = false ]; then
    echo "Error: CUDA is required for NVENC/NVDEC support and TensorFlow GPU"
    echo ""
    echo "Please install CUDA for your distribution:"
    echo "  Arch Linux: sudo pacman -S cuda"
    echo "  Ubuntu/Debian: sudo apt install nvidia-cuda-toolkit"
    echo "  Fedora: sudo dnf install cuda-toolkit"
    echo "  Other: Install from https://developer.nvidia.com/cuda-downloads"
    echo ""
    exit 1
fi

# Check for cuDNN (required for TensorFlow GPU)
echo "Checking for cuDNN installation..."
CUDNN_FOUND=false

# Check for cuDNN libraries in common locations
if [ -f "/usr/lib/libcudnn.so" ] || [ -f "/usr/lib64/libcudnn.so" ] || \
   [ -f "/usr/local/cuda/lib64/libcudnn.so" ] || [ -f "/opt/cuda/lib64/libcudnn.so" ] || \
   find /usr/lib* /usr/local/cuda* /opt/cuda* -name "libcudnn.so*" 2>/dev/null | grep -q .; then
    CUDNN_FOUND=true
    echo "✓ cuDNN libraries found"
fi

if [ "$CUDNN_FOUND" = false ]; then
    echo "Error: cuDNN is required for TensorFlow GPU support"
    echo ""
    echo "Please install cuDNN for your distribution:"
    echo "  Arch Linux: sudo pacman -S cudnn"
    echo "    Or from AUR: yay -S cuda-cudnn"
    echo "  Ubuntu/Debian: sudo apt install libcudnn8 libcudnn8-dev"
    echo "  Fedora: sudo dnf install libcudnn"
    echo "  Other: Download from https://developer.nvidia.com/cudnn"
    echo "    Extract to /usr/local/cuda or /opt/cuda"
    echo ""
    echo "Note: cuDNN requires NVIDIA Developer account registration"
    echo ""
    exit 1
fi
echo ""

# Check for assembler (nasm or yasm) - required for x86 optimizations
if ! command -v nasm &> /dev/null && ! command -v yasm &> /dev/null; then
    echo "Error: nasm or yasm is required for x86 assembly optimizations"
    echo ""
    echo "Please install one of them:"
    echo "  Arch Linux: sudo pacman -S nasm"
    echo "  Ubuntu/Debian: sudo apt install nasm"
    echo "  Fedora: sudo dnf install nasm"
    echo ""
    echo "Alternatively, you can disable x86asm (not recommended, slower build):"
    echo "  Add --disable-x86asm to the configure command"
    exit 1
fi

# Check nasm version if available (needs to be >= 2.13)
if command -v nasm &> /dev/null; then
    NASM_VERSION=$(nasm -v 2>&1 | grep -oP 'version \K[0-9]+\.[0-9]+' | head -1)
    if [ -n "$NASM_VERSION" ]; then
        MAJOR=$(echo "$NASM_VERSION" | cut -d. -f1)
        MINOR=$(echo "$NASM_VERSION" | cut -d. -f2)
        if [ "$MAJOR" -lt 2 ] || ([ "$MAJOR" -eq 2 ] && [ "$MINOR" -lt 13 ]); then
            echo "Warning: nasm version $NASM_VERSION is too old (need >= 2.13)"
            echo "Please update nasm or use yasm instead"
        else
            echo "✓ Found nasm version $NASM_VERSION"
        fi
    fi
fi

echo "✓ All required tools found"
echo ""

# Check for build dependencies
echo "Checking for build dependencies..."
MISSING_DEPS=()

# Detect distribution
if [ -f /etc/arch-release ]; then
    DISTRO="arch"
    PKG_MGR="pacman"
    # Arch Linux package names
    DEPS=(
        "autoconf" "automake" "base-devel" "cmake" "curl" "git"
        "libass" "libfdk-aac" "freetype2" "gnutls" "lame" "libvorbis"
        "libvpx" "x264" "x265" "nasm" "pkg-config" "python" "texinfo" "yasm" "zlib"
    )
elif [ -f /etc/debian_version ]; then
    DISTRO="debian"
    PKG_MGR="apt"
    # Debian/Ubuntu package names
    DEPS=(
        "autoconf" "automake" "build-essential" "cmake" "curl" "git"
        "libass-dev" "libfdk-aac-dev" "libfreetype6-dev" "libgnutls28-dev"
        "libgomp1" "libmp3lame-dev" "libnuma-dev" "libopus-dev"
        "libsdl2-dev" "libtool" "libunistring-dev" "libva-dev"
        "libvdpau-dev" "libvorbis-dev" "libvpx-dev"
        "libxcb-shm0-dev" "libxcb-xfixes0-dev" "libxcb1-dev"
        "libx264-dev" "libx265-dev" "nasm" "pkg-config" "python3" "texinfo" "yasm" "zlib1g-dev"
    )
elif [ -f /etc/fedora-release ]; then
    DISTRO="fedora"
    PKG_MGR="dnf"
    # Fedora package names
    DEPS=(
        "autoconf" "automake" "cmake" "curl" "gcc" "gcc-c++" "git"
        "libass-devel" "fdk-aac-devel" "freetype-devel" "gnutls-devel"
        "lame-devel" "libvorbis-devel" "libvpx-devel"
        "x264-devel" "x265-devel" "nasm" "pkg-config" "python3" "texinfo" "yasm" "zlib-devel"
    )
else
    echo "⚠ Warning: Unknown distribution, skipping dependency check"
    echo "  You may need to install build dependencies manually"
    DISTRO="unknown"
    DEPS=()
fi

# Check for missing dependencies
if [ "$DISTRO" != "unknown" ]; then
    for dep in "${DEPS[@]}"; do
        if [ "$DISTRO" = "arch" ]; then
            # Arch: check if package is installed
            if ! pacman -Qi "$dep" &>/dev/null; then
                MISSING_DEPS+=("$dep")
            fi
        elif [ "$DISTRO" = "debian" ]; then
            # Debian/Ubuntu: check if package is installed
            if ! dpkg -l | grep -q "^ii.*$dep "; then
                MISSING_DEPS+=("$dep")
            fi
        elif [ "$DISTRO" = "fedora" ]; then
            # Fedora: check if package is installed
            if ! rpm -q "$dep" &>/dev/null; then
                MISSING_DEPS+=("$dep")
            fi
        fi
    done
    
    if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
        echo "⚠ Missing build dependencies detected:"
        printf "  %s\n" "${MISSING_DEPS[@]}"
        echo ""
        echo "Please install them:"
        if [ "$DISTRO" = "arch" ]; then
            echo "  sudo pacman -S ${MISSING_DEPS[*]}"
        elif [ "$DISTRO" = "debian" ]; then
            echo "  sudo apt update && sudo apt install ${MISSING_DEPS[*]}"
        elif [ "$DISTRO" = "fedora" ]; then
            echo "  sudo dnf install ${MISSING_DEPS[*]}"
        fi
        echo ""
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    else
        echo "✓ All build dependencies found"
    fi
fi
echo ""

# Step 1: Download and extract libtensorflow
echo "Step 1: Checking libtensorflow ${VERSION_LIBTENSORFLOW}..."
LIBTENSORFLOW_DIR="${TEMP_DIR}/libtensorflow"

# Check if already downloaded
if [ -d "$LIBTENSORFLOW_DIR" ] && [ -d "$LIBTENSORFLOW_DIR/lib" ] && [ -d "$LIBTENSORFLOW_DIR/include" ]; then
    echo "✓ libtensorflow already downloaded, skipping..."
else
    echo "Downloading libtensorflow..."
    mkdir -p "$LIBTENSORFLOW_DIR"
    # New URL format: https://storage.googleapis.com/tensorflow/versions/VERSION/libtensorflow-{cpu|gpu}-linux-x86_64.tar.gz
    LIBTENSORFLOW_URL="https://storage.googleapis.com/tensorflow/versions/${VERSION_LIBTENSORFLOW}/libtensorflow-${TENSORFLOW_TYPE}-linux-x86_64.tar.gz"
    curl -fsSL "$LIBTENSORFLOW_URL" | tar -xzC "$LIBTENSORFLOW_DIR" -f -
    echo "✓ libtensorflow downloaded"
fi
echo ""

# Step 2: Download ffmpeg source
echo "Step 2: Checking ffmpeg ${VERSION_FFMPEG} source..."
FFMPEG_DIR="${TEMP_DIR}/ffmpeg-${VERSION_FFMPEG}"

# Check if already downloaded (look for configure script)
if [ -d "$FFMPEG_DIR" ] && [ -f "$FFMPEG_DIR/configure" ]; then
    echo "✓ ffmpeg source already downloaded, skipping..."
else
    echo "Downloading ffmpeg source..."
    mkdir -p "$FFMPEG_DIR"
    FFMPEG_URL="https://ffmpeg.org/releases/ffmpeg-${VERSION_FFMPEG}.tar.bz2"
    curl -fsSL "$FFMPEG_URL" | tar --strip 1 -xjC "$FFMPEG_DIR" -f -
    echo "✓ ffmpeg source downloaded"
fi
echo ""

# Step 3: Build ffmpeg with libtensorflow
echo "Step 3: Configuring ffmpeg with libtensorflow..."
cd "$FFMPEG_DIR"

# Set up libtensorflow paths
export PKG_CONFIG_PATH="${LIBTENSORFLOW_DIR}/lib/pkgconfig:${PKG_CONFIG_PATH}"
export LD_LIBRARY_PATH="${LIBTENSORFLOW_DIR}/lib:${LD_LIBRARY_PATH}"
export C_INCLUDE_PATH="${LIBTENSORFLOW_DIR}/include:${C_INCLUDE_PATH}"
export CPLUS_INCLUDE_PATH="${LIBTENSORFLOW_DIR}/include:${CPLUS_INCLUDE_PATH}"

# Check for ffnvcodec (required for NVENC/NVDEC)
# ffnvcodec is typically available as ffnvcodec-headers package on Arch
FFNVCODEC_INCLUDE=""
if pkg-config --exists ffnvcodec 2>/dev/null || \
   [ -d "/usr/include/ffnvcodec" ] || \
   [ -d "/usr/local/include/ffnvcodec" ] || \
   find /usr/include /usr/local/include -name "nvEncodeAPI.h" 2>/dev/null | grep -q .; then
    echo "✓ ffnvcodec found, enabling NVENC/NVDEC"
    # Set include path - pkg-config handles it, otherwise use standard paths
    if ! pkg-config --exists ffnvcodec 2>/dev/null; then
        if [ -d "/usr/include/ffnvcodec" ]; then
            FFNVCODEC_INCLUDE="/usr/include"
        elif [ -d "/usr/local/include/ffnvcodec" ]; then
            FFNVCODEC_INCLUDE="/usr/local/include"
        fi
    fi
    NVENC_ENABLED="--enable-nvdec --enable-nvenc"
else
    echo "Error: ffnvcodec is required for NVENC/NVDEC support"
    echo ""
    echo "Please install ffnvcodec:"
    echo "  Arch Linux: sudo pacman -S ffnvcodec-headers"
    echo "  Fedora: sudo dnf install nv-codec-headers"
    echo "  openSUSE: sudo zypper install ffnvcodec-devel"
    echo "  Ubuntu/Debian: Build from source (see below)"
    echo ""
    echo "Or build from source:"
    echo "  git clone https://github.com/FFmpeg/nv-codec-headers.git"
    echo "  cd nv-codec-headers && make && sudo make install"
    echo ""
    exit 1
fi

# Build extra-cflags with all include paths
EXTRA_CFLAGS="-I${LIBTENSORFLOW_DIR}/include"
if [ -n "$FFNVCODEC_INCLUDE" ]; then
    EXTRA_CFLAGS="$EXTRA_CFLAGS -I${FFNVCODEC_INCLUDE}"
fi

# Build extra-ldflags with library paths and rpath
# Use rpath with $ORIGIN so the binary can find libtensorflow relative to itself
# $ORIGIN refers to the directory containing the executable, so ../lib from bin/ will work
# Note: libtensorflow only provides shared libraries, not static
EXTRA_LDFLAGS="-L${LIBTENSORFLOW_DIR}/lib -Wl,-rpath,'\$\$ORIGIN/../lib' -ltensorflow"

# Configure ffmpeg
# Can --disable-x86asm if you run into issues...
./configure \
    --prefix="${OUTPUT_DIR}" \
    --pkg-config-flags='--static' \
    --extra-libs='-lpthread -lm' \
    --extra-cflags="$EXTRA_CFLAGS" \
    --extra-ldflags="$EXTRA_LDFLAGS" \
    --enable-gpl \
    --enable-gnutls \
    --enable-libass \
    --enable-libfdk-aac \
    --enable-libfreetype \
    --enable-libmp3lame \
    --enable-libopus \
    --enable-libvorbis \
    --enable-libvpx \
    --enable-libx264 \
    --enable-libx265 \
    --enable-libtensorflow \
    $NVENC_ENABLED \
    --enable-nonfree

echo "✓ ffmpeg configured"
echo ""

echo "Step 4: Building ffmpeg (this may take a while)..."
make -j$(nproc)
echo "✓ ffmpeg built"
echo ""

echo "Step 5: Installing ffmpeg to ${OUTPUT_DIR}..."
make install
echo "✓ ffmpeg installed"
echo ""

# Step 6: Clone sr repository
echo "Step 6: Checking super resolution repository..."
SR_DIR="${TEMP_DIR}/sr"

# Use the updated repository that supports TensorFlow 2.x Keras API
# Original: https://github.com/XueweiMeng/sr (TensorFlow 1.x, outdated)
# Updated: https://github.com/rubeniskov/ffmpeg-super-resolution-models (TensorFlow 2.x compatible)
SR_REPO="https://github.com/rubeniskov/ffmpeg-super-resolution-models.git"

# Check if already cloned
if [ -d "$SR_DIR" ] && [ -d "$SR_DIR/.git" ]; then
    echo "✓ Repository already cloned, skipping..."
    # Make sure we're on the latest commit
    cd "$SR_DIR"
    git fetch origin 2>/dev/null || true
    git pull origin main 2>/dev/null || git pull origin master 2>/dev/null || true
else
    echo "Cloning repository (TensorFlow 2.x compatible version)..."
    git clone "$SR_REPO" "$SR_DIR"
    echo "✓ Repository cloned"
fi
echo ""

# Step 7: Create temporary virtual environment for Python dependencies
echo "Step 7: Checking temporary virtual environment..."
VENV_DIR="${TEMP_DIR}/venv"

# Check if venv already exists
if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/activate" ]; then
    echo "✓ Virtual environment already exists, reusing..."
    source "$VENV_DIR/bin/activate"
else
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    echo "✓ Virtual environment created"
fi
echo ""

# Step 8: Install Python dependencies
echo "Step 8: Checking Python dependencies (tensorflow, numpy)..."
# Check if packages are already installed
if python3 -c "import tensorflow, numpy" 2>/dev/null; then
    echo "✓ Python dependencies already installed, skipping..."
else
    echo "Installing Python dependencies..."
    pip install --upgrade pip
    # Install latest TensorFlow 2.x (the updated repo uses tf.keras.layers which works with newer versions)
    pip install tensorflow numpy
    echo "✓ Python dependencies installed"
fi
echo ""

# Step 9: Generate super resolution models
echo "Step 9: Generating super resolution models..."
cd "$SR_DIR"

# Ensure we're using the venv
source "$VENV_DIR/bin/activate"
# Don't override LD_LIBRARY_PATH - let TensorFlow Python use its own bundled libraries
# Our libtensorflow is only for ffmpeg, not for Python TensorFlow
unset LD_LIBRARY_PATH

# Check if checkpoints directory exists
if [ ! -d "checkpoints/espcn" ]; then
    echo "Warning: checkpoints/espcn directory not found in repository"
    echo "You may need to download the model checkpoints separately"
    echo "Continuing anyway..."
fi

# The updated repository already uses TensorFlow 2.x Keras API, so no patching needed
echo "  Using TensorFlow 2.x compatible repository (no patching required)"

# Generate header and model
python3 generate_header_and_model.py --model=espcn --ckpt_path=checkpoints/espcn/ || {
    echo "Warning: Model generation failed."
    echo "This may be due to:"
    echo "  - Missing model checkpoints"
    echo "  - TensorFlow version incompatibility"
    echo "  - Library conflicts"
    echo "You can download checkpoints separately and run this step again."
}
echo "✓ Model generation attempted"
echo ""

# Step 10: Copy everything to thirdparty
echo "Step 10: Copying files to ${OUTPUT_DIR}..."
mkdir -p "$OUTPUT_DIR"

# Copy libtensorflow libraries
echo "  Copying libtensorflow libraries..."
mkdir -p "${OUTPUT_DIR}/lib"
cp -r "${LIBTENSORFLOW_DIR}/lib"/* "${OUTPUT_DIR}/lib/" 2>/dev/null || true

# Copy generated super resolution model files
echo "  Copying generated model files..."
mkdir -p "${OUTPUT_DIR}/sr"
# Copy generated .pb (protobuf), .h (header), and .model (binary) files
if [ -f "$SR_DIR/espcn.pb" ]; then
    cp "$SR_DIR"/*.pb "${OUTPUT_DIR}/sr/" 2>/dev/null || true
    echo "    Copied .pb model files"
fi
if [ -f "$SR_DIR/dnn_espcn.h" ]; then
    cp "$SR_DIR"/dnn_*.h "${OUTPUT_DIR}/sr/" 2>/dev/null || true
    echo "    Copied .h header files"
fi
if [ -f "$SR_DIR/espcn.model" ]; then
    cp "$SR_DIR"/*.model "${OUTPUT_DIR}/sr/" 2>/dev/null || true
    echo "    Copied .model binary files"
fi

# Make ffmpeg and ffprobe executable
if [ -f "${OUTPUT_DIR}/bin/ffmpeg" ]; then
    chmod +x "${OUTPUT_DIR}/bin/ffmpeg"
fi
if [ -f "${OUTPUT_DIR}/bin/ffprobe" ]; then
    chmod +x "${OUTPUT_DIR}/bin/ffprobe"
fi

# Create wrapper scripts that set LD_LIBRARY_PATH
# These use paths relative to the script location so they work even if the folder moves
echo "  Creating wrapper scripts..."

# Build the library path setup code (shared for both wrappers)
# This sets up LD_LIBRARY_PATH for libtensorflow, CUDA, and cuDNN
LIBRARY_PATH_SETUP='# Get the directory where this wrapper script is located
WRAPPER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Set LD_LIBRARY_PATH to the lib directory relative to this script (for libtensorflow)
export LD_LIBRARY_PATH="${WRAPPER_DIR}/../lib:${LD_LIBRARY_PATH}"

# Add CUDA libraries to path (required for TensorFlow GPU and NVENC/NVDEC)
# Arch Linux: CUDA libraries are typically in /opt/cuda/targets/x86_64-linux/lib/
[ -d "/opt/cuda/targets/x86_64-linux/lib" ] && export LD_LIBRARY_PATH="/opt/cuda/targets/x86_64-linux/lib:${LD_LIBRARY_PATH}"
# Standard CUDA installation locations (Ubuntu/Debian/Fedora)
[ -d "/opt/cuda/lib64" ] && export LD_LIBRARY_PATH="/opt/cuda/lib64:${LD_LIBRARY_PATH}"
[ -d "/usr/local/cuda/lib64" ] && export LD_LIBRARY_PATH="/usr/local/cuda/lib64:${LD_LIBRARY_PATH}"
# Add standard library paths (Arch/Debian often install CUDA libs here)
# Note: /usr/lib must come after CUDA paths so CUDA libraries take precedence
[ -d "/usr/lib" ] && export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:/usr/lib"
[ -d "/usr/lib64" ] && export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:/usr/lib64"

# Add cuDNN paths if found (cuDNN is usually in /usr/lib on Arch, or with CUDA on other distros)
[ -d "/opt/cuda/targets/x86_64-linux/lib" ] && [ -f "/opt/cuda/targets/x86_64-linux/lib/libcudnn.so" ] && export LD_LIBRARY_PATH="/opt/cuda/targets/x86_64-linux/lib:${LD_LIBRARY_PATH}"
[ -d "/opt/cuda/lib64" ] && [ -f "/opt/cuda/lib64/libcudnn.so" ] && export LD_LIBRARY_PATH="/opt/cuda/lib64:${LD_LIBRARY_PATH}"
[ -d "/usr/local/cuda/lib64" ] && [ -f "/usr/local/cuda/lib64/libcudnn.so" ] && export LD_LIBRARY_PATH="/usr/local/cuda/lib64:${LD_LIBRARY_PATH}"
# cuDNN on Arch Linux is typically in /usr/lib
[ -d "/usr/lib" ] && [ -f "/usr/lib/libcudnn.so" ] && export LD_LIBRARY_PATH="/usr/lib:${LD_LIBRARY_PATH}"

# Set TensorFlow environment variables to suppress warnings and help find CUDA
# Suppress TensorFlow CUDA warnings (they'\''re harmless if GPU isn'\''t available)
#export TF_CPP_MIN_LOG_LEVEL=2
# Set CUDA paths for TensorFlow (optional, but helps with library discovery)
[ -d "/opt/cuda" ] && export CUDA_HOME="/opt/cuda"
[ -d "/usr/local/cuda" ] && export CUDA_HOME="/usr/local/cuda"'

if [ -f "${OUTPUT_DIR}/bin/ffmpeg" ]; then
    cat > "${OUTPUT_DIR}/bin/ffmpeg.wrapper" << EOF
#!/bin/bash
${LIBRARY_PATH_SETUP}

# Execute the actual ffmpeg binary
exec "\${WRAPPER_DIR}/ffmpeg" "\$@"
EOF
    chmod +x "${OUTPUT_DIR}/bin/ffmpeg.wrapper"
fi

if [ -f "${OUTPUT_DIR}/bin/ffprobe" ]; then
    cat > "${OUTPUT_DIR}/bin/ffprobe.wrapper" << EOF
#!/bin/bash
${LIBRARY_PATH_SETUP}

# Execute the actual ffprobe binary
exec "\${WRAPPER_DIR}/ffprobe" "\$@"
EOF
    chmod +x "${OUTPUT_DIR}/bin/ffprobe.wrapper"
fi

echo "✓ Files copied"
echo ""

# Step 11: Verify ffmpeg build
echo "Step 11: Verifying ffmpeg build..."
if [ -f "${OUTPUT_DIR}/bin/ffmpeg.wrapper" ]; then
    echo "Checking build configuration..."
    BUILD_CONF=$("${OUTPUT_DIR}/bin/ffmpeg.wrapper" -buildconf 2>&1)
    
    # Filter out TensorFlow warnings for cleaner output
    BUILD_CONF_CLEAN=$(echo "$BUILD_CONF" | grep -v "cudart_stub\|gpu_device\|Could not find cuda")
    
    if echo "$BUILD_CONF_CLEAN" | grep -q "libtensorflow"; then
        echo "✓ ffmpeg built with libtensorflow support!"
    else
        echo "⚠ Warning: libtensorflow may not be enabled in ffmpeg"
    fi
    
    if echo "$BUILD_CONF_CLEAN" | grep -qi "nvenc"; then
        echo "✓ ffmpeg built with NVENC support!"
    else
        echo "⚠ Warning: NVENC may not be enabled (requires NVIDIA drivers and Video Codec SDK)"
    fi
    
    if echo "$BUILD_CONF_CLEAN" | grep -qi "nvdec"; then
        echo "✓ ffmpeg built with NVDEC support!"
    else
        echo "⚠ Warning: NVDEC may not be enabled (requires NVIDIA drivers and Video Codec SDK)"
    fi
    
    echo ""
    echo "Build configuration summary:"
    echo "$BUILD_CONF_CLEAN" | grep -E "(configuration:|--enable-|--prefix=)" | head -15
else
    echo "⚠ Warning: ffmpeg wrapper not found at ${OUTPUT_DIR}/bin/ffmpeg.wrapper"
fi
echo ""

echo "=========================================="
echo "Build complete!"
echo "=========================================="
echo "ffmpeg location: ${OUTPUT_DIR}/bin/ffmpeg"
echo "ffprobe location: ${OUTPUT_DIR}/bin/ffprobe"
echo "Super resolution models: ${OUTPUT_DIR}/sr/"
echo ""
echo "To use this ffmpeg, update your config to point to:"
echo "  ${OUTPUT_DIR}/bin/ffmpeg"
echo ""
echo "Note: Use the wrapper scripts to run ffmpeg (they set LD_LIBRARY_PATH automatically):"
echo "  ${OUTPUT_DIR}/bin/ffmpeg.wrapper"
echo "  ${OUTPUT_DIR}/bin/ffprobe.wrapper"
echo ""
echo "The wrapper scripts automatically add:"
echo "  - libtensorflow libraries (from ${OUTPUT_DIR}/lib)"
echo "  - CUDA libraries (from /opt/cuda/lib64, /usr/local/cuda/lib64, /usr/lib, /usr/lib64)"
echo "  - cuDNN libraries (if found)"
echo ""
echo "If you see TensorFlow CUDA warnings, they're harmless - TensorFlow will use CPU mode."
echo "To use GPU, ensure CUDA and cuDNN are properly installed and in the library paths."
echo ""

