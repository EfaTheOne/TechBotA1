#!/bin/bash

# ══════════════════════════════════════════════════════════════════════════════
# TECHBOT A1 PHOENIX - LINUX INSTALLATION SCRIPT
# ══════════════════════════════════════════════════════════════════════════════
# This script installs all system dependencies and sets up a Python virtual 
# environment (venv) for the TechBot A1 framework.
# ══════════════════════════════════════════════════════════════════════════════

# Text formatting
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}🚀 Initializing TechBot A1 Phoenix Installation...${NC}"

# 1. Update System
echo -e "\n${YELLOW}[1/5] Updating system package list...${NC}"
sudo apt update

# 2. Install System Dependencies (Apt)
echo -e "\n${YELLOW}[2/5] Installing system dependencies...${NC}"
# Components:
# python3-venv: For virtual environments
# python3-tk: For GUI (Tkinter)
# portaudio19-dev, libasound2-dev: For PyAudio
# libpcap-dev: For Scapy (Network Sniffing)
# scrot, libxtst-dev: For PyAutoGUI (Screen interaction)
# espeak, ffmpeg: For Pyttsx3 (Text-to-Speech)
sudo apt install -y \
    python3-dev \
    python3-pip \
    python3-tk \
    python3-venv \
    portaudio19-dev \
    libasound2-dev \
    libpcap-dev \
    scrot \
    libxtst-dev \
    at-spi2-core \
    espeak \
    ffmpeg \
    libjpeg-dev \
    zlib1g-dev \
    libpng-dev

# 3. Setup Virtual Environment (venv)
echo -e "\n${YELLOW}[3/5] Setting up Python Virtual Environment...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓ Created new venv.${NC}"
else
    echo -e "${CYAN}ℹ venv already exists.${NC}"
fi

# 4. Activate venv and Install Python Requirements
echo -e "\n${YELLOW}[4/5] Installing Python libraries in venv...${NC}"
source venv/bin/activate

# Upgrade pip first
pip install --upgrade pip

# Install requirements
if [ -f "requirements.txt" ]; then
    echo -e "${CYAN}Installing from requirements.txt...${NC}"
    pip install -r requirements.txt
else
    echo -e "${RED}⚠ requirements.txt not found! Installing manual list...${NC}"
    pip install customtkinter psutil Pillow pyttsx3 SpeechRecognition groq pyaudio requests cryptography scapy pyautogui beautifulsoup4
fi

# 5. Finale - Create Launcher
echo -e "\n${YELLOW}[5/5] Finalizing...${NC}"
chmod +x techbot_gui.py

echo -e "\n${GREEN}══════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ INSTALLATION COMPLETE!${NC}"
echo -e "${CYAN}To run TechBot A1, use the following commands:${NC}"
echo -e "${YELLOW}  source venv/bin/activate${NC}"
echo -e "${YELLOW}  sudo ./venv/bin/python3 techbot_gui.py${NC}"
echo -e "${CYAN}(Note: sudo is required for network sniffing/packet capture features)${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════════════════════${NC}"
