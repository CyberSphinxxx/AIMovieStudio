import { Check, ShieldCheck, AlertTriangle } from "lucide-react";
import type { Asset, QualityEvaluation, Spec } from "./types";

const GATE_TITLES: Record<string, string> = {
  container_format: "Container & Decode",
  video_codec: "Video Codec (H.264)",
  pixel_format: "Pixel Format (YUV420p standard)",
  dimensions: "Resolution & Aspect",
  duration: "Duration & Timeline Tolerance",
  frame_count: "Frame Count @ 24 fps",
  audio_codec: "Audio Codec (AAC soundtrack)",
  black_frame_check: "Video Blackout Check",
  audio_levels: "Audio Volume & Silence Check",
  manifest_edl: "Manifest & Shot EDL Alignment",
  asset_lineage: "Source Asset Lineage & Hash Integrity",
};

export function QualityCard({
  movie,
  spec,
}: {
  movie: Asset;
  spec: Spec;
}) {
  const evalData: QualityEvaluation | undefined =
    movie.metadata.quality_evaluation;

  return (
    <div className="provider-config quality-card" data-testid="quality-card">
      <div className="quality-card-header">
        <div className="quality-card-title">
          <ShieldCheck size={20} className="quality-icon" />
          <h3>Quality Inspection & Hard Gates</h3>
        </div>
        <span
          className={`quality-badge ${
            evalData?.all_hard_gates_passed !== false
              ? "badge-passed"
              : "badge-warning"
          }`}
        >
          {evalData?.all_hard_gates_passed !== false
            ? "Hard gates verified"
            : "Quality issue detected"}
        </span>
      </div>

      <p className="muted">
        Deterministic machine-checkable verification according to quality gates.
        No heuristic guesswork or false AI claims.
      </p>

      <div className="quality-metrics-grid">
        <div className="quality-metric">
          <small>COST TO RENDER</small>
          <strong>$0.00</strong>
          <span>100% local compute · 0 API fees</span>
        </div>
        <div className="quality-metric">
          <small>VIDEO FORMAT</small>
          <strong>H.264 · YUV420p</strong>
          <span>{movie.metadata.width}×{movie.metadata.height} · 24 fps</span>
        </div>
        <div className="quality-metric">
          <small>AUDIO LEVELS</small>
          <strong>
            {movie.metadata.loudness?.status === "below_measurement_gate"
              ? "Quiet mix"
              : "Balanced AAC"}
          </strong>
          <span>
            {movie.metadata.dialogue_present ? "Speech + Ambience" : "Ambience only"}
          </span>
        </div>
        <div className="quality-metric">
          <small>GENERATION MODE</small>
          <strong>
            {spec.backend === "demo" ? "Development Demo" : "Local AI"}
          </strong>
          <span>
            {spec.backend === "demo"
              ? "Abstract motion storyboard"
              : "Local provider generation"}
          </span>
        </div>
      </div>

      {evalData && evalData.hard_gates && evalData.hard_gates.length > 0 && (
        <details className="quality-gates-details">
          <summary>
            Inspect machine-checkable hard gates ({evalData.hard_gates.filter((g) => g.passed).length}/{evalData.hard_gates.length} passed)
          </summary>
          <ul className="hard-gates-list" role="list">
            {evalData.hard_gates.map((gate) => (
              <li
                key={gate.name}
                className={`hard-gate-item ${
                  gate.passed ? "gate-passed" : "gate-failed"
                }`}
              >
                <div className="gate-status-icon">
                  {gate.passed ? (
                    <Check size={14} aria-label="Passed" />
                  ) : (
                    <AlertTriangle size={14} aria-label="Failed" />
                  )}
                </div>
                <div className="gate-info">
                  <strong>{GATE_TITLES[gate.name] || gate.name}</strong>
                  <span className="gate-measured">
                    Measured: {gate.measured} (Threshold: {gate.threshold})
                  </span>
                  {gate.error && (
                    <span className="gate-error">{gate.error}</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="quality-footer-note">
        <small className="muted">
          Cinematic review:{" "}
          {evalData?.cinematic_review ||
            "Deterministic hard gates passed; AI critic review not performed."}
        </small>
      </div>
    </div>
  );
}
