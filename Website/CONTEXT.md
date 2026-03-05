# Website — Project Context

The main landing site for a personal stock research platform. Static HTML/CSS — no build tool or framework required. Open `index.html` directly in a browser, or serve it with any static file server.

---

## Purpose

This site is the public-facing front door to a collection of stock research tools and dashboards. It provides:
- A brief personal background and site mission
- Navigation to all dashboards
- A blog section (future)

---

## Files

| File | Purpose |
|------|---------|
| `index.html` | Single-page site (hero, dashboards, about, blog) |
| `styles.css` | All site styles |
| `CONTEXT.md` | This file |

---

## Design System

Shared with `MarketDashboard/dashboard.html` for visual consistency.

| Token | Value | Usage |
|-------|-------|-------|
| `--bg` | `#f5f4f0` | Page background (warm off-white) |
| `--surface` | `#ffffff` | Cards, panels |
| `--accent` | `#2d6a4f` | Primary brand color (forest green) |
| `--ink` | `#1a1a18` | Body text |
| `--ink-2` | `#4a4a46` | Secondary text |
| `--ink-3` | `#8a8a82` | Muted text, labels |

**Fonts (Google Fonts CDN):**
- `Instrument Serif` — headings and display text
- `DM Sans` — body copy and UI
- `DM Mono` — eyebrows, labels, monospaced elements

---

## Dashboard Links

The Market Scanner card links to `http://localhost:8080` — this requires the Flask app in `MarketDashboard/` to be running (`python app.py`). The port auto-detects starting at 8080.

As new dashboards are added, add a new `.dashboard-card` block in the `#dashboards` section of `index.html`.

---

## Customization Notes

- **Site name / logo text:** Update `.nav-logo` and `.footer-logo` in `index.html`
- **Hero headline / body:** Edit `.hero-headline` and `.hero-body` in `index.html`
- **About text:** Edit the `.about-text` paragraphs to reflect your personal background
- **Stats:** The four `.stat-card` blocks in the About section pull from MarketDashboard data — update numbers if the scanner changes
- **Blog:** Replace `.blog-coming-soon` with actual post cards when the blog is ready
