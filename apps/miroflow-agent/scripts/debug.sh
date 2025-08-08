#!/bin/bash

BENCHMARK_NAME="gaia-validation"
LLM_PROVIDER="qwen"
AGENT_SET="evaluation"
BASE_URL=${BASE_URL:-"https://your-api.com/v1"}
LLM_MODEL=${LLM_MODEL:-"MiroThinker-Models"}


RESULTS_DIR="../../debug"
mkdir -p "$RESULTS_DIR"

uv run python benchmarks/common_benchmark.py \
    benchmark=gaia-validation \
    llm=qwen3-32b \
    llm.provider=$LLM_PROVIDER \
    llm.model_name=$LLM_MODEL \
    llm.openai_base_url=$BASE_URL \
    llm.async_client=true \
    llm.temperature=0.3 \
    benchmark.execution.max_tasks=2 \
    benchmark.execution.max_concurrent=10 \
    benchmark.execution.pass_at_k=1 \
    benchmark.data.data_dir=../../data/gaia-2023-validation \
    agent=$AGENT_SET \
    hydra.run.dir=${RESULTS_DIR}
