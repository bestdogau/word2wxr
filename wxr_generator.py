"""
WXR (WordPress eXtended RSS) Generator
Generates WordPress-importable XML files by:
1. Reading a reference XML to extract the exact site structure
2. Injecting converted Gutenberg block content from Word files
"""

import re
import os
from datetime import datetime, timezone


class WXRGenerator:
    """Generates WXR XML files based on a reference XML template."""
    
    def __init__(self, reference_xml_path):
        """
        Initialize with a reference WordPress export XML.
        Extracts site info, author info, and post structure.
        """
        self.ref_path = reference_xml_path
        self._parse_reference()
    
    def _parse_reference(self):
        """Parse the reference XML to extract template components."""
        with open(self.ref_path, 'r', encoding='utf-8') as f:
            self.ref_content = f.read()
        
        # Extract the XML declaration and RSS opening tag with namespaces
        rss_match = re.search(r'(<\?xml.*?\?>.*?<rss[^>]*>)', self.ref_content, re.DOTALL)
        self.xml_header = rss_match.group(1) if rss_match else '<?xml version="1.0" encoding="UTF-8" ?>\n<rss version="2.0"\n\txmlns:excerpt="http://wordpress.org/export/1.2/excerpt/"\n\txmlns:content="http://purl.org/rss/1.0/modules/content/"\n\txmlns:wfw="http://wellformedweb.org/CommentAPI/"\n\txmlns:dc="http://purl.org/dc/elements/1.1/"\n\txmlns:wp="http://wordpress.org/export/1.2/"\n>'
        
        # Extract channel opening (everything from <channel> to first <item>)
        channel_match = re.search(r'(<channel>.*?)(?=<item>)', self.ref_content, re.DOTALL)
        self.channel_header = channel_match.group(1).rstrip() if channel_match else '<channel>'
        
        # Extract channel closing
        self.channel_footer = '\n</channel>\n</rss>'
        
        # Extract site URL
        url_match = re.search(r'<wp:base_site_url>(.*?)</wp:base_site_url>', self.ref_content)
        self.site_url = url_match.group(1) if url_match else 'https://example.com'
        
        # Extract author login (default author for new posts)
        creator_match = re.search(r'<dc:creator><!\[CDATA\[(.*?)\]\]></dc:creator>', self.ref_content)
        self.default_creator = creator_match.group(1) if creator_match else 'admin'
        
        # Extract a sample post's meta fields to use as template
        self.template_meta = self._extract_template_meta()
        
        # Find the highest post_id in reference
        post_ids = re.findall(r'<wp:post_id>(\d+)</wp:post_id>', self.ref_content)
        self.next_post_id = max([int(pid) for pid in post_ids]) + 100 if post_ids else 5000
    
    def _extract_template_meta(self):
        """Extract meta field keys from the most complete post in reference."""
        # Find all posts and their meta fields
        items = re.findall(r'<item>(.*?)</item>', self.ref_content, re.DOTALL)
        
        best_meta = []
        for item_xml in items:
            # Only look at actual posts
            if '<wp:post_type><![CDATA[post]]></wp:post_type>' not in item_xml:
                continue
            
            metas = re.findall(
                r'<wp:postmeta>\s*<wp:meta_key><!\[CDATA\[(.*?)\]\]></wp:meta_key>\s*<wp:meta_value><!\[CDATA\[(.*?)\]\]></wp:meta_value>\s*</wp:postmeta>',
                item_xml, re.DOTALL
            )
            
            if len(metas) > len(best_meta):
                best_meta = metas
        
        return best_meta
    
    def generate_single(self, parsed_doc, gutenberg_content, post_id=None):
        """
        Generate a single <item> XML block for one post.
        
        Args:
            parsed_doc: Dict from docx_parser.parse_docx()
            gutenberg_content: String of Gutenberg HTML from AI converter
            post_id: Optional post ID (auto-generated if None)
        
        Returns:
            String of XML for one <item>
        """
        meta = parsed_doc.get('meta', {})
        title = parsed_doc.get('title', 'Untitled Post')
        categories = parsed_doc.get('categories', [])
        
        if post_id is None:
            post_id = self.next_post_id
            self.next_post_id += 1
        
        # Build post fields
        slug = meta.get('slug', self._slugify(title))
        status = meta.get('status', 'draft')
        creator = meta.get('author', self.default_creator)
        now = datetime.now(timezone.utc)
        post_date = now.strftime('%Y-%m-%d %H:%M:%S')
        post_date_gmt = post_date
        pub_date = now.strftime('%a, %d %b %Y %H:%M:%S +0000')
        
        # Build meta fields
        meta_xml = self._build_meta_xml(meta, gutenberg_content)
        
        # Build category tags
        cat_xml = self._build_category_xml(categories, meta)
        
        item_xml = f'''		<item>
\t\t<title><![CDATA[{title}]]></title>
\t\t<link>{self.site_url}/?p={post_id}</link>
\t\t<pubDate>{pub_date}</pubDate>
\t\t<dc:creator><![CDATA[{creator}]]></dc:creator>
\t\t<guid isPermaLink="false">{self.site_url}/?p={post_id}</guid>
\t\t<description></description>
\t\t<content:encoded><![CDATA[{gutenberg_content}]]></content:encoded>
\t\t<excerpt:encoded><![CDATA[]]></excerpt:encoded>
\t\t<wp:post_id>{post_id}</wp:post_id>
\t\t<wp:post_date><![CDATA[{post_date}]]></wp:post_date>
\t\t<wp:post_date_gmt><![CDATA[{post_date_gmt}]]></wp:post_date_gmt>
\t\t<wp:post_modified><![CDATA[{post_date}]]></wp:post_modified>
\t\t<wp:post_modified_gmt><![CDATA[{post_date_gmt}]]></wp:post_modified_gmt>
\t\t<wp:comment_status><![CDATA[open]]></wp:comment_status>
\t\t<wp:ping_status><![CDATA[open]]></wp:ping_status>
\t\t<wp:post_name><![CDATA[{slug}]]></wp:post_name>
\t\t<wp:status><![CDATA[{status}]]></wp:status>
\t\t<wp:post_parent>0</wp:post_parent>
\t\t<wp:menu_order>0</wp:menu_order>
\t\t<wp:post_type><![CDATA[post]]></wp:post_type>
\t\t<wp:post_password><![CDATA[]]></wp:post_password>
\t\t<wp:is_sticky>0</wp:is_sticky>
{cat_xml}{meta_xml}\t\t</item>'''
        
        return item_xml
    
    def generate_wxr(self, items_xml_list):
        """
        Generate complete WXR XML file content.
        
        Args:
            items_xml_list: List of <item> XML strings
        
        Returns:
            Complete WXR XML string ready to save
        """
        items_combined = '\n'.join(items_xml_list)
        
        # Build the complete WXR
        wxr = (
            f'{self.xml_header}\n\n'
            f'{self.channel_header}\n\n'
            f'{items_combined}\n\n'
            f'{self.channel_footer}'
        )
        
        return wxr
    
    def _build_meta_xml(self, meta, gutenberg_content):
        """Build wp:postmeta XML blocks from parsed meta and reference template."""
        meta_parts = []
        
        # Core Rank Math fields from Word file meta
        rank_math_fields = {
            'rank_math_title': meta.get('seo_title', ''),
            'rank_math_description': meta.get('seo_description', ''),
            'rank_math_focus_keyword': meta.get('focus_keyword', ''),
            'rank_math_internal_links_processed': '1',
        }
        
        # Add secondary keywords if present
        secondary = meta.get('secondary_keywords', [])
        if secondary:
            # Rank Math stores focus keywords as comma-separated
            all_keywords = [meta.get('focus_keyword', '')]
            all_keywords.extend(secondary)
            rank_math_fields['rank_math_focus_keyword'] = ','.join(
                [k for k in all_keywords if k]
            )
        
        # Add fields from reference template that aren't overridden
        ref_keys_added = set()
        for key, value in self.template_meta:
            if key in rank_math_fields:
                continue
            if key.startswith('_wp_trash') or key.startswith('_wp_desired'):
                continue
            if key == '_edit_last':
                continue
            ref_keys_added.add(key)
            meta_parts.append(self._meta_entry(key, value))
        
        # Add Rank Math fields
        for key, value in rank_math_fields.items():
            if value:
                meta_parts.append(self._meta_entry(key, value))
        
        # Add ILJ fields if they were in reference but not yet added
        if 'ilj_linkdefinition' not in ref_keys_added:
            meta_parts.append(self._meta_entry('ilj_linkdefinition', 'a:0:{}'))
        if 'ilj_blacklistdefinition' not in ref_keys_added:
            meta_parts.append(self._meta_entry('ilj_blacklistdefinition', 'a:0:{}'))
        
        return '\n'.join(meta_parts) + '\n' if meta_parts else ''
    
    def _meta_entry(self, key, value):
        """Generate a single wp:postmeta XML entry."""
        return (
            f'\t\t<wp:postmeta>\n'
            f'\t\t<wp:meta_key><![CDATA[{key}]]></wp:meta_key>\n'
            f'\t\t<wp:meta_value><![CDATA[{value}]]></wp:meta_value>\n'
            f'\t\t</wp:postmeta>'
        )
    
    def _build_category_xml(self, categories, meta):
        """Build category XML tags."""
        parts = []
        
        if categories:
            for cat in categories:
                parts.append(
                    f'\t\t<category domain="category" nicename="{cat["nicename"]}">'
                    f'<![CDATA[{cat["name"]}]]></category>'
                )
        elif meta.get('category'):
            # Fallback to meta category
            cat_name = meta['category']
            nicename = re.sub(r'[^a-z0-9]+', '-', cat_name.lower()).strip('-')
            parts.append(
                f'\t\t<category domain="category" nicename="{nicename}">'
                f'<![CDATA[{cat_name}]]></category>'
            )
        
        # Add tags if present
        tags = meta.get('tags', [])
        for tag in tags:
            nicename = re.sub(r'[^a-z0-9]+', '-', tag.lower()).strip('-')
            parts.append(
                f'\t\t<category domain="post_tag" nicename="{nicename}">'
                f'<![CDATA[{tag}]]></category>'
            )
        
        return '\n'.join(parts) + '\n' if parts else ''
    
    def _slugify(self, text):
        """Convert text to URL-friendly slug."""
        slug = text.lower()
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)
        slug = re.sub(r'[\s]+', '-', slug)
        slug = re.sub(r'-+', '-', slug)
        return slug.strip('-')


if __name__ == '__main__':
    import sys
    sys.path.insert(0, '.')
    from docx_parser import parse_docx
    
    if len(sys.argv) < 3:
        print("Usage: python wxr_generator.py <reference.xml> <file.docx>")
        sys.exit(1)
    
    ref_path = sys.argv[1]
    docx_path = sys.argv[2]
    
    # Parse Word file
    parsed = parse_docx(docx_path)
    
    # Generate WXR with placeholder content
    gen = WXRGenerator(ref_path)
    fake_content = '<!-- wp:paragraph -->\n<p>Content placeholder - run convert.py for AI conversion.</p>\n<!-- /wp:paragraph -->'
    item_xml = gen.generate_single(parsed, fake_content)
    wxr = gen.generate_wxr([item_xml])
    
    # Save output
    output_path = os.path.splitext(os.path.basename(docx_path))[0] + '_import.xml'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(wxr)
    
    print(f"Generated: {output_path}")
    print(f"Title: {parsed['title']}")
    print(f"Blocks: {len(parsed['content'])}")
    print(f"File size: {len(wxr):,} bytes")
