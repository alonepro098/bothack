# 🚀 Telegram Bot Token Studio

A modern high-performance suite to validate Telegram bot tokens you own, generate synthetic test keys, stream real-time verification logs, and export results.

---

## 🌐 Web Application Interface

A glassmorphic, dark-mode web application is included with full real-time streaming capabilities:

### Starting the Web App:
```bash
python server.py
# or double-click run_web.bat on Windows
```

### Key Web Features:
- **⚡ Live Batch Validator**:
  - Paste tokens one per line or drag & drop files (`.txt`, `.csv`).
  - Real-time Server-Sent Events (SSE) streaming verification cards.
  - Concurrency slider (1–10 threads) & rate delay control.
  - Demo / Sandbox mode toggle.
- **🎲 Mock Token Generator**:
  - Configurable count (1 to 1,000+), bot ID digit length, and secret length.
  - One-click copy, download as `.txt`, or direct *"Send to Validator & Test"*.
- **💎 Verified Hit Vault**:
  - Searchable data explorer with bot avatars, names, `@handles`, bot IDs, capabilities badges (`[groups]`, `[read-all]`, `[inline]`), latency, and direct `https://t.me/<username>` links.
  - Export to **JSON** or **CSV**.
- **💻 Cyberpunk Live Terminal**:
  - Color-coded activity feed with timestamped logs.
- **🔊 Synthetic Audio Feedback**:
  - Subtle futuristic Web Audio API chimes on new hits and skips (toggleable).

---

## 🖥️ Command-Line Interface (CLI)

You can also run validation and generation entirely from the terminal using [`validator.py`](file:///c:/Users/Ayush%20Raj/Downloads/tkn/validator.py):

```bash
# 1. Generate 20 test tokens
python validator.py --generate 20

# 2. Generate and save to tokens.txt
python validator.py --generate 50 --save-generated tokens.txt

# 3. Validate tokens from tokens.txt
python validator.py --token-file tokens.txt

# 4. Validate with export
python validator.py --token-file tokens.txt --export-json hits.json --export-csv hits.csv

# 5. Offline Demo mode
python validator.py --demo --token 111111111:DEMOtokenAAAAAAAAAAAAAAAAAAAAAAAAA
```
