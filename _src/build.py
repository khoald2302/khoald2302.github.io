#!/usr/bin/env python3
"""Sinh trang Privacy Policy + Support cho mọi app từ _src/apps/*.json.

    python3 _src/build.py            # sinh tất cả app
    python3 _src/build.py chef-ai    # chỉ một app

Câu chữ dùng chung (quyền người dùng, trẻ em, cập nhật, subscription...) nằm ở
file này. Thông tin riêng từng app (thu thập gì, gửi cho ai, xin quyền gì) nằm
trong JSON. Kết quả ghi ra <slug>/privacy/index.html và <slug>/support/index.html.

Script DỪNG, không sinh trang, nếu JSON thiếu thông tin mà Apple bắt buộc —
ví dụ gửi dữ liệu cho một bên thứ ba mà không khai link chính sách của bên đó,
hoặc gửi nội dung người dùng cho AI mà không có màn consent. Đó chính là dạng
lỗi của lần bị từ chối R1 (5.1.1(i) / 5.1.2(i)).
"""
import html
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPS_DIR = ROOT / "_src" / "apps"
SITE = "https://khoald2302.github.io"
DEVELOPER = "Khoa Le Duy"
STUDIO = "KTTLab"
APPLE_CANCEL_URL = "https://support.apple.com/en-us/118428"

# device_name (tuỳ chọn): tên app hiện dưới icon / trong iOS Settings, nếu khác tên store.
REQUIRED = ["slug", "name", "tagline", "app_store_id", "contact_email",
            "last_updated", "processors", "data_sent", "stored_on_device",
            "not_collected", "permissions", "tracking", "ads", "your_controls"]


class SpecError(Exception):
    pass


# ---------------------------------------------------------------- validate

def validate(app, src):
    errs = []
    for k in REQUIRED:
        if k not in app:
            errs.append(f"thiếu trường bắt buộc '{k}'")
    if errs:
        raise SpecError(f"{src.name}: " + "; ".join(errs))

    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", app["slug"]):
        errs.append("slug chỉ được chứa a-z, 0-9 và dấu gạch ngang")
    if app["slug"] != src.stem:
        errs.append(f"slug '{app['slug']}' phải trùng tên file '{src.stem}'")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", app["contact_email"]):
        errs.append("contact_email không hợp lệ")
    try:
        date.fromisoformat(app["last_updated"])
    except ValueError:
        errs.append("last_updated phải có dạng YYYY-MM-DD")

    procs = app["processors"]
    for pid, p in procs.items():
        for k in ("name", "purpose", "policy_url", "data"):
            if not p.get(k):
                errs.append(f"processors.{pid} thiếu '{k}'")
        if p.get("policy_url") and not p["policy_url"].startswith("https://"):
            errs.append(f"processors.{pid}.policy_url phải là https://")

    content_recipients = set()
    for i, item in enumerate(app["data_sent"]):
        for k in ("what", "to", "why"):
            if not item.get(k):
                errs.append(f"data_sent[{i}] thiếu '{k}'")
        to = item.get("to")
        if to and to not in procs:
            errs.append(f"data_sent[{i}].to = '{to}' không có trong processors")
        if item.get("user_content"):
            content_recipients.add(to)
        if item.get("source") == "health" and app.get("health", {}).get("never_shared"):
            errs.append(f"data_sent[{i}] gửi dữ liệu Health đi, trong khi health.never_shared = true")

    # G1: nội dung người dùng rời máy → bắt buộc có consent trong app
    consent = app.get("ai_consent")
    if content_recipients:
        if not consent or not consent.get("screen_name") or not consent.get("withdraw"):
            errs.append("có data_sent.user_content nhưng thiếu ai_consent.screen_name / ai_consent.withdraw (G1)")
        for pid in content_recipients:
            if not procs.get(pid, {}).get("requires_consent"):
                errs.append(f"processors.{pid} nhận nội dung người dùng nên phải có requires_consent: true")

    for i, perm in enumerate(app["permissions"]):
        if not perm.get("name") or not perm.get("why"):
            errs.append(f"permissions[{i}] cần 'name' và 'why'")

    if app["tracking"] and not app.get("tracking_detail"):
        errs.append("tracking = true thì phải có tracking_detail (ATT, IDFA dùng vào đâu)")

    if app.get("subscription") and not app["subscription"].get("restore_location"):
        errs.append("subscription cần 'restore_location' (Restore Purchases nằm ở đâu trong app)")

    if errs:
        raise SpecError(f"{src.name}:\n  - " + "\n  - ".join(errs))


# ---------------------------------------------------------------- helpers

e = html.escape


def rich(text):
    """Escape rồi cho phép **đậm** và [chữ](https://link)."""
    t = e(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"\[(.+?)\]\((https://[^)\s]+)\)", r'<a href="\2" rel="noopener">\1</a>', t)
    return t


def ul(items):
    return "<ul>\n" + "\n".join(f"  <li>{rich(i)}</li>" for i in items) + "\n</ul>"


def human_date(iso):
    d = date.fromisoformat(iso)
    return d.strftime("%B %-d, %Y")


def urls(app):
    base = f"{SITE}/{app['slug']}"
    return {
        "privacy": f"{base}/privacy/",
        "support": f"{base}/support/",
        "store": f"https://apps.apple.com/app/id{app['app_store_id']}",
        "home": f"{SITE}/",
    }


CSS = """
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 3rem 1.25rem; font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         background: #fff; color: #1c1c1e; display: flex; justify-content: center; }
  main { width: 100%; max-width: 40rem; }
  h1 { font-size: 1.5rem; margin: 0 0 .25rem; }
  .sub { color: #6b6b70; margin: 0 0 2rem; }
  h2 { font-size: 1.0625rem; margin: 2.25rem 0 .75rem; }
  p, li, dd { color: #3a3a3f; }
  ul { padding-left: 1.25rem; }
  li { margin-bottom: .4rem; }
  a { color: #0a63d8; }
  .box { border: 1px solid #e3e3e6; border-radius: 12px; padding: 1rem 1.25rem; }
  .box ul { margin: .25rem 0 0; }
  table { width: 100%; border-collapse: collapse; font-size: .9375rem; margin: .5rem 0 1rem; }
  th, td { text-align: left; vertical-align: top; padding: .55rem .5rem; border-bottom: 1px solid #e3e3e6; }
  th { font-weight: 600; }
  .contact a { font-weight: 600; text-decoration: none; }
  .contact p { margin: .5rem 0 0; color: #6b6b70; font-size: .9375rem; }
  dl { margin: 0; }
  dt { font-weight: 600; margin-top: 1.125rem; }
  dd { margin: .25rem 0 0; }
  footer { margin-top: 2.75rem; padding-top: 1.25rem; border-top: 1px solid #e3e3e6; font-size: .875rem; }
  footer a { margin-right: 1rem; text-decoration: none; }
  @media (max-width: 480px) { th, td { padding: .5rem .25rem; } }
  @media (prefers-color-scheme: dark) {
    body { background: #000; color: #f2f2f7; }
    p, li, dd { color: #c7c7cc; }
    .sub, .contact p { color: #98989d; }
    a { color: #4d9bff; }
    .box, th, td, footer { border-color: #2c2c2e; }
  }
"""


def page(title, body, app):
    u = urls(app)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)} — {e(app['name'])}</title>
<!-- Sinh tự động bởi _src/build.py từ _src/apps/{e(app['slug'])}.json — đừng sửa tay. -->
<style>{CSS}</style>
</head>
<body>
<main>
{body}
  <footer>
    <a href="{u['privacy']}">Privacy Policy</a>
    <a href="{u['support']}">Support</a>
    <a href="{u['store']}">App Store</a>
    <a href="{u['home']}">Developer</a>
  </footer>
</main>
</body>
</html>
"""


# ---------------------------------------------------------------- privacy

def privacy(app):
    name, mail = e(app["name"]), e(app["contact_email"])
    procs = app["processors"]
    health = app.get("health")
    consent = app.get("ai_consent")
    sections = []

    # tóm tắt
    summary = []
    if not app["ads"] and not app["tracking"]:
        summary.append("**No ads, no tracking.** We do not show third-party ads, do not collect your advertising identifier (IDFA), and do not track you across other companies' apps or websites.")
    elif app["tracking"]:
        summary.append(f"**Tracking.** {app['tracking_detail']}")
    if consent:
        names = [procs[p]["name"] for p in procs if procs[p].get("requires_consent")]
        who = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        summary.append(f"**AI features.** Content you choose to submit is sent to {who} for processing — only after you agree on the in-app “{consent['screen_name']}” screen.")
    if health:
        summary.append("**Apple Health.** Health data stays on your device and is never sent to our AI providers, our servers, or any third party." if health.get("never_shared") else "**Apple Health.** See section 4.")
    summary.append("**No account, no server of our own.** " + app.get("storage_summary", "Your app data is stored on your device."))
    summary.append("**We never sell your data.**")
    sections.append(f'<h2>Summary</h2>\n<div class="box">{ul(summary)}</div>')

    # 1. gửi đi đâu
    rows = "\n".join(
        f"<tr><td>{rich(d['what'])}</td><td>{e(procs[d['to']]['name'])}</td><td>{rich(d['why'])}</td></tr>"
        for d in app["data_sent"])
    txt = "<p>The table below lists everything that leaves your device.</p>"
    if consent:
        txt += f"<p>Items sent to an AI provider are sent <strong>only after you agree</strong> on the in-app “{e(consent['screen_name'])}” screen. If you tap “{e(consent.get('decline_label', 'Not now'))}”, nothing is sent and the AI feature does not run.</p>"
    sections.append(f"""<h2>1. What leaves your device</h2>
{txt}
<table><thead><tr><th>Data</th><th>Sent to</th><th>Why</th></tr></thead><tbody>
{rows}
</tbody></table>""")

    # 2. lưu trên máy + không thu thập
    sections.append(f"""<h2>2. What stays on your device</h2>
{ul(app['stored_on_device'])}
<p><strong>What we do not collect:</strong></p>
{ul(app['not_collected'])}""")

    # 3. quyền hệ thống
    perms = [f"**{p['name']}** — {p['why']}" for p in app["permissions"]]
    sections.append(f"""<h2>3. Device permissions</h2>
<p>{name} asks for a permission only when you use the feature that needs it. You can decline, and you can change your choice at any time in iOS Settings.</p>
{ul(perms)}""")

    # 4. Health
    n = 4
    if health:
        body = [f"**Read:** {', '.join(health['read'])} — {health['read_why']}"]
        if health.get("write"):
            body.append(f"**Write:** {', '.join(health['write'])} — {health['write_why']}")
        never = ("<p>Health data is kept on your device by Apple Health. We <strong>never</strong> send it to our AI providers, analytics providers, our servers, advertisers or anyone else, and we never use it for advertising or data mining.</p>"
                 if health.get("never_shared") else "")
        sections.append(f"""<h2>{n}. Apple Health (HealthKit)</h2>
<p>If you connect Apple Health, the app uses it only to power in-app features:</p>
{ul(body)}
{never}
<p>You can review or revoke access at any time in <em>iOS Settings → Privacy &amp; Security → Health → {e(app.get('device_name', app['name']))}</em>.</p>""")
        n += 1

    # 5. bên thứ ba
    plist = []
    for p in procs.values():
        note = " Shared only with your in-app consent." if p.get("requires_consent") else ""
        plist.append(f"**{p['name']}** — {p['purpose']} Receives: {p['data']}.{note} Their privacy policy: [{p['policy_url'].split('//')[1].rstrip('/')}]({p['policy_url']})")
    plist.append("**Legal requirements** — we may disclose information if required by law, or as part of a merger, acquisition or sale of assets.")
    # Với app có tracking, "không chia sẻ với nhà quảng cáo" mâu thuẫn với mục Tracking
    # và với khai báo Third-Party Advertising trên App Store Connect.
    share_intro = ("We do not sell your personal information." if app["tracking"]
                   else "We do not sell your personal information and do not share it with advertisers.")
    sections.append(f"""<h2>{n}. Who we share data with</h2>
<p>{share_intro} We share data only with these service providers, each of which is bound by its own privacy policy and data-protection terms:</p>
{ul(plist)}""")
    n += 1

    # retention
    # App không có AI thì không được nhắc "AI providers"; app có quảng cáo phải nói đối tác
    # quảng cáo giữ dữ liệu theo chính sách của họ. App có AI giữ nguyên câu cũ từng chữ.
    keep = "Data stored on your device stays there until you delete it or uninstall the app. We do not run our own servers and keep no copy of the content you submit."
    if consent:
        keep += " AI providers process requests to return a result to you and retain request data only as described in their own policies."
    if app["ads"]:
        keep += " Advertising partners retain ad data only as described in their own policies."
    keep += " Analytics and crash data are kept for the provider's standard retention period."
    sections.append(f"""<h2>{n}. How long we keep it</h2>
<p>{keep}</p>""")
    n += 1

    # legal bases
    bases = []
    if consent or health:
        bases.append(("For AI features" if consent else "For Apple Health") + (" and Apple Health" if consent and health else "") + " we rely on your <strong>consent</strong>, which you can withdraw at any time.")
    if app["ads"]:
        bases.append("For personalised ads we rely on your <strong>consent</strong> (the App Tracking Transparency prompt and, where the law requires it, the ad consent form); you can withdraw it at any time. Non-personalised ads rely on our legitimate interest in keeping the app free.")
    basis = " ".join(bases)
    sections.append(f"""<h2>{n}. Legal bases</h2>
<p>{basis} For analytics and crash diagnostics we rely on our legitimate interest in keeping the app working and improving it. For purchases, we rely on performing our contract with you.</p>""")
    n += 1

    # rights
    sections.append(f"""<h2>{n}. Your choices and rights</h2>
<p>Depending on where you live (for example under the GDPR or the CCPA), you may have the right to access, correct, delete or restrict the processing of your personal information. In the app you can:</p>
{ul(app['your_controls'])}
<p>For any other request, email <a href="mailto:{mail}">{mail}</a>. We will respond within 30 days.</p>""")
    n += 1

    # tracking
    if app["tracking"]:
        trk = f"<p>{rich(app['tracking_detail'])}</p>"
    else:
        trk = "<p>We do <strong>not</strong> track you across other companies' apps or websites. We do not access your advertising identifier (IDFA), so the app never shows the App Tracking Transparency prompt.</p>"
    sections.append(f"<h2>{n}. Tracking</h2>\n{trk}")
    n += 1

    sections.append(f"""<h2>{n}. Children</h2>
<p>The app is not directed at children under 13, and we do not knowingly collect personal information from them. If you believe a child has provided us personal information, contact us and we will delete it.</p>""")
    n += 1
    sections.append(f"""<h2>{n}. Changes to this policy</h2>
<p>We may update this policy. The date at the top shows the latest version, and material changes will also be noted in the app's release notes.</p>""")
    n += 1
    sections.append(f"""<h2>{n}. Contact</h2>
<p>{e(DEVELOPER)} ({e(STUDIO)}) — <a href="mailto:{mail}">{mail}</a></p>""")

    head = f"""  <h1>Privacy Policy</h1>
  <p class="sub">{name} · Last updated {human_date(app['last_updated'])}</p>
  <p>This policy explains what information <strong>{name}</strong> (“the app”, “we”) collects, why, and who it is shared with. It is written to match exactly what the app does.</p>"""
    return page("Privacy Policy", head + "\n" + "\n\n".join(sections), app)


# ---------------------------------------------------------------- support

def support(app):
    name, mail = e(app["name"]), e(app["contact_email"])
    u = urls(app)
    faq = list(app.get("support_faq", []))
    sub = app.get("subscription")
    if sub:
        faq[:0] = [
            {"q": "I paid but the app still shows the upgrade screen.",
             "a": f"Tap **Restore Purchases** ({sub['restore_location']}). Make sure you are signed in with the same Apple Account you used to buy."},
            {"q": "How do I cancel my subscription?",
             "a": f"Subscriptions are billed by Apple, so you cancel them in your Apple Account, not in the app: open iOS **Settings**, tap your name, then **Subscriptions**. See [Apple's instructions]({APPLE_CANCEL_URL})."},
            {"q": "How do I get a refund?",
             "a": "Refunds are handled by Apple. Request one at [reportaproblem.apple.com](https://reportaproblem.apple.com)."},
        ]
    faq.append({"q": "How is my data handled?",
                "a": f"See our [Privacy Policy]({u['privacy']})."})
    items = "\n".join(f"    <dt>{rich(f['q'])}</dt>\n    <dd>{rich(f['a'])}</dd>" for f in faq)
    body = f"""  <h1>Support</h1>
  <p class="sub">{name} — {e(app['tagline'])}</p>
  <div class="box contact">
    <a href="mailto:{mail}">{mail}</a>
    <p>Email us with any question, bug report or refund enquiry. We aim to reply within 2 business days. Including your device model and iOS version helps us answer faster.</p>
  </div>
  <h2>Frequently asked questions</h2>
  <dl>
{items}
  </dl>"""
    return page("Support", body, app)


# ---------------------------------------------------------------- main

def main(only=None):
    files = sorted(APPS_DIR.glob("*.json"))
    if only:
        files = [f for f in files if f.stem in only]
        missing = set(only) - {f.stem for f in files}
        if missing:
            sys.exit(f"Không tìm thấy: {', '.join(sorted(missing))}")
    failed = False
    for src in files:
        try:
            app = json.loads(src.read_text(encoding="utf-8"))
            validate(app, src)
        except (SpecError, json.JSONDecodeError) as err:
            print(f"✗ {err}", file=sys.stderr)
            failed = True
            continue
        out = ROOT / app["slug"]
        for kind, render in (("privacy", privacy), ("support", support)):
            (out / kind).mkdir(parents=True, exist_ok=True)
            (out / kind / "index.html").write_text(render(app), encoding="utf-8")
        u = urls(app)
        print(f"✓ {app['slug']}\n    {u['privacy']}\n    {u['support']}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:] or None)
