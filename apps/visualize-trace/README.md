# Trace Analysis Web Demo

An interactive web interface for analyzing and visualizing trace JSON files.

## Installation and Running

### Method 1: Using Python (Recommended)

```bash
pip install -r requirements.txt
python run.py
```

The startup script will automatically check and install dependencies, then start the web application. Visit `http://127.0.0.1:5000`

### Method 2: Using uv

```bash
uv run run.py
```

## Usage

1. **Start the application**: After running, visit `http://127.0.0.1:5000` in your browser

1. **Load files**:

   - Select the trace JSON file to analyze from the dropdown menu in the top navigation bar
   - Click the "Load" button to load the file

1. **View analysis results**:

   - **Left panel**: Shows basic information, execution summary, and performance statistics
   - **Right panel**: Displays detailed execution flow
   - **Bottom panel**: Shows spans statistics and step logs statistics

1. **Interactive operations**:

   - Click on execution steps to expand/collapse detailed information
   - Use "Expand All"/"Collapse All" buttons to control all steps
   - Click "View Details" button to see complete message content
