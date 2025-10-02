# Check if OPENAI_API_KEY is set
if [ -z "$OPENAI_API_KEY" ]; then
    echo "Error: OPENAI_API_KEY is not set."
    exit 1
else
    echo "OPENAI_API_KEY detected."
fi

# Get the directory where the current script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Current script directory: $SCRIPT_DIR"


# Enter the apps/miroflow-agent directory
TARGET_DIR="$SCRIPT_DIR/../../miroflow-agent"
echo "Target directory: $TARGET_DIR"
cd $TARGET_DIR

mkdir -p ../../logs
LOG_DIR="../../logs/collect_trace_gpt41"
echo "Log directory: $LOG_DIR"
mkdir -p $LOG_DIR

# Collect traces
uv run python benchmarks/common_benchmark.py \
    benchmark=collect_trace \
    benchmark.data.data_dir="../../data/debug" \
    benchmark.data.metadata_file="standardized_data.jsonl" \
    llm=gpt-5 \
    llm.provider=openai \
    llm.model_name=gpt-4.1-mini \
    llm.api_key="$OPENAI_API_KEY" \
    llm.base_url=https://api.openai.com/v1 \
    llm.async_client=true \
    benchmark.execution.max_tasks=null \
    benchmark.execution.max_concurrent=10 \
    benchmark.execution.pass_at_k=1 \
    agent=evaluation \
    hydra.run.dir=$LOG_DIR \
    2>&1 | tee "$LOG_DIR/output.log"

# Enter the apps/collect-trace directory
TARGET_DIR="$SCRIPT_DIR/../"
echo "Target directory: $TARGET_DIR"
cd $TARGET_DIR

# Process traces
uv run python $TARGET_DIR/utils/process_logs.py $LOG_DIR/benchmark_results.jsonl


