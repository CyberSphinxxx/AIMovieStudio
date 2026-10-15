import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronRight,
  Clapperboard,
  Download,
  Film,
  FolderOpen,
  House,
  LoaderCircle,
  Pause,
  Play,
  Plus,
  Settings2,
  ShieldCheck,
  Square,
  WandSparkles,
} from "lucide-react";
import { api, assetUrl, stageLabel, stepLabel } from "./types";
import type { Project, Recent, Spec } from "./types";
import { DraftEditor } from "./DraftEditor";
import { BackupRestore } from "./BackupRestore";
import { ReferenceViews } from "./ReferenceViews";
import { ShowInFolder } from "./ShowInFolder";

const EXAMPLE =
  "A lighthouse keeper receives a message from a ship that vanished thirty years ago. Tonight, the light begins to answer.";
const modes = [
  ["clip", "Clip", "5–30 seconds"],
  ["drama", "Drama", "30–180 seconds"],
  ["film", "Film", "1–10 minutes"],
  ["series", "Series", "A complete season"],
] as const;
function navigate(path: string) {
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
  window.scrollTo(0, 0);
}

export function App() {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const update = () => setPath(window.location.pathname);
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, []);
  const studio = path.startsWith("/project/");
  return (
    <div className="app">
      <a href="#main" className="skip">
        Skip to workspace
      </a>
      <aside className="sidebar" aria-label="Studio navigation">
        <a
          className="brand"
          href="/"
          onClick={(e) => {
            e.preventDefault();
            navigate("/");
          }}
          aria-label="AI Movie Studio home"
        >
          <Clapperboard size={26} />
          <span>
            Movie<span className="brand-sub">STUDIO</span>
          </span>
        </a>
        <nav aria-label="Main navigation">
          <Nav
            icon={<House size={19} />}
            text="Create"
            path="/"
            current={path}
          />
          <Nav
            icon={<FolderOpen size={19} />}
            text="Projects"
            path="/projects"
            current={path}
          />
          <Nav
            icon={<Settings2 size={19} />}
            text="Settings"
            path="/settings"
            current={path}
          />
        </nav>
        <div className="sidebar-note">
          <ShieldCheck size={19} />
          <span>
            Made here.
            <br />
            <small>Private by default.</small>
          </span>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span>
            {studio
              ? "THE CUTTING ROOM"
              : path === "/settings"
                ? "YOUR LOCAL STUDIO"
                : "YOUR DIRECTOR’S CHAIR"}
          </span>
          <span className="local">
            <i /> Local workspace
          </span>
        </header>
        <main id="main" key={path} tabIndex={-1}>
          {path === "/settings" ? (
            <Settings />
          ) : path === "/projects" ? (
            <Projects />
          ) : studio ? (
            <Studio id={path.split("/")[2]} />
          ) : (
            <Home />
          )}
        </main>
        <footer>
          <span>AI Movie Studio</span>
          <span>A little imagination. A world of possibility.</span>
        </footer>
      </div>
    </div>
  );
}
function Nav({
  icon,
  text,
  path,
  current,
}: {
  icon: React.ReactNode;
  text: string;
  path: string;
  current: string;
}) {
  return (
    <a
      className={`nav-item ${path === current ? "selected" : ""}`}
      aria-current={path === current ? "page" : undefined}
      aria-label={text}
      href={path}
      onClick={(e) => {
        e.preventDefault();
        navigate(path);
      }}
    >
      {icon}
      <span>{text}</span>
    </a>
  );
}
function ErrorMessage({ message }: { message: string }) {
  return message ? (
    <div role="alert" className="error">
      {message}
    </div>
  ) : null;
}
function DemoNotice() {
  return (
    <div className="demo-notice">
      <Film size={17} />
      <span>
        <strong>Development demo</strong> · Story templates and abstract
        footage. Not AI generated.
      </span>
    </div>
  );
}

function Home() {
  const [idea, setIdea] = useState("");
  const [kind, setKind] = useState<Spec["kind"]>("clip");
  const [orientation, setOrientation] =
    useState<Spec["orientation"]>("portrait");
  const [seconds, setSeconds] = useState(30);
  const [episodes, setEpisodes] = useState(6);
  const [backend, setBackend] = useState<Spec["backend"]>("demo");
  const [prewrite, setPrewrite] = useState(false);
  const [reviewStory, setReviewStory] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [recent, setRecent] = useState<Recent[]>([]);
  const key = useRef(crypto.randomUUID());
  const submittedSpec = useRef("");
  useEffect(() => {
    api<Recent[]>("/projects")
      .then(setRecent)
      .catch((e) => setError(e.message));
  }, []);
  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    const signature = JSON.stringify({
      idea,
      kind,
      orientation,
      seconds,
      episodes,
      backend,
      prewrite,
      reviewStory,
    });
    if (signature !== submittedSpec.current) {
      key.current = crypto.randomUUID();
      submittedSpec.current = signature;
    }
    try {
      const project = await api<Project>("/projects", {
        method: "POST",
        body: JSON.stringify({
          idea,
          kind,
          orientation,
          target_seconds: seconds,
          episodes,
          backend,
          prewrite_season: kind === "series" && prewrite,
          review_story: reviewStory,
          style: "Cinematic realism",
          language: "English",
          idempotency_key: key.current,
        }),
      });
      navigate(`/project/${project.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create movie");
      setBusy(false);
    }
  }
  const changeMode = (next: Spec["kind"]) => {
    setKind(next);
    setSeconds(
      next === "clip" ? 30 : next === "drama" ? 60 : next === "film" ? 120 : 30,
    );
    key.current = crypto.randomUUID();
  };
  return (
    <>
      <div className="home-intro">
        <div>
          <p className="eyebrow">FROM A SPARK TO THE SCREEN</p>
          <h1>
            Every movie starts
            <br />
            with <em>one idea.</em>
          </h1>
          <p className="lead">
            You bring the imagination. Your studio brings it together.
          </p>
        </div>
        <div className="intro-mark" aria-hidden="true">
          <span>01</span>
          <div />
          <span>STORY · SOUND · SCREEN</span>
        </div>
      </div>
      <form onSubmit={create} className="composer">
        <div className="composer-heading">
          <label htmlFor="idea">What’s your movie about?</label>
          <button
            type="button"
            className="text-button"
            onClick={() => {
              setIdea(EXAMPLE);
              key.current = crypto.randomUUID();
              document.getElementById("idea")?.focus();
            }}
          >
            <WandSparkles size={15} /> Try an idea
          </button>
        </div>
        <textarea
          id="idea"
          name="idea"
          value={idea}
          onChange={(e) => {
            setIdea(e.target.value);
            key.current = crypto.randomUUID();
          }}
          minLength={8}
          maxLength={8000}
          required
          placeholder="A lost astronaut discovers that the planet is remembering her childhood…"
          rows={3}
        />
        <div className="creative-controls">
          <fieldset>
            <legend>MAKE IT A</legend>
            <div className="modes">
              {modes.map(([value, label, hint]) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={kind === value}
                  className={kind === value ? "active" : ""}
                  onClick={() => changeMode(value)}
                >
                  <span>{label}</span>
                  <small>{hint}</small>
                </button>
              ))}
            </div>
          </fieldset>
          <div className="format-row">
            <fieldset>
              <legend>FRAME</legend>
              <div className="segmented">
                {(["portrait", "landscape", "square"] as const).map((value) => (
                  <button
                    type="button"
                    aria-pressed={orientation === value}
                    className={orientation === value ? "active" : ""}
                    onClick={() => setOrientation(value)}
                    key={value}
                  >
                    <span className={`ratio ${value}`} />
                    {value}
                  </button>
                ))}
              </div>
            </fieldset>
            <label className="duration">
              {kind === "series" ? "SECONDS / EPISODE" : "SECONDS"}
              <input
                type="number"
                value={seconds}
                min={5}
                max={kind === "clip" ? 30 : 600}
                onChange={(e) => setSeconds(Number(e.target.value))}
                required
              />
            </label>
            {kind === "series" && (
              <label className="duration">
                EPISODES
                <input
                  type="number"
                  value={episodes}
                  min={1}
                  max={24}
                  onChange={(e) => setEpisodes(Number(e.target.value))}
                  required
                />
              </label>
            )}
          </div>
        </div>
        <div className="composer-bottom">
          <button
            type="button"
            className="text-button"
            aria-expanded={advanced}
            onClick={() => setAdvanced(!advanced)}
          >
            <Settings2 size={16} /> Creative settings
          </button>
          <button className="primary" disabled={busy || idea.trim().length < 8}>
            {busy ? (
              <LoaderCircle className="spin" size={18} />
            ) : (
              <Clapperboard size={18} />
            )}{" "}
            {busy ? "Saving your idea…" : "Create movie"}
            <ArrowRight size={17} />
          </button>
        </div>
        {advanced && (
          <div className="advanced">
            <label>
              Production backend
              <select
                value={backend}
                onChange={(e) => setBackend(e.target.value as Spec["backend"])}
              >
                <option value="demo">
                  Development demo · no models required
                </option>
                <option value="local">
                  Real local · requires installed providers
                </option>
              </select>
            </label>
            {kind === "series" && (
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={prewrite}
                  onChange={(e) => setPrewrite(e.target.checked)}
                />
                Prewrite every episode before making footage
              </label>
            )}
            <label className="check-label">
              <input
                type="checkbox"
                checked={reviewStory}
                onChange={(e) => setReviewStory(e.target.checked)}
              />
              Review the screenplay before making footage
            </label>
            <p>
              English · cinematic style · 24 fps draft export. Real local
              creation saves your story and reports missing providers; it never
              substitutes demo footage.
            </p>
          </div>
        )}
        <ErrorMessage message={error} />
      </form>
      <DemoNotice />
      <section className="journey" aria-label="Production stages">
        {[
          "Develop the story",
          "Build the world",
          "Direct every shot",
          "Bring it together",
        ].map((s, i) => (
          <div key={s}>
            <span>0{i + 1}</span>
            <p>{s}</p>
            {i < 3 && <ChevronRight size={17} />}
          </div>
        ))}
      </section>
      <section className="recent">
        <div className="section-heading">
          <h2>
            {recent.length ? "Your recent stories" : "A studio that remembers"}
          </h2>
          {recent.length > 0 && (
            <button
              className="text-button"
              onClick={() => navigate("/projects")}
            >
              All projects <ArrowRight size={15} />
            </button>
          )}
        </div>
        {recent.length ? (
          <ProjectCards projects={recent.slice(0, 3)} />
        ) : (
          <div className="empty-home">
            <div className="film-lines" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
            <p>
              Your first story belongs here.
              <br />
              <small>
                Scripts, characters, shots and episode continuity stay with your
                project.
              </small>
            </p>
          </div>
        )}
      </section>
    </>
  );
}
function ProjectCards({ projects }: { projects: Recent[] }) {
  return (
    <div className="project-grid">
      {projects.map((p) => (
        <button
          key={p.id}
          className="project-card"
          onClick={() => navigate(`/project/${p.id}`)}
        >
          <div className={`project-art ${p.spec.orientation}`}>
            <Film size={30} />
            <small>
              {p.spec.backend === "demo"
                ? "DEMO STORYBOARD"
                : "LOCAL PRODUCTION"}
            </small>
          </div>
          <div className="project-card-body">
            <small>
              {p.spec.kind.toUpperCase()} · {p.spec.target_seconds}s ·{" "}
              {p.spec.orientation}
            </small>
            <h3>{p.title}</h3>
            <span className="status">
              {stageLabel(p.status)} <ArrowRight size={15} />
            </span>
          </div>
        </button>
      ))}
    </div>
  );
}
function Projects() {
  const [projects, setProjects] = useState<Recent[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    api<Recent[]>("/projects")
      .then(setProjects)
      .catch((e) => setError(e.message));
  }, []);
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">YOUR FILM LIBRARY</p>
          <h1>Stories in the making.</h1>
        </div>
        <button className="primary" onClick={() => navigate("/")}>
          <Plus size={18} /> New movie
        </button>
      </div>
      <label className="search">
        Find a project
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search your stories"
        />
      </label>
      <ErrorMessage message={error} />
      <ProjectCards
        projects={projects.filter((p) =>
          p.title.toLowerCase().includes(query.toLowerCase()),
        )}
      />
      {!projects.length && !error && (
        <p className="empty">Your library is waiting for its first movie.</p>
      )}
    </>
  );
}

function Studio({ id }: { id: string }) {
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("Overview");
  const [episode, setEpisode] = useState(1);
  const [busy, setBusy] = useState(false);
  const reload = useCallback(
    () =>
      api<Project>(`/projects/${id}`)
        .then(setProject)
        .catch((e) => setError(e.message)),
    [id],
  );
  useEffect(() => {
    void reload();
    const timer = window.setInterval(() => void reload(), 1500);
    return () => clearInterval(timer);
  }, [reload]);
  async function action(name: string, body?: object) {
    setBusy(true);
    setError("");
    try {
      const result = await api<{ episode?: number }>(
        `/projects/${id}/${name}`,
        {
          method: "POST",
          body: body ? JSON.stringify(body) : "{}",
        },
      );
      if (
        name.startsWith("references/") &&
        name.endsWith("/variants") &&
        result.episode !== undefined
      ) {
        setEpisode(result.episode);
      }
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }
  if (!project)
    return (
      <>
        <ErrorMessage message={error} />
        <div className="empty">
          <LoaderCircle size={24} className="spin" /> Opening your story…
        </div>
      </>
    );
  const job = project.jobs.find((j) => j.episode === episode);
  const ep = project.episodes.find((e) => e.number === episode);
  const movies = project.assets.filter(
    (a) =>
      ["export", "export-edition"].includes(a.role) &&
      a.metadata.episode === episode,
  );
  const movie = movies.at(-1);
  const clips = movie
    ? (movie.metadata.parent_asset_ids || []).flatMap((aid) =>
        project.assets.filter(
          (a) => a.id === aid && ["clip", "clip-revision"].includes(a.role),
        ),
      )
    : project.assets.filter(
        (a) => a.role === "clip" && a.metadata.episode === episode,
      );
  const frame = project.assets.find(
    (a) => a.role === "keyframe" && a.metadata.episode === episode,
  );
  const currentSteps = job?.steps.filter((s) => s.state !== "SUPERSEDED") || [];
  const done = currentSteps.filter((s) => s.state === "SUCCEEDED").length;
  const count = currentSteps.length || 1;
  const waitingForResources = job?.state === "WAITING_RESOURCES";
  const running =
    job?.state === "RUNNING" || job?.state === "QUEUED" || waitingForResources;
  const active = job?.steps.find((s) => s.state === "RUNNING");
  const unfinishedTake = currentSteps.some(
    (s) =>
      ["RETAKE_FRAME", "RETAKE_CLIP", "RECUT"].includes(s.stage) &&
      s.state !== "SUCCEEDED",
  );
  const unfinishedReferenceView = currentSteps.some(
    (s) => s.stage === "REFERENCE_VARIANT" && s.state !== "SUCCEEDED",
  );
  const episodeState =
    ep?.status === "REVIEW_REQUIRED"
      ? ep.status
      : job?.state || ep?.status || project.status;
  return (
    <>
      <button
        className="text-button back"
        onClick={() => navigate("/projects")}
      >
        <ArrowLeft size={16} /> Your projects
      </button>
      <div className="page-heading studio-heading">
        <div>
          <p className="eyebrow">
            {project.spec.kind.toUpperCase()} ·{" "}
            {project.spec.orientation.toUpperCase()} ·{" "}
            {project.spec.target_seconds} SECONDS{" "}
            {project.spec.kind === "series" && `/ EPISODE ${episode}`}
          </p>
          <h1>{project.title}</h1>
        </div>
        <span
          className={`state-label ${job?.state === "FAILED" ? "failed" : ""}`}
        >
          {active ? stepLabel(active) : stageLabel(episodeState)}
        </span>
      </div>
      {project.spec.backend === "demo" && <DemoNotice />}
      <ErrorMessage message={error || job?.error || ""} />
      <div className="tabs" role="tablist" aria-label="Project workspace">
        {[
          "Overview",
          "Story",
          "Cast & World",
          "Shots",
          "Episodes",
          "Export",
        ].map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            tabIndex={tab === t ? 0 : -1}
            onKeyDown={(event) => {
              const tabs = Array.from(
                event.currentTarget.parentElement!.querySelectorAll<HTMLButtonElement>(
                  '[role="tab"]',
                ),
              );
              const index = tabs.indexOf(event.currentTarget);
              const next =
                event.key === "ArrowRight"
                  ? (index + 1) % tabs.length
                  : event.key === "ArrowLeft"
                    ? (index + tabs.length - 1) % tabs.length
                    : event.key === "Home"
                      ? 0
                      : event.key === "End"
                        ? tabs.length - 1
                        : -1;
              if (next >= 0) {
                event.preventDefault();
                tabs[next].click();
                tabs[next].focus();
              }
            }}
            aria-controls="project-panel"
            id={`tab-${t.replaceAll(" ", "-")}`}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>
      <div className="studio-layout">
        <section
          id="project-panel"
          role="tabpanel"
          aria-labelledby={`tab-${tab.replaceAll(" ", "-")}`}
          className="project-panel"
        >
          {tab === "Overview" && (
            <>
              <div className={`preview ${project.spec.orientation}`}>
                {movie ? (
                  <video
                    key={movie.id}
                    controls
                    preload="metadata"
                    src={assetUrl(movie)}
                    poster={frame ? assetUrl(frame) : undefined}
                    aria-label="Movie preview"
                  />
                ) : frame ? (
                  <img
                    src={assetUrl(frame)}
                    alt="Development storyboard keyframe"
                  />
                ) : (
                  <div className="preview-empty">
                    <Clapperboard size={42} />
                    <p>Your story is taking shape.</p>
                    <small>
                      {active ? stepLabel(active) : stageLabel(project.status)}
                    </small>
                  </div>
                )}
              </div>
              <div className="preview-meta">
                <span>
                  {movie
                    ? `Draft export · Cut ${movie.metadata.edition || 1}`
                    : clips.length
                      ? `${clips.length} shots saved`
                      : "Your movie preview"}
                </span>
                <span>
                  {movie
                    ? `${movie.metadata.width} × ${movie.metadata.height} · 24 fps`
                    : "Completed work is saved automatically"}
                </span>
              </div>
              <div className="story-teaser">
                <p className="eyebrow">THE IDEA</p>
                <p>{project.spec.idea}</p>
                {project.plan && (
                  <button
                    className="text-button"
                    onClick={() => setTab("Story")}
                  >
                    Read the screenplay <ArrowRight size={15} />
                  </button>
                )}
              </div>
            </>
          )}
          <div hidden={tab !== "Story"}>
            <h2>The story bible</h2>
            {project.plan ? (
              <>
                <p className="lead">{project.plan.logline}</p>
                <details className="ending">
                  <summary>Planned ending · contains spoilers</summary>
                  <p>{project.plan.ending}</p>
                </details>
                <h3>World rules</h3>
                <ul>
                  {project.plan.world_rules.map((rule) => (
                    <li key={rule}>{rule}</li>
                  ))}
                </ul>
                <h3>Episode {episode} screenplay</h3>
                <pre className="screenplay">
                  {ep?.script?.screenplay ||
                    "The screenplay will appear when this episode is prepared."}
                </pre>
                {ep?.script && (
                  <DraftEditor
                    key={`${id}:${episode}`}
                    project={project}
                    episode={ep}
                    onSaved={reload}
                  />
                )}
                <h3>Saved continuity</h3>
                {project.canon.length ? (
                  project.canon.map((event, i) => (
                    <p key={i}>
                      Episode {event.episode} · {event.value}
                    </p>
                  ))
                ) : (
                  <p className="muted">
                    Episode outcomes commit after the export passes validation.
                  </p>
                )}
              </>
            ) : (
              <p className="empty">Preparing the story plan…</p>
            )}
          </div>
          {tab === "Cast & World" && (
            <>
              <h2>Cast & world</h2>
              <p className="muted">
                References and identities stay with the story across episodes.
              </p>
              <div className="asset-grid">
                {[
                  ...(project.plan?.characters || []),
                  ...(project.plan?.locations || []),
                  ...(project.plan?.props || []),
                ].map((entity) => {
                  const ref = project.assets.find(
                    (a) =>
                      a.id === project.reference_choices[entity.id]?.asset_id,
                  );
                  return (
                    <article className="entity" key={entity.id}>
                      {ref ? (
                        <img
                          src={assetUrl(ref)}
                          alt={`${ref.metadata.is_mock ? "Demo" : "Local"} reference for ${entity.name}`}
                        />
                      ) : (
                        <div className="entity-empty">
                          <Film />
                        </div>
                      )}
                      <h3>{entity.name}</h3>
                      <p>
                        {"appearance" in entity
                          ? entity.appearance
                          : entity.description}
                      </p>
                      <small>
                        Reference revision {ref?.metadata.revision || 1} ·{" "}
                        {"voice" in entity
                          ? `Voice: ${entity.voice}`
                          : "owner_id" in entity
                            ? `Prop owner: ${project.plan?.characters.find((c) => c.id === (project.canon.filter((e) => e.entity_id === entity.id && e.field === "prop_owner" && e.episode <= episode).at(-1)?.value ?? entity.owner_id))?.name || "Unowned"}`
                            : "Location reference"}
                      </small>
                      <ReferenceViews
                        project={project}
                        entityId={entity.id}
                        entityName={entity.name}
                        character={"appearance" in entity}
                        busy={busy}
                        action={action}
                      />
                    </article>
                  );
                })}
              </div>
            </>
          )}
          {tab === "Shots" && (
            <>
              <h2>Every shot has a purpose.</h2>
              <p className="muted">
                {clips.length} of {ep?.script?.shots.length || 0} clips saved ·
                pinned character and location references
              </p>
              {movie && (
                <p className="muted">
                  Another take keeps the story, timing, references and
                  soundtrack. Two retakes per shot; each saves a separate movie
                  cut. Demo takes remain mock footage.
                </p>
              )}
              <div className="shot-list">
                {ep?.script?.shots.map((shot) => {
                  const clip = clips.find(
                    (a) => a.metadata.shot_id === shot.id,
                  );
                  const image = project.assets.find((a) =>
                    clip
                      ? a.id === clip.metadata.parent_asset_ids?.[0]
                      : a.role === "keyframe" && a.metadata.shot_id === shot.id,
                  );
                  const used =
                    job?.steps.filter(
                      (s) =>
                        s.stage === "RETAKE_FRAME" &&
                        s.payload?.shot?.id === shot.id,
                    ).length || 0;
                  return (
                    <article className="shot" key={shot.id}>
                      <div className="shot-visual">
                        {clip ? (
                          <video
                            key={clip.id}
                            controls
                            preload="none"
                            src={assetUrl(clip)}
                            poster={image ? assetUrl(image) : undefined}
                            aria-label={`Shot ${shot.number}`}
                          />
                        ) : image ? (
                          <img
                            src={assetUrl(image)}
                            alt={`Shot ${shot.number} storyboard`}
                          />
                        ) : (
                          <span>{String(shot.number).padStart(2, "0")}</span>
                        )}
                      </div>
                      <div>
                        <small>
                          SHOT {String(shot.number).padStart(2, "0")} ·{" "}
                          {shot.duration.toFixed(1)}s ·{" "}
                          {clip ? "SAVED" : "PLANNED"}
                        </small>
                        <h3>{shot.camera}</h3>
                        <p>{shot.action}</p>
                        <blockquote>{shot.narration}</blockquote>
                        {movie && (
                          <>
                            <button
                              className="secondary"
                              aria-label={`Another take for shot ${shot.number}`}
                              disabled={
                                busy ||
                                used >= 2 ||
                                ep?.status !== "COMPLETED" ||
                                project.jobs.some(
                                  (j) => j.state !== "SUCCEEDED",
                                )
                              }
                              onClick={() => {
                                const frameId =
                                  clip?.metadata.parent_asset_ids?.[0];
                                const seed =
                                  project.assets.find((a) => a.id === frameId)
                                    ?.metadata.seed || 0;
                                void action(
                                  `episodes/${episode}/shots/${shot.id}/retake`,
                                  {
                                    source_export_id: movie.id,
                                    revision: project.revision,
                                    idempotency_key: crypto.randomUUID(),
                                    seed: (seed + 1) % 2147483648,
                                  },
                                );
                              }}
                            >
                              <Film size={16} /> Another take
                            </button>
                            <small className="muted">
                              {" "}
                              {used} of 2 retakes requested
                            </small>
                          </>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            </>
          )}
          {tab === "Episodes" && (
            <>
              <h2>A season with an ending.</h2>
              <p className="muted">
                Plan the whole journey. Produce one chapter at a time.
              </p>
              <div className="episode-list">
                {project.episodes.map((e) => (
                  <button
                    key={e.id}
                    className={episode === e.number ? "active" : ""}
                    onClick={() => setEpisode(e.number)}
                  >
                    <span className="episode-number">
                      {String(e.number).padStart(2, "0")}
                    </span>
                    <span>
                      <strong>{e.outline.title}</strong>
                      <small>{e.outline.summary}</small>
                      <small>{e.status.replaceAll("_", " ")}</small>
                    </span>
                    {e.status === "COMPLETED" ? (
                      <Check size={20} />
                    ) : (
                      <ChevronRight size={20} />
                    )}
                  </button>
                ))}
              </div>
              {ep &&
                ["PLANNED", "DRAFTED", "REVIEW_REQUIRED"].includes(
                  ep.status,
                ) && (
                  <button
                    className="primary"
                    disabled={
                      busy ||
                      project.jobs.some((j) => j.state !== "SUCCEEDED") ||
                      (episode > 1 &&
                        project.episodes.find((e) => e.number === episode - 1)
                          ?.status !== "COMPLETED")
                    }
                    onClick={() => void action("produce", { episode })}
                  >
                    <Play size={17} /> Produce episode {episode}
                  </button>
                )}
              {episode > 1 &&
                project.episodes.find((e) => e.number === episode - 1)
                  ?.status !== "COMPLETED" && (
                  <p className="muted">
                    Finish episode {episode - 1} before producing this chapter
                    so its completed canon is available.
                  </p>
                )}
            </>
          )}
          {tab === "Export" && (
            <>
              <h2>
                {movie
                  ? "Your movie, ready to leave the studio."
                  : "The final cut is on its way."}
              </h2>
              <p className="muted">
                Exports include H.264 video, AAC soundtrack and timed subtitles
                when speech is enabled.
              </p>
              {movie && (
                <>
                  <div className="export-summary">
                    <Film size={30} />
                    <div>
                      <strong>
                        Episode {episode} · Cut {movie.metadata.edition || 1} ·
                        MP4
                      </strong>
                      <p>
                        {movie.metadata.width} × {movie.metadata.height} ·{" "}
                        {movie.metadata.duration?.toFixed(1)} seconds ·{" "}
                        {movie.metadata.is_mock
                          ? "development demo"
                          : "local generation"}
                      </p>
                    </div>
                  </div>
                  <a className="primary" href={assetUrl(movie, true)}>
                    <Download size={18} /> Download MP4
                  </a>
                  <ShowInFolder key={movie.id} assetId={movie.id} />
                  <p className="muted">
                    {movie.metadata.dialogue_present
                      ? "Windows synthetic speech + original ambience."
                      : "Soundtrack only · dialogue omitted in Settings."}
                    {movie.metadata.sound_effects_present &&
                      " Original synthesized sound effects; no AI sound model."}
                    {movie.metadata.loudness &&
                      (movie.metadata.loudness.status ===
                      "below_measurement_gate"
                        ? " Quiet soundtrack preserved."
                        : " Volume balanced for playback.")}
                  </p>
                  <div className="provider-config">
                    <h3>Make a copy for another screen</h3>
                    <p className="muted">
                      Keeps the whole picture with black bars, plus your audio
                      and subtitles. Uses the saved movie; no AI generation.
                    </p>
                    <div className="download-list">
                      {(
                        [
                          ["portrait", "Portrait · 9:16", 360, 640],
                          ["landscape", "Landscape · 16:9", 640, 360],
                          ["square", "Square · 1:1", 480, 480],
                        ] as const
                      ).map(([orientation, label, width, height]) => {
                        const copy = project.assets.find(
                          (a) =>
                            (a.id === movie.id ||
                              (a.role === "export-variant" &&
                                a.metadata.parent_asset_ids?.[0] ===
                                  movie.id)) &&
                            a.metadata.episode === episode &&
                            a.metadata.width === width &&
                            a.metadata.height === height,
                        );
                        return copy ? (
                          <a key={orientation} href={assetUrl(copy, true)}>
                            <Download size={16} /> Download {label} · MP4
                          </a>
                        ) : (
                          <button
                            key={orientation}
                            className="secondary"
                            disabled={
                              busy ||
                              project.jobs.some((j) => j.state !== "SUCCEEDED")
                            }
                            onClick={() =>
                              void action(`episodes/${episode}/export-copy`, {
                                orientation,
                              })
                            }
                          >
                            <Film size={16} /> Make {label} copy
                          </button>
                        );
                      })}
                    </div>
                    {job?.steps.some(
                      (s) => s.stage === "REFORMAT" && s.state !== "SUCCEEDED",
                    ) && (
                      <p className="muted" role="status">
                        {running
                          ? "Making your copy. The current cut is ready to download."
                          : "Copy stopped. Use the production controls in Overview to resume or inspect the error."}
                      </p>
                    )}
                    {project.assets
                      .filter(
                        (a) =>
                          a.role === "manifest-variant" &&
                          a.metadata.episode === episode,
                      )
                      .map((a) => (
                        <p key={a.id}>
                          <a href={assetUrl(a, true)}>
                            {a.metadata.orientation} copy provenance · JSON
                          </a>
                        </p>
                      ))}
                  </div>
                </>
              )}
              {movies.length > 1 && (
                <details className="provider-config">
                  <summary>Earlier movie cuts</summary>
                  <p className="muted">
                    Your earlier footage and exports are preserved.
                  </p>
                  <div className="download-list">
                    {movies.slice(0, -1).map((a) => (
                      <a key={a.id} href={assetUrl(a, true)}>
                        <Download size={16} /> Download cut{" "}
                        {a.metadata.edition || 1} · MP4
                      </a>
                    ))}
                    {project.assets
                      .filter(
                        (a) =>
                          a.role === "export-variant" &&
                          a.metadata.episode === episode &&
                          a.metadata.parent_asset_ids?.[0] !== movie?.id,
                      )
                      .map((a) => (
                        <a key={a.id} href={assetUrl(a, true)}>
                          <Download size={16} /> Download cut{" "}
                          {a.metadata.edition || 1} · {a.metadata.orientation}{" "}
                          copy · MP4
                        </a>
                      ))}
                  </div>
                </details>
              )}
              <div className="download-list">
                <a href={`/api/projects/${id}/manifest`}>
                  <Download size={16} /> Story & project manifest
                </a>
                {project.assets
                  .filter(
                    (a) =>
                      [
                        "manifest",
                        "subtitles",
                        "manifest-edition",
                        "subtitles-edition",
                      ].includes(a.role) && a.metadata.episode === episode,
                  )
                  .map((a) => (
                    <a key={a.id} href={assetUrl(a, true)}>
                      <Download size={16} />
                      {a.role.startsWith("subtitles")
                        ? "Timed subtitles · SRT"
                        : "Export provenance · JSON"}{" "}
                      · Cut {a.metadata.edition || 1}
                    </a>
                  ))}
              </div>
              {movie && (
                <details className="provider-config">
                  <summary>Audio stems for editing</summary>
                  <p className="muted">
                    Saved WAV sources, including untrimmed spoken lines when
                    dialogue is enabled.
                  </p>
                  <div className="download-list">
                    {project.assets
                      .filter(
                        (a) =>
                          a.metadata.episode === episode &&
                          ([
                            "dialogue",
                            "ambience",
                            "sound-effects",
                            "unbalanced-mix",
                            "soundtrack",
                          ].includes(a.role) ||
                            a.role.startsWith("voice-")),
                      )
                      .map((a) => (
                        <a key={a.id} href={assetUrl(a, true)}>
                          <Download size={16} />
                          {a.role.startsWith("voice-")
                            ? `Shot ${a.metadata.shot_number} · ${project.plan?.characters.find((c) => c.id === a.metadata.speaker_id)?.name || "Voice"} · original voice`
                            : {
                                dialogue: a.metadata.dialogue_present
                                  ? "Dialogue track"
                                  : "Scene atmosphere",
                                ambience: "Original ambience",
                                "sound-effects": "Original sound effects",
                                "unbalanced-mix": "Mix before volume balancing",
                                soundtrack: "Mixed soundtrack",
                              }[a.role]}
                          {" · WAV"}
                        </a>
                      ))}
                  </div>
                </details>
              )}
            </>
          )}
        </section>
        <aside className="progress-panel" aria-label="Production progress">
          <p className="eyebrow">PRODUCTION</p>
          <h2>
            {waitingForResources
              ? "Waiting for your computer."
              : running
                ? "Making your movie."
                : movie && job?.state === "SUCCEEDED"
                  ? "That’s a wrap."
                  : stageLabel(episodeState)}
          </h2>
          <p aria-live="polite" className="muted">
            {waitingForResources
              ? `${job?.resource_wait?.message || "Waiting for safe memory and graphics conditions."} Studio will continue automatically when resources are free. You can pause or stop at any time.`
              : active
                ? stepLabel(active)
                : movie && job?.state === "SUCCEEDED"
                  ? "Your draft passed media validation."
                  : job?.state === "PAUSED"
                    ? ep?.can_edit_draft
                      ? "Your screenplay is saved. Review it in Story, then resume to make footage."
                      : "Saved progress. Resume when you’re ready."
                    : job?.state === "FAILED"
                      ? "Your completed work is safe."
                      : job?.state === "CANCELLED"
                        ? "Production stopped. Assets are preserved."
                        : "Every completed step is saved."}
          </p>
          <div
            className="progress-track"
            role="progressbar"
            aria-label="Production steps"
            aria-valuemin={0}
            aria-valuemax={count}
            aria-valuenow={done}
          >
            <div style={{ width: `${(done / count) * 100}%` }} />
          </div>
          <small>
            {done} / {count} steps{" "}
            {project.plan ? "" : "· more added after planning"}
          </small>
          <ol className="stage-list">
            {[
              "PLAN",
              "SCRIPT",
              "REFERENCE",
              "FRAME",
              "CLIP",
              "AUDIO",
              "EXPORT",
            ].map((stage) => {
              const steps =
                currentSteps.filter(
                  (s) =>
                    s.stage === stage ||
                    (stage === "REFERENCE" &&
                      s.stage === "REFERENCE_VARIANT") ||
                    (stage === "FRAME" && s.stage === "RETAKE_FRAME") ||
                    (stage === "CLIP" && s.stage === "RETAKE_CLIP") ||
                    (stage === "EXPORT" && s.stage === "RECUT") ||
                    (stage === "SCRIPT" &&
                      ["SCRIPT_BATCH", "DRAFT_BATCH", "DRAFT"].includes(
                        s.stage,
                      )),
                ) || [];
              const finished =
                steps.length > 0 && steps.every((s) => s.state === "SUCCEEDED");
              const working = steps.some((s) => s.state === "RUNNING");
              return (
                <li
                  key={stage}
                  className={finished ? "finished" : working ? "working" : ""}
                >
                  <span>
                    {finished ? (
                      <Check size={14} />
                    ) : working ? (
                      <LoaderCircle className="spin" size={14} />
                    ) : (
                      <i />
                    )}
                  </span>
                  {stageLabel(stage)}
                </li>
              );
            })}
          </ol>
          <div className="production-actions">
            {ep?.can_edit_draft &&
              ["PAUSED", "FAILED"].includes(job?.state || "") && (
                <button className="secondary" onClick={() => setTab("Story")}>
                  Review or edit screenplay
                </button>
              )}
            {running && (
              <>
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => void action(`episodes/${episode}/pause`)}
                >
                  <Pause size={16} />{" "}
                  {waitingForResources ? "Pause" : "Pause after this step"}
                </button>
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={() => void action(`episodes/${episode}/cancel`)}
                >
                  <Square size={13} /> Stop production
                </button>
              </>
            )}
            {["PAUSED", "FAILED"].includes(job?.state || "") && (
              <button
                className="primary"
                disabled={busy}
                onClick={() => void action(`episodes/${episode}/resume`)}
              >
                <Play size={16} />
                {job?.state === "FAILED" ? "Retry safely" : "Resume movie"}
              </button>
            )}
            {movie &&
              unfinishedTake &&
              !active &&
              ["PAUSED", "FAILED", "CANCELLED"].includes(job?.state || "") && (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() =>
                    void action(`episodes/${episode}/discard-retake`)
                  }
                >
                  Keep current cut & discard unfinished take
                </button>
              )}
            {unfinishedReferenceView &&
              !active &&
              ["PAUSED", "FAILED", "CANCELLED"].includes(job?.state || "") && (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() =>
                    void action(`episodes/${episode}/discard-reference-view`)
                  }
                >
                  Keep current reference & discard unfinished view
                </button>
              )}
            {movie && (
              <button className="primary" onClick={() => setTab("Export")}>
                <Download size={16} /> Get your movie
              </button>
            )}
          </div>
          <div className="provider-note">
            <ShieldCheck size={17} />
            <p>
              {project.spec.backend === "demo"
                ? "Demo visual provider"
                : "Local generation requested"}
              <small>
                1 job at a time · no cloud uploads
                <br />
                No cinematic quality review performed.
              </small>
            </p>
          </div>
        </aside>
      </div>
    </>
  );
}

type Health = {
  database: string;
  free_disk_gb: number;
  worker_alive: boolean;
  media: Record<string, { available: boolean; message?: string }>;
  native_export: string;
  hardware?: {
    python: string;
    memory: { available: boolean; total_gb?: number; free_gb?: number };
    gpu: {
      available: boolean;
      name?: string;
      total_mb?: number;
      used_mb?: number;
      temperature_c?: number;
      driver?: string;
    };
  };
};
type Provider = {
  id: string;
  name: string;
  available: boolean;
  is_mock: boolean;
  models?: string[];
  message?: string;
  status?: string;
  attention?: boolean;
  last_check_at?: number;
  last_image_check_at?: number;
};
function Settings() {
  const [health, setHealth] = useState<Health | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [model, setModel] = useState("");
  const [speech, setSpeech] = useState("windows");
  const [soundEffects, setSoundEffects] = useState(true);
  const [balancedAudio, setBalancedAudio] = useState(true);
  const [reserve, setReserve] = useState(1024);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [engine, setEngine] = useState("ollama");
  const [wangp, setWangp] = useState({
    installation: "",
    python: "",
    image_model: "",
    video_model: "",
    license_reviewed: false,
    native_resolution: "480x832",
    steps: 12,
    memory_profile: 4,
    smart_memory_pinning: null as boolean | null,
  });
  useEffect(() => {
    Promise.allSettled([
      api<Health>("/health"),
      api<{ providers: Provider[] }>("/providers"),
      api<{
        story_model: string;
        story_engine: string;
        wangp: typeof wangp;
        speech: string;
        sound_effects: boolean;
        balanced_audio: boolean;
        reserve_mb: number;
      }>("/settings"),
    ]).then(([h, p, s]) => {
      if (h.status === "fulfilled") setHealth(h.value);
      if (p.status === "fulfilled") setProviders(p.value.providers);
      if (s.status === "fulfilled") {
        setModel(s.value.story_model);
        setEngine(s.value.story_engine || "ollama");
        setWangp((w) => ({ ...w, ...s.value.wangp }));
        setSpeech(s.value.speech);
        setSoundEffects(s.value.sound_effects);
        setBalancedAudio(s.value.balanced_audio);
        setReserve(s.value.reserve_mb);
        setSettingsLoaded(true);
      }
      setError(
        [h, p, s]
          .filter((result) => result.status === "rejected")
          .map((result) =>
            String(result.reason?.message || "Studio check failed"),
          )
          .join(" "),
      );
      setLoading(false);
    });
  }, []);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!settingsLoaded) return;
    setSaved(false);
    setError("");
    try {
      await api("/settings", {
        method: "PATCH",
        body: JSON.stringify({
          story_model: model,
          story_engine: engine,
          wangp,
          speech,
          sound_effects: soundEffects,
          balanced_audio: balancedAudio,
          reserve_mb: reserve,
        }),
      });
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save settings");
    }
  }
  async function refreshDiagnostics() {
    setRefreshing(true);
    const checks = await Promise.allSettled([
      api<Health>("/health"),
      api<{ providers: Provider[] }>("/providers"),
    ]);
    if (checks[0].status === "fulfilled") setHealth(checks[0].value);
    if (checks[1].status === "fulfilled")
      setProviders(checks[1].value.providers);
    const failures = checks.filter((c) => c.status === "rejected");
    if (failures.length)
      setError(
        "Some diagnostics could not be refreshed. Saved preferences are preserved.",
      );
    setRefreshing(false);
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">PRIVATE. LOCAL. YOURS.</p>
          <h1>The studio behind the scenes.</h1>
          <p className="lead">
            Clear capabilities. No subscriptions. No surprise downloads.
          </p>
        </div>
      </div>
      <ErrorMessage message={error} />
      <section className="settings-section">
        <h2>Your workstation</h2>
        <button
          className="secondary"
          disabled={loading || refreshing}
          onClick={() => void refreshDiagnostics()}
        >
          {refreshing ? "Refreshing…" : "Refresh diagnostics"}
        </button>
        {loading && <p role="status">Checking your studio…</p>}
        <div className="diagnostics">
          <div>
            <span>Project storage</span>
            <strong>
              {health?.database === "ok" ? "Healthy" : "Checking…"}
            </strong>
          </div>
          <div>
            <span>Free disk space</span>
            <strong>
              {health ? `${health.free_disk_gb} GB` : "Checking…"}
            </strong>
          </div>
          <div>
            <span>Production worker</span>
            <strong>
              {!health
                ? "Checking…"
                : health.worker_alive
                  ? "Running · sequential"
                  : "Not running"}
            </strong>
          </div>
          <div>
            <span>Media tools</span>
            <strong>
              {!health
                ? "Checking…"
                : Object.values(health.media).every((t) => t.available)
                  ? "FFmpeg + FFprobe ready"
                  : "Setup needed"}
            </strong>
          </div>
          <div>
            <span>Graphics card</span>
            <strong>
              {!health
                ? "Checking…"
                : health.hardware?.gpu.available
                  ? `${health.hardware.gpu.name} · ${health.hardware.gpu.total_mb} MB`
                  : "Not detected"}
            </strong>
          </div>
          <div>
            <span>Available memory</span>
            <strong>
              {!health
                ? "Checking…"
                : health.hardware?.memory.available
                  ? `${health.hardware.memory.free_gb} / ${health.hardware.memory.total_gb} GB`
                  : "Not measured"}
            </strong>
          </div>
          <div>
            <span>GPU temperature</span>
            <strong>
              {!health
                ? "Checking…"
                : health.hardware?.gpu.available
                  ? `${health.hardware.gpu.temperature_c} °C`
                  : "Not measured"}
            </strong>
          </div>
          <div>
            <span>Python runtime</span>
            <strong>{health?.hardware?.python || "Checking…"}</strong>
          </div>
        </div>
        {health?.hardware?.memory.free_gb !== undefined &&
          health.hardware.memory.free_gb < 5 && (
            <p className="resource-note">
              The initial GPU and 1.5B CPU profiles require at least 5 GiB free
              RAM. Close heavy applications and refresh diagnostics. This
              resource check does not prove model fit.
            </p>
          )}
        <p className="muted">
          {health && `Draft export: ${health.native_export}. `}GPU performance
          and cinematic quality are not yet verified.
        </p>
      </section>
      <section className="settings-section">
        <h2>Generation providers</h2>
        {providers.map((p) => (
          <div key={p.id} className="provider-row">
            <div>
              <strong>{p.name}</strong>
              <p>
                {p.message ||
                  (p.is_mock
                    ? "Watermarked abstract fixtures for workflow development."
                    : "Installed models are discovered locally.")}
              </p>
              {(p.last_image_check_at || p.last_check_at) && (
                <small>
                  {p.last_image_check_at ? "Last image test" : "Last check"}:{" "}
                  {new Date(
                    (p.last_image_check_at ?? p.last_check_at ?? 0) * 1000,
                  ).toLocaleString()}
                </small>
              )}
            </div>
            <span
              className={
                p.attention || !p.available ? "unavailable" : "available"
              }
            >
              {p.status || (p.available ? "Installed" : "Setup needed")}
            </span>
          </div>
        ))}
      </section>
      <section className="settings-section">
        <h2>Your studio backup</h2>
        <p className="muted">
          Save all projects, stories, canon and completed media in one portable
          archive. Models and machine-specific provider settings are excluded.
          Restore missing projects below, or use the local README for a separate
          studio copy.
        </p>
        <a className="secondary" href="/api/backup">
          <Download size={17} /> Download studio backup
        </a>
        <BackupRestore />
      </section>
      <form onSubmit={save} className="settings-section settings-form">
        <h2>Your defaults</h2>
        {!settingsLoaded && (
          <p>
            {loading
              ? "Loading saved settings…"
              : "Saved settings could not be loaded. Reload this page before editing."}
          </p>
        )}
        <fieldset disabled={!settingsLoaded} className="settings-fields">
          <legend>Studio preferences</legend>
          <label>
            Local story engine
            <select
              aria-label="Local story engine"
              value={engine}
              onChange={(e) => setEngine(e.target.value)}
            >
              <option value="ollama">Ollama · your installed model</option>
              <option value="small_cpu">
                Small CPU story · Qwen 0.5B (feasibility)
              </option>
              <option value="cpu_1_5b">
                CPU story · Qwen 1.5B (experiment
                {providers.find((p) => p.id === "cpu-1-5b")?.available
                  ? ", installed"
                  : ", separate install"}
                )
              </option>
              <option
                value="cpu_4b"
                disabled={!providers.find((p) => p.id === "cpu-4b")?.available}
              >
                CPU story · Qwen3 4B (experiment, requires 7 GB free RAM)
              </option>
            </select>
          </label>
          <label>
            Installed Ollama story model
            <select value={model} onChange={(e) => setModel(e.target.value)}>
              <option value="">No local story model selected</option>
              {providers
                .find((p) => p.id === "ollama")
                ?.models?.map((m) => (
                  <option key={m}>{m}</option>
                ))}
            </select>
          </label>
          <label>
            Soundtrack
            <select
              aria-label="Soundtrack"
              value={speech}
              onChange={(e) => setSpeech(e.target.value)}
            >
              <option value="windows">
                Installed Windows voices + synthetic ambience
              </option>
              <option value="none">
                Synthetic ambience only · no spoken dialogue
              </option>
            </select>
          </label>
          <label className="check-label">
            <input
              type="checkbox"
              checked={soundEffects}
              onChange={(e) => setSoundEffects(e.target.checked)}
            />
            Add sound effects to new movies
          </label>
          <p className="muted">
            Original synthesized signals, footsteps and door sounds, matched to
            scene actions. No downloads or AI sound model.
          </p>
          <label className="check-label">
            <input
              type="checkbox"
              checked={balancedAudio}
              onChange={(e) => setBalancedAudio(e.target.checked)}
            />
            Balance volume in new movies
          </label>
          <p className="muted">
            Measures playback volume and protects loud peaks. Quiet atmosphere
            stays restrained; your original mix is saved separately.
          </p>
          <label>
            Reserved disk space (MB)
            <input
              type="number"
              min={100}
              max={102400}
              value={reserve}
              onChange={(e) => setReserve(Number(e.target.value))}
            />
          </label>
          <details className="provider-config">
            <summary>Connect an existing WanGP installation</summary>
            <p>
              Keep its Python/CUDA environment separate. Inference uses
              installed weights only; provider downloads are blocked. These
              paths are local settings, never supplied by the story model.
            </p>
            <label>
              WanGP folder
              <input
                aria-label="WanGP folder"
                value={wangp.installation}
                onChange={(e) =>
                  setWangp({ ...wangp, installation: e.target.value })
                }
                placeholder="C:\\WanGP"
              />
            </label>
            <label>
              WanGP Python executable
              <input
                aria-label="WanGP Python executable"
                value={wangp.python}
                onChange={(e) => setWangp({ ...wangp, python: e.target.value })}
                placeholder="C:\\WanGP\\venv\\Scripts\\python.exe"
              />
            </label>
            <label>
              Installed image model ID
              <input
                value={wangp.image_model}
                onChange={(e) =>
                  setWangp({ ...wangp, image_model: e.target.value })
                }
              />
            </label>
            <label>
              Installed video model ID
              <input
                value={wangp.video_model}
                onChange={(e) =>
                  setWangp({ ...wangp, video_model: e.target.value })
                }
              />
            </label>
            <label>
              Native generation format
              <select
                value={wangp.native_resolution}
                onChange={(e) =>
                  setWangp({ ...wangp, native_resolution: e.target.value })
                }
              >
                <option value="480x832">Portrait · 480 × 832</option>
                <option value="832x480">Landscape · 832 × 480</option>
                <option value="512x512">Square · 512 × 512</option>
              </select>
            </label>
            <label className="check-label">
              <input
                type="checkbox"
                checked={wangp.license_reviewed}
                onChange={(e) =>
                  setWangp({ ...wangp, license_reviewed: e.target.checked })
                }
              />
              I reviewed WanGP and model rights for my intended use.
            </label>
            <label>
              Memory use
              <select
                value={wangp.memory_profile}
                onChange={(e) =>
                  setWangp({ ...wangp, memory_profile: Number(e.target.value) })
                }
              >
                <option value={4}>Standard</option>
                <option value={4.5}>Use less GPU memory (slower)</option>
                <option value={5}>Use less RAM and GPU memory (slower)</option>
              </select>
            </label>
            <p className="muted">
              Lower memory use can mean slower generation. Changing this setting
              does not guarantee that a model fits.
            </p>
            <label className="check-label">
              <input
                type="checkbox"
                checked={wangp.smart_memory_pinning === false}
                onChange={(e) =>
                  setWangp({
                    ...wangp,
                    smart_memory_pinning: e.target.checked ? false : null,
                  })
                }
              />
              Use smaller RAM transfer buffers
            </label>
            <p className="muted">
              Can reduce reserved system memory but may slow generation. Uses a
              private job configuration; your engine settings stay intact. Model
              fit still needs a real test.
            </p>
            <p>
              Image models must support reference conditioning for shot
              identity. Actual 6 GB compatibility and cinematic quality remain
              unverified. Inspect capabilities before selecting a model.
            </p>
          </details>
          <div>
            <button className="primary">
              Save settings <Check size={17} />
            </button>
            {saved && (
              <span role="status" className="saved">
                Settings saved.
              </span>
            )}
          </div>
        </fieldset>
      </form>
      <section className="settings-section">
        <h2>Local model setup</h2>
        <p>
          Real image and video generation requires a separately installed,
          licensed model that passes testing on your 6 GB GPU. The app does not
          download weights or install drivers automatically.
        </p>
        <p className="muted">
          WanGP and individual model weights have separate licensing terms.
          Review the source register in docs before installing or distributing
          providers. Large downloads require approval. This build is for local
          development and is not a finished production release.
        </p>
      </section>
    </>
  );
}
