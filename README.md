# 🚛 Moovez Vision Agent

AI-powered computer vision system that analyzes images of furniture and household items to automatically generate accurate moving quotes. Eliminates manual inventory creation and provides instant, data-driven estimates.

---

### Demo Link - [Streamlit App](https://visionagent.streamlit.app/) 
##### *you may need to update the link here*
---

## 🎯 Overview

Moovez Vision Agent analyzes room images to:
- Identify and categorize furniture (80+ item types, 24+ categories)
- Calculate volume, weight, and time requirements
- Recommend optimal vehicles and workforce
- Generate detailed pricing estimates

**Powered by:** Google Gemini 2.5 Flash & OpenAI GPT-4 Vision

---

## 🚀 Quick Start

### Installation
```bash
git clone https://github.com/SUKHMAN-SINGH-1612/Moovez-Vision-Agent.git
cd Moovez-Vision-Agent
pip install -r requirements.txt
```

### Configuration
Create `.env` file:
```env
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=your_openai_api_key_here  # Optional
```

### Run
```bash
# Command Line (Version 9 - Latest with Modular Architecture)
cd "Version 9/Gemini"
python vision-agent.py

# Command Line (Version 5 - Video Support)
cd "Version 5/Gemini"
python vision-agent.py

# Web Interface (Version 9 — Quotetron UI)
streamlit run app.py
# Same app: streamlit run "UI App/app.py"
```

---

## ☁️ Deploying on Streamlit Cloud

You can deploy the Moovez Vision Agent web interface for free on [Streamlit Community Cloud](https://streamlit.io/cloud) so anyone can access it from a browser without installing anything locally.

### Prerequisites

- A [GitHub](https://github.com) account with this repository forked or pushed
- A [Streamlit Community Cloud](https://share.streamlit.io) account (free)
- A [Google AI Studio](https://makersuite.google.com/app/apikey) Gemini API key

### Step 1: Push the Repository to GitHub

Ensure your code is pushed to a GitHub repository (public or private).

```bash
git add .
git commit -m "Prepare for Streamlit Cloud deployment"
git push origin main
```

### Step 2: Create a New App on Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with your GitHub account.
2. Click **"New app"**.
3. Under **Repository**, select your forked/pushed repository (e.g., `your-username/Moovez-Vision-Agent`).
4. Under **Branch**, select `main` (or whichever branch you want to deploy).
5. Under **Main file path**, enter either:
   ```
   app.py
   ```
   or `UI App/app.py` (same application).
6. Click **"Deploy!"**.

Streamlit Cloud will install the dependencies listed in `requirements.txt` automatically and launch the app.

### Step 3: Add Environment Variables (Secrets)

The app requires a `GEMINI_API_KEY` to call the Google Gemini API. On Streamlit Cloud, API keys and other sensitive values are managed through **Secrets** — never commit them to your repository.

#### Adding Secrets via the Streamlit Cloud Dashboard

1. In your app's dashboard on [share.streamlit.io](https://share.streamlit.io), click the **⋮ (three-dot menu)** next to your app and select **"Settings"**.
2. Click the **"Secrets"** tab.
3. Paste your secrets in **TOML format**:
   ```toml
   GEMINI_API_KEY = "your_gemini_api_key_here"
   ```
4. Click **"Save"**. The app will automatically restart and pick up the new secrets.

> **How it works:** Streamlit Cloud injects secrets defined in the Secrets tab as environment variables at runtime. The app's existing `os.getenv('GEMINI_API_KEY')` call will find the key automatically — no code changes are needed.

#### Example Secrets (TOML format)

```toml
# Required
GEMINI_API_KEY = "AIza..."

# Optional (only needed for OpenAI-based versions)
OPENAI_API_KEY = "sk-..."
```

> **Note:** Do **not** commit a `.env` file with real API keys to your repository. The `.env` file is only used for local development.

### Step 4: Access Your Deployed App

Once deployed, Streamlit Cloud provides a public URL in the format:
```
https://<your-app-name>.streamlit.app
```

Share this URL with anyone who needs access to the Vision Agent.

---

## 📦 Versions

### **Version 9** - Logistics Tuning & Refinement ⭐ **Latest**
- **Path**: `/Version 9/Gemini/`
- **Model**: Gemini 2.5 Flash
- **Key Features**:
  - **82% Volume Buffer rule** for safe vehicle selection
  - **Movers restricted to 2** for small vehicles (Pickup, Cargo Van, 10'-12' Truck)
  - **Travel Time** included in pricing calculations
  - **Updated Pricing**: $170/hr for 2-person crew
  - **🏗️ Modular architecture** with abstraction, inheritance, and polymorphism
  - **🔧 Separation of concerns** - Clean modular structure
  - **✅ 100% backward compatible**
  - **📹 Video file support**
  - **📱 iPhone HEIC/HEIF image support**
  - **🛗 Additive elevator model** - Per-trip time instead of percentage inflation
  - **⚖️ Explicit load+unload split** — `total_time = load_time + (load_time × category_ratio)` where `load_time = baseTime` from JSON. Default unload ratio = 0.65× (boxes = 0.90×, fragile = 0.80×, appliances = 0.55×). Replaced the old flat 1.2× then 1.65× multipliers that inflated-then-deflated the same number.
  - **👷 Interactive crew override** — slider in the Logistics tab lets the user change the number of movers (2–6) post-analysis. Time and price recalculate instantly without re-running AI. Algorithm recommendation is always shown alongside the override. Capped by vehicle seating.
  - **💰 Pricing range display** — Total Expected Price shown as `$min – $max` derived from the `Vision_Agent_Hour_Range_Mapping.csv` hour range (same source as the Estimated Range clock). `base_price_min = min_hours × 60 × movers × wage_rate`, `base_price_max = max_hours × 60 × movers × wage_rate`, both with GST.
  - **Production-ready** - Maintainable, scalable codebase
- **Best For**: Production use, precise logistics, maintaining safety margins

### **Version 5** - Video Support
- **Path**: `/Version 5/Gemini/`
- **Model**: Gemini 2.5 Flash
- **Key Features**:
  - **📹 Video file support** (.mp4, .mov, .avi, .mkv, .webm, etc.)
  - **📱 iPhone HEIC/HEIF image support**
  - **Mixed media uploads** (images + videos in single request)
  - Single API call for all files (batch processing)
  - Smart file type detection and processing
  - Automatic video processing wait
  - All Version 4 features retained
- **Best For**: Video walkthroughs, large properties, virtual tours, iPhone photos
- **Note**: Monolithic architecture (1188-line single file)

### **Version 4** - File API Optimization
- **Path**: `/Version 4/Gemini/`
- **Model**: Gemini 2.5 Flash
- **Key Features**:
  - **Single API call** for multiple images (uses File API)
  - 40-50% faster processing vs Version 3
  - Reduced API costs through batch processing
  - Disabled thinking budget for faster responses
  - Same accuracy with optimized performance
- **Best For**: Production use, cost-efficiency, multiple images

### **Version 3** - Database-Driven System
- **Path**: `/Version 3/`
- **Models**: Gemini 2.0 Flash & OpenAI GPT-4 Vision
- **Key Features**:
  - Pre-calculated volume/weight from JSON database
  - Advanced size classification (S/M/L)
  - Multi-vehicle optimization
  - Fatigue multipliers for stairs
  - Separate API call per image
- **Best For**: OpenAI integration, detailed item analysis

### **Version 2** - AI Estimation System
- **Path**: `/Version 2/`
- **Models**: Gemini & OpenAI GPT-4 Vision
- **Key Features**:
  - AI calculates dimensions/weight directly
  - Basic category matching
  - Single vehicle selection
- **Note**: Higher API costs, slower processing

---

## ✨ Key Features

- **🏗️ Modular Architecture**: Clean separation with abstraction, inheritance, polymorphism (V6)
- **🧪 Performance Testing**: Run 5 iterations with statistical analysis and graphs (UI App)
- **📹 Video & Image Analysis**: Process videos and images in one batch
- **Multi-File Support**: Upload multiple images and/or videos simultaneously
- **Smart Item Detection**: 80+ item types with size classification
- **Video Processing**: Automatic frame extraction and analysis
- **Logistics Calculation**: Volume, weight, time, access factors (stairs = multiplicative friction, elevator = additive per-trip model)
- **Vehicle Selection**: Optimal truck recommendations with multi-vehicle support
- **Dynamic Pricing**: Hourly rates, GST, shown as a min–max range derived from the hour-range CSV
- **👷 Crew Override**: Post-analysis slider to explore time/cost trade-offs for different crew sizes
- **Web Interface**: Streamlit UI with image/video upload, performance testing, and export

---

## 💻 Usage Examples

### Command Line
```bash
# Version 9 (Modular Architecture - Recommended)
cd "Version 9/Gemini"
python vision-agent.py

# Version 5 (Monolithic - Also works)
cd "Version 5/Gemini"
python vision-agent.py
```
**Interactive Prompts:**
- Media file path(s) - images and/or videos (comma-separated)
- Pickup/dropoff access type (ground/stairs/elevator)
- Number of floors
- Travel time

**Supported Media Formats:**
- Images: .jpg, .jpeg, .png, .gif, .bmp, .webp, .tiff, .heic, .heif (iPhone)
- Videos: .mp4, .mov, .avi, .mkv, .webm, .flv, .wmv, .m4v

### Streamlit UI
```bash
# From repository root (recommended)
streamlit run app.py
```
Upload images and/or videos, configure access settings, view detailed quotes. The root `app.py` is a thin launcher; implementation lives in `UI App/app.py`.

**Features:**
- **V9 Integration**: Uses modular backend V7 for better maintainability (Version 9)
- **Performance Testing**: Run 5 iterations to measure AI consistency
- **Statistical Analysis**: Graphs showing KPI variations across runs
- **Video Support**: Drag-and-drop interface for mixed media
- **Export Options**: JSON results and CSV statistics

---

## 🔧 Technical Details

### Architecture
```
Images/Videos → AI Vision Model → Item Detection → JSON Database → 
Logistics Calculator → Vehicle Selection → Quote Generation
```

### Core Components
- **`MoovEZVisionAnalyzerV7`**: Modular orchestrator (V9 - Recommended)
  - `modules/base.py`: Abstract base classes
  - `modules/file_handlers.py`: Polymorphic file handling
  - `modules/calculator.py`: Logistics calculations
  - `modules/ai_client.py`: AI service abstraction
- **`MoovEZVisionAnalyzerV5`**: Monolithic implementation (V5 - Legacy)
- **Data Files**: 
  - `moving_items_logistics_v2.json` (80+ items)
  - `moving_calculation_rules.json` (calculation rules)

### Performance (Version 6)
- **Same as V5**: No performance penalty from modular architecture
- **Image Analysis**: ~2-3 seconds per image
- **Video Processing**: ~15-30 seconds per video (30-60 sec video)
- **Calculation**: <1 second
- **API Calls**: 1 (batch upload for all media)
- **Code Metrics**: 62% reduction in main file size (1188 → 450 lines)

### Performance (Version 5)
- **Image Analysis**: ~2-3 seconds per image
- **Video Processing**: ~15-30 seconds per video (30-60 sec video)
- **Calculation**: <1 second
- **API Calls**: 1 (batch upload for all media)

### Performance (Version 4)
- **Image Analysis**: ~2-3 seconds per image
- **Calculation**: <1 second
- **API Calls**: 1 (batch upload)

### Calculation Logic
```
load_time   = baseTime                           # from JSON
unload_time = baseTime * category_unload_ratio   # varies by item type
total_time  = load_time + unload_time

Total Time = Loading + Travel + Unloading
Loading    = sum of all load_time  + Disassembly + Access Time
Unloading  = sum of all unload_time + Access Time
Stairs     = Multiplicative friction (effort scales per flight)
Elevator   = Additive per-trip (fixed wait/ride per load, parallelism capped at 1.5 teams)
```

Per-category unload ratios (relative to load time):

| Item Type | Ratio | Why |
|---|---|---|
| **Standard furniture** (default) | 0.65 | Pre-wrapped, no truck Tetris; slowed by placement decisions |
| **Boxes, totes, bins** | 0.90 | Grab-and-go from truck |
| **Fragile (TV, mirror, artwork)** | 0.80 | Careful placement required at dropoff |
| **Heavy appliances** | 0.55 | Positioning difficulty, connections, door clearances |
| **Disassembly items** (beds, desks) | 0.50 | Reassembly time at dropoff |
| **Piano, treadmill** | 0.55 | Heavy + awkward positioning |

---

### Model Deep Dive

Two recent calibration changes improve real-world accuracy while keeping total estimates stable:

| Model | Before | After | Impact |
|---|---|---|---|
| **Elevator** | Percentage multiplier on total time (up to 68% inflation) | Additive per-trip time (fixed wait/ride per elevator load) | Large jobs no longer over-inflate. Parallelism capped at 1.5 teams. |
| **Load/Unload** | 1.2× then 1.65× flat multiplier (inflating then deflating) | Explicit `load_time + unload_time` with per-category ratios | No more multiply-then-divide dance. JSON `baseTime` untouched. Per-item display shows honest load/unload split. Job-level split is exact sum of per-item times. |

Details in `Version 9/Gemini/README.md` and `tests/test_elevator_fix.py`.

## 📂 Project Structure

```
/Data/                  # JSON databases
/Version 2/            # AI-estimated dimensions
/Version 3/            # Database-driven system
/Version 4/            # File API optimization (images only)
/Version 5/            # Video + image support (monolithic)
/Version 9/            # Modular architecture (latest - recommended)
  └─ Gemini/
     ├─ vision-agent.py          # Main orchestrator
     └─ modules/                 # Modular components
        ├─ base.py              # Abstract interfaces
        ├─ file_handlers.py     # Polymorphic handlers
        ├─ calculator.py        # Logistics engine
        └─ ai_client.py         # AI abstraction
/UI App/               # Streamlit web interface (V6 + performance testing)
/Test Images/          # Sample images
/Test Results/         # Analysis outputs
```

---

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open Pull Request

---

## 📞 Support

**Issues**: [GitHub Issues](https://github.com/SUKHMAN-SINGH-1612/Moovez-Vision-Agent/issues)
