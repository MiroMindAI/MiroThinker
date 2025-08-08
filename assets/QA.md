# MiroFlow QA Documentation

## Q1: Can I extract GAIA-Text-103 results from existing GAIA-Validation evaluations?

**Answer:** Yes! If you have completed GAIA-Validation evaluations, you can extract and re-grade the GAIA-Text-103 subset using our specialized tools.

### Step-by-Step Process

1. **Extract GAIA-Text-103 Tasks**

   ```bash
   # Extract text-103 tasks to a separate directory
   uv run benchmarks/subset_extraction/gaia-to-text-103-mover.py ../../logs/gaia-validation/0806/qwen_MiroThinker-32B-SFT_evaluation
   ```

   This creates a new directory: `gaia-text-103-extraction/qwen_MiroThinker-32B-SFT_evaluation`

2. **Re-grade with GAIA-Text-103 Evaluator**

   ```bash
   # Apply GAIA-Text-103 specific grading
   uv run benchmarks/subset_extraction/gaia-text-103-grader.py ../../logs/gaia-validation/0806/gaia-text-103-extraction
   ```

3. **Verify Results**

   ```bash
   # Check accuracy and generate statistics
   uv run benchmarks/check_progress/check_progress_gaia-validation-text-103.py ../../logs/gaia-validation/0806/gaia-text-103-extraction
   ```

## Q2: Does the choice of judgment model affect evaluation performance?

**Answer:** Yes, there is a measurable difference in evaluation outcomes between the two judgment models.

A comparison between GPT-4.1-2025-04-14 and Qwen2.5-72B-Instruct as judgment LLMs.

### Experimental Setup

We conducted a comparative evaluation using the GAIA-Validation-text-103 dataset:

- **Dataset size:** 103 questions
- **Evaluation runs:** 8 iterations per model
- **Total evaluations:** 824 questions (103 × 8)

### Results

| Judge Model | Accuracy Results |
|-------------|------------------|
| GPT-4.1-2025-04-14 | 55.0% / 55.8% / 55.2% |
| Qwen2.5-72B-Instruct | 53.2% / 52.9% / 53.5% |

### Analysis and Implications

The results demonstrate that the choice of judgment LLM can meaningfully impact benchmark outcomes. When comparing model performance, it's important to account for the specific evaluator used, as this introduces a systematic variance of approximately 1-2 percentage points in our testing.

### Our Choice: GPT-4.1

We have standardized on GPT-4.1-2025-04-14 as our primary judgment model for several practical reasons:

- **Ease of deployment:** No need to host additional GPU-intensive models
- **Consistency:** Aligns with evaluation standards used in other benchmarks (SimpleQA, BrowseComp)
- **Reproducibility:** Provides a consistent baseline for cross-evaluation comparisons

## Code Quality Checks

Before submitting a pull request, ensure your code meets our quality standards:

```bash
# Fix linting issues automatically
uv tool run ruff@0.8.0 check --fix .

# Format code according to our style guidelines
uv tool run ruff@0.8.0 format .
```

## Know Issues

- The context management component before the summary requires further refinement to improve accuracy and reliability. I guess this is because the length estimation is not accurate.
