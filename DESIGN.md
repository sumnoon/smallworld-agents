---
name: Smallworld Agents
description: Lamplight. A lit isometric town on an evening-dark stage; the chrome is darkness, the town is the light.
colors:
  ink: "#0b1311"
  panel: "#121c19"
  raise: "#182521"
  raise-2: "#1f2e29"
  line: "#23332e"
  line-strong: "#30463f"
  text: "#e7efea"
  text-2: "#b9c9c0"
  muted: "#a1b4aa"
  amber: "#e8a85c"
  amber-soft: "#f2c48a"
  amber-ink: "#1d130a"
  mint: "#7fd3a8"
  mint-ink: "#0c2219"
  caution: "#e9c46a"
  caution-ink: "#2a1f05"
  coral: "#f08f78"
  coral-ink: "#2b0d06"
typography:
  display:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, -apple-system, sans-serif"
    fontSize: "clamp(1.375rem, 1.05rem + 0.8vw, 1.75rem)"
    fontWeight: 650
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  name:
    fontFamily: "Georgia, Iowan Old Style, Palatino Linotype, serif"
    fontSize: "1.875rem"
    fontWeight: 400
    lineHeight: 1.05
    letterSpacing: "-0.01em"
  clock:
    fontFamily: "Georgia, Iowan Old Style, Palatino Linotype, serif"
    fontSize: "1.625rem"
    fontWeight: 400
    lineHeight: 1
    fontFeature: "tnum"
  headline:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, -apple-system, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, -apple-system, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: 1.45
  body:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, -apple-system, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.6
  body-sm:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, -apple-system, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, -apple-system, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.5
  status:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, -apple-system, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "0.12em"
  data:
    fontFamily: "Cascadia Mono, Consolas, ui-monospace, monospace"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.55
rounded:
  tab: "8px"
  control: "10px"
  inner: "12px"
  card: "14px"
  portrait: "16px"
  stage: "22px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  panel: "18px 20px"
components:
  button:
    backgroundColor: "{colors.raise}"
    textColor: "{colors.text}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.control}"
    padding: "7px 13px"
    height: "36px"
  button-primary:
    backgroundColor: "{colors.amber}"
    textColor: "{colors.amber-ink}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.control}"
    padding: "7px 13px"
    height: "36px"
  button-send:
    backgroundColor: "{colors.amber}"
    textColor: "{colors.amber-ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "10px 14px"
    height: "42px"
    width: "100%"
  button-rail:
    textColor: "{colors.text}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.control}"
    padding: "6px 9px"
    height: "32px"
  rail-group:
    backgroundColor: "{colors.panel}"
    rounded: "{rounded.inner}"
    padding: "4px"
  chip-example:
    textColor: "{colors.text-2}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "4px 10px"
    height: "30px"
  resident-switch-active:
    backgroundColor: "{colors.amber}"
    textColor: "{colors.amber-ink}"
    rounded: "{rounded.control}"
    height: "34px"
  status-chip:
    backgroundColor: "{colors.raise-2}"
    textColor: "{colors.text-2}"
    rounded: "{rounded.pill}"
    padding: "3px 9px"
  status-chip-completed:
    backgroundColor: "{colors.mint}"
    textColor: "{colors.mint-ink}"
  status-chip-blocked:
    backgroundColor: "{colors.caution}"
    textColor: "{colors.caution-ink}"
  status-chip-failed:
    backgroundColor: "{colors.coral}"
    textColor: "{colors.coral-ink}"
  textarea:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.text}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "11px 12px"
  panel-card:
    backgroundColor: "{colors.panel}"
    rounded: "{rounded.card}"
    padding: "{spacing.panel}"
  sidecar:
    backgroundColor: "{colors.panel}"
    rounded: "{rounded.stage}"
    padding: "18px"
  task-card:
    backgroundColor: "{colors.raise}"
    rounded: "{rounded.inner}"
    padding: "14px"
  tab:
    textColor: "{colors.muted}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.tab}"
    height: "40px"
  tab-active:
    textColor: "{colors.text}"
---

# Design System: Smallworld Agents

## Overview

**Creative North Star: "The Lit Diorama"**

The town is the only light source. Everything around it is evening darkness in a dusk-green register, and the isometric town sits on a rounded stage like a lamplit diorama on a dark shelf: a radial pool of light at its centre, a vignette that lets its edges fall away. The chrome never competes with it. Panels are barely-lifted shades of the same dark, text is cool and quiet, and colour is spent almost entirely on light: warm lantern amber for the clock, the one action you should take next, and the selected resident; cool mint for anything verified, live, or healthy.

Density is operational rather than decorative. The page is a working instrument for watching agents: one fluid world column (heading, stage, footer), a fixed resident sidecar beside it, and the depth (requests, community, event log, tools) waiting underneath without competing. Figures are tabular, data sits in a mono face, and the two moments of personality in type are the Georgia clock and the Georgia resident name, the two things in the interface that are about time and people.

Motion is sparse and physical. The page has one signature moment, the stage lighting up once the artwork has loaded; after that, values snap and leave a short afterglow instead of tweening, buttons compress under the press, and hover exists only for fine pointers. Rejected by the chosen direction: the pale dashboard with the game shrunk to one tile among many.

**Key Characteristics:**
- Dusk-green darkness around a single lit stage; the stage is the brightest thing on the page.
- Amber is light, not ink: fills, text, rings, and radial pools, never a stroke on chrome.
- Mint is reserved for verified, live, and healthy states.
- System sans for the interface; Georgia only for the clock and resident names; mono only for data.
- Resting surfaces are flat and bordered; only floating surfaces cast shadows.
- One lighting-up moment on load, then snap-and-afterglow.

## Colors

A two-temperature light scheme on a dusk-green dark: warm amber as lantern light, cool mint as confirmation, with district hues supplied by data as the only other saturation.

### Primary
- **Lantern Amber** (amber): the single light colour. The primary action ("Say it to <name>", "Ask selected resident to organize a picnic"), the active resident in the switcher, the clock, event timestamps, the active-tab underline, the selected resident's ring on the canvas, focus outlines, text selection, caret and native accent controls. **Amber Glow** (amber-soft) is its text-weight companion on dark: inventory line, interaction status, the connection message, inline code, the player's own speaker line. **Amber Ink** (amber-ink) is the near-black brown set on amber fills.

### Secondary
- **Verified Mint** (mint): completed request chips, finished request steps, need bars, the live-mode dot, and the visitor's ring on the canvas. **Mint Ink** (mint-ink) sits on mint fills. Mint is also the fallback colour of a district chip whose district has no colour.

### Tertiary
- **Caution Straw** (caution) with **caution-ink**: blocked and paused request chips only.
- **Ember Coral** (coral) with **coral-ink**: failed, cancelled and declined request chips only.

### Neutral
- **Night Ground** (ink): page ground, masthead (at 97% opacity), textarea and code wells, the stage veil.
- **Dusk Panel** (panel): depth cards, sidecar, docked rail groups.
- **Raised Moss** (raise): buttons, selects, task cards, memories, chat bubbles, the portrait plate.
- **Raised Moss 2** (raise-2): toast, neutral status chips, the active input-mode segment.
- **Hairline** (line): the 1px border on every resting surface; row dividers.
- **Hairline Strong** (line-strong): textarea border, empty step and need tracks, scrollbar thumb, example-chip outline.
- **Lamp Text** (text), **Soft Text** (text-2), **Muted Sage** (muted): primary copy, secondary copy, and metadata respectively.

### Named Rules
**The Single Light Rule.** Amber is the only warm light in the chrome and there is one amber action per region. If two amber fills compete in the same panel, one of them is wrong.

**The Mint Means Proven Rule.** Mint appears only where the world has confirmed something: a completed step, a live connection, a healthy need. It is never decoration.

**The District Hue Rule.** District colours come from layout data (set per chip as `--district-color`) and appear only as an 8px dot, or as a 24% tint with a 45% edge when the district is active. They are never hard-coded into the stylesheet.

## Typography

**Display Font:** Segoe UI Variable Text (with Segoe UI, system-ui, -apple-system, sans-serif)
**Name Font:** Georgia (with Iowan Old Style, Palatino Linotype, serif)
**Data Font:** Cascadia Mono (with Consolas, ui-monospace, monospace)

**Character:** A plain, well-set system sans carries the whole instrument; a single old-style serif is kept for the clock and resident names so that time and people read as warmer than the machinery around them. Mono appears only where a value is literally data.

### Hierarchy
- **Display** (650, clamp(1.375rem, 1.05rem + 0.8vw, 1.75rem), 1.15, -0.02em): the world heading above the stage. One per page.
- **Name** (Georgia 400, 1.875rem, 1.05): the selected resident's name in the sidecar portrait.
- **Clock** (Georgia 400, 1.625rem, 1, tabular figures, amber): the town clock in the masthead; 1.25rem at 520px and below, 1.0625rem at 380px and below.
- **Headline** (600, 1.0625rem): depth-card headings.
- **Title** (550 to 600, 0.875rem): task titles, tools summary, sub-headings in tools.
- **Body** (400, 0.875rem, 1.6): paragraphs and the composer.
- **Body small** (0.8125rem): controls, chat lines, memories, section notes; the default size of every button.
- **Label** (0.75rem): hints, footers, need labels, example chips, compact actions.
- **Status** (650, 0.6875rem): the connection-mode pill (uppercase, 0.12em tracking) and request status chips (capitalized, 0.04em). Status words only.
- **Data** (Cascadia Mono, 0.75rem, 1.55): event timestamps, replay time, memory metadata, scenario JSON and its output.

### Named Rules
**The Two Serifs Rule.** Georgia is used in exactly two places: the clock and the resident's name. Headings, buttons, and labels stay in the system sans.

**The Mono Is Data Rule.** Cascadia Mono marks machine values (timestamps, scores, JSON). Human prose never goes mono, and running counts use tabular figures in the sans instead.

## Layout

A two-column shell, max 1760px wide, centred, with 18px top and clamp(16px, 2.2vw, 32px) side padding. The left column is fluid and holds the world: the heading row, the stage (canvas height clamp(440px, 66vh, 780px)), and a one-line footer of model and usage metrics. The right column is the resident sidecar, 372px wide (400px at 1600px and above, 330px at 1180px and below), sticky 82px from the top and scrolling internally. Below the world column, the depth grid runs two equal columns with a 16px gap; requests and tools span both.

The stage carries two control rails. Below 1340px they dock as rows above and below the canvas; at 1340px and above they float inside the stage 14px from its edges as glass groups, and the camera is re-framed so the town never sits under them. At 860px and below the shell collapses to one column in the order town, resident, requests; rails become single horizontally scrolling rows faded out at the right edge, the canvas drops to clamp(260px, 40vh, 420px), and finished requests become two unboxed lines each. At 520px the masthead shrinks to 56px and the save action hides.

Spacing moves on a 4px base (4, 6, 8, 12, 14, 16, 18, 20); panels pad 18px by 20px, cards 14px. On coarse pointers every control grows to 44px (tabs to 48px). Breakpoints: 380, 520, 860, 1180, 1340, 1600.

### Named Rules
**The World First Rule.** The stage owns the first viewport at every width; depth content always starts below it, never beside it.

## Elevation & Depth

Depth is tonal first: the page steps from ink to panel to raise to raise-2, each separated by a 1px hairline. Shadows are reserved for surfaces that float over something else. The stage itself gets depth from light, not shadow: a radial pool (#2c3d2e at centre falling to #0d1513) and a 45% black vignette at its edges.

### Shadow Vocabulary
- **Float** (`box-shadow: 0 12px 32px -10px rgb(0 0 0 / 0.55), 0 2px 6px rgb(0 0 0 / 0.35)`): glass rail groups at 1340px and above, the toast, the connection pill. Always dark and offset downward; never coloured.
- **Canvas label** (canvas shadow rgba(0,0,0,.45), blur 8, offset 2): place and resident labels drawn on the town; speech bubbles use blur 10, offset 3.

### Named Rules
**The Rest Or Float Rule.** A resting surface has a 1px border and no shadow; a floating surface has a shadow and no border. Never both.

**The Clear Glass Rule.** Glass over the live canvas is a 90% opaque dusk fill (rgb(14 23 20 / 0.9)), never a backdrop blur; the town under it keeps moving and stays sharp.

## Shapes

Softly rounded, nested radii that tighten as they go inward: 22px for the two big containers (stage and sidecar), 16px for the portrait plate, 14px for depth cards, 12px for task cards, memories, chat bubbles and rail groups, 10px for controls, 8px for tab tops. Status chips, example chips, the hint and the connection pill are full pills. Chat bubbles pinch one corner to 4px toward the speaker. Step and need tracks are 5 to 6px bars with fully rounded ends. Icons are 16px single-stroke SVG (1.8 stroke, round caps).

## Components

### Buttons
Quiet, tactile, and compressible.
- **Shape:** gently rounded (10px), 36px tall, 1px hairline border on raised moss.
- **Primary:** amber fill with amber-ink text at weight 650; the send button is full width, 42px, label left and arrow icon right.
- **Hover / Focus:** hover (fine pointers only) raises an overlay's opacity to 7% of the text colour (12% white on primary) over 150ms; nothing else animates. Focus is a 2px amber outline at 2px offset. Press scales to 0.97 over 160ms on the ease-out curve; reduced motion swaps the scale for 0.85 opacity.
- **Rail buttons:** transparent and borderless inside a panel-coloured group, 32px tall.
- **Disabled:** 45% opacity, not-allowed cursor.

### Chips
- **District chips:** an 8px dot in the district's own colour before the name; active adds a 24% district tint and a 45% district edge.
- **Example chips:** transparent pill with a strong-hairline outline and soft text.
- **Status chips:** pill, status weight; neutral on raise-2, mint for completed, caution for blocked and paused, coral for failed, cancelled and declined.

### Cards / Containers
- **Corner Style:** 14px depth cards, 22px sidecar, 12px inner cards.
- **Background:** panel for containers, raise for cards inside them.
- **Shadow Strategy:** none at rest (see Elevation & Depth).
- **Border:** 1px hairline.
- **Internal Padding:** 18px by 20px on depth cards, 18px on the sidecar, 14px on task cards.

### Inputs / Fields
- **Style:** the composer is a sunken well: ink background, strong hairline, 10px radius, 84 to 200px tall. Selects match buttons with a drawn chevron.
- **Focus:** the border turns amber with a flush 2px amber outline (the only place amber touches an edge, and only while focused).

### Navigation
- **Sidecar tabs (Talk, Memories, Plans):** equal-width, 40px, muted text; the active tab turns to lamp text at 600 and an amber 2px underline grows from the centre (scaleX 0 to 1, 200ms ease-out). Tabs do not press-scale.
- **Input modes (Chat, Assign task):** a segmented control sunk into an ink well; the active segment lifts to raise-2.
- **Resident switcher:** a grid of small buttons; the active resident is filled amber.

### The Stage (signature component)
The rounded 22px stage holds the canvas under a radial light pool and vignette. While the artwork loads the stage is dim (a 92% ink veil, the canvas at 60% opacity and scale 0.97); once loaded, the veil lifts and the town settles to full size over 900ms on the ease-out curve. The veil exists only while dim, so a script failure never leaves the town hidden. On the canvas, labels are 11px sans on a dark rounded plate with an optional district dot, speech bubbles are warm paper (#fff6e6) with dark text, the selected resident stands in an amber ring and the visitor in a mint ring, and the portrait sits on a soft amber pool of light.

### Request Afterglow
When a request changes state its status chip snaps to the new colour, and a radial amber glow behind it fades from full to nothing over 1100ms. Values never tween; the afterglow is the transition.

### Toast
Raise-2 plate, 12px radius, float shadow, fixed 24px from the bottom. It rises and fades in over 400ms and hides with visibility delayed until the fade completes.

## Do's and Don'ts

### Do:
- **Do** keep the stage the brightest thing on screen; chrome steps only from ink (#0b1311) to raise-2 (#1f2e29).
- **Do** spend amber on light: one primary fill per region, the clock, timestamps, the active underline, focus, and the selected ring.
- **Do** reserve mint for states the world has verified (completed steps, live connection, need levels).
- **Do** give resting surfaces a 1px hairline and no shadow, and floating surfaces the float shadow and no border.
- **Do** animate only transform and opacity, on the ease-out curve (cubic-bezier(0.23, 1, 0.32, 1)); gate hover behind (hover: hover) and (pointer: fine).
- **Do** keep reduced-motion users' state legible: keep opacity changes, drop scale and translation.
- **Do** grow every control to 44px on coarse pointers.
- **Do** let district hues come from data, as dots and tints only.

### Don't:
- **Don't** use Georgia anywhere except the clock and the resident name.
- **Don't** set prose, headings, or buttons in mono; mono is for timestamps, metadata, and JSON.
- **Don't** use amber as a border or divider colour on chrome; amber is light, not a line.
- **Don't** put coloured box-shadow halos on chrome; the only coloured glows are the radial light pools of the stage, the portrait, and the request afterglow.
- **Don't** blur what sits over the live canvas; glass is an opaque dusk fill.
- **Don't** add eyebrow kickers or tracked uppercase labels above headings; uppercase tracking is kept for the connection-status pill and memory kind labels.
- **Don't** tween changing numbers or colours; snap them and let the afterglow mark the change.
- **Don't** shrink the town into one tile among many dashboard panels.
