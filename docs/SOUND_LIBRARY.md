# Local sound-effects library

New jobs capture the **Add sound effects to new movies** setting when queued. Changing Settings later does not change that job. Older persisted jobs missing this option retain their original audio behavior. Completed movies and retakes keep their saved soundtrack.

The initial provider is `procedural-effects-v1`: original mathematical synthesis, with no imported recording, download, remote service or AI sound model. It is a small stylized library, not a cinematic foley or music-quality acceptance pass.

| Effect | Explicit action examples | Maximum length |
|---|---|---|
| Electronic signal | beeps, alarm rings, radio crackles | 0.6 seconds |
| Door movement | door opens/closes/slams, opens the door | 0.45 seconds |
| Footsteps | footsteps, walks, walking, runs | 0.8 seconds |

Selection uses conservative action matching, with at most one effect per shot and 120 cues per film. Mentioning a signal in a letter does not add a beep. Silent or negated action suppresses selection. Matching can miss nuanced descriptions or select an imperfect stylized sound; disable the option when inappropriate. Broader context-sensitive sound planning remains unfinished.

Each cue records its source shot ID/number, start, duration, deterministic seed and gain. Short shots bound cues to their duration. Synthesis streams one second at a time into a temporary mono PCM WAV at 16 kHz, then atomically replaces the stage output after its cancellation check. Pause/interruption preserves existing originals; unfinished files never become published assets.

The soundtrack mixer lowers effects beneath measured dialogue with FFmpeg sidechain compression and limits the final mix. Original voices, subtitle timings and the separate effects stem remain intact. This is peak limiting and ducking; integrated loudness normalization and broad listening review are still open.

Export → **Audio stems for editing** downloads the original effects WAV when cues were selected. Its immutable ID, SHA256, cue list and synthesis/rights provenance join the mixed soundtrack's lineage and portable backup. With no matching action or the option off, there is no effects stem and no invented generated-sound claim. Movie visuals still show their actual demo or local provider.
