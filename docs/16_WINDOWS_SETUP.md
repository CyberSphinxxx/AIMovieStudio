# 16 — Windows developer and user setup

## Principles
Never hardcode personal paths. No manual command prompt required for typical end-user creation after first run. Dev installs happen in isolated local environments; install prompts explain sizes/permissions. Do not bundle multi-GB weights in main application ZIP. Use official sources only.

## Codex machine inspection (non-destructive)
- `nvidia-smi` (NVIDIA driver, VRAM), `Get-CimInstance Win32_OperatingSystem` (RAM), `Get-PSDrive` (disk).
- `python --version`, `node --version`, `npm --version`, `ffmpeg -version`, `ffprobe -version`, `git --version`.
- Check GPU CUDA tooling from the actual Python environment. Document all results; no assumption that CUDA toolkit on PATH is required for a compatible PyTorch wheel.
- Identify output root on roomy SSD; projected weight downloads may exceed 30 GB for FramePack.

## Proposed dev startup
Backend with local virtualenv or `uv` package manager after dependencies verified; frontend Vite dev server; `scripts/dev.ps1` launches both and checks health. Include one-command `scripts/verify.ps1`, `scripts/demo.ps1` and `scripts/run.ps1`. Use configured ports and show actual local URL. A Windows Defender/firewall prompt should not require external bind.

## First-run app steps
1. App checks media tools, GPU, RAM, disk, provider installations and operating mode.
2. If no model installed: offer `Try Demo` immediately and `Set Up Local Generation` with free/licensed badge, actual model sizes, required RAM/VRAM and download approval.
3. Download from official model hosting only (HTTPS, checksum when available), progress with pause/resume if supported; disk checks and rollback for partial files.
4. Run built-in 1-image + short-video self-test, records evidence/measurements; only then label provider 'Ready'.
5. User enters prompt and presses Create. Installed models may be switched later without losing project.

## Recovery
Failed dependencies produce actionable messages with logs/redacted env, link official sources, one-click retry, not a broken launcher. Keep `Help > Diagnostics > Export Support Bundle` (no scripts/voice secrets by default). Do not install drivers, CUDA toolkit or Conda globally without user approval.

## Windows-specific notes
Power profiles, laptop thermal conditions, display GPU consumers, sleeping under load, path lengths, Unicode, DLL conflicts, shell quoting, process groups, SIGTERM differences, antivirus false positives, no admin user, firewall/local-only port. Test on clean Windows account before release.
