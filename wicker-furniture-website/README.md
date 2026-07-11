# Veranda Wicker Co. — Outdoor Wicker Furniture Website

A complete static website for an outdoor wicker furniture store, built to rank in
both traditional Google search and AI answer engines (Google AI Overviews, ChatGPT,
Claude, Perplexity). No frameworks, no build step — plain HTML and one small CSS
file. Deploy it by copying the folder to any static host (GitHub Pages, Netlify,
Cloudflare Pages, S3).

> The brand, address, phone number, prices and reviews are **fictional
> placeholders**. Replace them with real data before going live — fabricated
> reviews/ratings in structured data violate Google's policies and can earn a
> manual action.

## Pages

| Page | Role | Structured data |
|---|---|---|
| `index.html` | Homepage: categories, material education, FAQ teaser | `Organization`, `WebSite` |
| `collections.html` | Catalog: 11 products in 4 categories | `BreadcrumbList`, `ItemList` of `Product` (offers, ratings) |
| `buying-guide.html` | Long-form guide: HDPE vs. PVC vs. rattan, frames, cushions, sizing, warranties | `BreadcrumbList`, `Article` |
| `care-guide.html` | Cleaning, mildew, winter storage, weave repair | `BreadcrumbList`, `HowTo` |
| `faq.html` | 12 Q&As on weather, durability, cost, shipping | `BreadcrumbList`, `FAQPage` |
| `about.html` | Story, test deck, plain-English warranty (E-E-A-T page) | `BreadcrumbList`, `AboutPage` |
| `contact.html` | Phone/email/form, hours, address | `BreadcrumbList`, `ContactPage` + `FurnitureStore` (local SEO) |

Plus: `robots.txt` (explicitly allows AI crawlers), `sitemap.xml`, and `llms.txt`
(a machine-readable site summary for LLM crawlers).

## SEO strategy baked into the site

**Classic on-page SEO**
- One intent per page, keyword-mapped: transactional queries → collections;
  "best material / X vs Y" → buying guide; "how to clean wicker" → care guide;
  question queries → FAQ.
- Unique `<title>` (primary keyword first) and meta description per page;
  canonical URLs; one `<h1>` per page with a logical heading hierarchy.
- Descriptive internal links between every page (guides link to categories and
  back), plus breadcrumb navigation with matching schema.
- Semantic HTML (`article`, `section`, `nav`, tables with `caption`/`scope`),
  ARIA labels on decorative-but-meaningful imagery.
- Performance: no JS, one ~6 KB stylesheet, inline SVG instead of image
  downloads — Core Web Vitals pass by construction.
- Open Graph + Twitter Card tags for share previews.

**AI search / answer-engine optimization (GEO)**
- Question-phrased headings with direct, self-contained, quotable answers in the
  first sentence (the pattern AI Overviews and chat assistants extract).
- Concrete, citable facts: comparison tables, price ranges, lifespan numbers,
  weight ratings, step-by-step lists.
- `FAQPage`, `HowTo`, `Product` and `Organization` JSON-LD so entities and
  answers are machine-readable.
- `robots.txt` explicitly allows AI crawlers; `llms.txt` gives LLMs a curated,
  factual site summary with per-page descriptions.
- E-E-A-T signals: a real "who we are" page, first-hand testing claims, dated
  and bylined guides, transparent warranty and return policies.

## Go-live checklist

1. **Replace the domain.** Search-and-replace `https://www.verandawicker.com`
   with your real domain across all HTML files, `sitemap.xml`, `robots.txt`
   and `llms.txt`.
2. **Replace placeholder business data**: name, address, phone, email, social
   URLs (in the JSON-LD and footers), and the fictional reviews/ratings.
3. **Add real product photography.** Replace the CSS-gradient card thumbs with
   `<img>` tags — use descriptive filenames (`espresso-wicker-sectional.jpg`),
   keyword-relevant `alt` text, `loading="lazy"`, and `width`/`height`
   attributes. Add real `og:image` files.
4. **Wire the contact form** to a form handler and connect a cart/checkout if
   selling directly (Shopify Buy Button, Snipcart, etc.).
5. **Validate structured data** with Google's Rich Results Test, then submit
   `sitemap.xml` in Google Search Console and Bing Webmaster Tools.
6. **Keep publishing.** The buying and care guides are the start of a content
   hub — add pages targeting long-tail queries ("wicker vs teak", "best patio
   furniture for coastal homes", per-collection detail pages) and update
   `sitemap.xml` and `llms.txt` as you go.
