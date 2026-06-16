# Category Monitor

Automated monitoring system for sheeel.com categories. Discovers new categories, detects removed categories, and creates GitHub Issues for changes.

## Overview

This system:
- ✅ Fetches all categories from sheeel.com navigation
- ✅ Compares with current registry (15 known categories)
- ✅ Detects new categories automatically
- ✅ Detects removed/moved categories automatically
- ✅ Creates GitHub Issues for any changes
- ✅ Maintains version-controlled registry

## Files

- **`categories.json`** - Central registry of all 15 known categories
- **`discover.py`** - Category discovery script (fetches from website)
- **`requirements.txt`** - Python dependencies
- **`.github/workflows/monitor_categories.yml`** - GitHub Actions automation

## Current Categories (15)

### Codinity Project
1. **emergency_need** - احتياجات طارئة
2. **power_bank_chargers** - بطاريات خارجية وشواحن
3. **long_life_food** - أطعمة طويلة الأجل
4. **kitchen_fun** - المطبخ والمتعة

### ThinkGrid Project
5. **cool_items** - أشياء عصرية
6. **best_seller** - الأكثر مبيعا
7. **supermarket** - السوبر ماركت

### Techvalue Project
8. **electronics** - إلكترونيات
9. **mobile_e_cards** - الهاتف والبطاقات الإلكترونية

### Sportive Project
10. **sports_toys** - الرياضة والألعاب

### Kerno Project
11. **home** - المنزل

### RogueBit Project
12. **perfumes_beauty** - العطور والجمال

### HyperStack Project
13. **flowers_chocolate_by_sogha** - الزهور والشوكولاتة من سوجة

### CircuitBloom Project
14. **only_on_sheeel** - حصرياً على شيل

### LogicPulse Project
15. **coupons** - كوبونات

## How It Works

### Step 1: Discovery (Every 2 Days at 2:00 AM UTC)

The workflow runs `discover.py` which:
1. Loads sheeel.com homepage
2. Extracts category links from navigation
3. Filters out non-category pages (account, checkout, etc.)
4. Compares discovered categories with `categories.json`

```python
python discover.py
```

### Step 2: Change Detection

Discovers:
- **🆕 New categories** - Not in registry, needs scraper
- **🗑️ Removed categories** - In registry, no longer on website
- **✓ Stable categories** - No changes

### Step 3: Registry Update

If changes found:
- Updates `categories.json` with new discoveries
- Commits changes to git
- Creates GitHub Issue with details

### Step 4: GitHub Issue

Auto-generated issue includes:
- List of new categories (with URLs)
- List of removed categories
- Action items needed
- Link to workflow run

**Example Issue:**
```
Title: 🔄 Category Changes: 2 added, 1 removed

## 🆕 New Categories (2)
- ❌ Home Decor (home-decor)
  - URL: https://www.sheeel.com/ar/home-decor.html
  - Project: NEW

## 🗑️ Removed Categories (1)
- ⚠️ Old Deals (old-deals)
  - Project: ThinkGrid
```

## Registry Format (categories.json)

```json
{
  "last_updated": "2026-04-18T02:00:00.000Z",
  "total_categories": 15,
  "categories": {
    "electronics": {
      "name": "إلكترونيات",
      "url": "https://www.sheeel.com/ar/electronics.html",
      "project": "Techvalue",
      "status": "active",
      "discovered": "2026-04-01T00:00:00.000Z",
      "has_scraper": true,
      "last_checked": "2026-04-18T02:00:00.000Z",
      "consecutive_failures": 0
    }
  }
}
```

## Workflow Schedule

**File:** `.github/workflows/monitor_categories.yml`

**Schedule:** Every 2 days at 2:00 AM UTC (`0 2 */2 * *`)

**Staggered with other workflows:**
- 12:00 AM UTC - ThinkGrid (scrapers)
- 1:00 AM UTC - Codinity (scrapers)
- 2:00 AM UTC - **Category Monitor** (discovery)
- 3:00 AM UTC - Techvalue (scrapers)
- 4:00 AM UTC - Sportive (scrapers)
- 5:00 AM UTC - Kerno (scrapers)

## Local Testing

```bash
cd HyperStack/category_monitor

# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Run discovery
python discover.py
```

**Output:**
```
======================================================================
🔍 CATEGORY DISCOVERY SYSTEM
======================================================================

📅 Date: 2026-04-18 02:15:30 UTC
🌐 Website: https://www.sheeel.com/ar/

✓ Loaded registry with 15 known categories

======================================================================
🌐 DISCOVERING CATEGORIES FROM WEBSITE
======================================================================

📡 Loading: https://www.sheeel.com/ar/
✓ Found category container

📂 Extracting categories from links...

  • إلكترونيات                     (electronics)            - ✅ Has scraper
  • الهاتف والبطاقات الإلكترونية    (mobile-e-cards)       - ✅ Has scraper
  • المنزل                         (home)                   - ✅ Has scraper
  ... (12 more categories)

✓ Discovered 15 categories

======================================================================
🔄 COMPARING WITH REGISTRY
======================================================================

📊 Summary:
  • Previous categories: 15
  • Currently discovered: 15
  • Unchanged: 15

✓ No changes - all categories stable

======================================================================

✓ Updated registry: categories.json
  Total categories: 15
  Last updated: 2026-04-18T02:15:30.000Z

======================================================================
📋 FINAL REPORT
======================================================================

✅ No changes detected - all categories stable
```

## Change Detection Example

If a new category is added:

```
======================================================================
🆕 NEW CATEGORIES (1):
======================================================================

  • نمط الحياة                      (lifestyle)              - ❌ No scraper
     URL: https://www.sheeel.com/ar/lifestyle.html

...

✅ GitHub Issue will be created with these changes
```

## Actions When Changes Detected

### When New Categories Found

**Automatic:**
- ✅ GitHub Issue created with category details
- ✅ Categories.json updated and committed
- ✅ Issue tagged with `category-change`, `monitoring`

**Manual:**
- Create new scraper using template
- Test locally
- Add to appropriate project folder
- Update workflow matrix if needed
- Create PR

### When Categories Removed

**Automatic:**
- ✅ GitHub Issue created with removal details
- ✅ Categories.json updated
- ✅ Registry marked as removed

**Manual:**
- Review scraper status
- Archive scraper or remove from workflow
- Verify no data is lost
- Clean up resources

## Integration with Existing Scrapers

This monitoring system works **independently** from existing scrapers:

- ✅ **Does NOT** modify existing scraper code
- ✅ **Does NOT** change workflow schedules
- ✅ **Does NOT** interrupt existing runs
- ✅ **Runs before** main scraping workflows (2:00 AM vs 12:00-5:00 AM)
- ✅ **Provides alerting** about category changes

## Selector Reference

**Navigation Container:**
```
.categories-slider-container
```

**Extract from:**
- All `<a>` tags with `href*="/ar/"`

**Filter out:**
- Non-category pages: customer, account, checkout, cart, etc.
- Non-product pages: policy, terms, about, contact, etc.

**Current selectors used:**
```python
# Primary
selector = '.categories-slider-container'

# Fallback selectors
'nav .categories'
'[class*="categor"]'
'.nav-strip'
```

## Known Limitations

- ⚠️ Discovery depends on website navigation structure
- ⚠️ Selector may need updates if website redesigns
- ⚠️ Manual category creation still required (no auto-generation)
- ⚠️ Only checks for category existence (not structure changes)

## Future Enhancements

- [ ] Auto-generate scraper template for new categories
- [ ] Detect category URL changes (moved categories)
- [ ] Track category structure changes (subcategories added/removed)
- [ ] Slack/email notifications for faster response
- [ ] Dashboard showing category status history
- [ ] Historical tracking of category additions/removals
- [ ] Performance metrics (page load times, etc.)

## Troubleshooting

### No categories discovered

**Check:**
1. Website is accessible: `https://www.sheeel.com/ar/`
2. Selectors are correct (website might have redesigned)
3. Playwright installation: `playwright install-deps chromium`

**Fix:**
```bash
# Test manually
cd HyperStack/category_monitor
python discover.py

# Check logs in GitHub Actions
```

### Issue not created

**Check:**
1. GitHub Actions permissions enabled
2. Secrets configured (usually auto-available)
3. categories.json actually changed

**Fix:**
```bash
# Check diff locally
git diff HyperStack/category_monitor/categories.json
```

### Wrong selectors

If categories not being discovered:

1. Inspect website: https://www.sheeel.com/ar/
2. Find category list in browser DevTools
3. Update selectors in `discover.py`
4. Test locally, then commit

## Version History

- **v1.0** (April 18, 2026) - Initial implementation
  - Discovers 15 known categories
  - Creates GitHub Issues on changes
  - Registry versioning in git

## Support

For issues or improvements, create GitHub Issue tagged with `category-monitor`.

---

**Last Updated:** April 18, 2026  
**Workflow Status:** Active (Every 2 days at 2:00 AM UTC)  
**Current Categories:** 15 known categories
