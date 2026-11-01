"use client";

import { useEffect, useState } from "react";

type PublicLink = { slug: string; status: "pending" | "active" | "review" | "blocked"; target_url?: string; reasons: string[] };
const Mark = () => <span className="mark" aria-hidden="true">↗</span>;

export default function VisitorPage({ params }: { params: Promise<{ slug: string }> }) {
  const [slug, setSlug] = useState(""); const [link, setLink] = useState<PublicLink | null>(null); const [missing, setMissing] = useState(false);
  useEffect(() => { params.then(({ slug }) => setSlug(slug)); }, [params]);
  useEffect(() => { if (!slug) return; let timer: number | undefined; const load = async () => { const response = await fetch(`/api/public/links/${encodeURIComponent(slug)}`); if (response.status === 404) return setMissing(true); if (!response.ok) return; const data: PublicLink = await response.json(); setLink(data); if (data.status === "active") window.location.assign(`/go/${encodeURIComponent(slug)}`); if (data.status === "pending") timer = window.setTimeout(load, 3000); }; load(); return () => window.clearTimeout(timer); }, [slug]);
  if (missing) return <State><p className="eyebrow">404</p><h1>This link<br /><em>isn’t here.</em></h1><p>It may have expired, been disabled, or never existed.</p><a className="text-button" href="/">Go to LiteLink</a></State>;
  if (!link || link.status === "pending") return <State><div className="scanner"><i /><i /><i /></div><p className="eyebrow">SAFETY CHECK IN PROGRESS</p><h1>One small<br /><em>moment.</em></h1><p>We’re checking this destination before we send you on.</p></State>;
  if (link.status === "review") return <State tone="review"><p className="eyebrow">PAUSE BEFORE CONTINUING</p><h1>Take a<br /><em>closer look.</em></h1><p>We couldn’t confirm this link is safe. Continue only if you trust the sender.</p><code>{link.target_url}</code><a className="text-button" href={link.target_url} rel="noopener noreferrer nofollow">Continue anyway <span>→</span></a></State>;
  return <State tone="blocked"><p className="eyebrow">LINK BLOCKED</p><h1>We stopped<br /><em>this one.</em></h1><p>This destination showed signs that it could be unsafe.</p>{link.reasons.length > 0 && <ul>{link.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>}<a className="text-button" href="/">Go to LiteLink</a></State>;
}

function State({ children, tone }: { children: React.ReactNode; tone?: string }) { return <main className={`visitor ${tone ?? ""}`}><a className="brand" href="/"><Mark /> LiteLink</a><section>{children}</section><p className="visitor-foot">Links, checked before they’re shared.</p></main>; }
