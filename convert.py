"""
Word to WordPress XML Converter (AI-Powered)
Uses DeepSeek V3.2 via OpenRouter to intelligently convert Word docs
to WordPress Gutenberg blocks matching your reference site's styling.

Usage:
    python convert.py --ref reference.xml --input posts/ --api-key sk-or-...
    python convert.py --ref reference.xml --input single-post.docx

Requirements:
    pip install python-docx lxml requests
    OpenRouter API key (https://openrouter.ai/settings/keys)
"""

import os
import sys
import glob
import json
import hashlib
import argparse
from datetime import datetime

from docx_parser import parse_docx
from reference_analyzer import build_style_guide, get_structure_rules
from ai_converter import convert_with_ai, DEFAULT_MODEL
from wxr_generator import WXRGenerator


CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')
CACHE_FILE = os.path.join(CACHE_DIR, 'prompt_cache.json')


def _hash_file(path):
    """SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def load_or_build_cache(ref_path):
    """Load cached style guide or rebuild from reference XML.
    
    Cache persists until the reference XML file changes.
    This also helps DeepSeek's server-side prompt caching —
    identical system prompts across calls get cached tokens at reduced cost.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    ref_hash = _hash_file(ref_path)
    
    # Try loading cache
    if os.path.isfile(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            if cache.get('ref_hash') == ref_hash:
                print("  Style guide loaded from cache (reference unchanged).")
                print(f"  Cache: {len(cache['style_guide']):,} chars style + {len(cache['structure_rules']):,} chars rules\n")
                return cache['style_guide'], cache['structure_rules']
            else:
                print("  Reference XML changed — rebuilding style guide...")
        except Exception:
            print("  Cache corrupted — rebuilding style guide...")
    else:
        print("  First run — analyzing reference XML for styling...")
    
    # Build fresh
    style_guide = build_style_guide(ref_path)
    structure_rules = get_structure_rules()
    
    # Save cache
    cache = {
        'ref_hash': ref_hash,
        'ref_file': os.path.basename(ref_path),
        'style_guide': style_guide,
        'structure_rules': structure_rules,
    }
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False)
        print(f"  Style guide cached ({len(style_guide):,} + {len(structure_rules):,} chars).")
        print(f"  Subsequent runs will load instantly.\n")
    except Exception as e:
        print(f"  Warning: Could not save cache: {e}\n")
    
    return style_guide, structure_rules


def convert_single(docx_path, generator, style_guide, structure_rules, api_key, model=None, verbose=False):
    """Convert a single Word file to a WXR item XML string using AI."""
    try:
        if verbose:
            print(f"  Processing: {os.path.basename(docx_path)}")
        
        # Parse Word document
        parsed = parse_docx(docx_path)
        
        if not parsed['title']:
            basename = os.path.splitext(os.path.basename(docx_path))[0]
            parsed['title'] = basename.replace('-', ' ').replace('_', ' ').title()
            print(f"  NOTE: No H1 title found, using filename: {parsed['title']}")
        
        # Call AI to convert to Gutenberg blocks
        gutenberg_html = convert_with_ai(
            parsed, style_guide, structure_rules,
            api_key, model, verbose
        )
        
        if not gutenberg_html:
            print(f"  ERROR: AI conversion failed for {os.path.basename(docx_path)}")
            return None
        
        # Generate WXR item
        item_xml = generator.generate_single(parsed, gutenberg_html)
        meta = parsed.get('meta', {})
        
        if verbose:
            print(f"    Title: {parsed['title'][:60]}...")
            slug = meta.get('slug', generator._slugify(parsed['title']))
            print(f"    Slug: {slug}")
            if meta.get('seo_title'):
                print(f"    SEO Title: {meta['seo_title'][:60]}")
            if meta.get('focus_keyword'):
                print(f"    Focus Keyword: {meta['focus_keyword']}")
            print(f"    Content length: {len(gutenberg_html):,} chars")
            cats = parsed.get('categories', [])
            if cats:
                print(f"    Categories: {len(cats)}")
        
        return item_xml
        
    except Exception as e:
        print(f"  ERROR processing {docx_path}: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def main():
    parser = argparse.ArgumentParser(
        description='AI-Powered Word to WordPress XML Converter',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Convert a single file:
    python convert.py --ref reference.xml --input my-post.docx --api-key sk-or-...

  Convert all files in a folder:
    python convert.py --ref reference.xml --input posts/

  Use a different model:
    python convert.py --ref reference.xml --input posts/ --model deepseek/deepseek-v3.2
        """
    )
    
    parser.add_argument(
        '--ref', '-r',
        required=True,
        help='Path to reference WordPress XML export file'
    )
    
    parser.add_argument(
        '--input', '-i',
        required=True,
        help='Path to a .docx file or folder containing .docx files'
    )
    
    parser.add_argument(
        '--output', '-o',
        default=None,
        help='Output file path (default: output/import_TIMESTAMP.xml)'
    )
    
    parser.add_argument(
        '--api-key', '-k',
        default=None,
        help='OpenRouter API key (or set in config.json)'
    )
    
    parser.add_argument(
        '--model', '-m',
        default=None,
        help=f'AI model to use (default: {DEFAULT_MODEL})'
    )
    
    parser.add_argument(
        '--single-files',
        action='store_true',
        help='Generate separate XML file per Word document instead of one combined file'
    )
    
    parser.add_argument(
        '--status',
        default=None,
        help='WordPress post status: draft (default) or publish'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show detailed progress'
    )
    
    args = parser.parse_args()
    
    # Validate reference XML
    if not os.path.isfile(args.ref):
        print(f"ERROR: Reference XML file not found: {args.ref}")
        sys.exit(1)
    
    # Find input .docx files
    docx_files = []
    if os.path.isfile(args.input):
        if args.input.lower().endswith('.docx'):
            docx_files = [args.input]
        else:
            print(f"ERROR: Input file must be a .docx file: {args.input}")
            sys.exit(1)
    elif os.path.isdir(args.input):
        docx_files = sorted(glob.glob(os.path.join(args.input, '*.docx')))
        if not docx_files:
            print(f"ERROR: No .docx files found in: {args.input}")
            sys.exit(1)
    else:
        print(f"ERROR: Input path not found: {args.input}")
        sys.exit(1)
    
    # Get API key
    api_key = args.api_key
    if not api_key:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
        if os.path.isfile(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                api_key = config.get('api_key', '')
    
    if not api_key or 'YOUR_' in api_key:
        print("ERROR: No valid API key found!")
        print("  Option 1: Create config.json with your key:")
        print('    {"api_key": "sk-or-v1-your-key-here"}')
        print("  Option 2: Pass --api-key sk-or-v1-your-key-here")
        print("\n  Get your key at: https://openrouter.ai/settings/keys")
        sys.exit(1)
    
    # Model
    model = args.model or DEFAULT_MODEL
    
    # Create output directory
    output_dir = 'output'
    if args.output:
        if args.output.endswith('.xml'):
            output_dir = os.path.dirname(args.output) or '.'
        else:
            output_dir = args.output
    os.makedirs(output_dir, exist_ok=True)
    
    # Extract style guide from reference XML (with caching)
    print(f"\n{'='*60}")
    print(f"  Word to WordPress XML Converter (AI-Powered)")
    print(f"{'='*60}")
    print(f"  Reference: {os.path.basename(args.ref)}")
    print(f"  AI Model: {model}")
    print(f"  Input files: {len(docx_files)}")
    print(f"  Output dir: {output_dir}")
    print(f"{'='*60}\n")
    
    style_guide, structure_rules = load_or_build_cache(args.ref)
    
    
    # Initialize WXR generator
    generator = WXRGenerator(args.ref)
    print(f"  Site: {generator.site_url}")
    print(f"  Default author: {generator.default_creator}")
    print()
    
    # Process files
    success_count = 0
    error_count = 0
    items = []
    
    for idx, docx_path in enumerate(docx_files):
        print(f"  [{idx+1}/{len(docx_files)}] {os.path.basename(docx_path)}")
        
        item_xml = convert_single(
            docx_path, generator, style_guide, structure_rules,
            api_key, model, verbose=args.verbose
        )
        
        if item_xml:
            if args.single_files:
                basename = os.path.splitext(os.path.basename(docx_path))[0]
                out_path = os.path.join(output_dir, f'{basename}_import.xml')
                wxr = generator.generate_wxr([item_xml])
                with open(out_path, 'w', encoding='utf-8') as f:
                    f.write(wxr)
                print(f"    Saved: {out_path}")
            else:
                items.append(item_xml)
            
            success_count += 1
        else:
            error_count += 1
        
        # Small delay between API calls to be nice to the rate limiter
        if idx < len(docx_files) - 1:
            import time
            time.sleep(1)
    
    # Save combined XML (if not single-files mode)
    if not args.single_files and items:
        if args.output and args.output.endswith('.xml'):
            out_path = args.output
        else:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            out_path = os.path.join(output_dir, f'import_{timestamp}.xml')
        
        wxr = generator.generate_wxr(items)
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(wxr)
        
        print(f"\n  Output: {out_path}")
        print(f"  File size: {os.path.getsize(out_path):,} bytes")
    
    # Summary
    print(f"\n{'='*60}")
    print(f"  DONE!")
    print(f"  Converted: {success_count} files")
    if error_count:
        print(f"  Errors: {error_count} files")
    print(f"{'='*60}")
    print(f"\n  Next step: Import the XML file in WordPress")
    print(f"  Dashboard > Tools > Import > WordPress Importer")
    print()


if __name__ == '__main__':
    main()
