"""
Category Discovery System for sheeel.com
Discovers new categories on the website and compares with current registry
Detects added, removed, and changed categories
"""
from playwright.sync_api import sync_playwright
import json
from datetime import datetime
from pathlib import Path
import re
import os
from textwrap import dedent

class CategoryDiscovery:
    def __init__(self):
        self.base_url = "https://www.sheeel.com/ar/"
        self.registry_path = Path(__file__).parent / 'categories.json'
        self.discovered_categories = {}
        self.old_registry = {}
    
    def load_registry(self):
        """Load current categories registry"""
        if self.registry_path.exists():
            with open(self.registry_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.old_registry = data.get('categories', {})
                return self.old_registry
        return {}
    
    def extract_slug_from_url(self, url):
        """Convert URL to slug format"""
        # Remove domain and .html
        slug = url.split('/ar/')[-1].replace('.html', '').strip()
        return slug if slug else None
    
    def discover_categories_from_website(self):
        """Fetch categories from website using Playwright"""
        print("\n" + "="*70)
        print("🌐 DISCOVERING CATEGORIES FROM WEBSITE")
        print("="*70)
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                print(f"\n📡 Loading: {self.base_url}")
                page.goto(self.base_url, wait_until='networkidle', timeout=30000)
                
                categories = {}
                seen_urls = set()
                
                print(f"✓ Page loaded\n")
                print(f"📂 Extracting categories from two sections...\n")
                
                # ====== SECTION 1: Top categories (.no-children-top-categories) ======
                print("📍 Section 1: Top Categories")
                section1_items = page.query_selector_all('.no-children-top-categories li.top-lvl a.level-top')
                
                for link in section1_items:
                    try:
                        href = link.get_attribute('href') or ''
                        
                        # Get text from span inside link
                        span = link.query_selector('span')
                        text = span.inner_text().strip() if span else link.inner_text().strip()
                        
                        if not href or ('/ar/' not in href):
                            continue
                        
                        slug = self.extract_slug_from_url(href)
                        if not slug or len(slug) < 2:
                            continue
                        
                        if href in seen_urls:
                            continue
                        
                        seen_urls.add(href)
                        
                        categories[slug] = {
                            'name': text or slug,
                            'url': href,
                            'slug': slug,
                            'section': 'top_categories',
                            'discovered': datetime.now().isoformat(),
                            'has_scraper': self.check_if_scraper_exists(slug)
                        }
                        
                        scraper_status = "✅" if categories[slug]['has_scraper'] else "❌"
                        print(f"  {scraper_status} {text[:35]:35} ({slug})")
                    
                    except Exception as e:
                        print(f"  ⚠️  Error: {e}")
                        continue
                
                print()
                
                # ====== SECTION 2: Parent categories with submenu (li.level0.category-item) ======
                print("📍 Section 2: Parent Categories")
                section2_items = page.query_selector_all('li.level0.category-item.parent > a.level-top')
                
                for link in section2_items:
                    try:
                        href = link.get_attribute('href') or ''
                        
                        # Get text from span inside link
                        span = link.query_selector('span')
                        text = span.inner_text().strip() if span else link.inner_text().strip()
                        
                        if not href or ('/ar/' not in href):
                            continue
                        
                        slug = self.extract_slug_from_url(href)
                        if not slug or len(slug) < 2:
                            continue
                        
                        if href in seen_urls:
                            continue
                        
                        seen_urls.add(href)
                        
                        categories[slug] = {
                            'name': text or slug,
                            'url': href,
                            'slug': slug,
                            'section': 'parent_categories',
                            'discovered': datetime.now().isoformat(),
                            'has_scraper': self.check_if_scraper_exists(slug)
                        }
                        
                        scraper_status = "✅" if categories[slug]['has_scraper'] else "❌"
                        print(f"  {scraper_status} {text[:35]:35} ({slug})")
                    
                    except Exception as e:
                        print(f"  ⚠️  Error: {e}")
                        continue
                
                browser.close()
                
                print(f"\n✓ Discovered {len(categories)} categories\n")
                return categories
        
        except Exception as e:
            print(f"\n❌ Error during discovery: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def check_if_scraper_exists(self, slug):
        """Check if scraper exists for this category"""
        
        # Map of known slugs to scraper paths (relative to discover folder)
        known_scrapers = {
            'emergency_need': 'emergency_need',
            'emergency-need': 'emergency_need',
            'power_bank_chargers': 'power_bank_chargers',
            'power-bank-chargers': 'power_bank_chargers',
            'long_life_food': 'long_life_food',
            'long-life-food': 'long_life_food',
            'kitchen_fun': 'kitchen_fun',
            'kitchen-fun': 'kitchen_fun',
            'cool_items': 'cool_items',
            'cool-items1': 'cool_items',
            'cool-items': 'cool_items',
            'best_seller': 'best_seller',
            'best-sellers': 'best_seller',
            'best_sellers': 'best_seller',
            'supermarket': 'supermarket',
            'electronics': 'electronics',
            'mobile_e_cards': 'mobile_e_cards',
            'mobiles-e-cards': 'mobile_e_cards',
            'mobiles_e_cards': 'mobile_e_cards',
            'sports_toys': 'sports_toys',
            'sports-toys': 'sports_toys',
            'home': 'home',
            'perfumes_beauty': 'perfumes_beauty',
            'perfumes-beauty': 'perfumes_beauty',
            'flowers_chocolate_by_sogha': 'flowers_chocolate_by_sogha',
            'flowers-chocolate-by-sogha': 'flowers_chocolate_by_sogha',
            'only_on_sheeel': 'only_on_sheeel',
            'only-on-sheeel': 'only_on_sheeel',
            'coupons': 'coupons'
        }
        
        if slug in known_scrapers:
            return True
        
        # Check in projects folder
        base_path = Path(__file__).parent.parent.parent
        
        for project_folder in base_path.iterdir():
            if project_folder.is_dir() and project_folder.name not in ['.git', '.github', 'category_monitor']:
                for category_folder in project_folder.iterdir():
                    if category_folder.is_dir():
                        if category_folder.name == slug or category_folder.name.replace('-', '_') == slug.replace('-', '_'):
                            return True
        
        return False
    
    def detect_subcategories(self, category_url):
        """Check if category has subcategories by visiting the page"""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                page.goto(category_url, wait_until='networkidle', timeout=20000)
                
                # Check for subcategory selectors (common patterns)
                has_sidebar_subcats = page.query_selector_all('.amshopby-filter-item')
                has_dropdown_subcats = page.query_selector_all('.level1')
                has_subcat_items = page.query_selector_all('li.level1')
                
                browser.close()
                
                has_subcategories = bool(has_sidebar_subcats or has_dropdown_subcats or has_subcat_items)
                return has_subcategories
        
        except Exception as e:
            print(f"  ⚠️  Could not detect subcategories: {e}")
            return False
    
    def create_scraper_for_category(self, slug, category_info):
        """Create scraper template for new category"""
        
        print(f"\n  🔧 Creating scraper template for '{slug}'...")
        
        try:
            # Determine scraper type based on subcategories
            has_subcats = self.detect_subcategories(category_info['url'])
            category_name_ar = category_info['name']
            
            # Create category folder in HyperStack
            project_path = Path(__file__).parent.parent / slug
            project_path.mkdir(exist_ok=True)
            
            # Create scraper.py
            if has_subcats:
                scraper_content = self._generate_async_scraper_template(slug, category_name_ar, category_info['url'])
            else:
                scraper_content = self._generate_sync_scraper_template(slug, category_name_ar, category_info['url'])
            
            scraper_path = project_path / 'scraper.py'
            with open(scraper_path, 'w', encoding='utf-8') as f:
                f.write(scraper_content)
            
            # Create requirements.txt
            requirements_content = self._get_requirements_for_type(has_subcats)
            req_path = project_path / 'requirements.txt'
            with open(req_path, 'w', encoding='utf-8') as f:
                f.write(requirements_content)
            
            # Create README.md
            readme_content = self._generate_readme(slug, category_name_ar, has_subcats)
            readme_path = project_path / 'README.md'
            with open(readme_path, 'w', encoding='utf-8') as f:
                f.write(readme_content)
            
            print(f"    ✅ Created: {project_path.name}/scraper.py")
            print(f"    ✅ Created: {project_path.name}/requirements.txt")
            print(f"    ✅ Created: {project_path.name}/README.md")
            
            return True
        
        except Exception as e:
            print(f"    ❌ Error creating scraper: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _generate_async_scraper_template(self, slug, name_ar, url):
        """Generate async scraper template for categories with subcategories"""
        
        return dedent(f'''
"""
Async scraper for {name_ar} category on sheeel.com
Handles subcategories with concurrent scraping for performance
"""
import asyncio
from playwright.async_api import async_playwright
import json
import pandas as pd
from datetime import datetime
from pathlib import Path

class {slug.title().replace('_', '')}Scraper:
    def __init__(self):
        self.base_url = "{url}"
        self.output_dir = Path('output')
        self.output_dir.mkdir(exist_ok=True)
        self.semaphore = asyncio.Semaphore(3)  # Limit concurrent requests
        self.all_products = []
    
    async def scrape_category(self):
        """Main scraping method"""
        print(f"\\n🌐 Starting scraper for {name_ar}")
        print(f"📡 URL: {{self.base_url}}")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            await page.goto(self.base_url, wait_until='networkidle', timeout=30000)
            
            # Extract subcategories
            subcat_links = await page.query_selector_all('li.level1 > a')
            subcategories = []
            
            for link in subcat_links:
                href = await link.get_attribute('href')
                text = await link.inner_text()
                if href and text.strip():
                    subcategories.append({{
                        'name': text.strip(),
                        'url': href
                    }})
            
            print(f"✓ Found {{len(subcategories)}} subcategories\\n")
            
            # Scrape each subcategory concurrently
            tasks = [
                self.scrape_subcategory(page, subcat['url'], subcat['name'])
                for subcat in subcategories
            ]
            
            await asyncio.gather(*tasks)
            
            await browser.close()
        
        # Save results
        self.save_results()
    
    async def scrape_subcategory(self, page, url, name):
        """Scrape individual subcategory with pagination"""
        async with self.semaphore:
            try:
                print(f"📂 Scraping: {{name}}")
                
                await page.goto(url, wait_until='networkidle', timeout=20000)
                
                page_num = 1
                while True:
                    # Extract products from current page
                    products = await self.extract_products_from_page(page, name)
                    self.all_products.extend(products)
                    
                    # Check for next page
                    next_button = await page.query_selector('a.next')
                    if next_button:
                        await next_button.click()
                        await page.wait_for_load_state('networkidle')
                        page_num += 1
                    else:
                        break
                
                print(f"  ✓ {{{{len(products)}}}} products from {{name}}")
            
            except Exception as e:
                print(f"  ❌ Error scraping {{name}}: {{e}}")
    
    async def extract_products_from_page(self, page, subcategory):
        """Extract product information from page"""
        products = []
        
        items = await page.query_selector_all('.product-item')
        
        for item in items:
            try:
                name_el = await item.query_selector('a.product-name')
                price_el = await item.query_selector('.price')
                brand_el = await item.query_selector('a.amshopby-brand-title-link')
                
                product = {{
                    'name': await name_el.inner_text() if name_el else 'N/A',
                    'price': await price_el.inner_text() if price_el else 'N/A',
                    'brand': await brand_el.inner_text() if brand_el else 'N/A',
                    'subcategory': subcategory,
                    'url': await name_el.get_attribute('href') if name_el else 'N/A',
                    'scraped_at': datetime.now().isoformat()
                }}
                products.append(product)
            
            except Exception as e:
                continue
        
        return products
    
    def save_results(self):
        """Save scraped products to Excel"""
        if not self.all_products:
            print("❌ No products scraped")
            return
        
        df = pd.DataFrame(self.all_products)
        output_file = self.output_dir / f"{{datetime.now().strftime('%Y%m%d_%H%M%S')}}_products.xlsx"
        
        df.to_excel(output_file, index=False, engine='openpyxl')
        print(f"\\n✅ Saved {{len(self.all_products)}} products to {{output_file}}")

async def main():
    scraper = {slug.title().replace('_', '')}Scraper()
    await scraper.scrape_category()

if __name__ == '__main__':
    asyncio.run(main())
''').strip()
    
    def _generate_sync_scraper_template(self, slug, name_ar, url):
        """Generate sync scraper template for categories without subcategories"""
        
        return dedent(f'''
"""
Sync scraper for {name_ar} category on sheeel.com
Simple single-level scraper without subcategories
"""
from playwright.sync_api import sync_playwright
import json
import pandas as pd
from datetime import datetime
from pathlib import Path

class {slug.title().replace('_', '')}Scraper:
    def __init__(self):
        self.base_url = "{url}"
        self.output_dir = Path('output')
        self.output_dir.mkdir(exist_ok=True)
        self.all_products = []
    
    def scrape_category(self):
        """Main scraping method"""
        print(f"\\n🌐 Starting scraper for {name_ar}")
        print(f"📡 URL: {{self.base_url}}")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            page.goto(self.base_url, wait_until='networkidle', timeout=30000)
            
            page_num = 1
            while True:
                # Extract products from current page
                products = self.extract_products_from_page(page)
                self.all_products.extend(products)
                
                print(f"✓ Page {{page_num}}: {{len(products)}} products")
                
                # Check for next page
                next_button = page.query_selector('a.next')
                if next_button:
                    next_button.click()
                    page.wait_for_load_state('networkidle')
                    page_num += 1
                else:
                    break
            
            browser.close()
        
        # Save results
        self.save_results()
    
    def extract_products_from_page(self, page):
        """Extract product information from page"""
        products = []
        
        items = page.query_selector_all('.product-item')
        
        for item in items:
            try:
                name_el = item.query_selector('a.product-name')
                price_el = item.query_selector('.price')
                brand_el = item.query_selector('a.amshopby-brand-title-link')
                
                product = {{
                    'name': name_el.inner_text() if name_el else 'N/A',
                    'price': price_el.inner_text() if price_el else 'N/A',
                    'brand': brand_el.inner_text() if brand_el else 'N/A',
                    'url': name_el.get_attribute('href') if name_el else 'N/A',
                    'scraped_at': datetime.now().isoformat()
                }}
                products.append(product)
            
            except Exception as e:
                continue
        
        return products
    
    def save_results(self):
        """Save scraped products to Excel"""
        if not self.all_products:
            print("❌ No products scraped")
            return
        
        df = pd.DataFrame(self.all_products)
        output_file = self.output_dir / f"{{datetime.now().strftime('%Y%m%d_%H%M%S')}}_products.xlsx"
        
        df.to_excel(output_file, index=False, engine='openpyxl')
        print(f"\\n✅ Saved {{len(self.all_products)}} products to {{output_file}}")

def main():
    scraper = {slug.title().replace('_', '')}Scraper()
    scraper.scrape_category()

if __name__ == '__main__':
    main()
''').strip()
    
    def _get_requirements_for_type(self, has_subcats):
        """Get requirements.txt content based on scraper type"""
        return dedent('''
playwright==1.40.0
pandas==2.1.0
openpyxl==3.1.2
boto3==1.34.0
requests==2.31.0
''').strip()
    
    def _generate_readme(self, slug, name_ar, has_subcats):
        """Generate README for new category"""
        scraper_type = "Async (with subcategories)" if has_subcats else "Sync (single level)"
        
        return dedent(f'''
# {name_ar} Scraper

Scraper for the **{name_ar}** category on sheeel.com

## Configuration
- **Type:** {scraper_type}
- **Category:** {slug}
- **Base URL:** https://www.sheeel.com/ar/

## Features
- Automated product discovery
- Price and brand extraction
- Pagination support
- Excel export with automatic formatting
- {"Concurrent subcategory scraping (3 parallel)" if has_subcats else "Sequential single-level scraping"}

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

## Usage

```bash
python scraper.py
```

Output files are saved to `output/` directory in Excel format.

## Auto-generated
Created by category discovery system on {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
''').strip()
    
    
        """Compare discovered categories with current registry"""
        
        print("\n" + "="*70)
        print("🔄 COMPARING WITH REGISTRY")
        print("="*70)
        
        discovered_slugs = set(self.discovered_categories.keys())
        registry_slugs = set(self.old_registry.keys())
        
        added = discovered_slugs - registry_slugs
        removed = registry_slugs - discovered_slugs
        unchanged = discovered_slugs & registry_slugs
        
        print(f"\n📊 Summary:")
        print(f"  • Previous categories: {len(registry_slugs)}")
        print(f"  • Currently discovered: {len(discovered_slugs)}")
        print(f"  • Unchanged: {len(unchanged)}")
        
        changes = {
            'added': list(added),
            'removed': list(removed),
            'unchanged': list(unchanged),
            'total_previous': len(registry_slugs),
            'total_current': len(discovered_slugs)
        }
        
        if added:
            print(f"\n🆕 NEW CATEGORIES ({len(added)}):")
            for slug in sorted(added):
                cat = self.discovered_categories[slug]
                scraper = "✅ Has scraper" if cat['has_scraper'] else "❌ No scraper"
                print(f"  • {cat['name'][:30]:30} ({slug:25}) - {scraper}")
                print(f"     URL: {cat['url']}")
        
        if removed:
            print(f"\n🗑️  REMOVED CATEGORIES ({len(removed)}):")
            for slug in sorted(removed):
                cat = self.old_registry[slug]
                scraper = "⚠️  Has scraper" if cat.get('has_scraper') else "✓ No scraper"
                print(f"  • {cat['name'][:30]:30} ({slug:25}) - {scraper}")
                print(f"     URL: {cat.get('url', 'unknown')}")
        
        if not added and not removed:
            print("\n✓ No changes - all categories stable")
        
        print("\n" + "="*70 + "\n")
        
        return changes
    
    def update_registry(self, changes):
        """Update categories.json with new discoveries"""
        
        # Start with discovered categories
        updated_registry = self.discovered_categories.copy()
        
        # Add metadata
        for slug, cat in updated_registry.items():
            # Preserve existing metadata if available
            if slug in self.old_registry:
                old_cat = self.old_registry[slug]
                cat['project'] = old_cat.get('project', 'unknown')
                cat['status'] = old_cat.get('status', 'active')
                cat['last_checked'] = datetime.now().isoformat()
                cat['consecutive_failures'] = old_cat.get('consecutive_failures', 0)
            else:
                # New category
                cat['project'] = 'NEW'
                cat['status'] = 'active'
                cat['last_checked'] = datetime.now().isoformat()
                cat['consecutive_failures'] = 0
        
        # Create full registry object
        registry_data = {
            'last_updated': datetime.now().isoformat(),
            'total_categories': len(updated_registry),
            'categories': updated_registry
        }
        
        # Save to file
        with open(self.registry_path, 'w', encoding='utf-8') as f:
            json.dump(registry_data, f, ensure_ascii=False, indent=2)
        
        print(f"✓ Updated registry: {self.registry_path}")
        print(f"  Total categories: {len(updated_registry)}")
        print(f"  Last updated: {registry_data['last_updated']}\n")
        
        return registry_data
    
    def generate_report(self, changes, discovered_count_before):
        """Generate detailed report of changes"""
        
        print("\n" + "="*70)
        print("📋 FINAL REPORT")
        print("="*70)
        
        if changes['added'] or changes['removed']:
            print("\n⚠️  CHANGES DETECTED!\n")
            
            if changes['added']:
                print(f"🆕 {len(changes['added'])} new categor{'ies' if len(changes['added']) != 1 else 'y'}:")
                for slug in sorted(changes['added']):
                    print(f"   • {slug}")
                print(f"\n   ⚠️  Action required: Create scraper template for new categories")
            
            if changes['removed']:
                print(f"\n🗑️  {len(changes['removed'])} removed categor{'ies' if len(changes['removed']) != 1 else 'y'}:")
                for slug in sorted(changes['removed']):
                    print(f"   • {slug}")
                print(f"\n   ⚠️  Action required: Archive or update scrapers for removed categories")
            
            print("\n" + "="*70)
            print("✅ GitHub Issue will be created with these changes")
            print("="*70 + "\n")
        
        else:
            print("\n✅ No changes detected - all categories stable\n")
            print("="*70 + "\n")
    
    def run(self):
        """Main execution flow"""
        
        print("\n" + "="*70)
        print("🔍 CATEGORY DISCOVERY SYSTEM")
        print("="*70)
        print(f"\n📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"🌐 Website: {self.base_url}\n")
        
        # Step 1: Load current registry
        self.old_registry = self.load_registry()
        print(f"✓ Loaded registry with {len(self.old_registry)} known categories")
        
        # Step 2: Discover categories from website
        self.discovered_categories = self.discover_categories_from_website()
        
        if not self.discovered_categories:
            print("\n❌ No categories discovered from website. Check selectors or website status.")
            return False
        
        # Step 3: Compare with registry
        changes = self.compare_with_registry()
        
        # Step 3.5: Create scrapers for new categories
        if changes['added']:
            print("\n" + "="*70)
            print("🔧 CREATING SCRAPERS FOR NEW CATEGORIES")
            print("="*70)
            scrapers_created = 0
            for slug in sorted(changes['added']):
                if self.create_scraper_for_category(slug, self.discovered_categories[slug]):
                    scrapers_created += 1
            print(f"\n✓ Created scrapers for {scrapers_created}/{len(changes['added'])} new categories\n")
        
        # Step 4: Update registry
        self.update_registry(changes)
        
        # Step 5: Generate report
        self.generate_report(changes, len(self.old_registry))
        
        # Return True if changes detected (for workflow decision)
        return bool(changes['added'] or changes['removed'])

if __name__ == '__main__':
    discovery = CategoryDiscovery()
    changes_detected = discovery.run()
    
    # Exit with code 0 always (we handle changes gracefully)
    # GitHub workflow will detect changes via git diff
    exit(0)
