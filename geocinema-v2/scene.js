import * as THREE from './assets/three.module.js';
const width=1080, height=1920;
const renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});
renderer.setSize(width,height); renderer.setPixelRatio(1); renderer.setClearColor(0x020917); document.body.prepend(renderer.domElement);
const scene=new THREE.Scene(); const camera=new THREE.PerspectiveCamera(35,width/height,0.1,100);
scene.add(new THREE.HemisphereLight(0xc8dcff,0x243029,2)); const sun=new THREE.DirectionalLight(0xffd8a4,3);sun.position.set(-3,8,4);scene.add(sun);
const urls=[[23,12],[24,12],[23,13],[24,13]].map(([x,y])=>`./assets/5-${x}-${y}.png`);
const images=await Promise.all(urls.map(url=>new Promise((resolve,reject)=>{const im=new Image();im.onload=()=>resolve(im);im.onerror=reject;im.src=url;})));
const cvs=document.createElement('canvas');cvs.width=512;cvs.height=512;const ctx=cvs.getContext('2d',{willReadFrequently:true});images.forEach((im,i)=>ctx.drawImage(im,(i%2)*256,Math.floor(i/2)*256));const pixels=ctx.getImageData(0,0,512,512).data;
const segments=255, geom=new THREE.PlaneGeometry(8,8,segments,segments);const pos=geom.attributes.position;const colors=[];for(let i=0;i<pos.count;i++){let u=i%(segments+1),v=Math.floor(i/(segments+1));let k=(Math.min(511,v*2)*512+Math.min(511,u*2))*4;let h=pixels[k]*256+pixels[k+1]+pixels[k+2]/256-32768;pos.setZ(i,Math.max(0,h)*0.00007);let c=new THREE.Color(); if(h>4600)c.set(0xd8d3bf);else if(h>3000)c.set(0x997b5c);else if(h>1300)c.set(0x6d7553);else c.set(0x3b654b);colors.push(c.r,c.g,c.b);}geom.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));geom.computeVertexNormals();const terrain=new THREE.Mesh(geom,new THREE.MeshStandardMaterial({vertexColors:true,roughness:1,side:THREE.DoubleSide}));terrain.rotation.x=-Math.PI/2;scene.add(terrain);
window.renderAt=(t)=>{const angle=-0.35+t*0.06;camera.position.set(9*Math.sin(angle),7.0,9*Math.cos(angle));camera.lookAt(0,0,0);renderer.render(scene,camera)};window.renderAt(0);window.sceneReady=true;

