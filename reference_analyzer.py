"""
Reference XML Analyzer
Extracts block style examples from a WordPress export XML to create
a style guide for the AI converter.
"""

import re


def extract_style_guide(xml_path):
    """Extract style guide examples from reference WordPress XML."""
    with open(xml_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find content:encoded blocks that contain actual Gutenberg blocks
    matches = re.findall(r'<content:encoded><!\[CDATA\[(.*?)\]\]></content:encoded>', content, re.DOTALL)
    post_content = None
    
    # Find a post with full styling
    for m in matches:
        if ('text-transform:uppercase' in m and 'wp:separator' in m 
                and 'wp:accordion' in m and 'generateblocks/image' in m):
            post_content = m
            break
    
    # Fallback
    if not post_content:
        for m in matches:
            if '<!-- wp:heading' in m and '<!-- wp:paragraph' in m:
                post_content = m
                break
    
    if not post_content:
        return None
    lines = post_content.split('\n')
    
    examples = {}
    
    # Track accordion depth to distinguish standalone vs accordion H3s
    in_accordion = False
    
    for i, line in enumerate(lines):
        
        # Track accordion state
        if '<!-- wp:accordion -->' in line:
            in_accordion = True
        if '<!-- /wp:accordion -->' in line:
            in_accordion = False
        
        # 1. Orange section H2 (centered, uppercase, background)
        if 'text-transform:uppercase' in line and 'h2_orange' not in examples:
            for j in range(i, max(0, i-5), -1):
                if '<!-- wp:heading' in lines[j]:
                    block = _extract_block_simple(lines, j, '<!-- /wp:heading -->')
                    if block:
                        examples['h2_orange'] = block
                    break
        
        # 2. Plain centered H2 (font-size:28px)
        if 'font-size:28px' in line and 'h2_plain' not in examples:
            for j in range(i, max(0, i-5), -1):
                if '<!-- wp:heading' in lines[j]:
                    block = _extract_block_simple(lines, j, '<!-- /wp:heading -->')
                    if block:
                        examples['h2_plain'] = block
                    break
        
        # 3. Intro H2 (no styling — "What You'll Learn")
        if '<h2 class="wp-block-heading"' in line and 'h2_intro' not in examples:
            # Only match if NO color, NO font-size, NO background
            if 'f9c030' not in line and 'font-size' not in line and 'uppercase' not in line:
                for j in range(i, max(0, i-5), -1):
                    if '<!-- wp:heading' in lines[j]:
                        # Verify the comment also has no styling
                        comment = lines[j]
                        if 'textAlign' not in comment and 'color' not in comment:
                            block = _extract_block_simple(lines, j, '<!-- /wp:heading -->')
                            if block:
                                examples['h2_intro'] = block
                        break
        
        # 4. FAQ H2 (background but NOT uppercase, NOT centered)
        if 'FAQs' in line and 'f9c030' in line and 'uppercase' not in line and 'h2_faq' not in examples:
            for j in range(i, max(0, i-5), -1):
                if '<!-- wp:heading' in lines[j]:
                    block = _extract_block_simple(lines, j, '<!-- /wp:heading -->')
                    if block:
                        examples['h2_faq'] = block
                    break
        
        # 5. Standalone H3 (orange TEXT color, NOT inside accordion)
        if ('<h3' in line and 'color:#f9c030' in line and not in_accordion 
                and 'accordion' not in line and 'h3_standalone' not in examples):
            for j in range(i, max(0, i-5), -1):
                if '<!-- wp:heading' in lines[j]:
                    block = _extract_block_simple(lines, j, '<!-- /wp:heading -->')
                    if block:
                        examples['h3_standalone'] = block
                    break
        
        # 6. Separator
        if '<!-- wp:separator' in line and 'separator' not in examples:
            block = _extract_block_simple(lines, i, '<!-- /wp:separator -->')
            if block:
                examples['separator'] = block
        
        # 7. Image placeholder (generateblocks/image)
        if '<!-- wp:generateblocks/image' in line and 'image_placeholder' not in examples:
            block = _extract_block_simple(lines, i, '<!-- /wp:generateblocks/image -->')
            if block:
                examples['image_placeholder'] = block
        
        # 8. Paragraph
        if '<!-- wp:paragraph -->' in line and 'paragraph' not in examples:
            block = _extract_block_simple(lines, i, '<!-- /wp:paragraph -->')
            if block and len(block) < 500:
                examples['paragraph'] = block
        
        # 9. Table
        if '<!-- wp:table' in line and 'table' not in examples:
            block = _extract_block_simple(lines, i, '<!-- /wp:table -->')
            if block:
                if len(block) > 1500:
                    block = block[:1500] + '\n... (more rows) ...\n</table></figure>\n<!-- /wp:table -->'
                examples['table'] = block
        
        # 10. List
        if '<!-- wp:list' in line and 'wp:list-item' not in line and 'list' not in examples:
            block = _extract_block_simple(lines, i, '<!-- /wp:list -->')
            if block:
                if len(block) > 800:
                    block = block[:800] + '\n... (more items) ...\n</ul>\n<!-- /wp:list -->'
                examples['list'] = block
        
        # 11. Orange accordion (first one — has orange heading)
        if '<!-- wp:accordion -->' in line and 'accordion_orange' not in examples:
            block = _extract_block_simple(lines, i, '<!-- /wp:accordion -->')
            if block and 'f9c030' in block:
                # Truncate to first item only
                end_first = block.find('<!-- /wp:accordion-item -->')
                if end_first > 0:
                    block = block[:end_first + len('<!-- /wp:accordion-item -->')] + '\n... (more items) ...\n</div>\n<!-- /wp:accordion -->'
                examples['accordion_orange'] = block
        
        # 12. Sources accordion (PLAIN heading — no orange, typically last accordion)
        # We'll catch this in a second pass below
        
        # 13. Rank Math FAQ
        if '<!-- wp:rank-math/faq-block' in line and 'faq_block' not in examples:
            block = _extract_block_simple(lines, i, '<!-- /wp:rank-math/faq-block -->')
            if block:
                json_end = block.find(' -->\n')
                if json_end < 0:
                    json_end = block.find('-->')
                
                if json_end > 0:
                    html_part = block[json_end + len(' -->\n'):]
                else:
                    html_part = ''
                
                first_q_end = block.find(',"visible":true},{"id"')
                if first_q_end > 0:
                    json_part = block[:first_q_end] + ',"visible":true},...(more questions)...]}'
                else:
                    json_part = block[:500]
                
                first_item_end = html_part.find('</div></div><div class="rank-math-faq-item">')
                if first_item_end > 0:
                    html_part = html_part[:first_item_end + len('</div></div>')] + '\n... (more Q&A items) ...\n</div>\n<!-- /wp:rank-math/faq-block -->'
                
                block = json_part + ' -->\n' + html_part if json_end > 0 else block[:3000]
                examples['faq_block'] = block
    
    # Second pass: find the LAST accordion (sources) which has plain heading
    last_acc_start = None
    for i, line in enumerate(lines):
        if '<!-- wp:accordion -->' in line:
            last_acc_start = i
    
    if last_acc_start and 'sources_accordion' not in examples:
        block = _extract_block_simple(lines, last_acc_start, '<!-- /wp:accordion -->')
        if block:
            # Verify it has a plain heading (no f9c030 in accordion-heading)
            heading_match = re.search(r'<!-- wp:accordion-heading[^>]*-->', block)
            if heading_match:
                heading_comment = heading_match.group(0)
                # Sources heading has NO color attributes
                if 'f9c030' not in heading_comment and 'color' not in heading_comment:
                    # Truncate - just show structure
                    end_panel_start = block.find('<!-- wp:accordion-panel -->')
                    if end_panel_start > 0:
                        panel_start = end_panel_start
                        # Get a bit of panel content
                        panel_preview = block[panel_start:panel_start+500]
                        block = block[:panel_start] + panel_preview + '\n... (more sources) ...\n</div>\n<!-- /wp:accordion-panel --></div>\n<!-- /wp:accordion-item -->\n</div>\n<!-- /wp:accordion -->'
                    examples['sources_accordion'] = block
    
    return examples


def _extract_block_simple(lines, start_idx, end_marker):
    """Extract lines from start_idx until end_marker is found."""
    block_lines = []
    for i in range(start_idx, min(start_idx + 100, len(lines))):
        block_lines.append(lines[i])
        if end_marker in lines[i]:
            break
    result = '\n'.join(block_lines)
    return result if len(result) > 10 else None


def build_style_guide(xml_path):
    """Build a complete style guide string from reference XML."""
    examples = extract_style_guide(xml_path)
    if not examples:
        return "No reference XML found. Use standard WordPress Gutenberg blocks."
    
    guide = """=== WORDPRESS GUTENBERG BLOCK STYLE GUIDE ===
(Extracted from reference site - MATCH THESE EXACTLY)

"""
    
    block_descriptions = {
        'h2_orange': (
            "ORANGE SECTION H2 - Main section headers\n"
            "Used for: History, Temperament, Health, Lifespan, Grooming, Exercise, Training, Is Right For You\n"
            "Has: centered, UPPERCASE, #f9c030 background, white text (base-3), <strong><strong>text</strong></strong>"
        ),
        'h2_plain': (
            "PLAIN CENTERED H2 - Sub-section headers before tables + Final Verdict\n"
            "Used for: Breed Quick Facts, Grooming Schedule, Socialisation & Training Timeline, Price & Costs, Final Verdict\n"
            "Has: centered, 28px font-size, NO background, NO uppercase, <strong>text</strong>"
        ),
        'h2_intro': (
            "INTRO H2 - Opening header (What You'll Learn)\n"
            "Has: NO styling at all — just a plain wp:heading with <strong>text</strong>"
        ),
        'h2_faq': (
            "FAQ H2 - Used ONLY for the FAQs section heading\n"
            "Has: #f9c030 background, white text, NOT uppercase, NOT centered, <strong>text</strong>"
        ),
        'h3_standalone': (
            "STANDALONE H3 - Orange text subheading (NOT inside accordion)\n"
            "Used when H3 group contains tables (Exercise, Training, Price sections)\n"
            "Has: #f9c030 TEXT color (not background!), <strong>text</strong>\n"
            "CRITICAL: This is different from accordion-heading! This is a simple wp:heading with orange text."
        ),
        'separator': (
            "SEPARATOR - Gold/orange horizontal rule\n"
            "Placed BEFORE: Quick Facts, Price & Costs, FAQs (one separator each)"
        ),
        'image_placeholder': (
            "IMAGE PLACEHOLDER - GenerateBlocks image block\n"
            "Placed BEFORE each orange section H2 only (not before plain/FAQ H2s)"
        ),
        'paragraph': "PARAGRAPH - Standard paragraph block",
        'table': (
            "TABLE - WordPress table with has-fixed-layout class\n"
            "Headers go in <thead><tr><th> (plain text, NO strong — th is already bold)\n"
            "Data rows in <tbody><tr><td>. First column cells wrapped in <strong> tags.\n"
            "Format: <!-- wp:table -->\\n<figure class=\"wp-block-table\"><table class=\"has-fixed-layout\">..."
        ),
        'list': (
            "LIST - WordPress list with wp:list-item blocks inside\n"
            "Each <li> is wrapped in <!-- wp:list-item --> comments"
        ),
        'accordion_orange': (
            "ORANGE ACCORDION - Collapsible sections with orange headings\n"
            "Used for H3 groups WITHOUT tables (Temperament, Health, Is Right For You)\n"
            "Structure: accordion → accordion-item → accordion-heading (orange bg + button + toggle-icon) → accordion-panel (content)\n"
            "CRITICAL: heading uses <button> with <span class=\"toggle-title\"> and <span class=\"toggle-icon\">+</span>"
        ),
        'sources_accordion': (
            "SOURCES ACCORDION - Plain accordion with NO colored heading\n"
            "Used ONLY for Sources/References section at the very end\n"
            "Structure is same as orange accordion BUT heading has NO color/background attributes"
        ),
        'faq_block': (
            "RANK MATH FAQ BLOCK - Schema-enabled FAQ with JSON + HTML\n"
            "The comment contains JSON with questions array using escaped unicode\n"
            "Each question title uses <strong> tags\n"
            "HTML uses <div class=\"rank-math-faq-item\"> → <h3 class=\"rank-math-question\"> + <div class=\"rank-math-answer\">"
        ),
    }
    
    for key, desc in block_descriptions.items():
        if key in examples:
            guide += f"--- {desc} ---\n"
            guide += f"{examples[key]}\n\n"
    
    return guide


def get_structure_rules():
    """Return the structural rules for block ordering."""
    return """
=== STRUCTURAL RULES (MUST FOLLOW EXACTLY) ===

1. EXACT POST FLOW ORDER:
   a) Intro paragraphs
   b) Intro H2 "What You'll Learn" (plain, no styling)
   c) Bullet list of topics
   d) [SEPARATOR] → Plain H2 "Quick Facts" → Table
   e) For each main section:
      [IMAGE] → Orange H2 → Content (see accordion rules below)
   f) [SEPARATOR] → Plain H2 "Price & Costs" → Table → Standalone orange-text H3s
   g) [IMAGE] → Orange H2 "Is This Breed Right for You?" → Accordion
   h) [SEPARATOR] → Plain H2 "Final Verdict" → Paragraphs (NO accordion) → [SEPARATOR]
   i) FAQ H2 → Rank Math FAQ block
   j) Sources accordion (plain heading, no orange)

2. H2 STYLES — 5 types:
   ORANGE (centered, uppercase, #f9c030 bg): History, Temperament, Health, Lifespan, Grooming, Exercise, Training, Is Right For You
   PLAIN (centered, 28px): Quick Facts, Grooming Schedule, Training Timeline, Price & Costs, Final Verdict
   FAQ (#f9c030 bg, NOT uppercase, NOT centered): FAQs only
   INTRO (no styling): What You'll Learn only
   SOURCES: Not an H2 — sources use accordion-heading (plain, no color)

3. ACCORDION SECTIONS — these 3 sections ALWAYS use accordion:
   a) TEMPERAMENT section → wrap H3 subheadings as accordion items
   b) HEALTH section → wrap bold-started paragraphs as accordion items
   c) IS RIGHT FOR YOU section → wrap bold-started paragraphs as accordion items
   
   IMPORTANT: If there are no H3 headings but paragraphs start with <strong>Topic:</strong>,
   treat the bold text as the accordion heading and the paragraph text as panel content.
   Example input: <strong>Hip Dysplasia:</strong> Description text here...
   → accordion-heading: "Hip Dysplasia"
   → accordion-panel: paragraph with the description text
   Group consecutive bold-started paragraphs (and any lists after them) into one accordion item.

4. NON-ACCORDION SECTIONS — these use standalone orange-text H3 headings:
   Exercise, Training, Price/Costs, Grooming
   H3 style: orange TEXT color (#f9c030), NOT background — simple wp:heading

5. FINAL VERDICT — special section:
   - [SEPARATOR] BEFORE Final Verdict H2
   - Plain H2 (centered, 28px) — NOT orange
   - Regular paragraphs only — NO accordion
   - [SEPARATOR] AFTER Final Verdict content (before FAQ)

6. SEPARATOR placement (one each):
   - Before Quick Facts
   - Before Price & Costs
   - Before Final Verdict
   - After Final Verdict (before FAQ)

7. IMAGE placement: BEFORE each ORANGE section H2 only
   URL: https://bestdog.au/wp-content/uploads/{slug}-section-image-{N}.jpg
   Unique 8-char hex ID per image block, padding-top:30px, padding-bottom:10px

8. ACCORDION structure (orange headings):
   <!-- wp:accordion -->
   <div role="group" class="wp-block-accordion"><!-- wp:accordion-item -->
   <div class="wp-block-accordion-item"><!-- wp:accordion-heading {"style":{"color":{"background":"#f9c030"},"elements":{"link":{"color":{"text":"var:preset|color|base-3"}}}},"textColor":"base-3"} -->
   <h3 class="wp-block-accordion-heading has-base-3-color has-text-color has-background has-link-color" style="background-color:#f9c030"><button class="wp-block-accordion-heading__toggle"><span class="wp-block-accordion-heading__toggle-title"><strong>Title</strong></span><span class="wp-block-accordion-heading__toggle-icon" aria-hidden="true">+</span></button></h3>
   <!-- /wp:accordion-heading -->
   <!-- wp:accordion-panel -->
   <div role="region" class="wp-block-accordion-panel">[PARAGRAPH AND LIST BLOCKS HERE]</div>
   <!-- /wp:accordion-panel --></div>
   <!-- /wp:accordion-item -->
   </div>
   <!-- /wp:accordion -->

9. SOURCES accordion (PLAIN — no orange):
   Same structure but heading has NO style/color attributes:
   <!-- wp:accordion-heading -->
   <h3 class="wp-block-accordion-heading"><button class="wp-block-accordion-heading__toggle"><span class="wp-block-accordion-heading__toggle-title"><strong>Sources & References</strong></span><span class="wp-block-accordion-heading__toggle-icon" aria-hidden="true">+</span></button></h3>

10. RANK MATH FAQ structure:
   - Comment contains JSON with questions array (escaped unicode for HTML tags)
   - Each question id format: "faq-question-TIMESTAMP"
   - Question titles wrapped in <strong> tags (escaped as \\u003cstrong\\u003e in JSON)
   - HTML: <div class="wp-block-rank-math-faq-block"> → <div class="rank-math-faq-item"> → <h3 class="rank-math-question"> + <div class="rank-math-answer">

11. TABLE formatting:
   - Comment: <!-- wp:table -->
   - Outer wrapper: <figure class="wp-block-table"><table class="has-fixed-layout">
   - Headers: <thead><tr><th>plain text</th></tr></thead> (NO <strong> in headers)
   - Data: <tbody><tr><td><strong>first col</strong></td><td>other cols plain</td></tr></tbody>
   - First column data cells always wrapped in <strong>

12. PRESERVE all HTML formatting: <strong>, <em>, <a href>, <sup> tags
"""


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python reference_analyzer.py <reference.xml>")
        sys.exit(1)
    guide = build_style_guide(sys.argv[1])
    print(guide)
    print(get_structure_rules())
