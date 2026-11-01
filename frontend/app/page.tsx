"use client";

import { FormEvent, useEffect, useState } from "react";

type Link = { slug: string; short_url: string; target_url: string; status: string };

const statusCopy: Record<string, string> = {
  pending: "Checking", active: "Safe", review: "Needs review", blocked: "Blocked", disabled: "Disabled"
};

function Mark() { return <span className="mark" aria-hidden="true">↗</span>; }

function GoogleIcon() {
  return <svg aria-hidden="true" viewBox="0 0 24 24"><path fill="#4285F4" d="M21.35 12.23c0-.72-.06-1.23-.2-1.76H12v3.42h5.37a4.6 4.6 0 0 1-1.99 3.02l2.93 2.27c1.71-1.57 2.7-3.9 2.7-6.95Z"/><path fill="#34A853" d="M12 21.7c2.62 0 4.82-.87 6.43-2.36l-2.93-2.27c-.81.54-1.85.86-3.5.86-2.53 0-4.68-1.71-5.45-4.01l-3.03 2.34C5.12 19.45 8.3 21.7 12 21.7Z"/><path fill="#FBBC05" d="M6.55 13.92A5.81 5.81 0 0 1 6.24 12c0-.67.12-1.31.31-1.92L3.52 7.74A9.7 9.7 0 0 0 2.5 12c0 1.53.37 2.97 1.02 4.26l3.03-2.34Z"/><path fill="#EA4335" d="M12 6.07c1.8 0 3.42.62 4.69 1.84l3.51-3.51C16.82 1.25 14.62.3 12 .3c-3.7 0-6.88 2.25-8.48 5.44l3.03 2.34C7.32 7.78 9.47 6.07 12 6.07Z"/></svg>;
}

function Landing() {
  function showHow(event: React.MouseEvent<HTMLAnchorElement>) {
    event.preventDefault();
    document.getElementById("how")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  return <main className="landing"><nav><a className="brand" href="/"><Mark /> LiteLink</a><a className="quiet-link how-trigger" href="#how" onClick={showHow}>How it works <span aria-hidden="true">↓</span></a></nav><section className="hero"><div className="hero-copy-block"><p className="eyebrow">A SAFER URL SHORTENER</p><h1>Send the link.<br /><em>Not the worry.</em></h1><p className="hero-copy">LiteLink is a URL shortener that checks each destination for phishing before your link goes live. Share with a little more confidence.</p><a className="google-button" href="/login"><GoogleIcon /> Continue with Google</a><p className="fine-print">Google sign-in creates your private link workspace. Nothing is posted on your behalf.</p></div><aside className="link-journey" aria-label="How LiteLink checks a link"><div className="journey-heading"><span className="journey-dot" /><span>ONE LINK, THREE STEPS</span></div><div className="journey-url"><span>Destination</span><strong>store.example.com/offer</strong></div><div className="journey-line" /><div className="journey-check"><span className="scan-icon">✓</span><div><strong>Checking the destination</strong><p>Scanning before the redirect is live.</p></div></div><div className="journey-line" /><div className="journey-result"><span>Safe to share</span><strong>litelink.to/7Kp9xQ</strong><i>↗</i></div><p className="journey-foot">If we can’t verify it, visitors see a warning instead of a surprise.</p></aside></section><section className="how-panel" id="how"><div className="how-content"><div className="how-intro"><p className="eyebrow">HOW LITELINK WORKS</p><h2 style={{ fontSize: "clamp(28px, 2.8vw, 40px)", fontWeight: 530, letterSpacing: "-.045em", lineHeight: 1.08, maxWidth: "670px" }}>One clear safety check before every redirect.</h2><p>Paste a destination once. We handle the safety check before anyone is sent there—and make uncertainty clear when a link needs a closer look.</p></div><div className="principles"><article><span>01</span><h3>Shorten</h3><p>Paste a long destination and get a clean link that is easy to share.</p></article><article><span>02</span><h3>Check</h3><p>We check the destination for phishing before the redirect can go live.</p></article><article><span>03</span><h3>Share</h3><p>Safe links redirect normally. Uncertain or unsafe links are stopped first.</p></article></div></div></section></main>;
}

function Dashboard({ initialLinks }: { initialLinks: Link[] }) {
  const [links, setLinks] = useState(initialLinks);
  const [target, setTarget] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const base = typeof window === "undefined" ? "" : window.location.origin;
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    const response = await fetch("/api/links", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ target_url: target }) });
    const body = await response.json(); setBusy(false);
    if (!response.ok) return setError(typeof body.detail === "string" ? body.detail : "That URL could not be shortened.");
    setLinks((items) => [body, ...items]); setTarget("");
  }
  async function copy(slug: string) { await navigator.clipboard.writeText(`${base}/${slug}`); setCopied(slug); window.setTimeout(() => setCopied(null), 1600); }
  return <main className="app-shell"><nav><a className="brand" href="/"><Mark /> LiteLink</a><form action="/logout" method="post"><button className="sign-out">Sign out</button></form></nav><section className="dashboard-header"><div><p className="eyebrow">YOUR WORKSPACE</p><h1>Links with a<br /><em>little more care.</em></h1></div><p>Every destination is checked before it becomes a redirect.</p></section><section className="shorten-card"><form onSubmit={submit}><label htmlFor="target">Destination URL</label><div className="url-field"><span>https://</span><input id="target" value={target} onChange={(e) => setTarget(e.target.value)} type="url" placeholder="example.com/a/very/long/link" required /><button disabled={busy}>{busy ? "Creating…" : "Shorten link"}</button></div>{error && <p className="error" role="alert">{error}</p>}</form></section><section className="links-section"><div className="section-heading"><h2>Recent links</h2><span>{links.length} total</span></div>{links.length ? <div className="link-list">{links.map((link) => <article className="link-row" key={link.slug}><div className="link-main"><a href={`/${link.slug}`}>{base}/{link.slug}</a><p title={link.target_url}>{link.target_url}</p></div><span className={`status ${link.status}`}>{statusCopy[link.status] ?? link.status}</span><button className="copy-button" onClick={() => copy(link.slug)}>{copied === link.slug ? "Copied" : "Copy"}</button></article>)}</div> : <div className="empty"><span>↗</span><h3>Your first safe link awaits.</h3><p>Paste a destination above and we’ll take it from there.</p></div>}</section></main>;
}

export default function Home() {
  const [state, setState] = useState<"loading" | "signed-out" | "signed-in">("loading");
  const [links, setLinks] = useState<Link[]>([]);
  useEffect(() => { fetch("/api/links").then(async (r) => { if (r.ok) { setLinks(await r.json()); setState("signed-in"); } else setState("signed-out"); }).catch(() => setState("signed-out")); }, []);
  if (state === "loading") return <main className="loading"><Mark /></main>;
  return state === "signed-in" ? <Dashboard initialLinks={links} /> : <Landing />;
}
