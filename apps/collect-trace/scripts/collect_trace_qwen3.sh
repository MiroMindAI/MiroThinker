# Get the directory where the current script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Current script directory: $SCRIPT_DIR"


# Enter the apps/miroflow-agent directory
TARGET_DIR="$SCRIPT_DIR/../../miroflow-agent"
echo "Target directory: $TARGET_DIR"
cd $TARGET_DIR

mkdir -p ../../logs
LOG_DIR="../../logs/collect_trace_qwen3"
echo "Log directory: $LOG_DIR"
mkdir -p $LOG_DIR

# Collect traces
uv run python benchmarks/common_benchmark.py \
    benchmark=collect_trace \
    benchmark.data.data_dir="../../data/debug" \
    benchmark.data.metadata_file="standardized_data.jsonl" \
    llm=qwen-3 \
    llm.provider=qwen \
    llm.model_name=qwen-3-32b \
    llm.api_key="" \
    llm.base_url=https://your-api.com/v1 \
    llm.async_client=true \
    benchmark.execution.max_tasks=null \
    benchmark.execution.max_concurrent=10 \
    benchmark.execution.pass_at_k=1 \
    agent=single_agent \
    hydra.run.dir=$LOG_DIR \
    2>&1 | tee "$LOG_DIR/output.log"

# Enter the apps/collect-trace directory
TARGET_DIR="$SCRIPT_DIR/../"
echo "Target directory: $TARGET_DIR"
cd $TARGET_DIR

# Process traces
uv run python $TARGET_DIR/utils/process_logs.py $LOG_DIR/benchmark_results.jsonl


