# 05 — Character, location, prop and reference image generation

## Central goal
Automatic image generation is mandatory, not a user-operated prerequisite. Idea alone should yield reusable visual references for every meaningful entity, while allowing optional user-uploaded references only if desired.

## Visual design pipeline
1. Derive project-wide visual style tokens: photorealistic, lighting, camera aesthetics, era, palette, geography, costume materials, aspect ratio/negative-space rules, censorship/age suitability.
2. Assign stable entity IDs and canonical appearance prompts. Generate neutral baseline character portraits first, then front/side/full-body/costume variants via reference-conditioned edits if provider supports it. Don't create impossible turnaround claims on unsupported models.
3. For each location: establishing, main angles, time-of-day, weather variants and important persistent objects.
4. Props/objects: image reference, dimensions, color/texture, owner and current state. Track transformations (broken sword etc.).
5. Create shot keyframes from approved references and script-specific blocking, environment and art cues. Primary path: **reference image -> image-to-video**, not unrelated text-to-video shots.
6. Score automatically: resolution, aspect, person count, cropping, visually obvious corruption, reference similarity when technically feasible. Use a score+rules with explanations; limit retries.
7. Store approved images, rejection reason, model ID/version, seed, prompt, source reference, hash; reuse originals across episodes. Always preserve source even if new generation created.

## Auto-prompting rules
Separate positive scene prompt, character descriptor and negative constraints. Include shot scope (single-shot, no scene cuts), subject, action, temporal motion, camera, lighting, style and environment. Avoid overlong contradictory aesthetic adjectives; include realistic physical actions. Different video backends use different prompt expectations — adapter-specific generation templates.

## Continuity
Do not rely solely on visual embedding similarity. Use stable approved references and story canon. Carry reference image(s), outfit version, scar/injury state, prop ownership, location weather/time in every shot plan. Automated face embedding/identity validation for fictional adults can be a later optional technique with local processing; compare to controlled generated references and avoid mislabeling as perfect identity proof.

## 9:16 and 16:9
Create framing for target aspect at **reference-image stage**, not after animation. For 9:16 protect face/hands and text safe zones; for 16:9 use wider establishing shots and cinematic blocking. Reframing after generation must provide preview, never distort. If model only generates fixed native aspect, letterbox or crop with logged fallback rather than promise perfect composition.

## File layout
`assets/characters/{uuid}/references/{revision}/...`, `assets/locations/{uuid}/...`, `scenes/{id}/shots/{id}/keyframe.png`, plus metadata sidecars. No user-provided filename used directly as filesystem path.

## Hard cases to design for
Crowds/same outfit/identical twins, age progression, wet clothing, changing hair, identical characters in reflections, image with extra limbs, multi-subject shots, reused locations changing sunlight, nonhuman creatures, flashbacks, weapons, gore/age ratings, logos/brand likeness, unknown model licensing. Document automated confidence and leave voluntary review controls.

## Tests
Given 2 scene shots with same character ID and unchanged outfit, generation requests contain same pinned appearance-reference IDs; after a scripted outfit change a different reference revision appears. Portrait keyframes correct dimensions; all references can be reloaded after app restart; removing/replacing one rejected reference invalidates only linked outputs.
