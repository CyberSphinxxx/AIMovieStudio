import type { Shot } from "./types";

type Moment = Pick<Shot, "flashback_episode" | "flashback_after_shot">;

export function storyMoment(shot: Moment): string | null {
  if (shot.flashback_episode == null) return null;
  const position = shot.flashback_after_shot;
  const moment =
    position == null
      ? "before the episode begins"
      : position === 0
        ? "before the first shot, after setup"
        : `after shot ${position}`;
  return `Flashback · Episode ${shot.flashback_episode} · ${moment}`;
}

export function StoryMoment({ shot }: { shot: Moment }) {
  const text = storyMoment(shot);
  return text ? <p className="muted">{text}</p> : null;
}
