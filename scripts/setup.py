#!/usr/bin/env python3
"""
scripts/setup.py

WHAT THIS IS FOR:
First-run bootstrap wizard for F.R.I.D.A.Y.
"""

from __future__ import annotations
import sys
import platform

def main():
    print('=== F.R.I.D.A.Y. Setup Wizard ===')
    
    # 1. Detect Windows version
    print(f"Windows Version: {platform.version()}")
    
    # 2. Detect hardware (CPU/RAM/GPU/VRAM)
    print("Detecting hardware...")
    try:
        from friday.models.hardware import detect_hardware, recommend_profile
        hw = detect_hardware()
        print(f"Hardware: {hw}")
        profile = recommend_profile(hw)
    except ImportError:
        print("friday module not found yet. Using fallback profile.")
        profile = "balanced.yaml"
        
    # 3. Check microphone/speaker
    print("Checking audio devices... (skipped)")
    
    # 4. Check Ollama installation
    print("Checking Ollama installation... (skipped)")
    
    # 5. Check browser runtime (Playwright)
    print("Checking browser runtime... (skipped)")
    
    # 6. Select hardware profile
    print(f"Selected hardware profile: {profile}")
    
    # 7. Show recommended models
    print("Recommended models: qwen2:8b, qwen2-vl")
    
    # 8. Download missing models
    print("Downloading missing models... (skipped)")
    
    # 9. Initialize database
    print("Initializing database... (skipped)")
    
    # 10. Initialize directories
    print("Initializing directories... (skipped)")
    
    # 11. Validate configuration
    print("Validating configuration... (skipped)")
    
    # 12. Run health checks
    print("Running health checks... (skipped)")
    
    # 13. Run smoke tests
    print("Running smoke tests... (skipped)")
    
    print('Setup Complete!')

if __name__ == '__main__':
    main()
