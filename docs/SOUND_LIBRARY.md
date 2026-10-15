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

The soundtrack mixer lowers effects beneath measured dialogue with FFmpeg sidechain compression and limits the final mix. New jobs also offer **Balance volume in new movies**: EBU R128 loudness/true-peak measurement, bounded linear gain, then output remeasurement. Spoken mixes aim for -16 LUFS and atmosphere for -26 LUFS; boosts are capped at 9/6 dB respectively, with a -2 dBTP PCM ceiling. If a quiet or peaky track cannot safely reach its target, metadata records the actual limited result. Silence/below-gate audio is never amplified. These are product defaults, not a claim that every platform requires those values.

The unbalanced mix remains a separate downloadable WAV, alongside original voices and effects. Voice/subtitle timing and dynamics stay intact. Settings are frozen per queued job; older jobs without this option retain their audio. Measurements refer to the PCM soundtrack; encoded AAC can differ. Broad listening/cinematic review remains open.

Implementation research checked 2026-10-15: [official FFmpeg loudnorm documentation](https://ffmpeg.org/ffmpeg-filters.html#loudnorm) and the installed binary's filter help. The application uses loudnorm as a meter, applies a capped constant volume gain, then measures again; it does not claim that the meter's unrendered output is the final soundtrack. Mono is measured for stereo playback using the documented dual_mono option.

Export → **Audio stems for editing** downloads the original effects WAV when cues were selected. Its immutable ID, SHA256, cue list and synthesis/rights provenance join the mixed soundtrack's lineage and portable backup. With no matching action or the option off, there is no effects stem and no invented generated-sound claim. Movie visuals still show their actual demo or local provider.
