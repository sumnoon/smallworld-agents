# Vibrant town expansion artwork

Four original sprites generated with the built-in image-generation tool for Smallworld Agents. Source PNGs are copied intact, including their generated alpha channels; no stock pack or external artwork is used. Their measured bounds are in [the manifest](../manifest.json), and the complete production prompts are in [expansion-prompts.json](../sources/expansion-prompts.json).

| Saved asset | Measured source size | Fully transparent pixels |
| --- | --- | --- |
| [market-pavilion.png](market-pavilion.png) | 1536 x 1024 | 51% |
| [garden-conservatory.png](garden-conservatory.png) | 1402 x 1122 | 49.2% |
| [plaza-fountain.png](plaza-fountain.png) | 1536 x 1024 | 62.3% |
| [blossom-tree.png](blossom-tree.png) | 1355 x 1160 | 51.5% |

The market pavilion uses coral-striped awnings and colorful produce. The conservatory combines teal glass framing, terracotta and flowering vines. The fountain brings turquoise water to the plaza. Peach-pink blossom trees repeat around the gardens and new streets.

Each sprite uses a fixed isometric view and a feet/base anchor. Runtime drawing reads the source bounds without cropping or changing the original PNG. Landmark collision footprints are explicit map data, not inferred from image dimensions. The greenhouse and pavilion are outdoor landmarks; this update does not add interiors for them.

Inspect the [actual expanded-map render](../../docs/media/expanded-town.png). Rebuild the manifest with `node tools/inspect-assets.mjs`.
