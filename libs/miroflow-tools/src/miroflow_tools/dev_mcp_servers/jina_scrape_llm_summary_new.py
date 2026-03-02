# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

import asyncio
import json
import logging
import os
import re
import io
import random
from typing import Any, Dict, List

import httpx
from mcp.server.fastmcp import FastMCP
from playwright.async_api import async_playwright
from pypdf import PdfReader


# Configure logging
logger = logging.getLogger("miroflow")

# --- 1. Environment Configuration ---
SUMMARY_LLM_BASE_URL = os.environ.get("SUMMARY_LLM_BASE_URL")
SUMMARY_LLM_MODEL_NAME = os.environ.get("SUMMARY_LLM_MODEL_NAME")
SUMMARY_LLM_API_KEY = os.environ.get("SUMMARY_LLM_API_KEY")

JINA_API_KEY = os.environ.get("JINA_API_KEY", "")
JINA_BASE_URL = os.environ.get("JINA_BASE_URL", "https://r.jina.ai")

FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
FIRECRAWL_BASE_URL = os.environ.get("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev/v2/scrape")

# --- 2. High Precision Configuration ---
CHUNK_SIZE = 100000  # Target approx 100k chars per Map task
CHUNK_OVERLAP = 10000  # 10k overlap to ensure semantic preservation
MAX_TOTAL_CHARS = 1000000  # Max context supported: 1MB
MAX_CONCURRENT_CHUNKS = 5  # Limit parallel LLM calls

# User-Agent Pool for Playwright and Baseline Fallbacks
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
]

# Initialize FastMCP server
mcp = FastMCP("jina_scrape_llm_summary_new")

# --- 3. PROMPT TEMPLATES ---
EXTRACT_INFO_PROMPT = """You are a professional information extraction assistant. Your goal is to analyze the provided content and extract the specific information requested by the user.

REQUESTED INFORMATION:
{}

STRICT INSTRUCTIONS:
1. FOCUS on the requested information. 
2. EXTRACT SPECIFIC DATA: Names, dates, numbers, coordinates, and clear facts must be preserved exactly as they appear.
3. HANDLING PARTIAL DATA: If the exact answer is not fully present, DO NOT simply say "not found". Instead, extract any partial clues, relevant background details, or "breadcrumbs" that might help a researcher find the answer elsewhere.
4. SUMMARIZE CONTEXT: If the content discusses related topics but misses the specific data points, summarize the related findings to provide context.
5. NO META-TALK: Avoid filler phrases. Directly output the data or the findings.
6. STRUCTURE: Use bullet points, key-value pairs, or clear lists to organize the data.
7. ACCURACY: Ensure every piece of information is directly derived from the source text.
8. RELIABILITY CHECK: After extracting data, add a brief note about data reliability:
   - [CONFIDENCE: HIGH]
   - [CONFIDENCE: MEDIUM]
   - [CONFIDENCE: LOW]

CONTENT TO ANALYZE:
{}

EXTRACTED DATA:"""

REDUCE_PROMPT = """You are an expert knowledge synthesizer. You have been provided with several information fragments extracted from different parts of a long document. 
Your goal is to merge these into a single, cohesive, and definitive answer to the original question.

ORIGINAL QUESTION:
{info}

COLLECTED FRAGMENTS:
{partials}

STRICT MERGING RULES:
1. DEDUPLICATION: Remove all redundant information.
2. SYNTHESIS: Cross-reference fragments. If different parts provide different components of the answer, merge them.
3. RESOLUTION: If fragments seem to contradict, use the one with more specific detail or more recent context.
4. FORMATTING: Organize the final answer clearly (e.g., a consolidated list or a concise table).
5. DIRECT OUTPUT: Do not provide any "Research Status", "Summary", or "Next Steps". Do not use introductory phrases. Output the final data immediately.
6. COMPLETENESS: If the data is still partial, present what is known and what is missing.
7. CONFIDENCE ASSESSMENT: After merging, add a reliability note:
   - If all fragments are consistent and from reliable sources, add: [CONFIDENCE: HIGH - CONSISTENT ACROSS SOURCES]
   - If fragments have minor inconsistencies or are from mixed quality sources, add: [CONFIDENCE: MEDIUM - CONSIDER ADDITIONAL VERIFICATION]
   - If fragments contradict each other or data quality is poor, add: [CONFIDENCE: LOW - STRONG RECOMMENDATION TO VERIFY WITH ADDITIONAL SOURCES]
"""

# --- 4. CORE HELPER FUNCTIONS ---
def smart_split_content(text: str, chunk_size: int, overlap: int) -> List[str]:
    """
    Split long text into overlapping chunks while preserving semantic boundaries.
    Logic aligned with V2 standard, with guaranteed forward progress.
    """
    if not text:
        return []
    
    chunks = []
    start = 0
    text_len = len(text)
    
    while start < text_len:
        end = start + chunk_size
        if end >= text_len:
            chunks.append(text[start:])
            break
            
        search_start = max(start, end - 500)
        search_end = min(text_len, end + 500)
        search_range = text[search_start:search_end]
        
        best_break_rel = -1
        for pattern in ['\n\n', '\n- ', '\n* ', '\n1. ', '\n', '. ', ' ']:
            idx = search_range.rfind(pattern)
            if idx != -1:
                best_break_rel = idx + len(pattern)
                break
        
        effective_end = search_start + best_break_rel if best_break_rel != -1 else end
        
        # Ensure we always move forward at least by 10% of chunk size or at least 'overlap'
        # to avoid infinite loops if overlap is too large
        if effective_end <= start:
            effective_end = start + chunk_size
            
        chunks.append(text[start:effective_end])
        
        # Calculate next start with overlap, but ensure it's ahead of previous start
        next_start = effective_end - overlap
        if next_start <= start:
            start = effective_end # No overlap if it would cause stall
        else:
            start = next_start
            
    return chunks

def _is_huggingface_dataset_or_space_url(url: str) -> bool:
    """Safety check for Hugging Face datasets."""
    if not url:
        return False
    return "huggingface.co/datasets" in url or "huggingface.co/spaces" in url

def check_content_quality(text: str) -> Dict[str, Any]:
    """
    Evaluates text density to detect fragmented or empty results.
    Preserves V2's heuristic density check.
    """
    if not text or len(text.strip()) < 50:
        return {"is_low_quality": True, "warning": "Content is empty or extremely short."}
    
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if not lines:
        return {"is_low_quality": True, "warning": "Content contains no readable text."}
    
    avg_line_length = sum(len(l) for l in lines) / len(lines)
    if len(text) > 2000 and avg_line_length < 15:
        return {
            "is_low_quality": True, 
            "warning": f"Low text density detected (avg {avg_line_length:.1f} chars/line). Content may be fragmented."
        }
    
    return {"is_low_quality": False, "warning": ""}

def get_content_score(res: Dict[str, Any], query: str = "") -> int:
    """
    Multi-dimensional quality scoring system (V3.3 - Robust Edition).
    Analyzes Relevance, Diversity, and Block Patterns with protective heuristics.
    """
    if not res or not res.get("success") or not res.get("content"):
        return -1
    
    content = res["content"]
    content_lower = content.lower()
    score = 10

    # --- 1. Semantic Relevance (Universal & Protective) ---
    relevance_bonus = 0
    if query:
        stop_words = {'what', 'is', 'the', 'of', 'in', 'and', 'to', 'a', 'list', 'show', 'find', 'get', 'me', 'how', 'about'}
        query_words = {w for w in re.findall(r'\w{3,}', query.lower()) if w not in stop_words}
        
        if query_words:
            matches = sum(1 for word in query_words if word in content_lower)
            match_ratio = matches / len(query_words)
            
            if matches == 0:
                score -= 5 # Zero mention of core keywords
            elif match_ratio > 0.6:
                relevance_bonus = 3 # High relevance flag
            elif match_ratio < 0.2:
                score -= 2

    # --- 2. Length & Structure (With Short-Text Protection) ---
    content_len = len(content)
    if content_len < 400:
        score -= (2 if relevance_bonus >= 3 else 6)
    elif content_len < 1200:
        score -= 2

    # --- 3. Information Diversity (Repetition Detection) ---
    words = re.findall(r'\w+', content_lower)
    if len(words) > 25:
        unique_ratio = len(set(words)) / len(words)
        if unique_ratio < 0.3: 
            score -= 4
        elif unique_ratio < 0.45:
            score -= 2

    # --- 4. Refined Block Patterns (Avoid Topic Overlap) ---
    hard_block_patterns = [
        "verification required", "anti-robot verification", "complete the challenge below",
        "checking your browser before accessing", "cloudflare ray id", "enable javascript to continue",
        "access denied", "403 forbidden", "just a moment... security check",
        "captcha", "robot check", "automated request", "please wait while we verify",
        "researchgate security check", "academia.edu verification"
    ]
    if any(pattern in content_lower for pattern in hard_block_patterns):
        score -= 9
        
    # --- 5. Empty/Useless Content Protection (Softer for short useful pages) ---
    if content_len < 30:
        score -= 9
    elif content_len < 100 or len(words) < 10:
        score -= 5
        
    # --- 6. Density Heuristic (V2 Standard) ---
    quality = check_content_quality(content)
    if quality["is_low_quality"]:
        score -= 4
        
    return max(0, min(10, score))

def get_prompt_with_truncation(info_to_extract: str, content: str, truncate_last_num_chars: int = -1) -> str:
    """
    Prepares the extraction prompt with optional gradient truncation.

    Safety mechanism from v4: Always keeps at least 2000 characters to prevent
    catastrophic information loss from misconfigured truncation parameters.
    """
    if truncate_last_num_chars > 0:
        # Calculate how many chars to KEEP (not how many to remove)
        keep_chars = max(len(content) - truncate_last_num_chars, 2000)
        if keep_chars < len(content):
            content = content[:keep_chars] + "\n[...truncated due to length limits]"
    return EXTRACT_INFO_PROMPT.format(info_to_extract, content)

# --- 5. SCRAPING ENGINES ---
async def scrape_url_with_jina(url: str, custom_headers: Dict[str, str] = None, max_chars: int = MAX_TOTAL_CHARS) -> Dict[str, Any]:
    """
    Scrape content from a URL using Jina.ai Reader API.
    """
    if not url or not url.strip():
        return {
            "success": False, "content": "", "error": "URL cannot be empty",
            "line_count": 0, "char_count": 0, "last_char_line": 0, "all_content_displayed": False
        }
    
    if not JINA_API_KEY:
        return {
            "success": False, "content": "", "error": "JINA_API_KEY environment variable is not set",
            "line_count": 0, "char_count": 0, "last_char_line": 0, "all_content_displayed": False
        }
    
    clean_url = url
    if clean_url.startswith("https://r.jina.ai/") and clean_url.count("http") >= 2:
        clean_url = clean_url[len("https://r.jina.ai/") :]
    
    jina_base = JINA_BASE_URL.rstrip('/')
    clean_path = clean_url.lstrip('/')
    jina_url = f"{jina_base}/{clean_path}"
    
    headers = {"Authorization": f"Bearer {JINA_API_KEY}"}
    if custom_headers:
        headers.update(custom_headers)
    
    retry_delays = [1, 2, 4, 8]
    response = None

    try:
        for attempt, delay in enumerate(retry_delays, 1):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        jina_url, 
                        headers=headers, 
                        timeout=httpx.Timeout(None, connect=20, read=60), 
                        follow_redirects=True
                    )
                
                # Check if request was successful
                response.raise_for_status()
                break # Success, exit retry loop
                
            except httpx.ConnectTimeout as e:
                if attempt < len(retry_delays):
                    logger.info(f"Jina Scrape: Connection timeout, {delay}s before next attempt (attempt {attempt + 1})")
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"Jina Scrape: Connection retry attempts exhausted, url: {url}")
                    raise e
            except httpx.ConnectError as e:
                if attempt < len(retry_delays):
                    logger.info(f"Jina Scrape: Connection error: {e}, {delay}s before next attempt")
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"Jina Scrape: Connection retry attempts exhausted, url: {url}")
                    raise e
            except httpx.ReadTimeout as e:
                if attempt < len(retry_delays):
                    logger.info(f"Jina Scrape: Read timeout, {delay}s before next attempt (attempt {attempt + 1})")
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"Jina Scrape: Read timeout retry attempts exhausted, url: {url}")
                    raise e
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                should_retry = status_code >= 500 or status_code in [408, 409, 425, 429]
                
                if should_retry and attempt < len(retry_delays):
                    logger.info(f"Jina Scrape: HTTP {status_code} (retryable), retry in {delay}s, url: {url}")
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"Jina Scrape: HTTP {status_code} ({'retry exhausted' if should_retry else 'non-retryable'}), url: {url}")
                    raise e
            except httpx.RequestError as e:
                if attempt < len(retry_delays):
                    logger.info(f"Jina Scrape: Unknown request exception: {e}, url: {url}, {delay}s before next attempt")
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"Jina Scrape: Unknown request exception retry attempts exhausted, url: {url}")
                    raise e
                    
    except Exception as e:
        error_msg = f"Jina Scrape: Unexpected error occurred: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False, "content": "", "error": error_msg,
            "line_count": 0, "char_count": 0, "last_char_line": 0, "all_content_displayed": False
        }

    content = response.text
    if not content:
        return {
            "success": False, "content": "", "error": "No content returned from Jina.ai API",
            "line_count": 0, "char_count": 0, "last_char_line": 0, "all_content_displayed": False
        }
    
    try:
        content_dict = json.loads(content)
        if isinstance(content_dict, dict) and content_dict.get("name") == "InsufficientBalanceError":
            return {
                "success": False, "content": "", "error": "Insufficient balance",
                "line_count": 0, "char_count": 0, "last_char_line": 0, "all_content_displayed": False
            }
    except json.JSONDecodeError:
        pass
    
    total_char_count = len(content)
    total_line_count = content.count("\n") + 1 if content else 0
    
    displayed_content = content[:max_chars]
    all_content_displayed = total_char_count <= max_chars
    last_char_line = displayed_content.count("\n") + 1 if displayed_content else 0
    
    return {
        "success": True,
        "content": displayed_content,
        "error": "",
        "line_count": total_line_count,
        "char_count": total_char_count,
        "last_char_line": last_char_line,
        "all_content_displayed": all_content_displayed
    }

async def scrape_url_with_firecrawl(url: str, max_chars: int = MAX_TOTAL_CHARS) -> Dict[str, Any]:
    """
    Scrape content from a URL using Firecrawl API.
    Used as the first fallback for Jina due to high reliability.
    Returns consistent format with other scraping methods.
    """
    if not FIRECRAWL_API_KEY:
        return {
            "success": False,
            "content": "",
            "error": "FIRECRAWL_API_KEY not set",
            "char_count": 0,
            "line_count": 0,
            "all_content_displayed": False,
            "last_char_line": 0
        }

    payload = {
        "url": url,
        "formats": ["markdown"],
        "onlyMainContent": True
    }
    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json"
    }
    
    retry_delays = [1, 2, 4]
    
    async with httpx.AsyncClient() as client:
        for attempt, delay in enumerate(retry_delays, 1):
            try:
                response = await client.post(
                    FIRECRAWL_BASE_URL, 
                    json=payload, 
                    headers=headers, 
                    timeout=httpx.Timeout(None, connect=20, read=60)
                )
                
                if response.status_code == 200:
                    res_data = response.json()
                    if res_data.get('success'):
                        content = res_data['data'].get('markdown', '')
                        if not content:
                            return {
                                "success": False,
                                "content": "",
                                "error": "Firecrawl returned empty content",
                                "char_count": 0,
                                "line_count": 0,
                                "all_content_displayed": False,
                                "last_char_line": 0
                            }
                        
                        total_char_count = len(content)
                        total_line_count = content.count("\n") + 1
                        displayed_content = content[:max_chars]
                        
                        return {
                            "success": True,
                            "content": displayed_content,
                            "error": "",
                            "char_count": total_char_count,
                            "line_count": total_line_count,
                            "all_content_displayed": total_char_count <= max_chars,
                            "last_char_line": displayed_content.count("\n") + 1 if displayed_content else 0
                        }
                    else:
                        error_msg = res_data.get('error', 'Unknown Firecrawl error')
                        if attempt < len(retry_delays):
                            await asyncio.sleep(delay)
                            continue
                        return {
                            "success": False,
                            "content": "",
                            "error": f"Firecrawl API error: {error_msg}",
                            "char_count": 0,
                            "line_count": 0,
                            "all_content_displayed": False,
                            "last_char_line": 0
                        }
                
                elif response.status_code >= 500 or response.status_code in [408, 429]:
                    if attempt < len(retry_delays):
                        await asyncio.sleep(delay)
                        continue
                
                response.raise_for_status()
                
            except Exception as e:
                if attempt < len(retry_delays):
                    await asyncio.sleep(delay)
                    continue
                return {
                    "success": False,
                    "content": "",
                    "error": f"Firecrawl exception: {str(e)}",
                    "char_count": 0,
                    "line_count": 0,
                    "all_content_displayed": False,
                    "last_char_line": 0
                }

    return {
        "success": False,
        "content": "",
        "error": "Firecrawl failed after retries",
        "char_count": 0,
        "line_count": 0,
        "all_content_displayed": False,
        "last_char_line": 0
    }

async def scrape_url_with_playwright(url: str, max_chars: int = MAX_TOTAL_CHARS) -> Dict[str, Any]:
    """
    Advanced fallback scraping using Playwright.
    Includes Stealth measures, PDF parsing fallback, and dynamic rendering waits.
    """
    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = await browser.new_context(user_agent=random.choice(USER_AGENTS), ignore_https_errors=True)
            page = await context.new_page()
            
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            logger.info(f"Playwright: Scraping {url}")
            response = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            if not response:
                return {
                    "success": False,
                    "content": "",
                    "error": "No response from Playwright",
                    "char_count": 0,
                    "line_count": 0,
                    "all_content_displayed": False,
                    "last_char_line": 0
                }
            
            content_type = response.headers.get("content-type", "").lower()
            content = ""
            
            if "application/pdf" in content_type or url.lower().endswith(".pdf"):
                pdf_bytes = await response.body()
                if PdfReader:
                    with io.BytesIO(pdf_bytes) as f:
                        reader = PdfReader(f)
                        pages_to_read = min(len(reader.pages), 50)
                        content = "\n".join(reader.pages[i].extract_text() for i in range(pages_to_read))
                else:
                    content = "PDF detected but pypdf is not installed."
            else:
                await asyncio.sleep(3)
                content = await page.evaluate("document.body.innerText")
            
            if not content or not content.strip():
                return {
                    "success": False,
                    "content": "",
                    "error": "No text extracted",
                    "char_count": 0,
                    "line_count": 0,
                    "all_content_displayed": False,
                    "last_char_line": 0
                }
            
            total_char_count = len(content)
            total_line_count = content.count("\n") + 1 if content else 0
            displayed_content = content[:max_chars]
            
            return {
                "success": True, 
                "content": displayed_content, 
                "char_count": total_char_count, 
                "line_count": total_line_count,
                "all_content_displayed": total_char_count <= max_chars,
                "last_char_line": displayed_content.count("\n") + 1 if displayed_content else 0
            }
        except Exception as e:
            return {
                "success": False,
                "content": "",
                "error": f"Playwright error: {str(e)}",
                "char_count": 0,
                "line_count": 0,
                "all_content_displayed": False,
                "last_char_line": 0
            }
        finally:
            if browser:
                await browser.close()

async def scrape_url_with_python(url: str, custom_headers: Dict[str, str] = None, max_chars: int = MAX_TOTAL_CHARS) -> Dict[str, Any]:
    """Final baseline fallback using standard httpx. Aligned with backup retry strategy."""
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    if custom_headers:
        headers.update(custom_headers)
        
    retry_delays = [1, 2, 4]
    
    async with httpx.AsyncClient() as client:
        for attempt, delay in enumerate(retry_delays, 1):
            try:
                response = await client.get(url, headers=headers, timeout=30, follow_redirects=True)
                response.raise_for_status()
                content = response.text
                
                total_char_count = len(content)
                total_line_count = content.count("\n") + 1 if content else 0
                displayed_content = content[:max_chars]
                
                return {
                    "success": True, 
                    "content": displayed_content, 
                    "char_count": total_char_count,
                    "line_count": total_line_count,
                    "all_content_displayed": total_char_count <= max_chars,
                    "last_char_line": displayed_content.count("\n") + 1 if displayed_content else 0
                }
            except Exception as e:
                if attempt < len(retry_delays):
                    await asyncio.sleep(delay)
                else:
                    return {
                        "success": False,
                        "content": "",
                        "error": f"Python fallback failed: {str(e)}",
                        "char_count": 0,
                        "line_count": 0,
                        "all_content_displayed": False,
                        "last_char_line": 0
                    }

# --- 6. LLM INTERACTION ENGINE ---
async def call_robust_llm(
    prompt: str, 
    max_tokens: int = 4096, 
    temperature: float = 0.2, 
    info_for_truncation: str = None, 
    original_content: str = None
) -> Dict[str, Any]:
    """
    Robust LLM API caller.
    Aligned with V2 logic: handles GPT-5 parameters, Context Limits, and Hallucination detection.
    """
    if not SUMMARY_LLM_BASE_URL or not SUMMARY_LLM_MODEL_NAME:
        return {"success": False, "extracted_info": "", "error": "LLM Base URL or Model Name not configured"}

    headers = {
        "Content-Type": "application/json",
        "HTTP-Referer": "https://miromind.site",
        "X-Title": "MiroThinker Information Extractor"
    }
    if SUMMARY_LLM_API_KEY:
        headers["Authorization"] = f"Bearer {SUMMARY_LLM_API_KEY}"

    payload = {
        "model": SUMMARY_LLM_MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature
    }
    
    is_gpt = "gpt" in str(SUMMARY_LLM_MODEL_NAME).lower()
    payload["max_completion_tokens" if is_gpt else "max_tokens"] = max_tokens
    
    if "gpt-5" in str(SUMMARY_LLM_MODEL_NAME).lower():
        payload.update({"service_tier": "flex", "reasoning_effort": "minimal"})

    retry_delays = [1, 2, 4, 8]
    for attempt, delay in enumerate(retry_delays):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    SUMMARY_LLM_BASE_URL, 
                    headers=headers, 
                    json=payload, 
                    timeout=httpx.Timeout(None, connect=30, read=600)
                )
                
                # Check for context window errors
                if response.status_code == 400:
                    resp_text = response.text.lower()
                    if any(kw in resp_text for kw in ["context_length", "too long", "too many tokens", "exceeds"]):
                        if original_content and info_for_truncation:
                            logger.warning(f"LLM: Context limit hit (attempt {attempt + 1}). Retrying with gradient truncation...")
                            payload["messages"][0]["content"] = get_prompt_with_truncation(
                                info_for_truncation, original_content, truncate_last_num_chars=40960 * (attempt + 1)
                            )
                            await asyncio.sleep(delay)
                            continue
                
                response.raise_for_status()
                data = response.json()
                output = data["choices"][0]["message"]["content"]
                
                # Hallucination Loop Protection
                if output and len(output) >= 50:
                    if output.count(output[-50:]) > 5:
                        logger.info("LLM: Hallucination loop detected. Retrying with higher temperature...")
                        payload["temperature"] = min(payload.get("temperature", 0.2) + 0.2, 1.0)
                        await asyncio.sleep(delay)
                        continue
                
                return {
                    "success": True, 
                    "extracted_info": output, 
                    "tokens_used": data.get("usage", {}).get("total_tokens", 0)
                }
                
        except Exception as e:
            # GPT-5 Special handling for service_tier
            if "gpt-5" in str(SUMMARY_LLM_MODEL_NAME).lower() and "service_tier" in payload:
                logger.info("Retrying GPT-5 without service_tier...")
                payload.pop("service_tier", None)
                continue
                
            if attempt < len(retry_delays) - 1:
                logger.warning(f"LLM attempt {attempt + 1} failed: {str(e)}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
            else:
                return {"success": False, "extracted_info": "", "error": f"LLM Error after {len(retry_delays)} attempts: {str(e)}"}
                
    return {"success": False, "extracted_info": "", "error": "LLM retries exhausted"}

# --- 7. MAIN MCP TOOL DEFINITION ---
@mcp.tool()
async def scrape_and_extract_info(
    url: str, 
    info_to_extract: str, 
    custom_headers: Dict[str, str] = None
):
    """  
    Scrape content from a URL, including web pages, PDFs, code files, and other supported resources, and extract meaningful information using an LLM.
    If you need to extract information from a PDF, please use this tool.
    
    This tool is optimized for high-precision extraction from extremely long documents (up to 1MB) by using a Map-Reduce strategy. Fallback Logic (first to last): Jina.ai, Firecrawl, Playwright, and Python HTTPX. The tool assigns quality scores to each result and selects the best possible input for the LLM.

    Args:
        url (str): The URL to scrape content from. Supports various types of URLs such as web pages, PDFs, research papers, raw text/code files (e.g., GitHub, Gist), and similar sources.
        info_to_extract (str): The specific types of information to extract (usually a detailed question or a list of data points).
        custom_headers (Dict[str, str]): Additional HTTP headers to include in the scraping request (e.g., for authentication or specific site requirements).

    Returns:
        Dict[str, Any]: A dictionary containing:
            - success (bool): Whether the operation was successful.
            - url (str): The original URL processed.
            - extracted_info (str): The final extracted information or answer to the question.
            - error (str): Error message if any part of the operation failed.
            - verification_recommendation (str): Guidance on whether additional verification is needed based on confidence level.
            - scrape_stats (Dict): Detailed statistics about the scraping (char_count, line_count, chunks_processed, method_used).
            - model_used (str): The specific LLM model used for extraction and synthesis.
            - tokens_used (int): Total number of tokens consumed across all LLM calls.
    """
    if _is_huggingface_dataset_or_space_url(url):
        return json.dumps({
            "success": False, "url": url, "error": "HF Dataset scraping blocked.", 
            "scrape_stats": {}, "tokens_used": 0
        }, ensure_ascii=False)

    # --- Phase 1: Robust Scraping Chain (Best Content Wins) ---
    best_res, best_method, best_score = None, None, -1

    # Tier 1: Jina
    jina_res = await scrape_url_with_jina(url, custom_headers)
    jina_score = get_content_score(jina_res, info_to_extract)
    best_res, best_method, best_score = jina_res, "Jina", jina_score

    # Tier 2: Firecrawl (First fallback, highly reliable)
    if best_score < 5:
        logger.info(f"Jina quality low (Score: {best_score}). Trying Firecrawl...")
        fc_res = await scrape_url_with_firecrawl(url)
        fc_score = get_content_score(fc_res, info_to_extract)
        if fc_score > best_score:
            best_res, best_method, best_score = fc_res, "Firecrawl", fc_score

    # Tier 3: Playwright
    if best_score < 5:
        logger.info(f"Current quality low (Score: {best_score}). Trying Playwright...")
        pw_res = await scrape_url_with_playwright(url)
        pw_score = get_content_score(pw_res, info_to_extract)
        if pw_score > best_score:
            best_res, best_method, best_score = pw_res, "Playwright", pw_score

    # Tier 4: Python
    if best_score < 3:
        logger.info(f"Current quality low (Score: {best_score}). Trying Python baseline...")
        py_res = await scrape_url_with_python(url, custom_headers)
        py_score = get_content_score(py_res, info_to_extract)
        if py_score > best_score:
            best_res, best_method, best_score = py_res, "Python (httpx)", py_score

    if not best_res or not best_res.get("success") or (best_score < 1 and best_res.get("char_count", 0) < 50):
        return json.dumps({
            "success": False, "url": url, 
            "extracted_info": "",
            "error": f"Scraping failed (Blocked or Extremely Low Quality). Method: {best_method}, Score: {best_score}/10. Content: {best_res.get('content', '')[:100] if best_res else 'None'}", 
            "scrape_stats": {"method_used": best_method, "score": best_score}, "tokens_used": 0
        }, ensure_ascii=False)

    full_content = best_res["content"]
    quality_result = check_content_quality(full_content)
    
    # --- Phase 2: Information Extraction ---
    if len(full_content) <= CHUNK_SIZE * 1.5:
        # Single Pass Extraction
        prompt = EXTRACT_INFO_PROMPT.format(info_to_extract, full_content)
        extracted = await call_robust_llm(
            prompt, 
            info_for_truncation=info_to_extract, 
            original_content=full_content
        )
        final_info = extracted["extracted_info"]
        success = extracted["success"]
        error = extracted.get("error", "")
        total_tokens = extracted.get("tokens_used", 0)
        num_chunks = 1
    else:
        # Map-Reduce Strategy for long documents
        chunks = smart_split_content(full_content, CHUNK_SIZE, CHUNK_OVERLAP)
        num_chunks = len(chunks)
        logger.info(f"Long content detected ({len(full_content)} chars). Map-Reduce with {num_chunks} parallel chunks (Concurrency: {MAX_CONCURRENT_CHUNKS}).")

        # Use Semaphore to limit parallel LLM calls
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHUNKS)

        async def sem_call_robust_llm(chunk_text):
            async with semaphore:
                chunk_prompt = EXTRACT_INFO_PROMPT.format(info_to_extract, chunk_text)
                return await call_robust_llm(
                    chunk_prompt, 
                    temperature=0.2, 
                    info_for_truncation=info_to_extract, 
                    original_content=chunk_text
                )

        # Map Phase: Parallel extraction with concurrency control
        chunk_results = await asyncio.gather(*(sem_call_robust_llm(c) for c in chunks))
        
        # Filter successful findings
        valid_partials = []
        total_tokens = 0
        for r in chunk_results:
            total_tokens += r.get("tokens_used", 0)
            text = r["extracted_info"]
            if r["success"] and text and len(text.strip()) > 10:
                valid_partials.append(text)
        
        if not valid_partials:
            logger.warning("No extracted information available from any chunk.")
            final_info = "The requested information was not found in the provided document."
            success = False
            error = "No valid information extracted from any document chunk"
        else:
            # Reduce Phase: Synthesize fragments into a single answer
            logger.info(f"Synthesizing {len(valid_partials)} data fragments into final response.")
            formatted_fragments = ""
            for i, p in enumerate(valid_partials):
                formatted_fragments += f"--- FRAGMENT {i+1} ---\n{p}\n\n"
            
            reduce_prompt = REDUCE_PROMPT.format(info=info_to_extract, partials=formatted_fragments)
            reduce_result = await call_robust_llm(reduce_prompt, max_tokens=8192, temperature=0.3)
            
            final_info = reduce_result["extracted_info"]
            success = reduce_result["success"]
            error = reduce_result.get("error", "")
            total_tokens += reduce_result.get("tokens_used", 0)

    if quality_result["is_low_quality"]:
        final_info += f"\n\n<!-- Quality Note: {quality_result['warning']} -->"
    
    # Analyze confidence level from extracted info to provide verification recommendation
    verification_note = ""
    if final_info:
        info_lower = final_info.lower()
        if "[confidence: low" in info_lower or "requires verification" in info_lower:
            verification_note = "⚠️ LOW CONFIDENCE: This information has low reliability. Strongly recommend verifying with additional independent sources before using."
        elif "[confidence: medium" in info_lower or "recommend cross-check" in info_lower or "consider additional verification" in info_lower:
            verification_note = "ℹ️ MEDIUM CONFIDENCE: Consider verifying this information with at least one additional source for increased reliability."
        elif "[confidence: high" in info_lower:
            verification_note = "✓ HIGH CONFIDENCE: Information appears reliable. Proceed with confidence."
    
    return json.dumps({
        "success": success,
        "url": url,
        "extracted_info": final_info,
        "error": error,
        "verification_recommendation": verification_note,
        "scrape_stats": {
            "char_count": len(full_content), 
            "line_count": best_res.get("line_count", 0),
            "method_used": best_method, 
            "chunks_processed": num_chunks,
            "low_quality": quality_result["is_low_quality"]
        },
        "model_used": SUMMARY_LLM_MODEL_NAME,
        "tokens_used": total_tokens
    }, ensure_ascii=False)

if __name__ == "__main__":
    mcp.run(transport="stdio")
