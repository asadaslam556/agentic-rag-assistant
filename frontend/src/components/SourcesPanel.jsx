import { useEffect, useState } from "react";
import { pageImageSrc } from "../api.js";

const TYPE_LABELS = {
  vector: "document",
  page: "page image",
  graph: "graph",
  web: "web",
  structured: "catalog",
  sql: "database",
  calculation: "calculation",
};

// With an API token the image has to be fetched with the header, see pageImageSrc.
function PageThumb({ url, title }) {
  const [src, setSrc] = useState("");
  useEffect(() => {
    let objectUrl = "";
    let live = true;
    pageImageSrc(url)
      .then((value) => {
        if (value !== url) objectUrl = value;
        if (live) setSrc(value);
      })
      .catch(() => live && setSrc(""));
    return () => {
      live = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url]);
  if (!src) return null;
  return (
    <a href={src} target="_blank" rel="noreferrer" className="page-thumb">
      <img src={src} alt={`Page image for ${title}`} loading="lazy" />
    </a>
  );
}

function SourceCard({ marker, item, anchorPrefix }) {
  if (!item) return null;
  return (
    <article className="source" id={`${anchorPrefix}-source-${marker}`}>
      <div className="source-head">
        <span className="badge">{marker}</span>
        <span className="source-title">{item.title}</span>
        <span className={`type t-${item.source_type}`}>{TYPE_LABELS[item.source_type] || item.source_type}</span>
      </div>
      {item.image_url && <PageThumb url={item.image_url} title={item.title} />}
      <p className="source-text">{item.text}</p>
      {item.url ? (
        <a className="ref" href={item.url} target="_blank" rel="noreferrer">
          {item.url}
        </a>
      ) : (
        <span className="ref">{item.source_ref}</span>
      )}
    </article>
  );
}

export default function SourcesPanel({ citations, evidence, anchorPrefix }) {
  if (!evidence.length) return null;
  const citedMarkers = new Set(citations.map((citation) => citation.marker));
  const uncited = evidence
    .map((item, index) => ({ item, marker: index + 1 }))
    .filter(({ marker }) => !citedMarkers.has(marker));

  return (
    <section className="card sources">
      <h2 className="card-label">Sources</h2>
      {citations.length === 0 && <p className="muted small">The answer doesn't cite any sources.</p>}
      {citations.map((citation) => (
        <SourceCard
          key={citation.marker}
          marker={citation.marker}
          item={evidence[citation.marker - 1]}
          anchorPrefix={anchorPrefix}
        />
      ))}
      {uncited.length > 0 && (
        <details className="more">
          <summary>
            {uncited.length} more retrieved passage{uncited.length === 1 ? "" : "s"} the answer didn't use
          </summary>
          {uncited.map(({ item, marker }) => (
            <SourceCard key={marker} marker={marker} item={item} anchorPrefix={anchorPrefix} />
          ))}
        </details>
      )}
    </section>
  );
}
