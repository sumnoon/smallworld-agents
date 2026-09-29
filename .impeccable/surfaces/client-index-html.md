---
version: 1
slug: "client-index-html"
primary_target: "client/index.html"
related_targets: ["client/style.css","client/app.js","client/tools.js","client/renderer.js"]
---

# Surface brief: Smallworld Agents client

Scope: `client/index.html` with its stylesheet, the DOM built by `client/app.js` and `client/tools.js`, and world styling in `client/renderer.js`. Mode: **Operate** — watch the town, act on residents, inspect evidence. Audience: evaluators, players and researchers equally (PRODUCT.md). Layout priority chosen by the user: world first, depth on demand. Constraints: no build step, no packages, no network fonts; all features, copy and behavior kept.

Chosen direction: **Lamplight**, picked by the user from three rendered mockups; the user's pick overrides the seed's assignment. Memorable moment: the town lighting up on a dark stage when it loads.

## Direction contract

THESIS: The town is the only light source. Chrome is evening darkness around a lit diorama; the page refuses the category default of a pale dashboard with the game shrunk into one tile among many.

OWN-WORLD: Dusk-green darkness (#0B1311 ground, #121C19 panels, #182521 raised) with warm lantern amber (#E8A85C) as the single light colour and a cool mint (#7FD3A8) reserved for verified, live and healthy states; district hues are the only other saturation. System sans UI with tabular figures; Georgia only for the clock and resident names. Translucent control glass floats on the stage; 22px stage and sidecar corners, 10px controls. Raised by the darkroom challenger: amber behaves as light, never as a border colour, and task steps read as stations in order. Raised by the cathode challenger: changed values snap and leave a short afterglow instead of tweening.

STORY: A visitor sees a living town at once, picks a resident beside it, talks or assigns an errand, and watches the steps complete with evidence; deeper tools wait below without competing.

FIRST VIEWPORT: Header 64px (brand, live mode, amber clock, save). Stage fills the left column at about 64vh, town fitted large; controls and district chips float in glass along its top edge, hint pill at its bottom. The 372px resident sidecar on the right holds switcher, lit portrait, needs, tabs, conversation and composer, with "Say it to <name>" as the one amber action.

FORM: Lamplight, user-chosen from three mockups (my ranked list: 1 Lamplight, 2 Field Notes, 3 Storybook Tin); seed key a74ff472.

Signature interaction: the stage lights up once on load (surround and controls settle, the town fades in). Motion grammar: snap-and-afterglow for changing values; press feedback on every button; hover on fine pointers only; reduced motion removes movement and keeps state.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
