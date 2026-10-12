const milestones = [
  ["01", "Projects", "Create a project and keep drawings, calculations, and revisions together."],
  ["02", "Drawing intake", "Upload structural PDFs and track their processing status."],
  ["03", "Verified calculations", "Answer questions from drawing evidence through the Python calculation engine."],
];

export default function Home() {
  return (
    <main className="shell">
      <nav><span className="brand">SITE<span>FLOW</span></span><span className="status">EARLY ACCESS</span></nav>
      <section className="hero">
        <p className="eyebrow">STRUCTURAL DRAWING INTELLIGENCE</p>
        <h1>Less searching.<br /><em>More building.</em></h1>
        <p className="intro">An evidence-led copilot for civil site engineers. Retrieve drawing details quickly, then calculate with deterministic IS-code rules.</p>
        <div className="actions"><button>Set up a project</button><a href="#workflow">Explore workflow ↓</a></div>
      </section>
      <section id="workflow" className="workflow">
        <p className="eyebrow">THE WORKSPACE</p>
        <div className="milestones">{milestones.map(([number, title, description]) => <article key={number}><span>{number}</span><h2>{title}</h2><p>{description}</p></article>)}</div>
      </section>
      <footer><span>Built for engineer verification, never blind automation.</span><span>v0.1.0</span></footer>
    </main>
  );
}
