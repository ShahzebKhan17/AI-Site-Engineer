"use client";

import { ChangeEvent, useRef, useState } from "react";

type Drawing = { name: string; size: string; status: "Ready" | "Processing" };
const starterDrawings: Drawing[] = [
  { name: "Structural column schedule.pdf", size: "2.4 MB", status: "Ready" },
  { name: "Foundation layout — rev 03.pdf", size: "4.1 MB", status: "Ready" },
];

export default function Home() {
  const [drawings, setDrawings] = useState<Drawing[]>(starterDrawings);
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  function uploadDrawing(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setDrawings((current) => [{ name: file.name, size: `${(file.size / 1_000_000).toFixed(1)} MB`, status: "Processing" }, ...current]);
    event.target.value = "";
  }
  return <main className="workspace-shell">
    <aside className="sidebar">
      <a className="brand" href="#top">SITE<span>FLOW</span></a><button className="new-project">+ New project</button>
      <nav aria-label="Main navigation"><a className="nav-link active" href="#workspace"><span>▦</span> Workspace</a><a className="nav-link" href="#drawings"><span>□</span> Drawings <b>{drawings.length}</b></a><a className="nav-link" href="#calculations"><span>⌁</span> Calculations</a></nav>
      <div className="project-card"><span className="tiny-label">ACTIVE PROJECT</span><strong>G+8 Residential</strong><small>Structural package · Rev 03</small></div><p className="sidebar-note">Results require engineer verification.</p>
    </aside>
    <section className="workspace" id="workspace">
      <header className="workspace-header"><div><p className="eyebrow">PROJECT WORKSPACE</p><h1>G+8 Residential</h1></div><button className="avatar" aria-label="Account">AS</button></header>
      <section className="overview"><div><p className="eyebrow">OVERVIEW</p><h2>Good morning, Arjun.</h2><p>Pick up where you left off, or add a drawing for the next calculation.</p></div><div className="readiness"><span className="ready-dot" /><b>{drawings.filter((drawing) => drawing.status === "Ready").length} drawings ready</b><small>for evidence retrieval</small></div></section>
      <section className="content-grid">
        <div className="drawings-panel" id="drawings"><div className="section-title"><div><p className="eyebrow">DRAWING LIBRARY</p><h2>Project drawings</h2></div><button className="text-button" onClick={() => inputRef.current?.click()}>Upload drawing +</button></div><input ref={inputRef} className="visually-hidden" type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={uploadDrawing} /><div className="drawing-list">{drawings.map((drawing, index) => <article className="drawing-row" key={`${drawing.name}-${index}`}><div className="file-icon">PDF</div><div className="drawing-name"><strong>{drawing.name}</strong><small>{drawing.size} · Uploaded today</small></div><span className={`drawing-status ${drawing.status === "Ready" ? "ready" : "processing"}`}>{drawing.status}</span><button className="more-button" aria-label={`More options for ${drawing.name}`}>•••</button></article>)}</div></div>
        <aside className="ask-panel" id="calculations"><p className="eyebrow">ASK SITEFLOW</p><h2>Start with a drawing question.</h2><p>We’ll find drawing evidence, then send validated inputs to the calculation engine.</p><div className="question-box"><textarea value={query} onChange={(event) => setQuery(event.target.value)} placeholder="e.g. What is the cutting length for C12 main bars?" /><button disabled={!query.trim()} aria-label="Submit question">↑</button></div><small>Calculation outputs are for engineer review.</small></aside>
      </section>
    </section>
  </main>;
}
