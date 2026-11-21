/* Deterministic offline build of Tailwind utilities used by the dashboard.
   Requires Tailwind CSS 4.x during development, NOT when running the app.
   Example: node web/build_tailwind.js (from project root, with module available).
*/
const fs=require('fs'),path=require('path');
let tw;
try {tw=require('tailwindcss')} catch(_){
  const options=['/opt/nvm/versions/node/v22.16.0/lib/node_modules/tailwindcss/dist/lib.js','/usr/local/slides_js/node_modules/tailwindcss/dist/lib.js'];
  let ok=false;
  for (const cand of options)if(fs.existsSync(cand)){tw=require(cand);ok=true;break}
  if(!ok)throw Error('Tailwind CSS 4.x não está instalado. Rode npm install -D tailwindcss.');
}
let themeFile;
try{themeFile=require.resolve('tailwindcss/theme.css')}catch(_){themeFile='/opt/nvm/versions/node/v22.16.0/lib/node_modules/tailwindcss/theme.css'}
const html=fs.readFileSync(path.join(__dirname,'index.html'),'utf8');
const candidateSet=new Set();
for (const hit of html.matchAll(/class=["']([^"']+)["']/g))for (const cls of hit[1].trim().split(/\s+/))candidateSet.add(cls);
const classes=[...candidateSet].filter(Boolean);
(async()=>{
 const css=fs.readFileSync(themeFile,'utf8')+'\n@tailwind utilities;';
 const c=await tw.compile(css);
 const output=c.build(classes);
 const dest=path.join(__dirname,'assets','tailwind.css');
 fs.writeFileSync(dest,output,'utf8');
 console.log(`Tailwind v4: ${classes.length} candidatos -> ${output.length} bytes em ${dest}`);
})().catch(e=>{console.error(e);process.exit(1)});
