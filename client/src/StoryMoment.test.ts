import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { StoryMoment, storyMoment } from "./StoryMoment";

describe("saved story moments", () => {
  it("leaves ordinary and legacy non-flashback scenes unlabeled", () => {
    expect(storyMoment({})).toBeNull();
    expect(renderToStaticMarkup(createElement(StoryMoment, { shot: {} }))).toBe(
      "",
    );
  });
  it("distinguishes episode start, setup and an exact later checkpoint", () => {
    expect(storyMoment({ flashback_episode: 1 })).toContain(
      "before the episode begins",
    );
    expect(
      storyMoment({ flashback_episode: 1, flashback_after_shot: 0 }),
    ).toContain("before the first shot, after setup");
    const html = renderToStaticMarkup(
      createElement(StoryMoment, {
        shot: { flashback_episode: 2, flashback_after_shot: 4 },
      }),
    );
    expect(html).toContain("Flashback · Episode 2 · after shot 4");
    expect(html).toContain('<p class="muted">');
  });
});
