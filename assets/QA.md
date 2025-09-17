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

1. **Re-grade with GAIA-Text-103 Evaluator**

   ```bash
   # Apply GAIA-Text-103 specific grading
   uv run benchmarks/subset_extraction/gaia-text-103-grader.py ../../logs/gaia-validation/0806/gaia-text-103-extraction
   ```

1. **Verify Results**

   ```bash
   # Check accuracy and generate statistics
   uv run benchmarks/check_progress/check_progress_gaia-validation-text-103.py ../../logs/gaia-validation/0806/gaia-text-103-extraction
   ```

## Q2: Does the choice of judgment model affect evaluation performance?

**Answer:** Yes, there is a measurable difference in evaluation outcomes between the two judgment models.

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
