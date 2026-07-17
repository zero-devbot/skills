# Reed & Rand — wicker couch showcase site

A single-page, self-contained website showcasing handwoven rattan/wicker
couches, built to compete in the same market as sites like wickerguys.co.za.
No build step, no dependencies — upload the four files to any static host
(Cloudflare Pages, Netlify, Vercel, or cPanel hosting).

## Files

| File          | Purpose                                                        |
|---------------|----------------------------------------------------------------|
| `index.html`  | The site: catalogue, collections, craft story, FAQ, contact. Includes JSON-LD structured data (FurnitureStore, Product list, FAQPage). |
| `robots.txt`  | Allows Google + AI crawlers (GPTBot, ClaudeBot, PerplexityBot). |
| `sitemap.xml` | Sitemap for Google Search Console.                             |
| `llms.txt`    | Plain-language brand/product summary for AI search engines.    |

## Before you launch — replace the placeholders

1. **Brand name** — "Reed & Rand" is a placeholder. Search-and-replace it with
   your real trading name (also inside the three `<script type="application/ld+json">`
   blocks and `llms.txt`).
2. **`YOURDOMAIN.co.za`** — appears in `index.html` (canonical + OG tags +
   JSON-LD), `robots.txt`, `sitemap.xml`, and `llms.txt`.
3. **Phone and email** — `+27 00 000 0000` and `hello@YOURDOMAIN.co.za`.
4. **Prices** — the ZAR prices are realistic placeholders; set your real ones
   in both the visible cards and the Product JSON-LD.
5. **Photos** — the woven SVG illustrations are placeholders. Replace each
   card's `<svg>` with a real photo of *your* couch (never a competitor's
   photo — that's a copyright problem and Google can detect duplicates).
   Keep descriptive `alt` text: "Handwoven rattan three-seater couch in honey
   weave, Johannesburg" beats "couch1.jpg".

## What actually gets you to #1 (honest checklist)

On-page SEO is done in this build. Ranking #1 on Google and being cited by AI
search is earned off-page, mostly in this order of impact:

1. **Google Business Profile** — create/claim one for the workshop, add photos,
   collect reviews. For "wicker couches Johannesburg"-type searches, the map
   pack outranks everything.
2. **Google Search Console** — verify the domain, submit `sitemap.xml`, watch
   which queries you appear for.
3. **Reviews** — Google reviews and HelloPeter. AI assistants and Google both
   lean heavily on review signals for "best/where to buy" queries.
4. **Real product pages** — as the catalogue grows, give each couch its own
   URL with its own Product JSON-LD, photos, dimensions and price. One page
   per product ranks; one page for everything doesn't.
5. **Backlinks and mentions** — SA Decor & Design directory, local
   home/lifestyle blogs, supplier listings, lodge-industry directories.
   Mentions on pages AI models crawl are what get a brand named in AI answers.
6. **Unique content** — a short buying guide ("Natural vs synthetic rattan in
   the SA climate") is the kind of page AI search engines quote directly.
7. **Speed** — this page is already a single file with no external requests;
   keep it that way when adding photos (compress to WebP, lazy-load).

No site can be *guaranteed* rank #1 — anyone promising that is selling
something. The build gives you every on-page and AI-readability signal;
the checklist above is how you win the rest over ~3–6 months.
