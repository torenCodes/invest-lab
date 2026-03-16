# Website — Project Context

The main landing site for The Invest Lab at `theinvestlab.com`. Static HTML/CSS hosted on GoDaddy.
No build tool or framework — open `index.html` directly in a browser or any static file server.

---

## Purpose

Public-facing front door to a collection of stock research dashboards and research blog. Provides:
- Navigation to all live dashboards
- Live market snapshot preview (fetches from Movers & Shakers scan data)
- About section explaining the platform
- Research blog with full post reader

---

## Files

| File | Purpose |
|------|---------|
| `index.html` | Single-page site (hero, market snapshot, dashboards, about, blog) |
| `styles.css` | All site styles — shared by index.html and blog.html |
| `blog.html` | Dynamic blog shell — renders listing or individual posts via `?post=slug` |
| `Blog/posts.json` | Blog post manifest — source of truth for listing and post metadata |
| `Blog/*.md` | Individual blog post content in Markdown |
| `robots.txt` | Allows all crawlers; points to sitemap |
| `sitemap.xml` | XML sitemap submitted to Google Search Console |
| `images/` | Site images including logo.png, favicon.png, vr.png |
| `CONTEXT.md` | This file |

---

## Design System

| Token | Value | Usage |
|-------|-------|-------|
| `--bg` | `#f5f4f0` | Page background (warm off-white) |
| `--bg-alt` | `#fdfefb` | Alternate section background |
| `--bg-dark` | `#1a1a18` | Hero, footer |
| `--surface` | `#fdfefb` | Cards, panels |
| `--accent` | `#38bda6` | Primary brand color (teal) |
| `--accent-dark` | `#2a9b87` | Hover / pressed state |
| `--ink` | `#1a1a18` | Near-black headings |
| `--ink-2` | `#4a4a46` | Body text |
| `--ink-3` | `#8a8a82` | Muted labels |

**Fonts (Google Fonts CDN):**
- `Barlow Condensed` — display headings, logos, stat numbers
- `Barlow` — body copy and UI

**Site header background:** `#ffffff` (white) — matches all dashboards.

---

## Dashboard Cards

Four live dashboards. The Analyst card is currently hidden (`display:none`) while the dashboard is under maintenance — all HTML is intact, just invisible.

| Dashboard | URL | Status |
|-----------|-----|--------|
| Movers & Shakers | `https://invest-movers-shakers.onrender.com` | Live |
| Tried & True | `https://invest-tried-true.onrender.com` | Live |
| The Analyst | `https://invest-the-analyst.onrender.com` | Hidden |
| Insider Buying | `https://invest-insider-buying.onrender.com` | Live |

All dashboard links open in the **same tab** (no `target="_blank"`).

---

## Blog Architecture

`blog.html` is a universal dynamic shell — no separate file per post.

- **Listing view:** `blog.html` — fetches `Blog/posts.json`, renders cards
- **Post view:** `blog.html?post=slug` — fetches `Blog/slug.md`, renders with `marked.js` (CDN v9.1.6)

**Adding a new blog post:**
1. Write the post as `Blog/your-slug.md` — start with `# Title`, then `*Date*`, then `---`, then body
2. Add one entry to `Blog/posts.json` (slug, title, date, readTime, excerpt, tags)
3. Add a URL entry to `sitemap.xml`
4. Upload all three files to GoDaddy

`blog.html` JS dynamically updates `<title>`, canonical tag, and Open Graph tags per post.
BlogPosting JSON-LD is injected into `<head>` on post load.

---

## SEO

Implemented Mar 2026. Both `index.html` and `blog.html` have:
- Favicon (`images/favicon.png`)
- Canonical URL
- `robots` meta (`index, follow`)
- Open Graph tags (og:title, og:description, og:image, og:url, og:type)
- Twitter Card tags

`index.html` also has Organization JSON-LD schema.
`blog.html` injects BlogPosting JSON-LD dynamically per post.

`robots.txt` and `sitemap.xml` are at the site root. Sitemap submitted to Google Search Console on 2026-03-16.

**When adding a new post:** update `sitemap.xml` and re-upload to GoDaddy.

**Upgrade opportunity:** `og:image` currently points to favicon (small). A dedicated 1200×630px social card image would improve LinkedIn/Twitter share previews.

---

## Browser Tab Titles

All dashboards follow the format: `The Invest Lab - [Dashboard Name]`

| Page | Title |
|------|-------|
| index.html | The Invest Lab — Market Intelligence |
| blog.html | Research Blog — The Invest Lab (or post title on post view) |
| MarketDashboard | The Invest Lab - Movers & Shakers |
| TriedAndTrue | The Invest Lab - Tried & True |
| InsiderBuying | The Invest Lab - Insider Buying |
| TheAnalyst | The Invest Lab - The Analyst |

---

## Customization Notes

- **To un-hide The Analyst card:** remove `style="display:none"` from its `<a>` tag in index.html (both the dashboard card and the nav dropdown item)
- **Hero headline / body:** edit `.hero-headline` and `.hero-body` in `index.html`
- **About text:** edit the `.about-text` paragraphs in `index.html`
- **Blog index card on homepage:** the `.blog-grid` in the blog section of `index.html` — add new `.blog-card` entries as posts are published
