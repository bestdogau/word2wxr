"""
AI-Powered Gutenberg Block Converter
Calls DeepSeek V3.2 via OpenRouter to convert parsed Word content
into WordPress Gutenberg blocks matching reference XML styling.
"""

import json
import os
import sys
import re

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package not found. Run: pip install requests")
    sys.exit(1)


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "deepseek/deepseek-v3.2"  # DeepSeek V3.2 on OpenRouter
MAX_RETRIES = 2


def load_config():
    """Load config from config.json."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    if os.path.isfile(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def call_openrouter(system_prompt, user_prompt, api_key, model=None):
    """Call OpenRouter API and return the response text."""
    if not model:
        model = DEFAULT_MODEL
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 30000,
        "temperature": 0.1,  # Low temperature for consistent formatting
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://bestdog.au",
        "X-Title": "Word2WXR Converter",
    }
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if attempt == 1:
                print("    Waiting for AI response (this may take 30-90 seconds)...")
            else:
                print(f"    Retry {attempt}/{MAX_RETRIES}...")
            
            response = requests.post(
                OPENROUTER_URL,
                headers=headers,
                json=payload,
                timeout=(30, 300),  # 30s connect, 5min read
            )
            
            # Handle rate limit / server busy with retry
            if response.status_code in (429, 503) and attempt < MAX_RETRIES:
                wait = 10 * attempt
                print(f"    Server busy (HTTP {response.status_code}), waiting {wait}s...")
                import time
                time.sleep(wait)
                continue
            
            response.raise_for_status()
            result = response.json()
            
            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message']['content']
                
                # Print token usage
                usage = result.get('usage', {})
                if usage:
                    prompt_tokens = usage.get('prompt_tokens', 0)
                    completion_tokens = usage.get('completion_tokens', 0)
                    total = prompt_tokens + completion_tokens
                    
                    # DeepSeek cache info
                    cache_hit = usage.get('cache_read_input_tokens', 0) or usage.get('prompt_tokens_details', {}).get('cached_tokens', 0)
                    cache_create = usage.get('cache_creation_input_tokens', 0)
                    
                    # Cost: cached tokens are free on DeepSeek
                    paid_input = prompt_tokens - cache_hit
                    cost = (paid_input * 0.25 + completion_tokens * 0.38) / 1_000_000
                    
                    print(f"    Tokens: {prompt_tokens:,} in + {completion_tokens:,} out = {total:,} total")
                    if cache_hit > 0:
                        print(f"    Cache hit: {cache_hit:,} tokens (free)")
                    elif cache_create > 0:
                        print(f"    Cache created: {cache_create:,} tokens (next calls will be free)")
                    print(f"    Est. cost: ${cost:.4f}")
                
                return content
            else:
                error = result.get('error', {})
                print(f"  API Error: {error.get('message', 'Unknown error')}")
                return None
                
        except requests.exceptions.Timeout:
            print(f"  Timeout Error: AI took too long to respond.")
            if attempt < MAX_RETRIES:
                print(f"    Retrying...")
                continue
            print(f"  Failed after {MAX_RETRIES} attempts.")
            return None
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 'unknown'
            body = e.response.text[:300] if e.response is not None else ''
            print(f"  HTTP Error {status}: {body}")
            return None
        except requests.exceptions.ConnectionError:
            print(f"  Connection Error: Could not reach OpenRouter. Check your internet.")
            return None
        except Exception as e:
            print(f"  Error: {str(e)}")
            return None
    
    return None


def _preprocess_content(content):
    """Pre-process content blocks to add explicit structure hints.
    
    Detects which sections need accordion treatment based on content patterns:
    - Sections with H3 subheadings (no tables) → accordion from H3s
    - Sections with bold-started paragraphs (no H3s, no tables) → accordion from bold
    - Sections with tables → no accordion (standalone H3s)
    - Final Verdict → explicitly marked, never accordion
    """
    # First pass: split content into sections by H2
    sections = []
    current = {"h2": None, "blocks": []}
    
    for block in content:
        if block['type'] == 'heading' and block['level'] == 2:
            if current['h2'] or current['blocks']:
                sections.append(current)
            current = {"h2": block, "blocks": []}
        else:
            current['blocks'].append(block)
    if current['h2'] or current['blocks']:
        sections.append(current)
    
    # Second pass: process each section
    output = []
    
    for sec in sections:
        h2 = sec['h2']
        blocks = sec['blocks']
        
        if not h2:
            # Intro blocks before first H2
            for b in blocks:
                output.append(_simplify(b))
            continue
        
        h2_text = h2['text'].lower()
        
        # Final Verdict — always special
        if 'final verdict' in h2_text:
            output.append({"type": "section_marker", "section": "FINAL_VERDICT_START"})
            output.append(_simplify(h2))
            for b in blocks:
                output.append(_simplify(b))
            output.append({"type": "section_marker", "section": "FINAL_VERDICT_END"})
            continue
        
        # Sources/References — pass through (handled as sources accordion by DeepSeek)
        if 'sources' in h2_text or 'references' in h2_text:
            output.append(_simplify(h2))
            for b in blocks:
                output.append(_simplify(b))
            continue
        
        # FAQ — pass through
        if 'faq' in h2_text or 'frequently asked' in h2_text:
            output.append(_simplify(h2))
            for b in blocks:
                output.append(_simplify(b))
            continue
        
        # Analyze section content
        has_h3 = any(b['type'] == 'heading' and b['level'] == 3 for b in blocks)
        has_table = any(b['type'] == 'table' for b in blocks)
        bold_paras = [b for b in blocks if b['type'] == 'paragraph' and b.get('text', '').strip().startswith('<strong>')]
        has_bold_pattern = len(bold_paras) >= 2  # At least 2 bold paragraphs = accordion pattern
        
        # These sections NEVER get accordion — always standalone H3s
        NEVER_ACCORDION = ['exercise', 'training', 'grooming', 'price', 'cost',
                           'lifespan', 'longevity', 'history', 'origin']
        is_never_accordion = any(kw in h2_text for kw in NEVER_ACCORDION)
        
        # Pass through if has tables or is in never-accordion list
        if has_table or is_never_accordion:
            output.append(_simplify(h2))
            for b in blocks:
                output.append(_simplify(b))
            continue
        
        # Sections with H3 subheadings (no tables) → accordion from H3s
        if has_h3 and not has_table:
            output.append(_simplify(h2))
            
            intro = []
            accordion_items = []
            current_item = None
            
            for b in blocks:
                if b['type'] == 'heading' and b['level'] == 3:
                    if current_item:
                        accordion_items.append(current_item)
                    current_item = {"heading": b['text'], "content": []}
                elif current_item is not None:
                    current_item["content"].append(_simplify(b))
                else:
                    intro.append(_simplify(b))
            
            if current_item:
                accordion_items.append(current_item)
            
            for ib in intro:
                output.append(ib)
            
            if accordion_items:
                output.append({
                    "type": "accordion_group",
                    "style": "orange",
                    "items": accordion_items
                })
            continue
        
        # Sections with bold-started paragraphs (no H3s, no tables) → accordion from bold
        if has_bold_pattern and not has_h3 and not has_table:
            output.append(_simplify(h2))
            
            intro = []
            accordion_items = []
            current_item = None
            
            for b in blocks:
                text = b.get('text', '')
                is_bold_start = b['type'] == 'paragraph' and text.strip().startswith('<strong>')
                
                if is_bold_start:
                    if current_item:
                        accordion_items.append(current_item)
                    
                    bold_match = re.match(r'<strong>(.*?)</strong>\s*:?\s*(.*)', text, re.DOTALL)
                    if bold_match:
                        heading_text = bold_match.group(1).strip().rstrip(':').strip()
                        remaining = bold_match.group(2).strip()
                        current_item = {"heading": heading_text, "content": []}
                        if remaining:
                            current_item["content"].append({"type": "paragraph", "text": remaining})
                    else:
                        heading_text = re.sub(r'<[^>]+>', '', text)[:60].strip().rstrip(':').strip()
                        current_item = {"heading": heading_text, "content": [{"type": "paragraph", "text": text}]}
                elif current_item is not None:
                    current_item["content"].append(_simplify(b))
                else:
                    intro.append(_simplify(b))
            
            if current_item:
                accordion_items.append(current_item)
            
            for ib in intro:
                output.append(ib)
            
            if accordion_items:
                output.append({
                    "type": "accordion_group",
                    "style": "orange",
                    "items": accordion_items
                })
            continue
        
        # Default: no special treatment
        output.append(_simplify(h2))
        for b in blocks:
            output.append(_simplify(b))
    
    return output


def _simplify(block):
    """Simplify a content block for JSON output."""
    btype = block['type']
    if btype == 'heading':
        return {"type": "heading", "level": block['level'], "text": block['text']}
    elif btype == 'paragraph':
        return {"type": "paragraph", "text": block['text']}
    elif btype == 'list':
        return {"type": "list", "style": block.get('style', 'unordered'), "items": block['items']}
    elif btype == 'table':
        return {"type": "table", "headers": block['headers'], "rows": block['rows']}
    elif btype == 'rank_math_faq':
        return {"type": "faq", "questions": block['questions']}
    elif btype == 'separator':
        return {"type": "separator"}
    elif btype == 'button':
        return {"type": "button", "text": block['text'], "url": block['url']}
    return {"type": btype, "text": block.get('text', '')}


def convert_with_ai(parsed_doc, style_guide, structure_rules, api_key, model=None, verbose=False):
    """Convert parsed document to Gutenberg HTML using AI."""
    
    title = parsed_doc.get('title', 'Untitled')
    meta = parsed_doc.get('meta', {})
    slug = meta.get('slug', '')
    if not slug:
        slug = re.sub(r'[^a-z0-9\s-]', '', title.lower())
        slug = re.sub(r'[\s]+', '-', slug).strip('-')
    
    # Build system prompt
    system_prompt = f"""You are a WordPress Gutenberg block converter. Convert blog post content into EXACT WordPress Gutenberg block HTML matching the reference site.

{style_guide}

{structure_rules}

CRITICAL OUTPUT RULES:
- Output ONLY raw Gutenberg block HTML. No markdown, no code fences, no explanations.
- Start with the first <!-- wp: block and end with the last <!-- /wp: block.
- Match EVERY block format EXACTLY — same JSON attributes, same CSS classes, same inline styles.
- For image placeholders, use slug "{slug}" and sequential numbering (1, 2, 3...).
- Generate unique 8-character hex IDs for each image block.
- Keep all HTML formatting from the input (<strong>, <em>, <a href>, <sup>) exactly as-is.

H2 RULES (5 styles — use the CORRECT one):
- ORANGE H2: centered, uppercase, #f9c030 bg — for: History, Temperament, Health, Lifespan, Grooming, Exercise, Training, Is Right For You
- PLAIN H2: centered, 28px — for: Quick Facts, Grooming Schedule, Training Timeline, Price & Costs, Final Verdict
- FAQ H2: #f9c030 bg, NOT uppercase, NOT centered — for FAQs only
- INTRO H2: no styling — for "What You'll Learn" only
- SOURCES: uses accordion-heading (plain, no color), not a regular H2

ACCORDION RULES — CRITICAL:
The content has been pre-processed. When you see type "accordion_group", convert it to a wp:accordion block:
  - Each item's "heading" → accordion-heading (orange bg, button, toggle-title, toggle-icon "+")
  - Each item's "content" → accordion-panel (containing paragraph/list blocks)
  - Wrap ALL items in ONE accordion block per group.
Orange accordion heading: background-color:#f9c030, white text, button with toggle-title and toggle-icon "+" spans.

NON-ACCORDION sections (Exercise, Training, Price/Costs):
  H3s become standalone headings with orange TEXT color (#f9c030), not background.

FINAL VERDICT — when you see section_marker "FINAL_VERDICT_START" / "FINAL_VERDICT_END":
  - Add [SEPARATOR] before the Final Verdict H2
  - Use Plain H2 style (centered, 28px) — NOT orange
  - Output paragraphs normally — NO accordion
  - Add [SEPARATOR] after the last Final Verdict paragraph

SOURCES: plain accordion (heading with NO color/background attributes)

IMAGE placement: BEFORE each ORANGE H2 only (not before plain/FAQ/intro H2s)
SEPARATOR placement: Before Quick Facts, Before Price & Costs, Before AND After Final Verdict
"""

    # Build content JSON with pre-processed structure
    content_blocks = _preprocess_content(parsed_doc.get('content', []))
    
    user_prompt = f"""Convert this blog post to WordPress Gutenberg blocks:

POST TITLE: {title}
POST SLUG: {slug}

CONTENT BLOCKS:
{json.dumps(content_blocks, ensure_ascii=False, indent=1)}

CONVERSION CHECKLIST — follow these EXACTLY:
1. Start with intro paragraphs, then plain H2 "What You'll Learn" (no styling), then bullet list
2. [SEPARATOR] → Plain H2 (centered, 28px) for Quick Facts → Table
3. For each main section: [IMAGE placeholder] → ORANGE H2 (centered, uppercase, #f9c030 bg)
4. "accordion_group" blocks → ONE wp:accordion with orange headings (button + toggle-title + toggle-icon "+")
5. Standalone orange-text H3s (#f9c030 text, not bg) for Exercise, Training, Price sections
6. [SEPARATOR] → Plain H2 for Price & Costs → Table → Standalone orange-text H3s
7. FINAL_VERDICT markers → [SEPARATOR] → Plain H2 → paragraphs → [SEPARATOR] (NO accordion)
8. FAQ H2 (#f9c030 bg, NOT uppercase) → rank-math/faq-block with JSON + HTML
9. Sources → plain accordion (heading with NO color/background)
10. Output ONLY raw Gutenberg HTML — no markdown fences, no explanations
"""

    if verbose:
        print(f"    Calling AI ({model or DEFAULT_MODEL})...")
    
    result = call_openrouter(system_prompt, user_prompt, api_key, model)
    
    if result:
        # Clean up: remove any markdown code fences if AI added them
        result = result.strip()
        if result.startswith('```'):
            # Remove opening fence safely
            newline_pos = result.find('\n')
            if newline_pos > 0:
                result = result[newline_pos + 1:]
            else:
                result = result[3:]
        if result.endswith('```'):
            result = result[:-3].rstrip()
        
        result = result.strip()
    
    return result


def convert_to_gutenberg(parsed_doc, style_guide=None, structure_rules=None, api_key=None, model=None, verbose=False):
    """Main entry point - matches old interface but uses AI."""
    if not api_key:
        config = load_config()
        api_key = config.get('api_key', '')
    
    if not api_key:
        print("  ERROR: No API key found. Set it in config.json or pass --api-key")
        return None
    
    if not style_guide:
        style_guide = "Use standard WordPress Gutenberg blocks with #f9c030 orange theme."
    if not structure_rules:
        structure_rules = ""
    
    return convert_with_ai(parsed_doc, style_guide, structure_rules, api_key, model, verbose)


if __name__ == '__main__':
    print("AI Converter module. Use convert.py to run conversions.")
