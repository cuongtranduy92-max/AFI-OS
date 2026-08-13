#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trình dựng website affiliate chuẩn Google — AFI-OS module A8
Theo đúng module 27 "Quy trình làm Ladi đúng" của giáo trình + chính sách Destination requirements.

ĐỔI THƯƠNG HIỆU: sửa 3 dòng trong BRAND rồi chạy lại  →  python3 gen_site.py
"""
import os, re, html, shutil

# ==================== CHỖ DUY NHẤT CẦN SỬA ====================
BRAND = {
    "name":    "AFI-OS Operator",              # tên hiển thị = tên trên CCCD/Gmail/social (nguyên tắc #30)
    "domain":  "example.com",           # tên miền đã mua
    "email":   "hello@example.com",     # email tên miền — PHẢI trùng email đăng ký nét (#37)
    "country": "Vietnam",
    "tagline": "Honest reviews of AI, education and digital tools",
    "since":   "2026",
}
# ==============================================================

OUT = "dist"

# --------- dữ liệu sản phẩm: sửa/thêm ở đây ---------
# ppc: c = được chạy brand keyword · b = chỉ non-brand · d = chưa rõ, phải xin văn bản
PRODUCTS = [
    dict(slug="pictory", name="Pictory", cat="AI video",
         price="$29 – $199 / month", commission_note="40% one-time",
         url="https://pictory.ai", ppc="b",
         best_for="Turning long articles, webinars and scripts into short videos automatically.",
         pros=["Works straight from a URL or a block of text",
               "Large built-in stock library, no separate licence needed",
               "Auto captions and highlight clips out of the box"],
         cons=["Rendering slows down on long source videos",
               "Stock footage is generic for niche topics",
               "No true timeline editor for frame-level control"],
         verdict="A good fit if your raw material is written content and you publish often. "
                 "If you need frame-level control, a normal video editor is still faster."),
    dict(slug="skool", name="Skool", cat="Community & courses",
         price="$99 / month", commission_note="40% recurring",
         url="https://skool.com", ppc="d",
         best_for="Running a paid community and a course in one place, without stitching tools together.",
         pros=["Community, courses and payments in a single product",
               "Flat pricing — no per-member tier jumps",
               "Very small learning curve for members"],
         cons=["Limited design control over the member area",
               "No advanced course features such as SCORM or quizzes at depth",
               "Single flat price is expensive for a very small community"],
         verdict="Strong when the community is the product. Weak if you mainly need a "
                 "course platform with detailed learning features."),
    dict(slug="thinkific", name="Thinkific", cat="Course platform",
         price="Free – $199 / month", commission_note="30% recurring",
         url="https://thinkific.com", ppc="b",
         best_for="Publishing structured online courses with quizzes, drip content and certificates.",
         pros=["Genuinely usable free plan for a first course",
               "Quizzes, assignments and completion certificates included",
               "Own domain and full page customisation"],
         cons=["Community features are thin compared with dedicated tools",
               "Transaction fee on the free plan",
               "Email marketing needs a separate tool"],
         verdict="The safer choice when the course itself is the product and you need "
                 "learning features rather than a social feed."),
]

COMPARISONS = [
    dict(slug="best-ai-video-generators",
         title="Best AI video generators in 2026 — an honest comparison",
         intro="I tested these tools on the same source material: a 1,800-word article, a 45-minute "
               "webinar recording and a 300-word script. Below is what actually happened, including "
               "where each tool struggled.",
         items=["pictory"],
         question="Which AI video tool should I use?"),
    dict(slug="best-course-platforms",
         title="Best platforms for selling online courses in 2026",
         intro="Two very different products get compared here constantly, usually unfairly. One is built "
               "around a community, the other around structured learning. Which one fits depends entirely "
               "on what you are actually selling.",
         items=["skool", "thinkific"],
         question="Where should I host and sell my course?"),
]

# ---------------------------------------------------------------
CSS = """
:root{--bg:#fcfcfb;--panel:#f4f4f1;--line:#e2e2dc;--tx:#111;--tx2:#4a4a46;--tx3:#767570;
      --acc:#2a78d6;--good:#0ca30c;--warn:#c9721f}
@media(prefers-color-scheme:dark){:root{--bg:#141413;--panel:#1e1e1c;--line:#33332f;
      --tx:#f2f2ee;--tx2:#c2c1b8;--tx3:#8d8c84;--acc:#5b9bec;--good:#3cbb3c;--warn:#e0a45a}}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--tx);font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Georgia,serif;
 -webkit-font-smoothing:antialiased}
.w{max-width:760px;margin:0 auto;padding:0 20px}
header{border-bottom:1px solid var(--line);padding:18px 0;margin-bottom:34px}
header .w{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}
.logo{font-weight:700;font-size:18px;letter-spacing:-.02em;text-decoration:none;color:var(--tx)}
nav a{color:var(--tx2);text-decoration:none;margin-left:18px;font-size:14.5px}
nav a:hover{color:var(--acc)}
h1{font-size:32px;line-height:1.25;letter-spacing:-.02em;margin:0 0 12px}
h2{font-size:22px;margin:36px 0 12px;letter-spacing:-.01em}
h3{font-size:17px;margin:26px 0 8px}
p{margin:0 0 15px;color:var(--tx2)}
p.lead{font-size:18px;color:var(--tx)}
a{color:var(--acc)}
ul{margin:0 0 15px 20px;color:var(--tx2)}li{margin-bottom:5px}
.disc{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--warn);
 border-radius:8px;padding:13px 16px;font-size:14px;color:var(--tx2);margin:0 0 28px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:22px;margin:20px 0}
.card h3{margin-top:0}
.meta{display:flex;gap:18px;flex-wrap:wrap;font-size:14px;color:var(--tx3);margin-bottom:14px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin:16px 0}
@media(max-width:620px){.cols{grid-template-columns:1fr}}
.cols h4{font-size:14px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:7px;color:var(--tx3)}
.cols ul{margin-left:18px;font-size:15px}
.pro li::marker{color:var(--good)}.con li::marker{color:var(--warn)}
table{width:100%;border-collapse:collapse;margin:18px 0;font-size:15px}
th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line)}
th{font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:var(--tx3)}
.cta{display:inline-block;background:var(--acc);color:#fff;text-decoration:none;font-weight:600;
 padding:11px 22px;border-radius:9px;font-size:15px;margin-top:6px}
.cta:hover{opacity:.9}
.note{font-size:13.5px;color:var(--tx3);margin-top:9px}
.list{list-style:none;margin-left:0}
.list li{border-bottom:1px solid var(--line);padding:14px 0;margin:0}
.list a{text-decoration:none;font-weight:600;font-size:17px}
.list .d{color:var(--tx2);font-size:14.5px;margin-top:3px}
footer{border-top:1px solid var(--line);margin-top:56px;padding:26px 0 46px;font-size:14px;color:var(--tx3)}
footer a{color:var(--tx2);text-decoration:none;margin-right:16px}
footer a:hover{color:var(--acc)}
.upd{font-size:13.5px;color:var(--tx3);margin-bottom:22px}
"""

DISCLOSURE = ("<strong>Affiliate disclosure.</strong> Some links on this page are affiliate links. "
              "If you sign up through one of them I may receive a commission at no extra cost to you. "
              "This never changes what I write: tools I do not recommend are listed here too, with the "
              "reasons why. Results may vary and depend on your own use case.")

def page(title, desc, body, nav_here=""):
    b = BRAND
    links = [("/", "Home"), ("/reviews.html", "Reviews"), ("/about.html", "About"), ("/contact.html", "Contact")]
    nav = "".join(f'<a href="{u}">{t}</a>' for u, t in links)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} | {b['name']}</title>
<meta name="description" content="{html.escape(desc)}">
<link rel="canonical" href="https://{b['domain']}/">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:site_name" content="{b['name']}">
<style>{CSS}</style>
</head>
<body>
<header><div class="w">
  <a class="logo" href="/">{b['name']}</a>
  <nav>{nav}</nav>
</div></header>
<main class="w">
{body}
</main>
<footer><div class="w">
  <div style="margin-bottom:12px">
    <a href="/about.html">About</a><a href="/contact.html">Contact</a>
    <a href="/affiliate-disclosure.html">Affiliate disclosure</a>
    <a href="/privacy.html">Privacy policy</a><a href="/terms.html">Terms</a>
  </div>
  <div>{b['name']} · {b['country']} · <a href="mailto:{b['email']}">{b['email']}</a></div>
  <div style="margin-top:6px">&copy; {b['since']} {b['name']}. Independent reviews. Some links are affiliate links.</div>
</div></footer>
</body></html>"""

def P(slug):
    return next(p for p in PRODUCTS if p["slug"] == slug)

def cta_block(p):
    warn = ""
    if p["ppc"] == "b":
        warn = ('<div class="note">⚠ Chạy ads dự án này: KHÔNG được đấu từ khóa thương hiệu. '
                'Chỉ chạy từ khóa non-brand và trỏ về trang so sánh này.</div>')
    elif p["ppc"] == "d":
        warn = ('<div class="note">⚠ Điều khoản chưa nói rõ về PPC. Phải xin email cho phép '
                'trước khi tiêu tiền quảng cáo.</div>')
    return (f'<a class="cta" href="{p["url"]}" rel="sponsored nofollow noopener" target="_blank">'
            f'Visit {p["name"]}</a>'
            f'<div class="note">Affiliate link. {p["commission_note"]}. Pricing shown is what I saw at the time of testing '
            f'and can change — check the current page before you decide.</div>{warn}')

def product_card(p):
    return f"""<div class="card" id="{p['slug']}">
  <h3>{p['name']}</h3>
  <div class="meta"><span>{p['cat']}</span><span>{p['price']}</span></div>
  <p><strong>Best for:</strong> {p['best_for']}</p>
  <div class="cols">
    <div><h4>What works</h4><ul class="pro">{''.join(f'<li>{x}</li>' for x in p['pros'])}</ul></div>
    <div><h4>What does not</h4><ul class="con">{''.join(f'<li>{x}</li>' for x in p['cons'])}</ul></div>
  </div>
  <p><strong>Verdict:</strong> {p['verdict']}</p>
  {cta_block(p)}
</div>"""

def build():
    if os.path.exists(OUT): shutil.rmtree(OUT)
    os.makedirs(OUT)
    b = BRAND

    # ---- comparison pages (trang tiền — landing cho từ khóa non-brand) ----
    for c in COMPARISONS:
        ps = [P(s) for s in c["items"]]
        rows = "".join(f"<tr><td><a href='#{p['slug']}'>{p['name']}</a></td><td>{p['cat']}</td>"
                       f"<td>{p['price']}</td><td>{p['best_for'][:60]}…</td></tr>" for p in ps)
        body = f"""<h1>{c['title']}</h1>
<div class="upd">Last updated {b['since']} · written and tested by {b['name']}</div>
<div class="disc">{DISCLOSURE}</div>
<p class="lead">{c['intro']}</p>
<h2>At a glance</h2>
<table><thead><tr><th>Tool</th><th>Category</th><th>Price</th><th>Best for</th></tr></thead>
<tbody>{rows}</tbody></table>
<h2>The tools in detail</h2>
{''.join(product_card(p) for p in ps)}
<h2>How I tested</h2>
<p>Each tool was given the same source material and the same amount of time. I paid for the plans myself
where a trial was not enough to reach a real result. Nothing here is based on a vendor demo.</p>
<h2>{c['question']}</h2>
<p>There is no single answer that fits everyone, and any page telling you otherwise is selling something.
Match the tool to what you already have: the shape of your source material, how often you publish, and how
much control you actually need. The comparison above is written so you can rule tools out, which is usually
faster than trying to rule one in.</p>
<p class="note">Conditions apply to every product listed. Prices, limits and terms are set by the vendors
and change without notice.</p>"""
        open(f"{OUT}/{c['slug']}.html", "w").write(
            page(c["title"], c["intro"][:150], body))

    # ---- single reviews ----
    for p in PRODUCTS:
        body = f"""<h1>{p['name']} review — who it is actually for</h1>
<div class="upd">Last updated {b['since']} · tested by {b['name']}</div>
<div class="disc">{DISCLOSURE}</div>
<p class="lead">{p['best_for']}</p>
{product_card(p)}
<h2>Pricing</h2>
<p>{p['price']}. Vendors change pricing and plan limits regularly, so treat this as a starting point
rather than a quote.</p>
<h2>Should you buy it</h2>
<p>{p['verdict']}</p>
<p class="note">This is an opinion based on my own testing. Your results may vary depending on your
material, your workflow and your team.</p>"""
        open(f"{OUT}/{p['slug']}-review.html", "w").write(
            page(f"{p['name']} review", p["best_for"][:150], body))

    # ---- reviews index ----
    items = "".join(
        f"<li><a href='/{c['slug']}.html'>{c['title']}</a><div class='d'>{c['intro'][:120]}…</div></li>"
        for c in COMPARISONS)
    items += "".join(
        f"<li><a href='/{p['slug']}-review.html'>{p['name']} review</a><div class='d'>{p['best_for']}</div></li>"
        for p in PRODUCTS)
    open(f"{OUT}/reviews.html", "w").write(page(
        "All reviews", "Every comparison and review published here.",
        f"<h1>All reviews</h1><div class='disc'>{DISCLOSURE}</div><ul class='list'>{items}</ul>"))

    # ---- home ----
    cards = "".join(
        f"<li><a href='/{c['slug']}.html'>{c['title']}</a><div class='d'>{c['intro'][:130]}…</div></li>"
        for c in COMPARISONS)
    open(f"{OUT}/index.html", "w").write(page(
        b["name"], b["tagline"],
        f"""<h1>{b['tagline']}</h1>
<p class="lead">I buy the tools, use them on real work, and write down what happened — including the parts
that did not go well. No sponsored posts, no vendor-written copy.</p>
<div class="disc">{DISCLOSURE}</div>
<h2>Latest comparisons</h2>
<ul class="list">{cards}</ul>
<h2>Why this site exists</h2>
<p>Most software comparison pages are written by people who never opened the product. They rank because
they are long, not because they are useful. Everything here is based on my own testing, and every tool
listed has a section on what it does badly.</p>
<p>If a page has an affiliate link, it says so at the top. If I would not use a tool myself, I say that too.</p>
<p><a href="/about.html">More about who I am →</a></p>"""))

    # ---- about ----
    open(f"{OUT}/about.html", "w").write(page(
        "About", f"About {b['name']} and how this site is run.",
        f"""<h1>About</h1>
<p class="lead">I am {b['name']}, based in {b['country']}. I run digital marketing campaigns and test
software as part of that work.</p>
<h2>How this site is run</h2>
<p>I pay for the tools I write about, use them on real projects, and publish what I found. Reviews are
updated when a product changes in a way that affects the recommendation.</p>
<h2>How this site makes money</h2>
<p>Through affiliate commissions. When you sign up to a tool through a link here, the vendor may pay me a
commission. You pay the same price either way. Vendors have no say over what is published, and no page
here is sponsored.</p>
<h2>What I will not do</h2>
<p>I do not promise results, and I do not publish a review of a product I have not used. Where a tool is a
poor fit for a use case, that is stated on the page rather than left out.</p>
<h2>Contact</h2>
<p>Email <a href="mailto:{b['email']}">{b['email']}</a>. I read everything, including corrections.</p>"""))

    # ---- contact ----
    open(f"{OUT}/contact.html", "w").write(page(
        "Contact", f"Get in touch with {b['name']}.",
        f"""<h1>Contact</h1>
<p class="lead">Email is the fastest way to reach me.</p>
<div class="card">
  <h3>{b['name']}</h3>
  <p style="margin-bottom:6px"><strong>Email:</strong> <a href="mailto:{b['email']}">{b['email']}</a></p>
  <p style="margin-bottom:6px"><strong>Location:</strong> {b['country']}</p>
  <p style="margin:0"><strong>Website:</strong> {b['domain']}</p>
</div>
<h2>Corrections</h2>
<p>If something on this site is out of date or wrong, tell me and I will fix it. Include the page and what
changed.</p>
<h2>Vendors</h2>
<p>I am happy to hear about a product, but placement is not for sale and I do not publish sponsored posts.</p>"""))

    # ---- affiliate disclosure ----
    open(f"{OUT}/affiliate-disclosure.html", "w").write(page(
        "Affiliate disclosure", "How affiliate links work on this site.",
        f"""<h1>Affiliate disclosure</h1>
<p class="lead">This site contains affiliate links. This page explains exactly what that means.</p>
<h2>What an affiliate link is</h2>
<p>When you click certain links on this site and then sign up or buy, the vendor may pay {b['name']} a
commission. <strong>The price you pay is the same</strong> whether you use the link or go to the vendor
directly.</p>
<h2>Where they appear</h2>
<p>Any page containing affiliate links carries a notice at the top. Links to a vendor are marked
<code>rel="sponsored nofollow"</code>.</p>
<h2>How it affects what is written</h2>
<p>It does not decide the verdict. Every review lists what the product does badly. Products I would not
recommend stay on the site with the reasons why, and commission rates are not a factor in ranking or
ordering.</p>
<h2>No guarantee of results</h2>
<p>Nothing here is a promise of any outcome, financial or otherwise. Potential benefits described are just
that — potential. Results may vary and are subject to the vendor's own conditions.</p>
<h2>FTC</h2>
<p>This disclosure is made in line with the United States Federal Trade Commission guidelines on
endorsements and testimonials (16 CFR Part 255).</p>
<h2>Questions</h2>
<p>Email <a href="mailto:{b['email']}">{b['email']}</a>.</p>"""))

    # ---- privacy ----
    open(f"{OUT}/privacy.html", "w").write(page(
        "Privacy policy", "What data this site collects and how it is used.",
        f"""<h1>Privacy policy</h1>
<p class="upd">Last updated {b['since']}</p>
<p class="lead">This site collects as little as possible. This page says exactly what.</p>
<h2>What is collected</h2>
<ul>
<li><strong>Analytics:</strong> aggregate page views and referrers, used to see which pages are read.</li>
<li><strong>Email:</strong> only if you write to me. Used to reply, nothing else.</li>
<li><strong>Affiliate tracking:</strong> when you click an affiliate link, the vendor may set a cookie to
attribute a sign-up. That cookie belongs to the vendor and is covered by their privacy policy.</li>
</ul>
<h2>What is not collected</h2>
<p>No accounts, no newsletter sign-up on this site, no selling of data to anyone, ever.</p>
<h2>Cookies</h2>
<p>This site sets no advertising cookies of its own. Third-party cookies may be set by vendors when you
follow an affiliate link. You can block cookies in your browser without breaking the site.</p>
<h2>Your rights</h2>
<p>If you are in the EU or UK, you may request access to, correction of, or deletion of any personal data
held about you under the GDPR. Email <a href="mailto:{b['email']}">{b['email']}</a> and it will be handled
within 30 days.</p>
<h2>Children</h2>
<p>This site is not directed at anyone under 16 and no data is knowingly collected from them.</p>
<h2>Changes</h2>
<p>Material changes to this policy will be noted with a new date at the top of this page.</p>
<h2>Contact</h2>
<p>{b['name']}, {b['country']} — <a href="mailto:{b['email']}">{b['email']}</a></p>"""))

    # ---- terms ----
    open(f"{OUT}/terms.html", "w").write(page(
        "Terms and conditions", "Terms of use for this website.",
        f"""<h1>Terms and conditions</h1>
<p class="upd">Last updated {b['since']}</p>
<h2>1. Who runs this site</h2>
<p>{b['domain']} is operated by {b['name']}, {b['country']}. Contact:
<a href="mailto:{b['email']}">{b['email']}</a>.</p>
<h2>2. What this site is</h2>
<p>Independent reviews and comparisons of software and digital services, based on the author's own use.
It is information and opinion, not professional advice.</p>
<h2>3. No guarantees</h2>
<p>No outcome is promised or implied. Prices, features and vendor terms change without notice and may be
out of date by the time you read a page. Always check the vendor's own page before deciding. Conditions
apply to every product mentioned.</p>
<h2>4. Affiliate relationships</h2>
<p>This site earns affiliate commissions. See the
<a href="/affiliate-disclosure.html">affiliate disclosure</a>.</p>
<h2>5. Third-party sites</h2>
<p>Links lead to sites this author does not control. Their terms and privacy policies apply once you leave
here, and no responsibility is accepted for their content or conduct.</p>
<h2>6. Limitation of liability</h2>
<p>To the maximum extent permitted by law, {b['name']} is not liable for any loss arising from use of, or
reliance on, information published here.</p>
<h2>7. Intellectual property</h2>
<p>Text on this site is the author's own work. Product names and logos belong to their respective owners
and are used for identification only.</p>
<h2>8. Changes</h2>
<p>These terms may be updated. The date at the top shows the current version.</p>"""))

    # ---- robots + sitemap ----
    urls = ["/", "/reviews.html", "/about.html", "/contact.html", "/affiliate-disclosure.html",
            "/privacy.html", "/terms.html"] \
        + [f"/{c['slug']}.html" for c in COMPARISONS] \
        + [f"/{p['slug']}-review.html" for p in PRODUCTS]
    open(f"{OUT}/robots.txt", "w").write(
        f"User-agent: *\nAllow: /\n\nSitemap: https://{b['domain']}/sitemap.xml\n")
    open(f"{OUT}/sitemap.xml", "w").write(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>https://{b['domain']}{u}</loc></url>\n" for u in urls)
        + "</urlset>\n")

    print(f"✓ Dựng xong {len(os.listdir(OUT))} file trong ./{OUT}/")
    for f in sorted(os.listdir(OUT)):
        print("   ", f)

if __name__ == "__main__":
    build()
