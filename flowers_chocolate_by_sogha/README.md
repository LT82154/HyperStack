# Flowers & Chocolate by Sogha Category Scraper

Automated scraper for the "Flowers & Chocolate by Sogha" category on **sheeel.com** with **concurrent subcategory scraping**.

## Category Details

- **URL:** https://www.sheeel.com/ar/flowers-chocolate-by-sogha.html
- **Category:** flowers_chocolate_by_sogha
- **Type:** Hierarchical (with subcategories)
- **S3 Folder:** `flowers_chocolate_by_sogha/`
- **Optimization:** Async scraping with semaphore (3 subcategories concurrently)

## Features

✅ **Concurrent Subcategory Scraping**
- **Performance:** ~2.5x faster than sequential scraping
- **Controlled:** Semaphore limits to 3 concurrent subcategories (configurable)
- **Stable:** Prevents server overload while maximizing speed

✅ **Incremental S3 Upload**
- **Performance:** ~30% faster than batch upload
- **Method:** Images uploaded to S3 immediately after download
- **Reliability:** Incremental progress reduces risk of data loss

✅ **Subcategory Support**
- Automatically extracts all subcategories from the main page
- Scrapes each subcategory independently with full pagination
- Each subcategory saved as a separate Excel sheet

✅ **Multi-Sheet Excel Output**
- One sheet per subcategory (flowers, chocolates, etc.)
- Additional "ALL_PRODUCTS" sheet with combined data
- Products tagged with `subcategory` field

✅ **Complete Data Extraction**
- Product ID, name, SKU, prices, availability
- Multiple product images (stored as arrays)
- Features & specifications
- Box contents, warranty info
- Discount badges, deal timers

✅ **Excel Character Sanitization**
- Automatic removal of illegal characters (control characters)
- Handles Arabic text safely
- Prevents openpyxl errors

✅ **AWS S3 Integration**
- Date partitioning: `year=YYYY/month=MM/day=DD/`
- Organized storage: separate folders for images and Excel files
- All images uploaded with indexed naming

## Data Structure

### S3 Path Structure

```
s3://{bucket}/sheeel_data/
    └── year=2026/
        └── month=04/
            └── day=16/
                └── flowers_chocolate_by_sogha/
                    ├── images/
                    │   ├── 12345_0.jpg
                    │   ├── 12345_1.jpg
                    │   └── ...
                    └── excel-files/
                        └── flowers_chocolate_by_sogha_20260416_120000.xlsx
```

### Excel Structure

**Multiple sheets:**
- One sheet per subcategory (flowers, chocolates, gift boxes, etc.)
- `ALL_PRODUCTS` sheet with combined data

**Columns (per product):**
- `product_id`, `name`, `sku`
- `old_price`, `special_price`
- `availability`, `times_bought`
- `description`
- `image_urls` (array - not flattened)
- `s3_image_paths` (array - not flattened)
- `features_specs` (array) + `feature_spec_0`, `feature_spec_1`, ... (flattened)
- `box_contents`, `warranty` (single values)
- `deal_time_left`, `discount_badge`
- `subcategory` (name of the subcategory)
- `url`, `scraped_at`

## Local Testing

```bash
cd HyperStack/flowers_chocolate_by_sogha

# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Set environment variables
export AWS_ACCESS_KEY_ID="your_key"
export AWS_SECRET_ACCESS_KEY="your_secret"
export S3_BUCKET_NAME="your_bucket"

# Optional: Configure concurrency (default: 3)
export MAX_CONCURRENT_SUBCATEGORIES=3

# Run scraper
python scraper.py
```

## Performance Configuration

The scraper uses concurrent scraping to improve performance:

- **MAX_CONCURRENT_SUBCATEGORIES**: Number of subcategories to scrape simultaneously (default: 3)
  - Lower values (1-2): More conservative, less server load
  - Higher values (4-6): Faster but may stress server
  - Recommended: 3 (balanced performance and stability)

```bash
# Set custom concurrency level
export MAX_CONCURRENT_SUBCATEGORIES=5
python scraper.py
```

## Technical Architecture

- **Engine:** Playwright (async) with Chromium browser
- **Concurrency:** asyncio.Semaphore for controlled parallelism
- **Upload Strategy:** Incremental (upload images as they're downloaded)
- **Data Processing:** pandas with Excel character sanitization
- **Storage:** AWS S3 with date partitioning

## Performance Metrics

- **Concurrent Scraping:** ~2.5x faster than sequential
- **Incremental Upload:** ~30% faster than batch upload
- **Combined:** ~3x overall speedup
- **Stability:** Semaphore prevents server overload

## Scraping Flow

1. Load main category page
2. Extract all subcategory links (filtered to `/ar/flowers-chocolate-by-sogha/`)
3. Scrape 3 subcategories concurrently (with semaphore control)
4. For each subcategory:
   - Scrape all pages (using Next button detection)
   - Extract product links from each page
   - Visit each product detail page
   - Extract 20+ fields per product
5. Download images and upload to S3 incrementally
6. Generate multi-sheet Excel file with sanitized data
7. Upload Excel to S3

## Error Handling

- **Page-level errors:** Continue to next page
- **Product-level errors:** Continue to next product
- **Image download errors:** Skip failed images, continue with others
- **S3 upload errors:** Log error but continue execution
- **Excel character errors:** Automatic sanitization prevents crashes

## Output

**Local files:**
- `data/images/{product_id}_{index}.{ext}` - Product images
- `data/flowers_chocolate_by_sogha_{timestamp}.xlsx` - Multi-sheet Excel file

**S3 files:**
- `sheeel_data/year=YYYY/month=MM/day=DD/flowers_chocolate_by_sogha/images/` - All product images
- `sheeel_data/year=YYYY/month=MM/day=DD/flowers_chocolate_by_sogha/excel-files/` - Excel file with all sheets

## GitHub Actions Integration

This scraper is designed to run automatically via GitHub Actions:

- **Schedule:** Every 2 days at 7:00 AM UTC (configurable in workflow)
- **Manual trigger:** Available via workflow_dispatch
- **Parallel execution:** Runs alongside other category scrapers
- **Artifact backup:** 7-day retention for local files

## Notes

- Scraper handles JavaScript-rendered content (Angular SPA)
- Pagination uses Next button detection (unlimited pages)
- Images stored as arrays (not flattened into separate columns)
- Features flattened into `feature_spec_0`, `feature_spec_1`, etc.
- Box contents and warranty stored as single values
- All Arabic text automatically sanitized for Excel compatibility
- URL filtering: `/ar/flowers-chocolate-by-sogha/` to avoid extracting all site categories
