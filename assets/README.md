# Smallworld Agents — Original Isometric Assets

These assets were created specifically for this project's first neighborhood: a cafe, a shop, two homes, a park, five residents, and a player. Raster illustrations were generated with the built-in image generation tool; interface icons were authored as SVG. No stock asset pack is used.

The visual direction is a fixed 2.5D isometric camera, warm illustrated buildings, diamond ground tiles, and eight-direction characters. The earlier top-down terrain experiment is superseded.

Source prompts are retained in `sources/prompts.json` and `sources/character-prompts.json`. The manifest records measured image sizes and frame rectangles; requested image dimensions are not assumed to be the output dimensions. Source sheets are preserved intact, and the preview reads their rectangles directly.

Buildings in the initial sheet are complete exterior sprites. Separate roof and wall pieces for enterable interiors are a subsequent integration asset; a complete exterior sheet must not be described as supporting roof removal. Animation and tiling quality are verified in the preview before production integration.

The initial pack contains 16 terrain tiles, 4 building exteriors, 16 props, six character sheets with 32 source frames each, and 8 interface icons: 236 source frames/icons in total. All nine final PNG sheets have verified transparent pixels and measured sprite bounds. Use `manifest.json` as the authoritative list of final files; some opaque drafts are retained and must not be loaded by the game. Final character files use the `-alpha` suffix except Maya.

Character rows are mapped to S, SW, W, NW, N, NE, E, SE. The manifest corrects mislabeled generated directions with the renderer's native horizontal flip for Elena, Samir, and Alex. Source images are unchanged. Frames use measured silhouettes and head-centered horizontal anchors with a feet baseline; animation remains illustrative and may benefit from further cleanup for a production-quality gait. Jun's passing poses have visible variation from the other residents.

Open `asset-preview.html` from the project root in a browser. It can also be served locally with `python -m http.server 8765 --bind 127.0.0.1`, then opened at http://127.0.0.1:8765/asset-preview.html. The preview has scripted walking, character selection, eight-facing animation inspection, click-to-walk for Alex, zoom, pan, pause, and a browsable gallery. Speech in this separate preview is sample text. The actual playable application uses these same assets with a Python simulation backend: run `python run.py` and open http://127.0.0.1:8766/. See the root README.md for task execution and optional live model configuration.

Run `node tools/inspect-assets.mjs` from the project root to rebuild `manifest.json` and `manifest.js`. This tool only reads PNG pixels and writes metadata, leaving generated artwork intact. Runtime terrain rendering maps source diamonds onto exact 2:1 ground diamonds to align the grid. The preview uses one ground level and complete building exteriors; layered occlusion and enterable interiors remain implementation work.

Visual review completed on the local preview: terrain and buildings render together; character sprites have real transparency; all source frames and gallery items load. Inspect the walk cycles at the intended in-game scale before adding more residents.
