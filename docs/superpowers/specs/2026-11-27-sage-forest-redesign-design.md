# Sage & Forest redesign of the Scene Filter screen

Mockups agreed with the owner: https://claude.ai/artifact/QAHnYagQ3owgFLPkbf2rbX (light and dark side by side).

## Intent

Scene Filter works but looks like a developer tool (stock Gradio: orange buttons, one long column, technical
labels). Its users are parents. The owner wants it **sleek and modern, with forest green as the main color**, so it
feels like a finished product someone would trust with family movie night.

## Goals

- **Light mode, "Sage & Forest":** soft pastel sage page, white cards, forest green for everything clickable, a modern
  rounded typeface, small pastel tags for what was detected.
- **Dark mode, its twin:** the same design with the colors flipped. Deep forest-green page (not black), slightly
  lighter green cards, soft sage buttons with dark text, pastel tags toned down. Follows the computer's light/dark
  setting automatically.
- **Simpler layout in three sections, Movie → Review → Save,** as in the mockup:
  - **Movie:** drop area or "Choose movie...", the chosen movie's name, the "Animated movie" switch, and a
    "Detection settings" section that is closed by default; then the **Scan movie** button.
  - **Review:** a big count ("2 scenes flagged"), a badge saying whether the accurate detector double-checked them,
    and the flagged scenes, each with a tick box, its time range, a pastel tag naming what was detected, and its
    confidence. Blurred previews stay available.
  - **Save:** the filter choice as one row of buttons (Cut out / Blur / Black screen / Times only), the mute option,
    **Save filtered movie**, and the result message and files.
- Version number shown in the header.

## Non-goals

- No change to scanning, filtering, saving, the starter or auto-updates. Same inputs and outputs as today.
- No new features (no Plex, no language filter, no posters fetched from the internet).

## Anti-goals (a failure even if it looks nice)

- Anything that used to work stops working: unticking scenes, the progress bar, choosing a movie, saving.
- Text that's hard to read in either mode, or a mode that looks unfinished.
- Labels getting *more* technical.

## Constraints

- Ships as a normal update (`app/` only, `app/VERSION` raised), so installed copies get it automatically.
- No new packages. Gradio 6, as today.
- Fonts load from Google Fonts with system fallbacks, so the app still looks right offline.

## Approaches

1. **Restyle the existing Gradio screen** with a custom theme and CSS, regrouped into the three sections.
   **Chosen** (Claude's call; the owner handed over the how): gets very close to the mockup, keeps every working
   part working, low risk. A few mockup details may come out simpler (the poster thumbnail).
2. Rebuild the screen as a custom web page. Pixel-perfect, but rewrites file picking, progress and the scene table
   that work today. Rejected: lots of new code for a small visual gain.

## Decided

- Palettes, from the agreed mockup:

  | Role | Light | Dark |
  |---|---|---|
  | Page | `#e7efe8` sage | `#10241a` deep forest |
  | Cards | `#ffffff` | `#173226` |
  | Text | `#15281d` | `#e3efe6` |
  | Muted text | `#5d7366` | `#9ab8a4` |
  | Borders | `#d5e1d8` | `#24432f` |
  | Buttons / accent | `#1f5136` forest, light text | `#a8d5b5` sage, dark text `#0f2418` |
  | "Double-checked" badge | `#dcefe1` / `#1f5c3b` | `#1f4331` / `#bfe6cb` |
  | Detection tags | `#f6e6dc` / `#8a4a2c` | `#3a2b24` / `#f0c9b2` |

- Typeface: Plus Jakarta Sans for everything, JetBrains Mono for timestamps.

## Left to the builder

- How the scene list is drawn (styled Gradio table vs. tick boxes plus a styled summary), as long as unticking still
  works and each scene shows time, tag and confidence.
- Exact spacing, corner radii and how close Gradio's controls can get to the mockup.
- Wording tweaks that make labels plainer.
