import { Download, Film, Check } from "lucide-react";
import { assetUrl } from "./types";
import type { Project } from "./types";

const viewLabels: Record<string, string> = {
  portrait: "Another portrait",
  side: "Side profile",
  full_body: "Full body",
  angle: "Another angle",
};

export function ReferenceViews({
  project,
  entityId,
  entityName,
  character,
  busy,
  action,
}: {
  project: Project;
  entityId: string;
  entityName: string;
  character: boolean;
  busy: boolean;
  action: (name: string, body?: object) => Promise<void>;
}) {
  const baseline = project.assets.find(
    (a) => a.role === "reference" && a.metadata.entity_id === entityId,
  );
  if (!baseline) return null;
  const current = project.reference_choices[entityId];
  const variants = project.assets.filter(
    (a) => a.role === "reference-variant" && a.metadata.entity_id === entityId,
  );
  const views = character ? ["portrait", "side", "full_body"] : ["angle"];
  const used = project.jobs
    .flatMap((j) => j.steps)
    .filter(
      (s) =>
        s.stage === "REFERENCE_VARIANT" && s.payload?.entity?.id === entityId,
    ).length;
  const disabled = busy || project.jobs.some((j) => j.state !== "SUCCEEDED");
  return (
    <details className="reference-views">
      <summary>Reference views</summary>
      <p className="muted">
        Choose a view for new shots. Completed movies and saved keyframes keep
        their pinned references. Check identity and framing before choosing.
      </p>
      <div
        className="reference-options"
        role="group"
        aria-label={`Saved references for ${entityName}`}
      >
        {[baseline, ...variants].map((asset) => {
          const selected = current?.asset_id === asset.id;
          const label =
            asset.role === "reference"
              ? "Original"
              : `${viewLabels[asset.metadata.requested_view || ""] || "View"} · ${asset.metadata.revision}`;
          return (
            <div className="reference-option" key={asset.id}>
              <a
                href={assetUrl(asset)}
                target="_blank"
                rel="noreferrer"
                aria-label={`Inspect ${label} reference for ${entityName}`}
              >
                <img
                  src={assetUrl(asset)}
                  alt={`${asset.metadata.is_mock ? "Mock" : "Local"} ${label} candidate for ${entityName}`}
                  loading="lazy"
                />
              </a>
              <span>
                {label}
                {asset.metadata.is_mock ? " · Demo" : " · Review needed"}
              </span>
              <button
                className="secondary"
                disabled={disabled || selected}
                aria-label={`${selected ? "Current" : "Use"} ${label} reference for ${entityName}`}
                onClick={() =>
                  void action(`references/${entityId}/select`, {
                    asset_id: asset.id,
                    current_asset_id: current?.asset_id || baseline.id,
                    revision: project.revision,
                  })
                }
              >
                {selected ? (
                  <>
                    <Check size={14} /> Current
                  </>
                ) : (
                  "Use for new shots"
                )}
              </button>
              <a href={assetUrl(asset, true)}>
                <Download size={13} /> Download PNG
              </a>
            </div>
          );
        })}
      </div>
      <div className="reference-buttons">
        {views.map((view) => (
          <button
            key={view}
            className="secondary"
            disabled={disabled || used >= 3}
            aria-label={`Create ${viewLabels[view]} reference for ${entityName}`}
            onClick={() =>
              void action(`references/${entityId}/variants`, {
                source_reference_id: baseline.id,
                revision: project.revision,
                idempotency_key: crypto.randomUUID(),
                view,
                seed: used + 1,
              })
            }
          >
            <Film size={14} /> {viewLabels[view]}
          </button>
        ))}
      </div>
      <small className="muted">
        {used} of 3 view requests used. Discarded requests count.{" "}
        {project.spec.backend === "demo"
          ? "Demo views are abstract mock images."
          : "View and identity quality are not automatically certified."}
      </small>
      {disabled && !busy && (
        <p className="muted">
          Finish or resolve production before changing references. Its episode
          controls are in Overview.
        </p>
      )}
    </details>
  );
}
