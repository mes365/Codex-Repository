const fs = require('node:fs/promises');
const path = require('node:path');
const assets = [
  ['three.module.js', 'https://unpkg.com/three@0.170.0/build/three.module.js'],
  ['earth.jpg', 'https://assets.science.nasa.gov/content/dam/science/esd/eo/images/bmng/bmng-base/july/world.200407.3x5400x2700.jpg'],
  ...[[23,12],[24,12],[23,13],[24,13]].map(([x,y]) => [`5-${x}-${y}.png`, `https://s3.amazonaws.com/elevation-tiles-prod/terrarium/5/${x}/${y}.png`])
];
(async()=>{await fs.mkdir(path.join(__dirname,'assets'),{recursive:true});for(const [name,url] of assets){const response=await fetch(url,{signal:AbortSignal.timeout(60000)});if(!response.ok)throw Error(`${url}: HTTP ${response.status}`);let data=Buffer.from(await response.arrayBuffer());if(data.length<1000)throw Error(`Unexpectedly small asset: ${name}`);await fs.writeFile(path.join(__dirname,'assets',name),data);console.log(name,data.length);}})().catch(e=>{console.error(e);process.exitCode=1});

