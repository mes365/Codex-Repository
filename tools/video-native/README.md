# VideoNative V1.0 (Windows 11 x64)

Standalone native C++ Win32 GUI built with Microsoft Media Foundation. No Python, Qt, or FFmpeg installation required on the destination computer.

## Features
- H.264 MP4 video-only transcode (normal container metadata is not intentionally copied).
- Recompute output file MD5.
- Experimental keyed low-amplitude visual watermark insertion (not validated against robust transcoding and does not have a detector).
- Visual near-duplicate *comparison* between two input videos. 64-bit difference hash (dHash) sampled approximately every 30 decoded frames, up to 12 samples. Displays average same-position similarity.

## Limitations
- **Audio is not preserved in V1.0.** Do not use for production video where audio matters.
- dHash similarity is approximate, may fail under cropping, temporal edits, mirrored frames, text overlays, or timing changes. It is not a TikTok similarity/uniqueness score.
- Output MD5 changing does not imply content uniqueness.
- No guaranteed removal of C2PA external credentials or other content identification. There is no validated C2PA parser in this release.
- Media Foundation codec support varies by system. The encoder assumes RGB32 buffers and particular video layouts; test real clips before relying on output.
- The program has no digital code signature, so Windows SmartScreen may warn.

## Download
GitHub Actions -> Build VideoNative Win11 x64 -> successful run -> Artifacts -> VideoNative-Win11-x64.

## Build
CMake 3.23+ and Visual Studio 2022 C++ workload, or automatically via the GitHub Actions workflow.
