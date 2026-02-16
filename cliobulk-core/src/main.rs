//! ---------------------------------------------------------------------------------------
//! ClioBulk-X Core Engine
//! ---------------------------------------------------------------------------------------
//! A high-performance, multi-threaded image processing backbone designed for high-throughput
//! batch operations. This core leverages Rust's safety and concurrency model to handle
//! both standard web formats and professional digital RAW files (ARW, CR2, NEF, DNG).
//!
//! FEATURES:
//! - Parallelized RAW decoding with optimized sub-sampling.
//! - SIMD-accelerated pixel manipulation (via Rayon and image crates).
//! - Single-pass filter application to minimize memory bandwidth overhead.
//! - Real-time IPC progress reporting via JSON-formatted stdout.
//!
//! @author Alejandro Ramírez
//! @version 2.2.0
//! @license MIT
//! ---------------------------------------------------------------------------------------

use clap::Parser;
use image::{DynamicImage, ImageBuffer, Rgb};
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::fs::File;
use std::io::BufReader;

/// Command-line argument schema for the core processor.
///
/// Provides a structured interface for the parent Python GUI to pass processing 
/// parameters and target file lists.
#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Args {
    /// Serialized JSON string of `ProcessOptions`.
    /// Encapsulates all filters and image adjustments to be applied.
    #[arg(short, long)]
    options: String,

    /// Comma-separated list of absolute paths OR path to a JSON manifest file.
    #[arg(short, long)]
    inputs: String,

    /// Target destination directory for processed outputs.
    #[arg(short, long)]
    output: String,
}

/// Image adjustment parameters and filter toggles.
///
/// Designed to be compatible with JSON serialization for cross-language IPC.
#[derive(Debug, Serialize, Deserialize, Clone)]
struct ProcessOptions {
    /// Normalized brightness offset: -1.0 (black) to 1.0 (white).
    pub brightness: f32, 
    /// Contrast scale factor: 0.0 to 3.0 (1.0 is neutral).
    pub contrast: f32,   
    /// Saturation scale factor: 0.0 to 2.0 (1.0 is neutral).
    pub saturation: f32, 
    /// Toggles adaptive thresholding for document scanning/high-contrast effects.
    pub adaptive_threshold: bool,
    /// Toggles median-filter based denoising to reduce sensor noise.
    pub denoise: bool,
}

/// Structured progress update for IPC.
///
/// Emitted to stdout as a JSON object, allowing the parent process to 
/// update UI progress bars and status labels in real-time.
#[derive(Serialize)]
struct Progress {
    /// Completion percentage (0.0 - 100.0).
    pub progress: f32,
    /// Filename currently being processed.
    pub current_file: String,
    /// State description (e.g., "processing", "error", "complete").
    pub status: String,
}

/// Decodes professional RAW image files with an emphasis on speed over fidelity.
///
/// Implements a "half-size" demosaicing algorithm that skips full interpolation 
/// by mapping Bayer patterns directly to RGB pixels. This is ideal for bulk 
/// processing and preview generation where performance is critical.
/// 
/// # Supported Formats
/// - Sony (.ARW)
/// - Canon (.CR2)
/// - Nikon (.NEF)
/// - Adobe Digital Negative (.DNG)
/// 
/// # Arguments
/// * `path` - Path to the RAW file on disk.
/// 
/// # Returns
/// * `anyhow::Result<DynamicImage>` - The decoded RGB image or a decoding error.
fn decode_raw(path: &str) -> anyhow::Result<DynamicImage> {
    let raw = rawloader::decode_file(path).map_err(|e| anyhow::anyhow!(e.to_string()))?;
    let width = raw.width;
    let height = raw.height;
    
    // Perform parallel demosaicing by sub-sampling the Bayer pattern.
    // This provides a significant speedup for preview/batch generation.
    match raw.data {
        rawloader::RawImageData::Integer(ref data) => {
            let out_w = width / 2;
            let out_h = height / 2;
            let mut vec = vec![0u8; out_w * out_h * 3];
            
            vec.par_chunks_exact_mut(out_w * 3)
                .enumerate()
                .for_each(|(y, row)| {
                    for x in 0..out_w {
                        let idx = (y * 2) * width + (x * 2);
                        // Sub-sampling R, (G1+G2)/2, B from the Bayer grid
                        row[x * 3] = (data[idx] >> 8) as u8;
                        row[x * 3 + 1] = (((data[idx + 1] as u32 + data[idx + width] as u32)) >> 9) as u8;
                        row[x * 3 + 2] = (data[idx + width + 1] >> 8) as u8;
                    }
                });
            
            let img = ImageBuffer::<Rgb<u8>, _>::from_raw(out_w as u32, out_h as u32, vec)
                .ok_or_else(|| anyhow::anyhow!("Failed to create image buffer"))?;
            Ok(DynamicImage::ImageRgb8(img))
        },
        rawloader::RawImageData::Float(ref data) => {
            let out_w = width / 2;
            let out_h = height / 2;
            let mut vec = vec![0u8; out_w * out_h * 3];
            
            vec.par_chunks_exact_mut(out_w * 3)
                .enumerate()
                .for_each(|(y, row)| {
                    for x in 0..out_w {
                        let idx = (y * 2) * width + (x * 2);
                        row[x * 3] = (data[idx].clamp(0.0, 1.0) * 255.0) as u8;
                        row[x * 3 + 1] = ((data[idx + 1] + data[idx + width]) * 127.5).clamp(0.0, 255.0) as u8;
                        row[x * 3 + 2] = (data[idx + width + 1].clamp(0.0, 1.0) * 255.0) as u8;
                    }
                });

            let img = ImageBuffer::<Rgb<u8>, _>::from_raw(out_w as u32, out_h as u32, vec)
                .ok_or_else(|| anyhow::anyhow!("Failed to create image buffer"))?;
            Ok(DynamicImage::ImageRgb8(img))
        }
    }
}

/// Applies a chain of visual filters and adjustments to an image.
///
/// To optimize cache locality and reduce memory iterations, primary color 
/// adjustments (Brightness, Contrast, Saturation) are fused into a single 
/// parallelized pass over the pixel buffer.
///
/// # Arguments
/// * `img` - The source `DynamicImage`.
/// * `options` - A reference to the `ProcessOptions` to apply.
///
/// # Returns
/// * `DynamicImage` - The modified image.
fn apply_filters(img: DynamicImage, options: &ProcessOptions) -> DynamicImage {
    let mut rgb = img.to_rgb8();
    
    // Multi-adjust pass: Processes pixel channels in a single parallel iteration.
    if options.brightness != 0.0 || options.contrast != 1.0 || options.saturation != 1.0 {
        let b = options.brightness * 255.0;
        let c = options.contrast;
        let s = options.saturation;
        
        rgb.pixels_mut().par_bridge().for_each(|pixel| {
            // Fused Brightness & Contrast
            for channel in 0..3 {
                let mut v = pixel[channel] as f32;
                // Linear adjustment: (v - 128) * c + 128 + b
                v = (v - 128.0) * c + 128.0 + b;
                pixel[channel] = v.clamp(0.0, 255.0) as u8;
            }
            
            // Perceptual saturation adjustment using standard ITU-R 601 luma weights
            if s != 1.0 {
                let r = pixel[0] as f32;
                let g = pixel[1] as f32;
                let b = pixel[2] as f32;
                let l = 0.299 * r + 0.587 * g + 0.114 * b;
                pixel[0] = (l + (r - l) * s).clamp(0.0, 255.0) as u8;
                pixel[1] = (l + (g - l) * s).clamp(0.0, 255.0) as u8;
                pixel[2] = (l + (b - l) * s).clamp(0.0, 255.0) as u8;
            }
        });
    }

    let mut final_img = DynamicImage::ImageRgb8(rgb);

    // Apply optional Denoising (3x3 Median Filter)
    if options.denoise {
        if let DynamicImage::ImageRgb8(rgb_inner) = final_img {
             final_img = DynamicImage::ImageRgb8(imageproc::filter::median_filter(&rgb_inner, 1, 1));
        }
    }

    // Apply optional Adaptive Thresholding for high-contrast/document-style output
    if options.adaptive_threshold {
        let luma = final_img.to_luma8();
        final_img = DynamicImage::ImageLuma8(imageproc::contrast::adaptive_threshold(&luma, 10));
    }

    final_img
}

/// Core Orchestrator for ClioBulk-X.
///
/// Responsible for:
/// 1. Bootstrapping the CLI environment and parsing parameters.
/// 2. Discovering input assets (from string lists or JSON manifests).
/// 3. Spawning a high-concurrency Rayon pool for image processing.
/// 4. Managing file-system operations and IPC reporting.
fn main() -> anyhow::Result<()> {
    let args = Args::parse();
    let options: ProcessOptions = serde_json::from_str(&args.options)?;
    
    // Resolve input sources: supports raw string lists or JSON path arrays.
    let input_paths: Vec<String> = if args.inputs.ends_with(".json") && Path::new(&args.inputs).exists() {
        let file = File::open(&args.inputs)?;
        let reader = BufReader::new(file);
        serde_json::from_reader(reader)?
    } else {
        args.inputs.split(',').map(|s| s.to_string()).collect()
    };

    let total = input_paths.len();
    let counter = Arc::new(AtomicUsize::new(0));
    let output_dir = PathBuf::from(&args.output);

    // Ensure output target exists
    if !output_dir.exists() {
        std::fs::create_dir_all(&output_dir)?;
    }

    // Parallel Processing Loop: Rayon automatically scales across all available CPU cores.
    input_paths.into_par_iter().for_each(|path_str| {
        let path = Path::new(&path_str);
        let name = path.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_else(|| "unknown".to_string());
        
        let c = counter.fetch_add(1, Ordering::SeqCst);
        let prog = Progress {
            progress: (c as f32 / total as f32) * 100.0,
            current_file: name.clone(),
            status: "processing".to_string(),
        };
        // Print JSON progress update for the parent GUI process
        println!("{}", serde_json::to_string(&prog).unwrap());

        let res = (|| -> anyhow::Result<()> {
            let name_lower = name.to_lowercase();
            // Select appropriate decoder based on file extension
            let mut img = if name_lower.ends_with(".arw") || 
                           name_lower.ends_with(".cr2") || 
                           name_lower.ends_with(".nef") || 
                           name_lower.ends_with(".dng") {
                decode_raw(&path_str)?
            } else {
                image::open(path)?
            };

            img = apply_filters(img, &options);
            // Save as JPEG with default compression
            let out_path = output_dir.join(format!("processed_{}.jpg", name));
            img.save(out_path)?;
            Ok(())
        })();

        // Error handling during the batch loop: report error but continue with the remaining items.
        if let Err(e) = res {
            let err_prog = Progress {
                progress: (c as f32 / total as f32) * 100.0,
                current_file: name,
                status: format!("error: {}", e),
            };
            println!("{}", serde_json::to_string(&err_prog).unwrap());
        }
    });

    // Signal completion to the parent process
    println!("{}", serde_json::to_string(&Progress {
        progress: 100.0,
        current_file: "Done".to_string(),
        status: "complete".to_string(),
    }).unwrap());

    Ok(())
}
