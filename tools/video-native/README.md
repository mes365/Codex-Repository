# VideoNative V1.1 — Windows 11 x64

Standalone C++ Win32 + Microsoft Media Foundation prototype. No Python, Qt or FFmpeg installation is required on the destination computer.

## Features
- Single MP4 H.264 re-encode and output MD5.
- Experimental low-amplitude keyed visual watermark insertion (no extraction/verification implementation).
- dHash approximate visual similarity comparison of sampled video frames.
- Batch process MP4 files in the folder of the selected input; writes *_v1.mp4 outputs into the selected output file's folder.
- Best-effort stereo PCM decoding to AAC audio output; requires real-input validation.
- Basic top-level ISO BMFF UUID box detection for a C2PA identifier.

## Critical limitations
- **Cloud compilation success does not mean audio playback, synchronisation, or batch processing has been tested.**
- Audio preservation is best-effort only and is not verified. Unsupported codecs, channel layouts or input files may fail.
- C2PA scanning is neither comprehensive detection nor signature verification. External manifests, nested boxes and other content credentials may go undetected. A negative scan is NOT proof that no C2PA exists.
- File MD5 changing doesn't make video visually unique.
- Experimental watermark has not been validated against re-encoding and has no verification implementation.
- No platform-unoriginal-content score is claimed.
- Unsigned executable may cause Windows SmartScreen warnings.

## Download
Go to GitHub Actions -> Build VideoNative Win11 x64 -> latest successful run -> Artifacts -> VideoNative-Win11-x64.

## Build
CMake 3.23+, Visual Studio 2022 C++ workload, or GitHub Actions workflow.
