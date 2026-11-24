const fs = require('node:fs/promises');
const url = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/5/23/13.png';
(async () => {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Terrain download failed: ${response.status}`);
  await fs.writeFile(process.argv[2] || 'terrain-5-23-13.png', Buffer.from(await response.arrayBuffer()));
  console.log(`Downloaded ${url}`);
})().catch(error => { console.error(error); process.exitCode = 1; });
