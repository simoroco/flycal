# 🎬 MyFlix

<p align="center">
  <img src="./app/assets/logo.png" alt="MyFlix Logo" width="150"/>
</p>

<p align="center">
  <strong>Modern Media Library Manager & Streamer</strong>
</p>

<p align="center">
  <a href="https://github.com/simoroco/myflix/stargazers"><img src="https://img.shields.io/github/stars/simoroco/myflix?style=flat-square" alt="GitHub stars"></a>
  <a href="https://github.com/simoroco/myflix/issues"><img src="https://img.shields.io/github/issues/simoroco/myflix?style=flat-square" alt="GitHub issues"></a>
  <a href="https://github.com/simoroco/myflix/network/members"><img src="https://img.shields.io/github/forks/simoroco/myflix?style=flat-square" alt="GitHub forks"></a>
  <a href="https://github.com/simoroco/myflix/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License"></a>
  <a href="https://hub.docker.com/r/simoroco/myflix"><img src="https://img.shields.io/docker/pulls/simoroco/myflix?style=flat-square" alt="Docker pulls"></a>
  <img src="https://img.shields.io/badge/python-%3E%3D3.9-brightgreen?style=flat-square" alt="Python version">
  <img src="https://img.shields.io/badge/platform-linux%20%7C%20macos%20%7C%20windows-blue?style=flat-square" alt="Platform">
</p>

<p align="center">
  <em>A modern, self-hosted web interface for streaming media to Chromecast with smart transcoding</em><br>
  <em>Perfect for Raspberry Pi, Synology NAS, and desktop setups</em>
</p>

---

MyFlix lets you browse your local media library and cast it to any Chromecast device through a clean web interface. It handles codec detection, H.265→H.264 transcoding, multiple audio/subtitle tracks, and VLC-based streaming — all automatically.

⭐ **Star this repo** if you find it useful • 🐛 **Report issues** • 🤝 **Contribute**

## 📚 Table of Contents

- [✨ Key Features](#-key-features)
- [⚡ Quick Start](#-quick-start)
- [🖥️ Screenshots](#-screenshots)
- [🚀 Production Deployment](#-production-deployment)
- [⚙️ How does it work?](#-how-does-it-work)
- [🔧 Configuration](#-configuration)
- [🛠️ Technologies](#-technologies)
- [🐛 Troubleshooting](#-troubleshooting)
- [� License](#-license)
- [🤝 Community & Roadmap](#-community--roadmap)

## ✨ Key Features

- 🎬 **Multi-Player Support** — Basic/Direct, VLC Local, and VLC Remote streaming
- 🔄 **Smart Transcoding** — Automatic H.265 to H.264 conversion for compatibility
- 🎵 **Audio & Subtitle Tracks** — Select from multiple audio tracks and subtitles
- 📱 **Chromecast Discovery** — Automatic detection of Chromecast devices on your network
- 🎮 **Playback Controls** — Play, pause, seek, skip intro, mute, and volume control
- 💻 **Responsive UI** — Clean, modern interface with real-time status updates
- 🐳 **Docker Support** — Easy deployment with Docker Compose on Raspberry Pi and Synology NAS
- 🖥️ **Native Mode** — Run locally on macOS/Windows for full Chromecast discovery
- ⌨️ **Keyboard Shortcuts** — Space for play/pause, M for mute/unmute

## ⚡ Quick Start

```bash
git clone https://github.com/simoroco/myflix.git
cd myflix
./start.sh
```

- Default UI: `http://localhost:2000`
- The script auto-detects your OS and installs all prerequisites (Python, FFmpeg, VLC)
- Docker image: [simoroco/myflix](https://hub.docker.com/r/simoroco/myflix)

```bash
docker pull simoroco/myflix:latest
```

## 🖥️ Screenshots

<p align="center">
  <img src="./Screens.gif" alt="MyFlix Screenshots" width="100%"/>
</p>

> **Note:** The screenshots show the main features of MyFlix including the media browser, Chromecast connection, playback controls, and transcoding progress.

## 🚀 Production Deployment

Deploy MyFlix on **Raspberry Pi 5**, **Synology NAS**, or any **Linux** server using Docker.

### 📋 Prerequisites

- **OS**: Linux, macOS, or Windows
- Docker and Docker-Compose installed
- Port 2000 available
- Media files accessible on the system

### ✨ Quick Deployment

Use the **automatic start script** that works on all platforms:

```bash
mkdir myflix && cd myflix

# Download deployment files
wget https://raw.githubusercontent.com/simoroco/myflix/main/deploy_prod/docker-compose.yml
wget https://raw.githubusercontent.com/simoroco/myflix/main/deploy_prod/.env.example

# Configure
cp .env.example .env
nano .env  # Edit MEDIA_PATH and other settings

# Create directories
mkdir -p data/media data/data/subtitles data/cache/hls data/logs

# Start
docker-compose up -d
```

Using `start.sh` is recommended for macOS and Windows platforms only. It's not required to use in Linux systems.

## ⚙️ How does it work?

### 1. Media Discovery
- Browse your local filesystem through the web interface
- Automatic codec detection (H.264, H.265/HEVC)
- Multiple audio and subtitle track detection

### 2. Chromecast Connection
- Automatic discovery of Chromecast devices on your network
- Real-time connection status
- Device selection from the interface

### 3. Streaming Methods
- **Direct Streaming** — For H.264 compatible files, no transcoding, lowest latency
- **VLC Remote** — Server-side transcoding with VLC, H.265→H.264 conversion, custom track selection
- **VLC Local** — Client-side VLC streaming, requires VLC on client machine

### 4. Smart Transcoding
- Automatic H.265 to H.264 conversion when needed
- Hardware acceleration support (VAAPI, V4L2M2M)
- Configurable quality presets
- Transcoded files cached for faster subsequent playback

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MEDIA_PATH` | Path to media files | `./data/media` |
| `SUBTITLES_PATH` | Path to subtitle files | `./data/data/subtitles` |
| `FFMPEG_THREADS` | Number of CPU threads for transcoding | `4` |
| `TRANSCODE_QUALITY` | Quality preset (low/medium/high/ultra) | `medium` |
| `NETWORK_MODE` | Docker network mode (bridge/host) | `bridge` (dev), `host` (prod) |
| `TZ` | Timezone | `Europe/Paris` |

### Network Modes

- **Bridge Mode (macOS/Windows)** — Port mapping required, compatible with Docker Desktop, limited Chromecast discovery (use native mode instead)
- **Host Mode (Linux/Raspberry Pi)** — Direct network access, optimal Chromecast discovery, no port mapping needed

## 🛠️ Technologies

- **Backend**: Python, Flask
- **Media**: FFmpeg, VLC, pychromecast
- **Frontend**: HTML5, CSS3, JavaScript
- **Containerization**: Docker, Docker Compose
- **Streaming**: Chromecast SDK, HTTP streaming

## 🎞️ Video Formats & Compatibility

MyFlix ensures **100% compatibility** with Chromecast 1st Gen and HTML5 web players through unified transcoding:

### Supported Output Format
- **Video**: H.264 (High Profile, Level 4.1) - preset `medium`, CRF `20`
- **Audio**: AAC-LC @ 192kbps (stereo) or 640kbps (5.1 surround)
- **Container**: MP4 with `faststart` flag for instant playback
- **Resolution**: Up to 1080p@30fps or 720p@60fps

### Supported Input Formats
- **Containers**: MP4, MKV, WebM, AVI, MOV, WMV, FLV, TS, M2TS, 3GP
- **Video Codecs**: H.264, H.265/HEVC, VP8, VP9 (auto-transcoded to H.264)
- **Audio Codecs**: AAC, MP3, Opus, Vorbis, FLAC, DTS, AC3, E-AC3 (auto-transcoded to AAC)
- **Subtitles**: SRT, ASS, SSA, VTT, SUB (embedded as soft subs)

It's recommanded to use `myflix_converter.sh` to scan & convert your media files to be full compatible with MyFlix/Chromecast 1st Gen & HTML5 web players.

## 📄 License

This project is distributed under the **MIT License**.
See [LICENSE](LICENSE) file for details.

## 🤝 Community & Roadmap

- ⭐️ Star the repo if you find it useful.
- 🐛 [Open an issue](https://github.com/simoroco/myflix/issues) for bugs or feature ideas.
- 🙌 Check the roadmap and "good first issue" label to start contributing.

**MyFlix**
Copyright © 2026 - All rights reserved.
