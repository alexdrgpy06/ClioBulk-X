# ClioBulk-X (Native Flagship)

ClioBulk-X is a high-performance batch image processor combining a modern PySide6 frontend with a multi-threaded Rust core. It is designed for high-throughput image processing, supporting both standard formats and professional RAW formats.

## Features

-   **High-Performance Rust Core**: Native image processing using `rayon` for massive parallelism.
-   **RAW Support**: Direct decoding of professional RAW formats (`.ARW`, `.CR2`, `.NEF`, `.DNG`).
-   **Modern UI**: Sleek, dark-mode interface built with PySide6.
-   **Batch Processing**: Efficiently handle hundreds of images with real-time progress tracking.
-   **Advanced Filters**:
    -   Brightness, Contrast, and Saturation adjustments.
    -   High-Frequency Denoising.
    -   Adaptive B&W Thresholding.

## Prerequisites

-   **Python 3.10+**
-   **Rust & Cargo** (latest stable)
-   **Dependencies**:
    ```bash
    pip install PySide6
    ```

## Local Setup

1.  **Clone the Repository**:
    ```bash
    git clone <repository-url>
    cd ClioBulk-X
    ```

2.  **Build the Rust Core**:
    ```bash
    cd cliobulk-core
    cargo build --release
    cd ..
    ```
    *Ensure the executable `cliobulk-core.exe` is generated in `cliobulk-core/target/release/`.*

3.  **Run the Application**:
    ```bash
    python cliobulk-pro.py
    ```

## Project Structure

-   `cliobulk-pro.py`: Main application entry point (PySide6).
-   `cliobulk-core/`: Rust source code for the processing engine.
-   `cliobulk-core/src/main.rs`: Core logic, filters, and multi-threading.

## Optimization Notes

-   **Connection**: Uses a temporary JSON exchange for batch inputs to avoid OS command-line limits.
-   **Processing**: Image operations are combined into a single pass where possible to minimize memory bandwidth usage.
-   **Parallelism**: Automatically scales to all available CPU cores using a work-stealing scheduler.

## License
MIT
