# Wickercraft Campaign Playbook — Step-by-Step "How To"

Companion to [wickercraft-marketing-strategy.md](wickercraft-marketing-strategy.md). That doc says *what* to run; this one shows *how* to set each campaign up, click by click, plus the copy, creative specs, and settings to use.

---

## 0. Tracking Setup (Do First — Everything Depends on This)

### Google Analytics 4 + Tag Manager
1. Create a GA4 property at analytics.google.com → Admin → Create Property.
2. Create a Google Tag Manager container at tagmanager.google.com; install the GTM snippet on your site (most site builders — Shopify, Wix, Squarespace, WooCommerce — have a field or plugin for this).
3. In GTM, add the **GA4 Configuration tag** with your Measurement ID (G-XXXXXXX), trigger: All Pages.
4. In GA4 → Admin → Events, mark `purchase`, `add_to_cart`, `begin_checkout`, and `generate_lead` (email signup) as **key events**.
5. If on Shopify: skip GTM and use the native **Google & YouTube channel app** — it wires GA4 + Merchant Center + conversion tracking automatically.

### Meta Pixel + Conversions API
1. business.facebook.com → create a Business Portfolio → Events Manager → Connect Data Sources → Web → create Pixel.
2. Install via your platform's native integration (Shopify: "Facebook & Instagram" app; WooCommerce: "Facebook for WooCommerce" plugin) — these also enable the **Conversions API** (server-side tracking), which you want because browser-only pixels miss ~20–30% of conversions.
3. Verify events fire: Events Manager → Test Events → browse your site → confirm PageView, ViewContent, AddToCart, Purchase appear.

### Pinterest Tag & TikTok Pixel
- Pinterest: ads.pinterest.com → Ads → Conversions → install via your platform's Pinterest app/plugin. Verify with the Pinterest Tag Helper Chrome extension.
- TikTok: ads.tiktok.com → Assets → Events → Web Events → create Pixel → install via platform app (Shopify/WooCommerce have one-click apps).

### Product feed (powers Google Shopping, Meta catalog, Pinterest catalog)
1. Google Merchant Center: merchants.google.com → create account → verify your website (DNS or HTML tag).
2. Connect your store platform (native integrations exist for all major platforms) or upload a feed file.
3. Fix feed quality before running ads:
   - **Titles:** `Handwoven [Material] [Product Type] – [Color], [Size]` e.g. "Handwoven Rattan Storage Basket – Natural, Large".
   - **Images:** white/neutral background, no text or watermarks, min 800×800px.
   - **GTIN:** handmade goods usually have none — set `identifier_exists: false`.
   - Fill `google_product_category` (e.g. Home & Garden > Decor > Baskets).
4. Reuse the same feed: Meta Commerce Manager → Catalog → add items → use partner platform; Pinterest → Catalogs → connect data source.

---

## 1. Google Ads — How To

### Account setup
1. ads.google.com → create account → **skip the "Smart campaign" wizard** (click "Switch to Expert Mode" at the bottom — the wizard creates a low-quality campaign).
2. Link accounts: Tools → Linked accounts → link GA4 and Merchant Center.
3. Tools → Conversions → import your GA4 `purchase` key event as the primary conversion.

### Campaign 1: Brand Search (15 minutes, ~5% of budget)
1. New campaign → Sales → Search → uncheck "Display Network" and "Search Partners".
2. One ad group, keywords: your brand name in `[exact match]` and "phrase match" (e.g. `[willow & reed]`, `"willow and reed baskets"`).
3. Bidding: Maximize Clicks with a low max CPC cap (e.g. $0.50) — brand clicks should be cheap.
4. Write one Responsive Search Ad: headlines with your brand name, "Official Site", "Free Shipping Over $X", "Handmade to Order"; pin your brand name headline to position 1.

### Campaign 2: Shopping / Performance Max (the workhorse, ~40%)
1. New campaign → Sales → Performance Max → select your Merchant Center feed.
2. Goal: purchases only. Budget: start at ~40% of daily Google budget.
3. Bidding: **Maximize Conversions** (no tROAS target yet — you need ~30 conversions first).
4. Asset group: upload 5–10 lifestyle images, 3–5 videos (your Reels work), all headline/description slots filled. Use audience signal: custom segment with keywords "wicker basket", "rattan decor", "boho home decor" + your website visitors.
5. **Critical setting:** Campaign settings → Final URL expansion → add exclusions for cart/checkout/account pages.
6. Let it learn for 2 weeks minimum before judging. After 30+ conversions, switch bidding to Target ROAS starting at your break-even ROAS minus 20% (e.g. if break-even is 2.5x, set 2.0x, then raise 10–15% every 2 weeks).

### Campaign 3: Non-brand Search (~25%)
1. New campaign → Sales → Search, no Display/Search Partners.
2. Ad groups by theme (tight = better Quality Score):
   - **Storage baskets:** `"wicker storage basket"`, `"rattan storage baskets"`, `[woven storage baskets with lids]`
   - **Laundry:** `"wicker laundry basket"`, `[wicker hamper with lid]`
   - **Planters:** `"wicker planter"`, `"woven plant basket"`
   - **Furniture** (if applicable): `"rattan side table"`, `"wicker chair indoor"`
3. Match types: start phrase + exact only. No broad match until the account has conversion history.
4. **Negative keyword list** (Tools → Negative keyword lists, apply to all campaigns): `free, cheap, diy, how to make, pattern, repair, kit, wholesale, used, second hand, ikea, amazon` (remove `wholesale` if you want B2B leads).
5. Responsive Search Ad per ad group — headline formula:
   - Keyword headline: "Handwoven Wicker Storage Baskets"
   - Differentiator: "Handmade, Not Mass-Produced"
   - Offer: "Free Shipping Over $75"
   - Trust: "★★★★★ Rated by 200+ Homes"
   - CTA: "Shop the Collection"
6. Add assets (extensions): sitelinks (Bestsellers, New Arrivals, Sale, Our Story), image assets, price assets, promotion assets during sales.

### Campaign 4: Remarketing (~15%)
1. Ensure GA4 audiences exist: Admin → Audiences → create "Added to cart, no purchase (30 days)" and "All visitors (30 days)".
2. New campaign → Demand Gen → target those two audiences (cart abandoners get 2–3x the budget of general visitors).
3. Creative: carousel of bestsellers + a "Still thinking it over?" headline. If you offer a first-order discount, this is the place to show it.
4. Frequency: watch Reach reports; if frequency exceeds ~8/week, lower budget.

### Weekly routine (30 min)
- Search terms report → add irrelevant queries as negatives.
- Pause any ad group with >2x target CPA and no sales after 100 clicks.
- Check Merchant Center → Diagnostics for disapproved products.

---

## 2. Meta (Facebook + Instagram) Ads — How To

### Setup
1. business.facebook.com → confirm you have: a Facebook Page, an Instagram professional account (connected to the Page), the Pixel (from step 0), and a Catalog.
2. Ads Manager → Ad account settings → set correct currency/timezone (can't change later).
3. Turn on **Instagram Shopping**: Commerce Manager → connect catalog → submit for review → once approved, tag products in posts.

### Campaign 1: Advantage+ Shopping (60% of Meta budget)
1. Ads Manager → Create → Sales → select "Advantage+ shopping campaign".
2. Conversion event: Purchase. Budget: 60% of daily Meta spend.
3. Creative — upload 6–10 assets mixing:
   - **Catalog ads** (auto-generated from your product feed),
   - 2–3 **Reels-style videos** (weaving process, styling video — 9:16, under 30s, hook in first 2 seconds),
   - 2–3 **lifestyle statics** with minimal text overlay.
4. Primary text formula: hook + story + CTA. Example:
   > "Every basket is woven by hand — no two are exactly alike. 🧺 Natural rattan, built to last decades, not landfill-bound in a year. Free shipping over $75."
5. Existing-customer budget cap: set to 20% so most spend goes to new customers.
6. Let it run 7 days before touching anything. Kill only creatives with 2x+ your target cost per purchase after ~$50 spend each.

### Campaign 2: Retargeting Dynamic Product Ads (25%)
1. Create → Sales → manual campaign → Catalog sales objective.
2. Ad set 1: "Viewed or added to cart, not purchased, last 14 days" — this is your money audience.
3. Ad set 2: "Purchased in last 180 days" with a cross-sell product set (e.g. bought a basket → show planters) — small budget.
4. Ad format: catalog carousel. Primary text: "Your cart misses you 🧺 — handmade pieces sell out and don't restock identically."
5. Optional: add a 10% code in the ad for cart abandoners only.

### Campaign 3: Prospecting video (15%)
1. Create → Sales → manual → one ad set, targeting: Advantage+ audience with interest suggestions "home decor", "Anthropologie", "West Elm", "sustainable living", women+men 25–55, your shipping countries.
2. Creative: your single best process/story video. Test 3 different opening hooks of the same video:
   - "This basket took 6 hours to weave by hand"
   - "Why I'll never buy plastic storage again"
   - "POV: your storage is actually beautiful"
3. After 2 weeks, whichever hook wins becomes your evergreen prospecting ad.

### Influencer whitelisting (branded content ads)
1. Gift product to creators; ask them to toggle **"Allow business partner to boost"** on their post (they add you as a partner in Instagram settings).
2. In Ads Manager, the post appears under "Use existing post → Branded content" — run it in your Advantage+ campaign. Creator content typically outperforms brand-made ads.

---

## 3. Pinterest — How To

### Organic engine
1. Convert to a **business account** (pinterest.com/business) → claim your website (adds your logo to all pins from your domain + unlocks analytics).
2. Create 6–8 boards with keyword-rich names: "Wicker Storage Ideas", "Boho Living Room Decor", "Cottagecore Kitchen", "Sustainable Home Swaps", "Woven Basket Wall Ideas", "Natural Home Decor".
3. Pin creation workflow (batch 1 hour/week):
   - Use Canva (free) — 1000×1500px (2:3) templates.
   - For each product photo make 2–3 variants: plain lifestyle image, image + text overlay ("5 Ways to Style Wicker Baskets"), collage.
   - Pin title = keyword phrase ("Wicker Laundry Basket with Lid – Handwoven Rattan"); description = 2 sentences with 2–3 keywords + link.
   - Schedule via Pinterest's native scheduler (up to 2 weeks ahead) — 2–4 pins/day.
4. Repurpose every Reel/TikTok as a video pin (Pinterest loves video and competition is lower).

### Paid: Catalog Shopping ads (main spend)
1. ads.pinterest.com → Catalogs → connect your product feed (from step 0) → wait for ingestion.
2. Create campaign → objective **Catalog sales**.
3. Ad group 1 — **Retargeting:** audience = site visitors + engaged pinners, dynamic product ads. Start here.
4. Ad group 2 — **Prospecting:** interest targeting "Home Decor" > "Storage & Organization", plus keywords: `wicker basket`, `rattan decor`, `woven storage`, `boho bedroom ideas`, `basket wall`. 
5. Bidding: automatic to start. Pinterest CPCs for decor are usually well below Meta — expect volume.
6. **Timing rule:** Pinterest users plan 6–8 weeks ahead. Launch Christmas campaigns mid-October, Mother's Day campaigns in March.

### Paid: Promoted standard pins (secondary)
- Take your 3 best-performing organic pins (check Analytics → top pins by outbound clicks) → promote with **Consideration (clicks)** objective at $5–10/day to feed the retargeting pool.

---

## 4. TikTok — How To

### Organic system (this is 90% of TikTok success)
1. Set up a **business account** (Settings → Manage account → switch) — unlocks analytics and the website link.
2. Filming setup: phone + tripod + natural window light in the workshop. Batch-film one afternoon per week.
3. The 4 formats to rotate (post 4–7x/week):
   - **Process time-lapse:** static camera over the workbench, 2–4 hours of weaving compressed to 30s, trending audio. Text hook: "6 hours of weaving in 30 seconds".
   - **ASMR:** close-up reed soaking, weaving sounds, scissors, order packing. No music, captions only.
   - **Founder story talking-head:** "I make baskets for a living — here's what a day looks like", "what I'd tell myself before starting a craft business".
   - **Trend adaptation:** browse your For You page 10 min/day; when a sound/format trends, apply it to baskets within 48 hours.
4. Structure every video: **hook in the first 1.5 seconds** (visual or text), payoff at the end ("wait for the final basket"), caption with 3–5 hashtags (#basketweaving #handmade #wickerdecor #smallbusiness + one trending).
5. **Reply to comments with video** — pick a question ("how long does one take?", "do you ship to UK?") and answer on camera. These regularly outperform original posts.
6. Post times: test 7–9am and 6–9pm your audience's timezone; check Analytics → Follower activity after 2 weeks.

### TikTok Shop (if available in your country)
1. Apply at seller.tiktok.com → link your account → upload products (or sync from Shopify).
2. Tag a product in every relevant video (yellow basket icon appears).
3. Once comfortable, try a live: "pack orders with me" or "watch me weave" — lives get pushed hard by the algorithm.

### Paid: Spark Ads only
1. Wait until an organic video clearly wins (top ~10% of your views).
2. Creator side: video → Ad settings → generate a **Spark Ad code**.
3. ads.tiktok.com → Create campaign → objective: Website conversions (Purchase) → ad: "Use TikTok post" → paste code.
4. Targeting: broad, your shipping countries, 24–55. Budget: $10–20/day per winner. Kill after a week if cost per purchase is 2x+ target.
5. Never run studio-polished ads on TikTok — native-looking content wins.

---

## 5. YouTube — How To

### Shorts pipeline (near-zero extra effort)
1. Download your TikToks without watermark **before** posting to TikTok (save the original export), or use your Reels exports.
2. Upload 3/week as Shorts. Title = the hook ("6 Hours of Basket Weaving in 30 Seconds"). Add `#shorts` and link your store in the channel header + pinned comment.

### Long-form (2/month)
1. Film with the same phone setup; edit in CapCut (free).
2. Priority videos, in order:
   - "How It's Made: A Handwoven Wicker Basket, Start to Finish" (8–12 min) — your evergreen trust asset.
   - "How to Clean and Care for Wicker Furniture" — targets a real search query; put the keyword in the title, first line of description, and say it aloud in the first 30s.
   - "Workshop Tour + Q&A".
3. End screens → link to your other videos; description → store link with UTM (`?utm_source=youtube&utm_medium=organic`).

### Paid (runs from your Google Ads account, part of the 15% video share)
1. Google Ads → New campaign → Sales → Video.
2. Ad: your How It's Made video cut to 30–60s (front-load the most satisfying weaving shot).
3. Audiences: custom segment "people who searched Google for: wicker basket, rattan furniture, boho decor" + in-market "Home Decor".
4. Format: skippable in-stream + Shorts placement. Start $5–10/day.

---

## 6. X (Twitter) — How To (organic only, ~20 min/day max)

1. Bio: what you make + where you ship + store link.
2. Post 3–4x/week: a great photo + one-line story ("Order #500 left the workshop today. She's a laundry basket headed to Vermont.").
3. Spend more time replying than posting: search `#shopsmall`, `#handmade`, "wicker", "home decor" and join conversations helpfully.
4. **Press pitching (the real value):** in September–October, search for journalists posting "gift guide" callouts (#journorequest), and pitch home/lifestyle writers a 2-sentence email: what the product is, why it fits their guide, link to a press photo folder (Google Drive with 5 hi-res images + price list).

---

## 7. LinkedIn Wholesale — How To

1. Create a company page + polish your personal founder profile (headline: "Founder @ [Brand] — handwoven wicker for homes & commercial spaces").
2. Build a **trade lookbook PDF** (Canva): 8–10 pages — hero photos, product line with wholesale pricing tiers, lead times, minimums, contact.
3. Post 1–2x/week from your **personal** profile (personal profiles get far more reach than company pages): founder story, install photos, sustainability practices.
4. Outreach (10/week, personalized):
   - Search: "interior designer" / "boutique buyer" / "hotel procurement" + your region.
   - Connection note: "Hi [Name] — I hand-weave wicker pieces and loved your [specific project]. We run a trade program with designer pricing; happy to send the lookbook if useful."
   - After connecting, send the lookbook. No follow-up spam — one bump after 2 weeks.
5. Track inquiries in a simple spreadsheet: name, company, date, status, order value.

---

## 8. Email Flows — How To (Klaviyo, Mailchimp, or your platform's native tool)

### Welcome flow (trigger: popup signup)
| Email | Timing | Content |
|---|---|---|
| 1 | Immediately | 10% code + 2-paragraph founder story + 1 photo of hands weaving |
| 2 | Day 2 | 4 bestsellers with styling photos ("here's where our customers put them") |
| 3 | Day 4 | 3 customer reviews + UGC photos + code reminder ("expires in 48h") |

### Abandoned cart (trigger: begin checkout, no purchase)
| Email | Timing | Content |
|---|---|---|
| 1 | 1 hour | Photo of their cart item, "we saved your basket 🧺", no discount |
| 2 | 24 hours | The handmade angle: "each piece is woven to order — here's what goes into yours" |
| 3 | 48 hours | Small incentive (free shipping or 10%) with expiry |

### Post-purchase
| Email | Timing | Content |
|---|---|---|
| 1 | On delivery | Care instructions + styling tips |
| 2 | Day 14 | Review request ("photo reviews get a 15% next-order code") |
| 3 | Day 30 | Cross-sell based on what they bought |

Weekly newsletter: pick ONE thing per email (new product, restock, or one styling idea). Subject lines under 40 characters; the process photos you're already shooting are the content.

---

## 9. The Weekly Operating Rhythm (put this in your calendar)

| Day | Task | Time |
|---|---|---|
| Monday | Check all ad dashboards; pause losers, note winners | 30 min |
| Tuesday | Batch-film workshop content (1 session = week of content) | 2–3 hrs |
| Wednesday | Edit + schedule TikToks/Reels/Shorts for the week | 1.5 hrs |
| Thursday | Create + schedule Pinterest pins; write newsletter | 1 hr |
| Friday | Google search-terms cleanup; reply to comments/DMs everywhere | 45 min |
| Monthly | Reallocate budget to best ROAS channel; 2 blog posts; influencer gifting batch; review KPI dashboard | half day |

### Decision rules (so you never guess)
- An ad gets **$50 or 100 clicks** to prove itself; 2x+ target cost per purchase = pause.
- A channel gets **90 days** before you judge it (except retargeting — that should work within 30).
- When a video outperforms your median by 5x+, put paid money behind it that week.
- Raise budget only on campaigns hitting target ROAS, by max +20% per week (bigger jumps reset ad-platform learning).
