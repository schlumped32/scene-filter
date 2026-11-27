# Light/dark switch and "Look closer" previews (version 9)

## Intent

Two additions the owner asked for after version 8:

1. Let people choose light or dark themselves instead of it always following the computer.
2. Let a parent get a better look at a flagged scene **after** the scan, to judge whether it needs filtering,
   without ever showing it fully clear. Today the only option is the "Show unblurred preview images" setting,
   chosen before the scan and all-or-nothing.

## Goals

- **Light/dark switch:** a small sun/moon button in the header next to the version pill. The app follows the
  computer's setting until the button is clicked; after that it remembers the choice the next time it opens.
- **Look closer, per scene:**
  - Each scene row gets a small, **heavily blurred** thumbnail at its left. The separate "Previews" strip is removed.
  - Each row has a **Look closer** button. It opens a larger, **lightly blurred** view under that scene only;
    **Blur again** closes it. Other scenes stay heavily blurred.
  - Light blur: enough to tell what kind of scene it is (a beach from a bedroom), no detail.
- Remove the "Show unblurred preview images" setting.
- Ship as version 9 (auto-update).

## Non-goals / anti-goals

- Never a fully clear preview, by any path. The clear frame is used only to make the two blurred versions, and is
  never saved to disk or sent to the screen.
- No change to detection, filtering or saving. Ticking/unticking scenes must keep working exactly as now.

## Approaches

1. **Make both blur levels at scan time; "Look closer" swaps between them in the page.** *Chosen (Claude's call,
   approved by the owner):* instant, works offline, and the clear frame never leaves memory.
2. Make the lighter version on demand from a clear copy kept on disk. Rejected: slower, and keeps a clear picture
   on disk.

## Decided

- One lighter step only (heavy → light), not several.
- The theme switch remembers its choice in the browser on that computer.

## Left to the builder

- Exact blur strengths (heavy stays about as strong as today's pixelation; light per the goal above).
- Thumbnail size, and how the larger view is laid out at phone width.
