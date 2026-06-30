# 🎨 Moovez Vision Agent - Streamlit UI Application (Version 6)

**Interactive Web Interface for AI-Powered Moving Quote Generation with Video Support**

A user-friendly Streamlit application that provides a visual interface for the Moovez Vision Agent, allowing users to upload images and videos to receive instant moving quotes with performance testing capabilities.

---

## ⚠️ Important Compatibility Notice

**This application works with Version 6 Gemini Vision Agent.**

- ✅ **Compatible**: Version 6 Gemini implementation (modular architecture with video support)
- ✅ **Backward Compatible**: Maintains V5 compatibility through aliases
- ⚠️ **Previous Versions**: Update imports to use Version 4 or Version 3 if needed
- ❌ **Not Compatible**: OpenAI implementations

The app is specifically designed to integrate with `Version 6/Gemini/vision-agent.py` and uses Google's Gemini AI models exclusively with a modular, scalable architecture.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [User Guide](#user-guide)
- [Interface Overview](#interface-overview)
- [Technical Architecture](#technical-architecture)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)

---

## 🎯 Overview


---

## ✨ Features

### � Media File Management
- **Multi-File Upload**: Drag-and-drop or browse for multiple images and videos
- **Image Preview**: See thumbnails of uploaded images before analysis
- **Video Info**: Display video file names and sizes
- **Format Support**: 
  - **Images**: JPG, JPEG, PNG, GIF, BMP, WEBP, TIFF, HEIC, HEIF (iPhone)
  - **Videos**: MP4, MOV, AVI, MKV, WEBM, FLV, WMV, M4V
- **Batch Processing**: Analyze entire rooms or properties at once
- **Mixed Media**: Combine images and videos in a single analysis

### ⚙️ Configuration Options
- **Pickup Location**:
  - Access type (Ground, Stairs, Elevator)
  - Number of floors
- **Dropoff Location**:
  - Access type (Ground, Stairs, Elevator)
  - Number of floors
- **Travel Time**: Customizable travel duration between locations
- **AI Model**: Uses Gemini 2.5 Flash (optimized for speed and accuracy)
- **Performance Testing**: Run 5 iterations to measure AI consistency and variation

### 📊 Results Display

#### Tab 1: Overview
- Total items count
- Total time estimate
- Total price
- Quick logistics summary

#### Tab 2: Items
- Comprehensive items table
- Detected categories and sizes
- Volume and weight per item
- Location information

#### Tab 3: Time Breakdown
- Per-item time analysis
- Loading/unloading breakdown
- Access time calculations
- Detailed time estimates

#### Tab 4: Logistics
- Vehicle recommendations
- Workforce requirements
- Volume and weight utilization
- Multi-vehicle solutions (if needed)

#### Tab 5: Pricing
- Base price calculation
- GST/taxes
- Insurance fees
- Total expected price
- Detailed breakdown

#### Tab 6: Metrics
- File analysis time
- Calculation time
- Total processing time
- API call count
- Images processed count
- Videos processed count
- AI model used

#### Tab 7: Performance Analysis (when enabled)
- **Statistical Summary**: Mean, Std Dev, Min, Max for all KPIs
- **Line Graphs**: Variations across 5 iterations
  - Total Items Detected
  - Total Time Required (hours)
  - Base Price ($)
  - Total Price ($)
  - Processing Time (seconds)
  - Number of Workers
- **Raw Data Table**: All iteration results
- **Export Options**: JSON (all results) and CSV (statistics)

### 💾 Export Functionality
- Download complete results as JSON
- Download performance data (when performance test is run)
- Export statistical summary as CSV
- Includes all analysis data
- Machine-readable format
- Integration-ready

---

## 🔧 Prerequisites

### System Requirements
- **Python**: 3.8 or higher
- **Operating System**: Windows, macOS, or Linux
- **Memory**: Minimum 4GB RAM recommended
- **Internet**: Required for Gemini API calls

### Required Dependencies
```
streamlit>=1.28.0
google-generativeai>=0.3.0
python-dotenv>=1.0.0
Pillow>=10.0.0
pandas>=2.0.0
```

### API Requirements
- **Gemini API Key**: Required from Google AI Studio
- Get your key at: [https://makersuite.google.com/app/apikey](https://makersuite.google.com/app/apikey)

---

## 🚀 Installation

### Step 1: Navigate to UI App Directory

```powershell
# Windows PowerShell
cd "C:\Users\susingh\Personal\Moovez\Moovez-Vision-Agent\UI App"
```

```bash
# macOS/Linux
cd ~/path/to/Moovez-Vision-Agent/UI\ App
```

### Step 2: Create Virtual Environment (Recommended)

```powershell
# Windows
python -m venv venv
.\venv\Scripts\Activate.ps1
```

```bash
# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies

From the **root directory** of the project:

```bash
pip install -r requirements.txt
```

Or install individually:

```bash
pip install streamlit google-generativeai python-dotenv Pillow pandas
```

### Step 4: Verify Installation

```bash
streamlit --version
```

Expected output: `Streamlit, version 1.28.0` (or higher)

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the **root directory** (not in UI App folder):

```env
# Required: Gemini API Key
GEMINI_API_KEY=your_gemini_api_key_here
```

**Important**: The app looks for the `.env` file in the parent directory, not in the `UI App` folder.

### File Structure

Ensure the following files are present:

```
Moovez-Vision-Agent/
├── .env                                    # API keys here
├── Data/
│   ├── moving_items_logistics_v2.json     # Required
│   └── moving_calculation_rules.json      # Required
└── UI App/
    ├── app.py                              # Main Streamlit app
```

### Verify Configuration

```python
# Test API key is loaded
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('API Key:', os.getenv('GEMINI_API_KEY')[:10] + '...')"
```

---

## 🎬 Running the Application

### Recommended (repository root)

```bash
# From Moovez-Vision-Agent/
streamlit run app.py
```

Root `app.py` loads this file (`UI App/app.py`). Use one entry point to avoid drift.

### Alternative (this directory)

```bash
cd "UI App"
streamlit run app.py
```

### Python module

```bash
streamlit run "UI App/app.py"
# or from repo root:
python -m streamlit run app.py
```

### Access the Application

Once started, the app will automatically open in your default browser at:
```
http://localhost:8501
```

If it doesn't open automatically, manually navigate to the URL shown in the terminal.

### Stopping the Application

Press `Ctrl+C` in the terminal to stop the server.

---

## 📖 User Guide

### Step-by-Step Usage

#### 0️⃣ Enable Performance Testing (Optional)

**Sidebar → Performance Testing Section**

- Check the box: "Run 5 iterations for performance analysis"
- When enabled:
  - The same analysis will run 5 times consecutively
  - Results from all iterations are stored
  - A new "🧪 Performance" tab appears with:
    - Statistical summary (mean, std dev, min, max)
    - Line graphs showing KPI variations
    - Raw data table
  - Takes 5x longer to complete
- Use this to:
  - Test AI consistency across multiple runs
  - Measure system performance and reliability
  - Identify variation in item detection and pricing
  - Generate performance reports

**Tips**:
- Enable for important quotes where consistency matters
- Useful for validating AI accuracy on complex moves
- Great for testing edge cases
- Provides confidence in results through statistical analysis

#### 1️⃣ Upload Media Files

**Sidebar → Media Upload Section**

- Click "Browse files" or drag and drop files
- Supported formats: 
  - **Images**: JPG, JPEG, PNG, GIF, BMP, WEBP, TIFF
  - **Videos**: MP4, MOV, AVI, MKV, WEBM, FLV, WMV, M4V
- Upload multiple files for better accuracy
- Images are displayed as thumbnails for verification
- Videos show file name and size

**Tips**:
- Capture clear, well-lit photos/videos
- Include multiple angles of rooms
- Focus on furniture and large items
- Avoid blurry or dark media
- For videos: 30-60 seconds per room, steady camera

#### 2️⃣ Configure Pickup Location

**Sidebar → Pickup Location Access**

- **Access Type**: Select from dropdown
  - `Ground` - Main floor, no stairs/elevator
  - `Stairs` - Multiple flights of stairs
  - `Elevator` - Building with elevator access
  
- **Number of Floors**: 
  - Enter floor number (e.g., 3 for 3rd floor)
  - Use 0 for ground floor
  - Affects time and labor calculations

#### 3️⃣ Configure Dropoff Location

**Sidebar → Dropoff Location Access**

Same options as pickup:
- Select access type
- Enter number of floors

#### 4️⃣ Set Travel Time

**Sidebar → Travel Time**

- Enter estimated travel time between locations
- Default: 30 minutes
- Impacts total job duration

#### 5️⃣ Analyze

Click the **"� Analyze Move"** button

- Processing typically takes 5-30 seconds (longer for videos)
- Progress spinner shows analysis status
- Results appear automatically when complete

#### 6️⃣ Review Results

Navigate through tabs to view:
- **Overview**: Summary metrics
- **Items**: Detailed item list
- **Time**: Breakdown by item
- **Logistics**: Vehicle and crew recommendations
- **Pricing**: Complete cost breakdown
- **Metrics**: Performance statistics
- **Performance** (if enabled): AI consistency analysis with graphs and statistics

#### 7️⃣ Export Results (Optional)

**Metrics Tab → Download Results**

Click **"📥 Download JSON Report"** to save results locally.

**Performance Tab → Download Performance Data** (if performance test was run)

- Click **"📥 Download All Results (JSON)"** for complete 5-iteration data
- Click **"📥 Download Statistics (CSV)"** for statistical summary table

---

## 🖥️ Interface Overview

### Sidebar (Left Panel)

```
┌─────────────────────────────┐
│  🚛 MoovEZ Vision Analyzer │
├─────────────────────────────┤
│                             │
│  📸 Upload Images           │
│  ┌────────────────────┐    │
│  │ Browse files...    │    │
│  └────────────────────┘    │
│                             │
│  🏠 Pickup Location         │
│  Access: [Dropdown]         │
│  Floors: [Number]           │
│                             │
│  🏢 Dropoff Location        │
│  Access: [Dropdown]         │
│  Floors: [Number]           │
│                             │
│  🚗 Travel Time             │
│  Minutes: [30]              │
│                             │
│  [� Analyze Move]          │
│                             │
└─────────────────────────────┘
```

### Main Panel (Right)

```
┌──────────────────────────────────────────┐
│  Tabs: Overview | Items | Time | etc.   │
│        (+ Performance tab if enabled)    │
├──────────────────────────────────────────┤
│                                          │
│  📊 Results Display Area                 │
│                                          │
│  - Metrics and visualizations            │
│  - Tables and charts                     │
│  - Detailed breakdowns                   │
│  - Performance graphs (when enabled)     │
│                                          │
└──────────────────────────────────────────┘
```

---

## 🔧 Technical Architecture

### Application Stack

```
┌────────────────────────────────────────┐
│         Streamlit Frontend             │
│  (User Interface & Interaction)        │
└─────────────┬──────────────────────────┘
              │
              ▼
┌────────────────────────────────────────┐
│      app.py (Main Application)         │
│  - Session state management            │
│  - UI components                       │
│  - Event handlers                      │
└─────────────┬──────────────────────────┘
              │
              ▼
┌────────────────────────────────────────┐
│   Version 6/Gemini/vision-agent.py     │
│  (Backend Processing Engine)           │
│                                        │
│  MoovEZVisionAnalyzerV6 Class:         │
│  - Modular architecture                │
│  - Image/video analysis                │
│  - Item detection                      │
│  - Logistics calculation               │
│                                        │
│  Modules:                              │
│  - base.py (abstract classes)          │
│  - file_handlers.py (polymorphism)     │
│  - calculator.py (logistics)           │
│  - ai_client.py (Gemini integration)   │
└─────────────┬──────────────────────────┘
              │
    ┌─────────┴──────────┐
    ▼                    ▼
┌─────────────┐    ┌──────────────────┐
│ Gemini API  │    │ JSON Data Files  │
│ (Google AI) │    │ - Items DB v2.0  │
│             │    │ - Calc Rules     │
└─────────────┘    └──────────────────┘
```

### Key Components

#### `app.py`
- Main Streamlit application
- UI rendering and layout
- User input handling
- Results visualization
- Uses Gemini 2.5 Flash model

#### `Version 6/Gemini/vision-agent.py`
- `MoovEZVisionAnalyzerV6` class (aliased as V5 for compatibility)
- Modular architecture with separation of concerns
- Image and video processing
- AI model integration
- Calculation engine

#### `Version 6/Gemini/modules/`
- **base.py**: Abstract base classes for extensibility
- **file_handlers.py**: Polymorphic file type handling
- **calculator.py**: Isolated logistics calculations
- **ai_client.py**: Gemini API client abstraction

#### Session State Management
```python
st.session_state.analyzer                 # Vision analyzer instance (V6)
st.session_state.analysis_result          # Latest results (first iteration)
st.session_state.performance_test_results # All 5 iteration results (when enabled)
st.session_state.enable_performance_test  # Performance test mode flag
st.session_state.uploaded_files           # Media file cache
```

#### Data Flow
1. User uploads images/videos → Saved to temp directory
2. User configures parameters → Stored in session state
3. Click "Analyze" → Calls `process_moving_request()`
4. Backend processes → Returns JSON results
5. Results displayed → Rendered in tabs
6. User downloads → JSON export

---

## 📝 Changelog

### Version 6.0 (Current)
- ✅ **Modular Architecture**: Abstraction, inheritance, and polymorphism
- ✅ **Performance Testing Feature**: Run 5 iterations with statistical analysis
- ✅ **Enhanced Visualization**: Line graphs for KPI variations
- ✅ **Statistical Analysis**: Mean, std dev, min, max for all metrics
- ✅ **Multiple Export Options**: JSON results + CSV statistics
- ✅ Integration with Version 6 modular backend
- ✅ Backward compatibility with V5 API
- ✅ Video file support (.mp4, .mov, .avi, etc.)
- ✅ HEIC/HEIF support (iPhone images)
- ✅ Mixed media uploads (images + videos)
- ✅ Single API call for all files
- ✅ Enhanced JSON database (v2.0)
- ✅ Tabbed results interface
- ✅ Performance metrics display

### Version 5.0
- ✅ Integration with Gemini 2.5 Flash (fixed model)
- ✅ Video file support
- ✅ Multi-file processing
- ✅ JSON export functionality
