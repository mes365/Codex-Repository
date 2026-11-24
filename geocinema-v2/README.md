# GeoCinema V2.0 — work in progress

This directory is an isolated project under the `geocinema-v2` branch. It is not a finished renderer.

## Reference observations

The supplied `Claude.mp4` is 64.534 seconds, 1080 × 1920. Sampled images show a space-to-Earth opening, a world map with subtropical latitude lines, circulation diagrams, a Cairo–Wuhan precipitation comparison, the Tibetan Plateau, monsoon streamlines, a geological-history sequence, and an Earth closing shot. Preserve this structure as a visual benchmark; check the narration and factual claims independently before finalizing the script.

## Terrain feasibility check

Run `node check-terrain.cjs [output.png]` to download a public Terrarium elevation tile (zoom 5, x 23, y 13). Decode RGB elevation as `R * 256 + G + B / 256 - 32768` metres. The downloaded sample was 256 × 256; observed elevations ranged from −1 to 7188 m. This confirms access and decoding of one tile, not a complete terrain pipeline. Verify source attribution and terms for any final assets.

## Outstanding work

- Inspect the full reference, including audio and exact timing; draft and fact-check the narration.
- Implement terrain coverage, three-dimensional rendering, animation, text, audio, and native-resolution frame export.
- Build, run, and debug a separate GitHub Actions workflow; verify the resulting MP4 with a media probe and visually against the reference.

## Experimental terrain preview

The prototype downloads four Terrarium tiles and Three.js, builds an elevation mesh, and renders 150 distinct 1080 × 1920 frames at 30 fps using Playwright and FFmpeg. It is a **five-second silent technical preview**, not the requested final film. Mesh heights are vertically exaggerated, colors are schematic, and geographic fidelity, narration, satellite imagery, and cinematic quality remain unfinished. It was visually tested locally as a still; MP4 and the Actions workflow must still be verified.

Requirements: Node.js 20+, Playwright Chromium, FFmpeg with libx264. From this directory run `npm install`, `npx playwright install chromium`, `npm run assets`, then `npm run render`. Output is `output/terrain-preview.mp4`. `npm run preview` renders a single still.

Terrain tiles: [Mapzen/Tilezen elevation tiles](https://github.com/tilezen/joerd/blob/master/docs/formats.md), Terrarium format, z5 x23–24 y12–13. Consult the [terrain attribution guidance](https://github.com/tilezen/joerd/blob/master/docs/attribution.md) and underlying source licenses before publication. Three.js is MIT licensed.

## Second prototype (in progress)

The timeline now includes an Earth view, Tibetan terrain textured with NASA Blue Marble, and schematic monsoon lines. The 18-second output is still silent and is not the full film. The Earth image is NASA Blue Marble Next Generation, July 2004: https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/ . The land-only base map is artistically recolored over dark regions to suggest ocean; it must not be presented as measured ocean imagery. The terrain is zoom 5 and the texture is coarse. The flow lines are artistic illustrations, not atmospheric observations. Further work includes movement, correct ocean imagery, geographical validation, narration, science review, scene transitions, and comparison with the reference.
