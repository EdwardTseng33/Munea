# Handoff: Munea 沐寧 — Bottom Navigation Bar

## Overview
A floating bottom tab bar for the Munea (沐寧) elder-care companion app. Five destinations —
**首頁 / 狀態 / 聊聊 / 家人 / 設定** — on a dark graphite-black rounded bar, with a raised
circular "cradle" in the center that wraps a teal floating action button (the 聊聊 / voice
companion action).

## About the Design Files
The file in this bundle (`V1-Home.html`) is a **design reference created in HTML** — a
prototype showing the intended look and behavior, **not production code to copy directly**.
Recreate this navigation bar in the target codebase's existing environment (React Native,
SwiftUI, Flutter, React web, etc.) using its established patterns, component library, and icon
set. If no environment exists yet, pick the framework most appropriate for the project.

The bar shape (rounded rectangle + center bump) is drawn as a single **inline SVG path** so the
concave fillet junctions render crisply — replicate it with an SVG/vector path, a custom shape,
or a Canvas/`Path` in the target platform. Do **not** fake it with a plain rounded rectangle +
a floating circle; the smooth cradle is the whole point.

## Fidelity
**High-fidelity (hifi).** Final colors, sizing, proportions, and states are specified below to
the pixel. Recreate pixel-perfectly using the codebase's own tokens/components. Exact hex values
are given; map them to existing design tokens where they already exist.

---

## The Component

### Layout
- The bar is a horizontal container, full width minus side gutters, pinned to the bottom safe area.
- Design width reference: **358px** wide bar inside a 390px-wide phone frame (≈15px side gutters +
  the frame padding). Treat measurements as **ratios**, not absolutes — scale to device width.
- Bar occupies a container **84px tall** (`.nav`); the visible dark bar sits in the lower **56px**
  of that box, and the top ~28px is reserved for the FAB + center bump to rise into.
- Five tab items are laid out in a `flex` row, each `flex:1`, content bottom-aligned
  (`align-items:flex-end`), with **22px horizontal padding** on the row so the outer items
  (首頁 / 設定) are pulled inward (spacing between the 5 items is intentionally tight, not edge-to-edge).
- Each tab item is a vertical stack: **icon on top, label below**, `gap:5px`, `padding-bottom:12px`.

### The bar shape (SVG)
Drawn as one filled path in a `viewBox="0 0 358 84"` SVG with `preserveAspectRatio="none"`,
`fill: var(--ink)` (#3A352E), and a drop shadow `drop-shadow(0 14px 26px rgba(0,0,0,.3))`.

```
M20,28 L141,28 A8 8 0 0 0 149.3,24 A31 31 0 0 1 208.7,24 A8 8 0 0 0 217,28
L338,28 A20 20 0 0 1 358,48 L358,62 A20 20 0 0 1 338,82
L20,82 A20 20 0 0 1 0,62 L0,48 A20 20 0 0 1 20,28 Z
```

Reading of the path (all in the 358×84 viewBox):
- **Bar body:** rounded rectangle, top edge y=28, bottom edge y=82 (height 54), left x=0, right x=358.
- **Corner radius: 20** (all four corners) — moderately rounded, NOT a full pill/stadium and NOT
  sharp. Ratio ≈ 0.37 × bar height.
- **Center bump:** a circular arc of **radius 31**, concentric with the FAB, centered at (179, 39).
  It rises to a peak at y=8, giving a dark "cap" that wraps up and over the FAB.
- **Fillet junctions:** where the bump meets the flat top edge there is a small **radius-8 concave
  arc** on each side (the `A8 8 0 0 0 …` segments) — this is the smooth S-shaped join the design
  requires. Without these fillets the join looks like a hard kink; keep them.

### The center FAB (聊聊)
- Circle **44×44px**, `border-radius:50%`, absolutely centered horizontally, top offset **11px**
  from the top of the 84px container (so its center sits ~y=33 and it nestles into the bump with a
  thin dark cap above it and a uniform ~9px dark margin wrapping its sides).
- Background: **`var(--teal)` #3AA8A0** (design-system 薄荷綠 / primary). **No drop shadow.**
- Icon inside: a **microphone** outline, white (`#fff`), 20×20, stroke-width 2.2, round caps/joins.
- z-index above the bar background; the bar's dark bump wraps and *exceeds* the FAB (bump is wider
  than the circle), so the FAB reads as cradled, not floating on top.

### Tab items (the four regular tabs + the center label)
| Order | Label | Icon (outline, stroke = currentColor) |
|---|---|---|
| 1 | 首頁 (Home) | house |
| 2 | 狀態 (Status) | activity / pulse line |
| 3 | 聊聊 (Chat) | *(label only; the FAB above is this tab's control — microphone icon)* |
| 4 | 家人 (Family) | **two-person** "users" icon |
| 5 | 設定 (Settings) | horizontal **sliders** (two rows w/ knobs) |

- Regular tab icons: 20×20, stroke-width **1.7**, round caps/joins, `fill:none`.
- Labels: font-size **10px**, weight **600**, letter-spacing **.05em**, line-height 1.
- The center "聊聊" item has no icon of its own (the FAB is the control); it shows only its label,
  bottom-aligned like the others.

### Colors / states
- **Inactive tab (icon + label):** `var(--cream)` **#F4F0E8** (a warm off-white — deliberately NOT
  pure #fff, which was too stark on the dark bar).
- **Active tab (icon + label):** `var(--teal)` **#3AA8A0** (薄荷綠). Active label weight bumps to **800**.
  In the prototype 首頁 is the active tab.
- Bar fill: `var(--ink)` **#3A352E** (規範石墨黑 / graphite black).
- Transition on color: `.15s`.

---

## SVG icon paths (24×24 viewBox, fill:none, stroke=currentColor, round caps/joins)
Use these or the codebase's equivalent icon set — match the visual weight (thin, ~1.7–2px stroke).

- **Home (首頁):** `M3 11l9-8 9 8` + `M5 10v10h14V10`
- **Status (狀態):** `M22 12h-4l-3 9L9 3l-3 9H2`
- **Microphone (FAB / 聊聊):** `M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z` +
  `M19 10v2a7 7 0 0 1-14 0v-2M12 19v3`
- **Family (家人, two people):** `M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2` + `circle cx=8.5 cy=7 r=4`
  + `M22 21v-2a4 4 0 0 0-3-3.87` + `M15.5 3.13a4 4 0 0 1 0 7.75`
- **Settings (設定, sliders):** `M4 8h9M17 8h3M4 16h3M11 16h9` + `circle cx=15 cy=8 r=2.3`
  + `circle cx=9 cy=16 r=2.3`

---

## Interactions & Behavior
- Tapping a tab switches the active destination; only one tab is `active` at a time. Active =
  teal icon + teal bold label.
- The center FAB opens the 聊聊 (voice companion) flow. Tap target ≥44px (it is exactly 44px; pad the
  hit area to ≥48px if the platform guideline requires).
- Color changes animate over ~150ms. No bounce/scale on the FAB in this design.
- Bar is fixed to the bottom; respect the device safe-area inset below it.

## State Management
- One piece of state: `activeTab` (enum: home | status | chat | family | settings).
- The FAB action (聊聊) may be modal/overlay rather than a tab route — confirm with product; in the
  prototype it's presented as the prominent center control.

## Design Tokens (from the app's palette — map to existing tokens)
```
--teal        #3AA8A0   薄荷綠 (primary / active / FAB)
--teal-d      #2E8A83   薄荷綠·深 (pressed / text)
--teal-dd     #236C66   深綠 (text emphasis only)
--coral       #D98841   暮色橘 (accent — times, medication)
--coral-d     #A8611E   暮色橘·深
--ink         #3A352E   石墨黑 (nav bar fill, primary text)
--muted       #5A6963   muted text (secondary labels, dates)
--cream       #F4F0E8   米白 (app background; inactive nav tint)
--mint        #E8F2EE   / --mint2 #D9EFE8  soft mint tiles
--line        #EAE3D6   hairline borders
```
Nav-specific numeric tokens:
```
bar height (container)   84px         corner radius        20
visible bar height       54px         bump arc radius      31 (concentric w/ FAB)
FAB diameter             44px         fillet radius         8
FAB top offset           11px         row side padding     22px
tab label size           10px / 600   active label weight  800
regular icon stroke      1.7          FAB icon stroke      2.2
```

## Assets
No raster assets — all icons are stroke SVG paths (listed above). Fonts in the prototype:
**Noto Sans TC** (UI) and **Noto Serif TC** (headings); substitute the codebase's brand fonts.

## Files
- `V1-Home.html` — the full home screen prototype; the navigation bar is the `<nav class="nav">`
  block near the end of `<body>`, with its styles under the `/* navbar */` comment in the `<style>`
  head. The rest of the screen (companion card, task list) is included for context on surrounding
  styling and token usage.
