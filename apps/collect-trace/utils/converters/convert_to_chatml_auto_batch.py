# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List


def get_llm_provider(json_file_path: str) -> str:
    """
    Extract llm_provider from JSON file

    Args:
        json_file_path: Path to JSON file

    Returns:
        llm_provider value or 'unknown' if not found
    """
    try:
        with open(json_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Extract llm_provider from env_info
        provider = data.get("env_info", {}).get("llm_provider")
        if provider:
            return provider
        else:
            return "unknown"
    except Exception as e:
        print(f"Error reading JSON file {json_file_path}: {e}")
        return "error"


def determine_conversion_method(provider: str) -> str:
    """
    Determine conversion method based on provider

    Args:
        provider: LLM provider name

    Returns:
        'oai' for OpenAI, 'non-oai' for others
    """
    if provider.lower() in ["openai", "claude_newapi", "deepseek_newapi"]:
        return "oai"
    else:
        return "non-oai"


def get_script_paths() -> tuple:
    """
    Get paths to conversion scripts

    Returns:
        Tuple of (oai_script_path, non_oai_script_path)
    """
    # Get directory of current script
    current_dir = Path(__file__).parent

    oai_script = current_dir / "convert_oai_to_chatml.py"
    non_oai_script = current_dir / "convert_non_oai_to_chatml.py"

    # Check if scripts exist
    if not oai_script.exists():
        raise FileNotFoundError(f"OAI conversion script not found: {oai_script}")

    if not non_oai_script.exists():
        raise FileNotFoundError(
            f"Non-OAI conversion script not found: {non_oai_script}"
        )

    return str(oai_script), str(non_oai_script)


def process_single_file(json_file_path: str, output_dir: str) -> bool:
    """
    Process a single JSON file

    Args:
        json_file_path: Path to JSON file
        output_dir: Output directory

    Returns:
        True if successful, False otherwise
    """
    try:
        # Get llm_provider
        provider = get_llm_provider(json_file_path)

        if provider == "error":
            print(f"❌ Failed to read provider from: {json_file_path}")
            return False

        # Determine conversion method
        conversion_method = determine_conversion_method(provider)

        # Get script paths
        oai_script, non_oai_script = get_script_paths()

        # Choose script based on conversion method
        if conversion_method == "oai":
            script_path = oai_script
            print(f"🔧 Using OAI conversion for provider: {provider}")
        else:
            script_path = non_oai_script
            print(f"🔧 Using Non-OAI conversion for provider: {provider}")

        # Run conversion script
        result = subprocess.run(
            [sys.executable, script_path, json_file_path, output_dir],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            print(f"✅ Successfully processed: {json_file_path}")
            return True
        else:
            print(f"❌ Failed to process {json_file_path}: {result.stderr}")
            return False

    except Exception as e:
        print(f"❌ Error processing {json_file_path}: {e}")
        return False


def find_json_files(input_paths: List[str]) -> List[str]:
    """
    Find JSON files from input paths

    Args:
        input_paths: List of file paths, directories, or patterns

    Returns:
        List of JSON file paths
    """
    json_files = []

    for path in input_paths:
        path_obj = Path(path)

        if path_obj.is_file():
            # Single file
            if path_obj.suffix.lower() == ".json":
                json_files.append(str(path_obj))
        elif path_obj.is_dir():
            # Directory - find all JSON files
            for json_file in path_obj.glob("*.json"):
                json_files.append(str(json_file))
        else:
            # Pattern matching
            try:
                for json_file in Path(".").glob(path):
                    if json_file.suffix.lower() == ".json":
                        json_files.append(str(json_file))
            except Exception:
                print(f"Warning: Could not process pattern: {path}")

    return json_files


def batch_process_files(input_paths: List[str], output_dir: str) -> Dict[str, int]:
    """
    Batch process multiple files

    Args:
        input_paths: List of input paths
        output_dir: Output directory

    Returns:
        Dictionary with processing statistics
    """
    # Find JSON files
    json_files = find_json_files(input_paths)

    if not json_files:
        print("❌ No JSON files found in the specified paths")
        return {"total": 0, "success": 0, "failed": 0}

    print(f"📁 Found {len(json_files)} JSON files to process")

    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Process files
    success_count = 0
    failed_count = 0

    for json_file in json_files:
        if process_single_file(json_file, output_dir):
            success_count += 1
        else:
            failed_count += 1

    return {"total": len(json_files), "success": success_count, "failed": failed_count}


def show_help():
    """Show help information"""
    help_text = """
Auto ChatML Conversion Script
============================

Automatically determines conversion method based on llm_provider field in JSON files

Usage:
  python convert_to_chatml_auto_batch.py <input_paths...> [output_dir]
  python convert_to_chatml_auto_batch.py <log_dir> [output_dir]
  python convert_to_chatml_auto_batch.py <log_file_pattern> [output_dir]

Parameters:
  input_paths: JSON files, directories, or patterns
  output_dir: Output directory (optional, default: extracted_chatml)

Examples:
  python convert_to_chatml_auto_batch.py logs/debug_logs/
  python convert_to_chatml_auto_batch.py logs/debug_logs/*.json
  python convert_to_chatml_auto_batch.py logs/debug_logs/ ./my_output
  python convert_to_chatml_auto_batch.py task_1.json task_2.json

Conversion Logic:
  - If llm_provider = 'openai': Use convert_oai_to_chatml.py
  - If llm_provider = anything else: Use convert_non_oai_to_chatml.py

Features:
  1. Auto-detect conversion method per file
  2. Batch process log files
  3. Extract main_agent_message_history
  4. Extract browser_agent_message_history_sessions
  5. Convert to OpenAI ChatML format
  6. Save as separate files
  7. Generate processing summary
"""
    print(help_text)


def main():
    """Main function"""
    # Check for help
    if len(sys.argv) < 2 or sys.argv[1] in ["-h", "--help"]:
        show_help()
        return

    # Parse arguments
    args = sys.argv[1:]

    # Check if last argument is output directory
    if len(args) > 1 and not args[-1].startswith("-"):
        # Check if last argument looks like a directory
        last_arg = args[-1]
        if (
            last_arg.endswith("/")
            or not Path(last_arg).suffix
            or last_arg == "extracted_chatml"
            or last_arg.startswith("./")
        ):
            output_dir = last_arg
            input_paths = args[:-1]
        else:
            output_dir = "extracted_chatml"
            input_paths = args
    else:
        output_dir = "extracted_chatml"
        input_paths = args

    print("🚀 Starting auto ChatML conversion")
    print(f"📂 Input paths: {input_paths}")
    print(f"📁 Output directory: {output_dir}")

    try:
        # Check if conversion scripts exist
        get_script_paths()

        # Process files
        stats = batch_process_files(input_paths, output_dir)

        # Show results
        print("\n" + "=" * 50)
        print("📊 Processing Summary")
        print("=" * 50)
        print(f"Total files: {stats['total']}")
        print(f"Successfully processed: {stats['success']}")
        print(f"Failed: {stats['failed']}")
        print(f"Output directory: {Path(output_dir).absolute()}")

        if stats["failed"] > 0:
            print(f"\n⚠️  {stats['failed']} files failed to process")
            sys.exit(1)
        else:
            print("\n✅ All files processed successfully!")

    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
