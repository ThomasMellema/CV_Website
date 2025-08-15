from playwright.sync_api import sync_playwright
from pathlib import Path
import shutil
from urllib.parse import urlparse
from pypdf import PdfWriter, PdfReader

URLS = [
    "https://thomasmellema.github.io/CV_Website/index.html",
    "https://thomasmellema.github.io/CV_Website/about.html",
    "https://thomasmellema.github.io/CV_Website/projects.html",
    "https://thomasmellema.github.io/CV_Website/contact.html",
]

OUTPUT_PDF = "cv.pdf"
TMP_DIR = Path("tmp_pdfs")
KEEP_TMP = False
FORCE_EACH_CARD_ON_NEW_PAGE = False  # True => elke card op nieuwe pagina
# Verwijder specifieke pagina's (1-based) uit de samengevoegde PDF
EXCLUDE_PAGE_NUMBERS = [3]

PRINT_CSS = f"""
@page {{ size: A4; margin: 12mm; }}

@media print {{
  header, footer {{ display:none !important; }}

  /* Blokken niet-splitsen */
  .no-split {{
    break-inside: avoid-page !important;
    page-break-inside: avoid !important;
  }}

  /* Optioneel: elke card op nieuwe pagina */
  .page-start {{ break-before: page !important; }}

  /* Consistente print */
  *, *::before, *::after {{
    text-shadow: none !important;
    filter: none !important;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
    box-shadow: none !important;
  }}

  html, body {{ background: #ffffff !important; }}
  body {{ margin: 0 !important; }}
}}
"""

# Alleen op about.html: kop/subtitel verbergen
ABOUT_HIDE_CSS = """
@media print {
  section.py-20 > .max-w-6xl > .text-center.mb-16 { display: none !important; }
}
"""

# DOM-tweaks:
# 1) markeer relevante blokken als no-split
# 2) verwijder *alleen* lege grijze/witte achtergronden (bg-gray-50/bg-gray-100/bg-white)
MARK_CARDS_JS = f"""
(() => {{
  const addNoSplit = (el) => {{
    el.classList.add('no-split');
    {"el.classList.add('page-start');" if FORCE_EACH_CARD_ON_NEW_PAGE else ""}
  }};

  // Kaarten/timelines/no-split
  const cardSelectors = [
    '.space-y-12 > div',                         // grote kaarten
    '.space-y-8 > div',                          // timeline cards
    'div.mt-6.p-4.bg-white.rounded-lg.border',   // Robodam sub-card
    'div[class*="border-l-4"][class*="rounded-lg"]'  // generiek kaartpatroon
  ];
  document.querySelectorAll(cardSelectors.join(',')).forEach(addNoSplit);

  // Grid-items (bullets/tech) intact houden
  document.querySelectorAll('.grid > *').forEach(el => el.classList.add('no-split'));

  // Helper: echt leeg? (geen zichtbare tekst en geen media)
  const isVisuallyEmpty = (el) => {{
    const hasText = (el.innerText || '').trim().length > 0;  // innerText = zichtbare tekst
    if (hasText) return false;
    if (el.querySelector('img, svg, video, canvas, iframe')) return false;
    return true;
  }};

  // Strip neutrale backgrounds; laat badges/cta met accentkleuren met rust
  const NEUTRAL_BG_SELECTOR = [
    '.bg-white',
    '.bg-gray-50', '.bg-gray-100', '.bg-gray-200',
    '.bg-slate-50', '.bg-slate-100',
    '.bg-neutral-50', '.bg-neutral-100',
    '.bg-zinc-50', '.bg-zinc-100',
    '.bg-stone-50', '.bg-stone-100',
    // gradient wrappers
    '[class*="bg-gradient-"]', '[class*="from-gray-"]', '[class*="to-gray-"]', '[class*="via-gray-"]',
    '[class*="from-slate-"]', '[class*="to-slate-"]', '[class*="via-slate-"]'
  ].join(', ');

  const isNearWhiteBackground = (el) => {{
    const cs = window.getComputedStyle(el);
    const bg = cs.backgroundColor;
    const m = bg && bg.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d\.]+))?\)/);
    if (!m) return false;
    const r = parseInt(m[1], 10);
    const g = parseInt(m[2], 10);
    const b = parseInt(m[3], 10);
    const a = m[4] === undefined ? 1 : parseFloat(m[4]);
    if (a < 0.2) return false; // vrijwel transparant
    const nearWhite = (r >= 235 && g >= 235 && b >= 235) || Math.max(r, g, b) >= 245;
    return nearWhite;
  }};

  const stripIfEmptyAndNeutral = (el) => {{
    if (!isVisuallyEmpty(el)) return;

    const hasAnyVisibleContent = Array.from(el.querySelectorAll('*')).some(child => {{
      const cs = window.getComputedStyle(child);
      const visible = cs.display !== 'none' && cs.visibility !== 'hidden';
      const hasSize = (child.offsetWidth > 0 && child.offsetHeight > 0);
      const txt = (child.innerText || '').trim().length > 0;
      const media = child.matches('img, svg, video, canvas, iframe');
      return visible && hasSize && (txt || media);
    }});
    if (hasAnyVisibleContent) return;

    const cs = window.getComputedStyle(el);
    const hasGradient = cs.backgroundImage && cs.backgroundImage !== 'none';
    const isNeutral = isNearWhiteBackground(el) || hasGradient || el.matches(NEUTRAL_BG_SELECTOR);
    if (!isNeutral) return;

    // echt leeg + neutraal -> verwijder achtergrond en collapse de box
    el.style.background = 'none';
    el.style.backgroundImage = 'none';
    el.style.boxShadow = 'none';
    el.style.border = '0';
    el.style.padding = '0';
    el.style.minHeight = '0';
    el.classList.remove(
      'bg-white', 'bg-gray-50', 'bg-gray-100', 'bg-gray-200',
      'bg-slate-50', 'bg-slate-100',
      'bg-neutral-50', 'bg-neutral-100',
      'bg-zinc-50', 'bg-zinc-100',
      'bg-stone-50', 'bg-stone-100'
    );
  }};

  // 1) Expliciet bekende neutrale/gradient klassen
  document.querySelectorAll(NEUTRAL_BG_SELECTOR).forEach(stripIfEmptyAndNeutral);

  // 2) Fallback: elk element met near-white bg of gradient en verder leeg
  document.querySelectorAll('*').forEach(el => {{
    const cs = window.getComputedStyle(el);
    const hasBgColor = cs.backgroundColor && cs.backgroundColor !== 'rgba(0, 0, 0, 0)' && cs.backgroundColor !== 'transparent';
    const hasGradient = cs.backgroundImage && cs.backgroundImage !== 'none';
    if (!hasBgColor && !hasGradient) return;
    stripIfEmptyAndNeutral(el);
  }});
}})();
"""

def prepare_tmp_dir():
    if TMP_DIR.exists():
        shutil.rmtree(TMP_DIR, ignore_errors=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)

def inject_per_url_customizations(page, url: str):
    path = urlparse(url).path.lower()
    if path.endswith("/about.html"):
        page.add_style_tag(content=ABOUT_HIDE_CSS)

def urls_to_pdf():
    prepare_tmp_dir()
    collected = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        page = context.new_page()

        for i, url in enumerate(URLS):
            print(f"Verwerken: {url}")
            page.goto(url, wait_until="networkidle", timeout=45000)
            page.emulate_media(media="print")

            # Inject print CSS + DOM-tweaks
            page.add_style_tag(content=PRINT_CSS)
            page.evaluate(MARK_CARDS_JS)
            inject_per_url_customizations(page, url)

            # Schrijf PDF
            filename = TMP_DIR / f"{i:03d}.pdf"
            page.pdf(
                path=str(filename),
                format="A4",
                prefer_css_page_size=True,
                print_background=True,
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
                scale=0.98,
            )
            collected.append(filename)

        browser.close()

    write_merged_pdf(collected, OUTPUT_PDF, set(EXCLUDE_PAGE_NUMBERS))

    if not KEEP_TMP:
        shutil.rmtree(TMP_DIR, ignore_errors=True)

    return OUTPUT_PDF, len(collected)

def write_merged_pdf(collected: list[Path], output_pdf: str, exclude_pages: set[int]) -> None:
    # Samenvoegen (met optioneel uitsluiten van specifieke pagina's)
    writer = PdfWriter()
    fhs = []
    try:
        page_counter = 0  # 1-based teller voor de uiteindelijke PDF
        for f in collected:
            fh = open(f, "rb"); fhs.append(fh)
            reader = PdfReader(fh)
            for pg in reader.pages:
                page_counter += 1
                if page_counter in exclude_pages:
                    continue
                writer.add_page(pg)
        with open(output_pdf, "wb") as out:
            writer.write(out)
    finally:
        for fh in fhs:
            try:
                fh.close()
            except:
                pass

if __name__ == "__main__":
    out, n = urls_to_pdf()
    print(f"Gereed: {out} ({n} pagina-PDF's samengevoegd)")
