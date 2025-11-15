<div align="center">
  <img src="assets/miro_thinker.png" width="55%" alt="MiroThinker" />
</div>

<br>

<div align="center">

[![DEMO](https://img.shields.io/badge/Demo-FFB300?style=for-the-badge&logo=airplayvideo&logoColor=white)](https://dr.miromind.ai/)
[![MODELS](https://img.shields.io/badge/Models-5EDDD2?style=for-the-badge&logo=huggingface&logoColor=ffffff&labelColor)](https://huggingface.co/collections/miromind-ai/mirothinker-v10)
[![Paper](https://img.shields.io/badge/Paper-B31B1B?style=for-the-badge&logo=arxiv&logoColor=white)](https://github.com/MiroMindAI/MiroThinker/blob/main/assets/MiroThinker_v1.0_Technical_Report.pdf)
[![Blog](https://img.shields.io/badge/Blog-4285F4?style=for-the-badge&logo=google-chrome&logoColor=white)](https://miromind.ai/#blog)
[![DATA](https://img.shields.io/badge/Data-0040A1?style=for-the-badge&logo=huggingface&logoColor=ffffff&labelColor)](https://huggingface.co/datasets/miromind-ai/MiroVerse-v0.1)

[![GITHUB](https://img.shields.io/badge/Github-24292F?style=for-the-badge&logo=github&logoColor=white)](https://github.com/MiroMindAI)
[![WEBSITE](https://img.shields.io/badge/Website-4285F4?style=for-the-badge&logo=google-chrome&logoColor=white)](https://miromind.ai/)
[![DISCORD](https://img.shields.io/badge/Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.com/invite/GPqEnkzQZd)
[![WeChat](https://img.shields.io/badge/WeChat-07C160?style=for-the-badge&logo=wechat&logoColor=white)](https://raw.githubusercontent.com/MiroMindAI/MiroThinker/refs/heads/main/assets/miromind_wechat.png)
[![RedNote](https://img.shields.io/badge/RedNote-FF2442?style=for-the-badge&logo=revoltdotchat&logoColor=white)](https://www.xiaohongshu.com/user/profile/5e353bd80000000001000239)

</div>

<div align="center">

### 🚀 [Try our Demo!](https://dr.miromind.ai/)

</div>

> **MiroThinker** is the official implementation of the MiroMind Research Agent Project. It is an open-source research agent designed to advance tool-augmented reasoning and information-seeking capabilities, enabling complex real-world research workflows across diverse challenges.

The project currently comprises four key components:

- 💡 **MiroThinker**: An open-source research agent model that natively supports tool-assisted reasoning, achieving state-of-the-art performance across multiple benchmarks (e.g., HLE, HLE-Text-2158, HLE-Text-500, BrowserComp, BrowserComp-ZH, GAIA, xBench-DeepSearch, FutureX, and Frames). See [Quick Start](#-quick-start).
- 🤖 **MiroFlow**: An open-source research agent framework that offers reproducible state-of-the-art performance across multiple benchmarks. See [MiroFlow](https://github.com/MiroMindAI/MiroFlow) for details.
- 📚 **MiroVerse**: A premium open-source training dataset with 147k samples supporting research agent training. See [MiroVerse](https://huggingface.co/datasets/miromind-ai/MiroVerse-v0.1) on HuggingFace.
- 🔧 **MiroTrain / MiroRL**: Training infrastructure that supports stable and efficient training for research agent models. See [MiroTrain](https://github.com/MiroMindAI/MiroTrain) and [MiroRL](https://github.com/MiroMindAI/MiroRL) for details.

## 📋 Table of Contents

- 📰 [News & Updates](#-news--updates)
- 📝 [Introduction](#-introduction)
- ✨ [Key Features](#-key-features)
- 📈 [Performance on Benchmarks](#-performance-on-benchmarks)
- 🚀 [Quick Start](#-quick-start)
- 📊 [Trace Collection](#-trace-collection)
- 📄 [License](#-license)
- 🙏 [Acknowledgments](#-acknowledgments)

## 📰 News & Updates

- **\[2025-11-13\]** 🎉🎉 [MiroThinker-v1.0](https://huggingface.co/collections/miromind-ai/mirothinker-v10) is now released! Introducing **interactive scaling** as a third dimension of performance improvement, MiroThinker v1.0 supports 256K context window and up to 600 tool calls per task. Available in 8B, 30B, and 72B parameter scales, achieving 37.7%, 47.1%, 55.6%, and 81.9% on HLE-Text, BrowseComp, BrowseComp-ZH, and GAIA-Text-103, respectively. See [Technical Report](https://github.com/MiroMindAI/MiroThinker/blob/main/assets/MiroThinker_v1.0_Technical_Report.pdf) for more details.
- **\[2025-09-11\]** 🎉 MiroThinker-72B-Preview ranked 4th in this week's FutureX benchmark. See [FutureX](https://futurex-ai.github.io/).
- **\[2025-09-08\]** [MiroThinker-v0.2](https://huggingface.co/collections/miromind-ai/mirothinker-v02) is now released, achieving open-source SOTA performance across multiple benchmarks, including HLE (17.8%), HLE-Text-Only (19.1%), BrowserComp-EN (17.2%), BrowserComp-ZH (29.4%), xBench-DeepSearch (56.0%), and Frames (74.8%).
- **\[2025-09-07\]** We supported more benchmarks, including [BrowseComp-ZH](https://arxiv.org/abs/2504.19314), [XBench-DeepSearch](https://xbench.org/agi/aisearch), and [FutureX](https://futurex-ai.github.io/). We plan to add more benchmarks in the future.
- **\[2025-09-04\]** Our in-development model, MiroThinker-72B-Preview, ranked 6th in this week's [FutureX benchmark](https://futurex-ai.github.io/). We will release the stable version of MiroThinker-72B soon.
- **\[2025-08-22\]** Introducing streamlined deployment options for MiroThinker models with optimized resource usage and faster startup times. Experience the interactive demo: [🚀 Try Gradio Demo](apps/gradio-demo)
- **\[2025-08-08\]** [MiroThinker-v0.1](https://huggingface.co/collections/miromind-ai/mirothinker-v01-689301b6d0563321862d44a1) released. Models, framework, and data are now fully open-sourced!

## 📝 Introduction

### MiroThinker-v1.0

Unlike previous agents that scale only model size or context length, MiroThinker v1.0 introduces **interactive scaling** at the model level, systematically training the model to handle deeper and more frequent agent–environment interactions as a third dimension of performance improvement. Interactive scaling leverages environment feedback and external information acquisition to correct errors and refine trajectories.

![image](https://huggingface.co/datasets/miromind-ai/MiroFlow-Benchmarks/resolve/main/assets/MiroThinker_v1.0_Overall.png)

### ✨ Key Features

- 🚀 **256K Context Window**: Supports long-horizon reasoning and deep multi-step analysis
- 🔧 **600 Tool Calls**: Handles up to 600 tool calls per task — a substantial improvement over previous open-source research agents
- 📦 **Multiple Scales**: Released in 8B, 30B, and 72B parameter scales, accompanied by a comprehensive suite of tools and workflows to flexibly support diverse research settings and compute budgets

<div align="center">

|      Model Name      |         Base Model          | Max Length | Max Tool Calls |                              HF Link                               |
|:--------------------:|:---------------------------:|:----------:|:--------------:|:------------------------------------------------------------------:|
| MiroThinker-v1.0-8B  |        Qwen3-8B             |    256K    |      600       | [🤗 link](https://huggingface.co/miromind-ai/MiroThinker-v1.0-8B)  |
| MiroThinker-v1.0-30B | Qwen3-30B-A3B-Thinking-2507 |    256K    |      600       | [🤗 link](https://huggingface.co/miromind-ai/MiroThinker-v1.0-30B) |
| MiroThinker-v1.0-72B |    Qwen2.5-72B-Instruct     |    256K    |      600       | [🤗 link](https://huggingface.co/miromind-ai/MiroThinker-v1.0-72B) |

</div>

MiroThinker v1.0 demonstrates strong general-research performance across a broad range of benchmarks, achieving **37.7%**, **47.1%**, **55.6%**, and **81.9%** on HLE-Text, BrowseComp, BrowseComp-ZH, and GAIA-Text-103, respectively. These results surpass previous open-source agents and narrow the gap with commercial counterparts such as **GPT-5-high**.

<div align="center">
  <img src="https://huggingface.co/datasets/miromind-ai/MiroFlow-Benchmarks/resolve/main/assets/MiroThinker_v1.0_Performance_1.png" width="100%" alt="MiroThinker" />
</div>

### MiroThinker-v0.2

<details>
  <summary>📦 Click to expand MiroThinker-v0.2 details</summary>

In this new version, we introduced three key improvements:

- 📚 **Richer training data** from both English and Chinese sources, yielding significant gains in benchmark performance and generalization
- 🎯 **Unified DPO training** with a single preference dataset across all models
- 📏 **Extended context length** from 40k to 64k for more challenging multi-turn tool-use tasks

Compared to v0.1, MiroThinker v0.2 delivers consistent gains across benchmarks. For example, scores improved from **57.3 → 64.1** on **GAIA-Text-103** and from **17.0 → 29.4** on **BrowseComp-ZH**, reflecting substantial advancements in the model’s general research agent capabilities.

<div align="center">

|        Model Name        |      Base Model       | Max Length |                                HF Link                                 |
|:------------------------:|:---------------------:|:----------:|:----------------------------------------------------------------------:|
| MiroThinker-4B-SFT-v0.2  |       Qwen3-4B        |    64K     | [🤗 link](https://huggingface.co/miromind-ai/MiroThinker-4B-SFT-v0.2)  |
| MiroThinker-4B-DPO-v0.2  |       Qwen3-4B        |    64K     | [🤗 link](https://huggingface.co/miromind-ai/MiroThinker-4B-DPO-v0.2)  |
| MiroThinker-8B-SFT-v0.2  |       Qwen3-8B        |    64K     | [🤗 link](https://huggingface.co/miromind-ai/MiroThinker-8B-SFT-v0.2)  |
| MiroThinker-8B-DPO-v0.2  |       Qwen3-8B        |    64K     | [🤗 link](https://huggingface.co/miromind-ai/MiroThinker-8B-DPO-v0.2)  |
| MiroThinker-14B-SFT-v0.2 |       Qwen3-14B       |    64K     | [🤗 link](https://huggingface.co/miromind-ai/MiroThinker-14B-SFT-v0.2) |
| MiroThinker-14B-DPO-v0.2 |       Qwen3-14B       |    64K     | [🤗 link](https://huggingface.co/miromind-ai/MiroThinker-14B-DPO-v0.2) |
| MiroThinker-32B-SFT-v0.2 |       Qwen3-32B       |    64K     | [🤗 link](https://huggingface.co/miromind-ai/MiroThinker-32B-SFT-v0.2) |
| MiroThinker-32B-DPO-v0.2 |       Qwen3-32B       |    64K     | [🤗 link](https://huggingface.co/miromind-ai/MiroThinker-32B-DPO-v0.2) |
| MiroThinker-72B-SFT-v0.2 | Qwen2.5-72B-Instruct  |    64K     |                              Coming Soon                               |
| MiroThinker-72B-DPO-v0.2 | Qwen2.5-72B-Instruct  |    64K     |                              Coming Soon                               |

</div>

</details>

### MiroThinker-v0.1

<details>
  <summary>📦 Click to expand MiroThinker-v0.1 details</summary>

<div align="center">
  <img src="assets/gaia_text_103.png" width="98%" alt="MiroFlow Performance on GAIA-Validation" />
  <p><strong>Performance of Open-Source Models on GAIA-Validation Benchmark.</strong></p>
</div>

We have released the **MiroThinker v0.1** series, including both SFT and DPO variants at parameter scales of **8B**, **14B**, and **32B**. Notably, MiroThinker v0.1 achieves **state-of-the-art performance** among open-source models on the [GAIA benchmark](https://huggingface.co/datasets/gaia-benchmark/GAIA), a rigorous evaluation suite for advanced agentic capabilities, demonstrating its strength in long-context, decision-intensive, and real-world task scenarios.

<div align="center">

| Model Name                | Base Model | Max Length | HF Link                                                               |
| :-----------------------: |:----------:|:----------:| :--------------------------------------------------------------------:|
| MiroThinker-8B-SFT-v0.1   |  Qwen3-8B  |    40K     | [🤗 link](https://huggingface.co/miromind-ai/MiroThinker-8B-SFT-v0.1)  |
| MiroThinker-8B-DPO-v0.1   |  Qwen3-8B  |    40K     | [🤗 link](https://huggingface.co/miromind-ai/MiroThinker-8B-DPO-v0.1)  |
| MiroThinker-14B-SFT-v0.1  | Qwen3-14B  |    40K     | [🤗 link](https://huggingface.co/miromind-ai/MiroThinker-14B-SFT-v0.1) |
| MiroThinker-14B-DPO-v0.1  | Qwen3-14B  |    40K     | [🤗 link](https://huggingface.co/miromind-ai/MiroThinker-14B-DPO-v0.1) |
| MiroThinker-32B-SFT-v0.1  | Qwen3-32B  |    40K     | [🤗 link](https://huggingface.co/miromind-ai/MiroThinker-32B-SFT-v0.1) |
| MiroThinker-32B-DPO-v0.1  | Qwen3-32B  |    40K     | [🤗 link](https://huggingface.co/miromind-ai/MiroThinker-32B-DPO-v0.1) |

</div>

</details>

## ✨ Key Features

### 🤖 **MiroThinker-Optimized Framework**

- 🔓 **Fully Open-Source Agent Framework**: Complete transparency with open framework and open models
- 🔗 **Tool Integration**: Seamless integration with external tools and APIs
- 📝 **Trace Collection**: Comprehensive logging and analysis of agent interactions with elapsed time and estimated completion time displayed in minutes. Ready for SFT and DPO
- 📊 **Benchmark Evaluation**: Extensive testing across multiple benchmark datasets

### 📊 **Comprehensive Benchmark Suite**

- **GAIA Validation**: A benchmark for General AI Assistants. ([paper](https://arxiv.org/abs/2311.12983))
- **GAIA-Text-103**: A subset of GAIA Validation for text-only tasks. ([paper](https://arxiv.org/abs/2505.22648))
- **HLE**: Humanity's Last Exam. ([paper](https://arxiv.org/abs/2501.14249))
- **HLE-Text-2158**: A subset of HLE for text-only tasks. ([paper](https://arxiv.org/abs/2501.14249))
- **HLE-Text-500**: A subset of HLE for text-only tasks, created by [WebThinker](https://arxiv.org/pdf/2504.21776). ([paper](https://arxiv.org/pdf/2504.21776))
- **BrowseComp-EN**: Web browsing and comprehension tasks. ([paper](https://arxiv.org/abs/2504.12516))
- **BrowseComp-ZH**: A Chinese version of BrowseComp. ([paper](https://arxiv.org/abs/2504.19314))
- **WebWalkerQA**: Web navigation and question answering. ([paper](https://arxiv.org/abs/2501.07572))
- **Frames**: Factuality, Retrieval, And reasoning MEasurement Set. ([paper](https://arxiv.org/abs/2409.12941))
- **XBench-DeepSearch**: A benchmark for deep research agents. ([website](https://xbench.org/agi/aisearch))
- **FutureX**: A live benchmark designed for predicting unknown future. ([website](https://futurex-ai.github.io/))
- **SEAL-0**: A benchmark for evaluating LLMs on conflicting-evidence web questions. ([paper](https://arxiv.org/abs/2506.01062))
- **AIME2025**: American Invitational Mathematics Examination 2025. ([website](https://artificialanalysis.ai/evaluations/aime-2025))

## 📈 Performance on Benchmarks

### MiroThinker-v1.0

<div align="center">
  <img src="https://huggingface.co/datasets/miromind-ai/MiroFlow-Benchmarks/resolve/main/assets/MiroThinker_v1.0_Performance_2.png" width="100%" alt="MiroThinker" />
</div>

### MiroThinker-v0.2

<details>
  <summary>📦 Click to expand MiroThinker-v0.2 details</summary>

#### Comparison with SOTA Research Agents

<div align="center">
  <img src="https://huggingface.co/datasets/miromind-ai/MiroFlow-Benchmarks/resolve/main/assets/MiroThinker_v0.2_Performance_2.png" width="90%" alt="MiroThinker" />
</div>

#### GAIA Benchmark

<div align="center">
  <img src="https://huggingface.co/datasets/miromind-ai/MiroFlow-Benchmarks/resolve/main/assets/MiroThinker_v0.2_Performance_1.png" width="80%" alt="MiroThinker" />
</div>

</details>

### MiroThinker-v0.1

<details>
  <summary>📦 Click to expand MiroThinker-v0.1 details</summary>

#### GAIA Benchmark

<div align="center">

| **Method**                   | Text-103<br>Best Pass@1 | Text-103<br>Pass@1 (Avg@8) | Val-165<br>Best Pass@1 | Val-165<br>Pass@1 (Avg@8) |
|------------------------------|:-----------------------:|:--------------------------:|:----------------------:|:-------------------------:|
| **🔹—— 7B/8B Models ——**     |                         |                            |                        |                           |
| Search-o1-7B                 |          17.5           |             -              |           -            |             -             |
| R1-Searcher-7B               |          20.4           |             -              |           -            |             -             |
| WebDancer-7B                 |          31.0           |             -              |           -            |             -             |
| WebSailor-7B                 |          37.9           |             -              |           -            |             -             |
| CK-Pro-8B                    |          40.3           |             -              |          32.7          |             -             |
| **MiroThinker-8B-SFT-v0.1**  |          44.7           |            40.1            |          34.6          |           31.8            |
|     + Commercial Tools       |          46.6           |            42.1            |          37.6          |           33.9            |
| **MiroThinker-8B-DPO-v0.1**  |          46.6           |            44.8            |          37.0          |           35.4            |
|     + Commercial Tools       |        **50.5**         |          **46.7**          |        **38.2**        |         **35.9**          |
| **🔹—— 14B Models ——**       |                         |                            |                        |                           |
| **MiroThinker-14B-SFT-v0.1** |          47.6           |            44.4            |          37.0          |           34.4            |
|     + Commercial Tools       |          49.5           |            47.5            |          41.8          |           39.8            |
| **MiroThinker-14B-DPO-v0.1** |          48.5           |            46.6            |          42.4          |           39.2            |
|     + Commercial Tools       |        **52.4**         |          **48.5**          |        **45.5**        |         **42.0**          |
| **🔹—— 32B Models ——**       |                         |                            |                        |                           |
| Qwen3-32B                    |          31.1           |            26.7            |          29.7          |           26.4            |
| Search-o1-32B                |          28.2           |             -              |           -            |             -             |
| WebThinker-32B-RL            |          48.5           |             -              |           -            |             -             |
| WebDancer-QwQ-32B            |          51.5           |             -              |           -            |             -             |
| WebSailor-32B                |          53.2           |             -              |           -            |             -             |
| WebShaper-QwQ-32B            |          53.3           |             -              |           -            |             -             |
| **MiroThinker-32B-SFT-v0.1** |          55.3           |            51.3            |          44.9          |           42.7            |
|     + Commercial Tools       |          58.3           |            54.2            |          48.5          |           45.8            |
| **MiroThinker-32B-DPO-v0.1** |          57.3           |            54.1            |          48.5          |           45.9            |
|     + Commercial Tools       |        **60.2**         |          **57.9**          |        **50.9**        |         **48.9**          |

</div>

1. Following the practices of WebThinker, WebAgents, and CognitiveKernel, we report the Best Pass@1, the highest score across three runs, which often reflects stronger performance, though it may exhibit some variability. To provide a more stable measure, we additionally report Pass@1 (Avg@8), which offers greater consistency at the cost of slightly lower scores.

1. For consistency with prior open-source works, we evaluate GAIA-Text-103 using the WebAgents LLM-as-judge template, and report results on GAIA-Val-165 using the official GAIA scorer script.

1. By default, we use open-source tools wherever possible, except for the code tool [E2B](https://github.com/e2b-dev/E2B) and the Google search tool [Serper](https://serper.dev/). We use [Whisper](https://huggingface.co/openai/whisper-large-v3-turbo), [Qwen2.5-VL-72B-Instruct](https://huggingface.co/Qwen/Qwen2.5-VL-72B-Instruct), and [Qwen3-235B-A22B-Thinking-2507](https://huggingface.co/Qwen/Qwen3-235B-A22B-Thinking-2507) in our implementation. The framework can be easily extended to other open-source tools of your choice.

1. Replacing these open-source tools with commercial alternatives can yield performance gains. Commercial tools were mainly used for multimodal capabilities and certain complex reasoning subtasks. The majority of tasks, including planning, browsing, refinement, navigation, and more, were handled by our models.

#### More Benchmarks

<div align="center">

| Method                       | HLE<br>Pass@1 | Frames<br>Pass@1 | BrowseComp<br>Pass@1 | BrowseComp-ZH<br>Pass@1 | WebWalkerQA<br>Pass@1 |
|------------------------------|:-------------:|:----------------:|:--------------------:|:-----------------------:|:---------------------:|
| OpenAI Deep Research         |     26.6      |        -         |         51.5         |          42.9           |           -           |
| Gemini Deep Research         |     26.9      |        -         |          -           |            -            |           -           |
| Kimi-Researcher              |     26.9      |       78.8       |          -           |            -            |           -           |
|                              |               |                  |                      |                         |                       |
| WebDancer-7B                 |       -       |        -         |          -           |            -            |         36.0          |
| WebSailor-7B                 |       -       |        -         |         6.7          |          14.2           |           -           |
| **MiroThinker-8B-SFT-v0.1**  |       -       |       58.0       |         5.5          |           9.3           |         41.3          |
| **MiroThinker-8B-DPO-v0.1**  |       -       |       64.4       |         8.7          |          13.6           |         45.7          |
|                              |               |                  |                      |                         |                       |
| WebThinker-32B-RL            |       -       |        -         |          -           |            -            |         46.5          |
| WebDancer-QwQ-32B            |       -       |        -         |         3.8          |          18.0           |         47.9          |
| WebSailor-32B                |       -       |        -         |         10.5         |          25.5           |           -           |
| WebShaper-32B                |       -       |        -         |          -           |            -            |         51.4          |
| **MiroThinker-32B-SFT-v0.1** |     10.2      |       70.4       |         10.6         |          13.8           |         45.7          |
| **MiroThinker-32B-DPO-v0.1** |     11.8      |       71.7       |         13.0         |          17.0           |         49.3          |

</div>

1. MiroThinker’s performance was tested with this repository and open-source tools; other models’ results are from their papers and official sites.

1. As [MiroVerse-v0.1](https://huggingface.co/datasets/miromind-ai/MiroVerse-v0.1) mainly contains English data, the model’s Chinese capability is limited. We plan to add more Chinese data to improve performance in the next version.

</details>

## 🚀 Quick Start

### Prerequisites

- 🐍 **Python 3.10+**
- 📦 **uv package manager** ([Installation guide](https://github.com/astral-sh/uv))
- 🔑 **Required API keys** (see configuration section below)

### Installation

#### 1. **Clone the Repository**

```bash
git clone https://github.com/MiroMindAI/MiroThinker
cd MiroThinker
```

#### 2. **Download Benchmark Data**

```bash
wget https://huggingface.co/datasets/miromind-ai/MiroFlow-Benchmarks/resolve/main/data_20250911_password_protected.zip
unzip data_20250911_password_protected.zip
# The unzip passcode is: pf4*
rm data_20250911_password_protected.zip
```

> **🔐 Password**: The unzip passcode is `pf4*`.

#### 3. **Setup Environment**

```bash
# Shift working dir
cd apps/miroflow-agent
# Install environment
uv sync
# Create .env file with your API keys
cp .env.example .env
# Edit .env with your actual API keys based on your chosen configuration
```

> **📝 Environment Variables**: The `.env.example` file contains all available environment variables. Configure the variables according to the tools used in your chosen agent configuration (see [Tool Configuration](#tool-configuration) section below).

### Tool Configuration

#### Tools Used in MiroThinker v1.0

MiroThinker v1.0 uses the following MCP servers in its evaluation (see [MiroFlow Tools README](libs/miroflow-tools/README.md) for details):

| Server | Description | Tools |
|:-------|:------------|:-----|
| **`tool-python`** | Execution environment and file management (E2B sandbox) | `create_sandbox`, `run_command`, `run_python_code`, `upload_file_from_local_to_sandbox`, `download_file_from_sandbox_to_local`, `download_file_from_internet_to_sandbox` |
| **`search_and_scrape_webpage`** | Google search via Serper API | `google_search` |
| **`jina_scrape_llm_summary`** | Web scraping with LLM-based information extraction | `scrape_and_extract_info` |

#### Additional Available Tools

The following optional tools are available but were not used in MiroThinker v1.0 evaluation:

| Category | Commercial | Open-Source |
|:---------|:-----------|:-----------|
| **Vision Processing** | `tool-vqa` (Claude) | `tool-vqa-os` |
| **Audio Processing** | `tool-transcribe` (OpenAI) | `tool-transcribe-os` (Whisper) |
| **Reasoning Engine** | `tool-reasoning` (Claude) | `tool-reasoning-os` |
| **Document Reading** | `tool-reading` (MarkItDown) | - |
| **Web Searching** | `tool-google-search` (Google + scraping) | `tool-sougou-search` (Sougou, Chinese) |

See the [MiroFlow Tools README](libs/miroflow-tools/README.md) for complete documentation of all available tools.

#### Pre-configured Agent Settings

The `apps/miroflow-agent/conf/agent/` directory contains several pre-configured agent settings. Each configuration uses different tools and requires corresponding environment variables in your `.env` file.

| Configuration File | Description | Max Turns | Context Retention | Required Environment Variables |
|:-------------------|:------------|:----------|:------------------|:-------------------------------|
| **`single_agent.yaml`** | Single-agent configuration used in MiroThinker v1.0 | 600 | Keep all results | `SERPER_API_KEY`, `SERPER_BASE_URL`, `JINA_API_KEY`, `JINA_BASE_URL`, `E2B_API_KEY`, `SUMMARY_LLM_BASE_URL`, `SUMMARY_LLM_MODEL_NAME`, `SUMMARY_LLM_API_KEY` |
| **`single_agent_keep5.yaml`** | Single-agent with recency-based context retention | 600 | Keep 5 most recent | Same as `single_agent.yaml` |
| **`default.yaml`** | Default multi-agent configuration with all tools | 20 | Keep all results | `E2B_API_KEY`, `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `SERPER_API_KEY`, `SERPER_BASE_URL`, `JINA_API_KEY`, `JINA_BASE_URL` |
| **`evaluation.yaml`** | Multi-agent with commercial tools (v0.1/v0.2) | 50 | Keep all results | Same as `default.yaml` |
| **`evaluation_os.yaml`** | Multi-agent with open-source tools (v0.1/v0.2) | 50 | Keep all results | `E2B_API_KEY`, `VISION_API_KEY`, `VISION_BASE_URL`, `VISION_MODEL_NAME`, `WHISPER_API_KEY`, `WHISPER_BASE_URL`, `WHISPER_MODEL_NAME`, `REASONING_API_KEY`, `REASONING_BASE_URL`, `REASONING_MODEL_NAME`, `SERPER_API_KEY`, `SERPER_BASE_URL`, `JINA_API_KEY`, `JINA_BASE_URL` |

> **💡 Note**: All environment variables are listed in `apps/miroflow-agent/.env.example`. Copy it to `.env` and fill in the values for the tools you plan to use.

#### Creating Custom Tool Configurations

You can create your own YAML configuration file to freely combine MCP servers. Here's how:

1. **Create a new YAML file** in `apps/miroflow-agent/conf/agent/`:

```yaml
# conf/agent/my_custom_config.yaml
defaults:
  - default
  - _self_

main_agent:
  tools:
    - tool-python                    # Execution environment
    - search_and_scrape_webpage      # Google search
    - jina_scrape_llm_summary        # Web scraping with LLM
    - tool-vqa                       # Vision processing (optional)
    - tool-transcribe                # Audio processing (optional)
    - tool-reasoning                 # Reasoning engine (optional)
    - tool-reading                   # Document reading (optional)
  max_turns: 400  # Maximum number of turns

sub_agents:
  agent-browsing:  # Optional sub-agent
    tools:
      - tool-google-search
      - tool-vqa
      - tool-reading
      - tool-python
    max_turns: 50

keep_tool_result: -1  # Context retention budget: -1 keeps all tool results, or specify K to keep only the K most recent tool responses
```

> **💡 Context Retention Strategy**: The `keep_tool_result` parameter implements a **recency-based context retention** strategy. In the standard ReAct paradigm, all tool outputs are retained in the message history, which can lead to inefficient context utilization. Empirically, we observe that the model's subsequent actions depend primarily on recent observations rather than distant ones. This strategy retains only the most recent K tool responses (where K is the `keep_tool_result` value) while preserving the complete sequence of thoughts and actions.
>
> **Benefits:**
>
> - ✅ Preserves the reasoning and action trace
> - ✅ Focuses the model's attention on the most contextually relevant observations
> - ✅ Frees additional context space for extended reasoning and deeper tool-use trajectories
> - ✅ Does not lead to performance degradation while allowing more context space for interactive scaling
>
> **Usage:** Set `keep_tool_result: -1` to keep all tool results, or specify a positive integer K (e.g., `keep_tool_result: 5`) to keep only the K most recent tool responses.

2. **Use your custom configuration** when running evaluations:

```bash
cd apps/miroflow-agent
uv run main.py llm=qwen-3 agent=my_custom_config llm.base_url=https://your_base_url/v1
```

3. **Configure environment variables** in `.env` based on the tools you use.

   All available environment variables are listed in `apps/miroflow-agent/.env.example`. Copy it to `.env` and configure the variables according to your chosen configuration:

   ```bash
   cd apps/miroflow-agent
   cp .env.example .env
   # Edit .env with your actual API keys
   ```

   **Example for MiroThinker v1.0** (`single_agent.yaml` or `single_agent_keep5.yaml`):

   ```bash
   # Required for MiroThinker v1.0 tools
   SERPER_API_KEY=your_serper_key                    # For search_and_scrape_webpage
   SERPER_BASE_URL="https://google.serper.dev"
   JINA_API_KEY=your_jina_key                         # For jina_scrape_llm_summary
   JINA_BASE_URL="https://r.jina.ai"
   E2B_API_KEY=your_e2b_key                           # For tool-python

   # Required for jina_scrape_llm_summary
   SUMMARY_LLM_BASE_URL=your_llm_base_url
   SUMMARY_LLM_MODEL_NAME=your_llm_model_name
   SUMMARY_LLM_API_KEY=your_llm_api_key               # Optional, depends on LLM provider
   ```

   **For other configurations**, refer to the table above to see which environment variables are required.

<details>
  <summary>🔑 Click to expand optional API keys</summary>

```bash
# API for LLM-as-Judge (for benchmark testing, optional)
OPENAI_API_KEY=your_openai_key

# API for Open-Source Audio Transcription Tool (for benchmark testing, optional)
WHISPER_MODEL_NAME="openai/whisper-large-v3-turbo"
WHISPER_API_KEY=your_whisper_key
WHISPER_BASE_URL="https://your_whisper_base_url/v1"

# API for Open-Source VQA Tool (for benchmark testing, optional)
VISION_MODEL_NAME="Qwen/Qwen2.5-VL-72B-Instruct"
VISION_API_KEY=your_vision_key
VISION_BASE_URL="https://your_vision_base_url/v1/chat/completions"

# API for Open-Source Reasoning Tool (for benchmark testing, optional)
REASONING_MODEL_NAME="Qwen/Qwen3-235B-A22B-Thinking-2507"
REASONING_API_KEY=your_reasoning_key
REASONING_BASE_URL="https://your_reasoning_base_url/v1/chat/completions"

# API for Claude Sonnet 3.7 as Commercial Tools (optional)
ANTHROPIC_API_KEY=your_anthropic_key

# API for Sougou Search (optional)
TENCENTCLOUD_SECRET_ID=your_tencent_cloud_secret_id
TENCENTCLOUD_SECRET_KEY=your_tencent_cloud_secret_key
```

</details>

### Serve the MiroThinker Model

#### Option 1 (Recommended): Serve with SGLang

Use SGLang to serve MiroThinker models at port 61002:

```bash
NUM_GPUS=4
PORT=61002

# Downloading model from HF
MODEL_PATH=miromind-ai/MiroThinker-32B-DPO-v0.2

python3 -m sglang.launch_server \
    --model-path $MODEL_PATH \
    --tp $NUM_GPUS \
    --dp 1 \
    --host 0.0.0.0 \
    --port $PORT \
    --trust-remote-code \
    --chat-template assets/qwen3_nonthinking.jinja
```

> **📍 Server URL**: This will start a server at `http://0.0.0.0:$PORT`. Use this as your server base URL (e.g., `http://0.0.0.0:61002/v1`).

#### Option 2: Quantized Light-Weight Options

We also provide comprehensive guidance for serving MiroThinker models using CPU-optimized and GPU-accelerated quantization techniques, along with detailed analysis and guidelines for deployment with llama.cpp, Ollama, SGLang, and other inference frameworks.

> **📖 Complete Guide**: See [Deployment Documentation](apps/gradio-demo/) for detailed deployment instructions.

### Basic Usage

#### 1. **Run a single evaluation**

```bash
cd apps/miroflow-agent
uv run main.py llm=qwen-3 agent=single_agent llm.base_url=https://your_base_url/v1
```

> **💡 Tip**: For MiroThinker v1.0, use `agent=single_agent` or `agent=single_agent_keep5`. Replace `https://your_base_url/v1` with your actual model server URL.

#### 2. **Run comprehensive benchmark evaluation**

> **Note:** For MiroThinker v1.0, use `single_agent` or `single_agent_keep5` configurations. The `evaluation` and `evaluation_os` configurations are for v0.1/v0.2.

```bash
# GAIA-Val-165
LLM_MODEL="xxx" BASE_URL="xxx" bash scripts/run_evaluate_multiple_runs_gaia-validation.sh
# Other benchmarks follow the same pattern.
```

<details>
  <summary>📋 Click to expand all benchmark commands</summary>

```bash
# GAIA-Text-103
LLM_MODEL="xxx" BASE_URL="xxx" bash scripts/run_evaluate_multiple_runs_gaia-validation-text-103.sh

# WebWalkerQA
LLM_MODEL="xxx" BASE_URL="xxx" bash scripts/run_evaluate_multiple_runs_webwalkerqa.sh

# HLE
LLM_MODEL="xxx" BASE_URL="xxx" bash scripts/run_evaluate_multiple_runs_hle.sh

# HLE-Text-2158
LLM_MODEL="xxx" BASE_URL="xxx" bash scripts/run_evaluate_multiple_runs_hle-text-2158.sh

# HLE-Text-500
LLM_MODEL="xxx" BASE_URL="xxx" bash scripts/run_evaluate_multiple_runs_hle-text-500.sh

# FRAMES
LLM_MODEL="xxx" BASE_URL="xxx" bash scripts/run_evaluate_multiple_runs_frames.sh

# BrowseComp-EN
LLM_MODEL="xxx" BASE_URL="xxx" bash scripts/run_evaluate_multiple_runs_browsecomp.sh

# BrowseComp-ZH
LLM_MODEL="xxx" BASE_URL="xxx" bash scripts/run_evaluate_multiple_runs_browsecomp_zh.sh

# XBench-DeepSearch
LLM_MODEL="xxx" BASE_URL="xxx" bash scripts/run_evaluate_multiple_runs_xbench_deepsearch.sh

# FutureX
LLM_MODEL="xxx" BASE_URL="xxx" bash scripts/run_evaluate_multiple_runs_futurex.sh
```

</details>

#### 3. **Monitor evaluation progress**

```bash
# For GAIA-Validation
python benchmarks/check_progress/check_progress_gaia-validation.py /path/to/evaluation/logs

# For GAIA-Text-103
python benchmarks/check_progress/check_progress_gaia-validation-text-103.py /path/to/evaluation/logs

# For HLE-Text-2158
python benchmarks/check_progress/check_progress_hle-text-2158.py /path/to/evaluation/logs

# For HLE-Text-500
python benchmarks/check_progress/check_progress_hle-text-500.py /path/to/evaluation/logs

# Others follow the same pattern
```

## 📊 Trace Collection

The trace collection scripts automatically save logs in the `logs/` directory in `chatml` format, ready for SFT and DPO training.

<details>
<summary>📋 Click to expand trace collection commands</summary>

```bash
cd apps/collect-trace

# Collect Traces for SFT
uv run bash scripts/collect_trace_claude37.sh
uv run bash scripts/collect_trace_gpt5.sh

# Collect Traces for DPO
uv run bash scripts/collect_trace_qwen3.sh
```

</details>

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

We extend our sincere gratitude to:

- 🏆 **Benchmark Contributors** for the comprehensive evaluation datasets
- 🌍 **Open Source Community** for the tools and libraries that make this possible
- 👥 **All Contributors** who have helped make MiroThinker better

<div align="center">
  <a href="https://github.com/MiroMindAI/MiroThinker/graphs/contributors">
    <img src="https://contrib.rocks/image?repo=MiroMindAI/MiroThinker" />
  </a>
</div>

Join our community and help us build the future of AI agents!

### References

```
@misc{2025mirothinker,
    title={MiroThinker: An open-source agentic model series trained for deep research and complex, long-horizon problem solving},
    author={MiroMind AI Team},
    howpublished={\url{https://github.com/MiroMindAI/MiroThinker}},
    year={2025}
}
```

[![Star History Chart](https://api.star-history.com/svg?repos=MiroMindAI/MiroThinker&type=Date)](https://star-history.com/#MiroMindAI/MiroThinker&Date)
