import * as THREE from './vendor/three.module.min.js';

const canvas = document.querySelector('#game');
// Real phones report a coarse pointer.  The width fallback also keeps the
// controls available in mobile browser previews and split-screen mode.
const TOUCH_MODE = matchMedia('(pointer: coarse)').matches || navigator.maxTouchPoints > 0 || matchMedia('(max-width: 900px)').matches;
document.documentElement.classList.toggle('touch-device', TOUCH_MODE);
const ui = {
  command: document.querySelector('#commandScreen'), equipment: document.querySelector('#equipmentScreen'), result: document.querySelector('#resultScreen'),
  progression: document.querySelector('#progressionScreen'),
  equipmentButton: document.querySelector('#equipmentButton'), equipmentBackButton: document.querySelector('#equipmentBackButton'),
  talentButton: document.querySelector('#talentButton'), weaponLabButton: document.querySelector('#weaponLabButton'), progressionBackButton: document.querySelector('#progressionBackButton'),
  returnMenuButton: document.querySelector('#returnMenuButton'), restartButton: document.querySelector('#restartButton'),
  stageGrid: document.querySelector('#stageGrid'), weaponGrid: document.querySelector('#weaponGrid'),
  menuWeaponName: document.querySelector('#menuWeaponName'), menuScrap: document.querySelector('#menuScrap'),
  menuMaterials: document.querySelector('#menuMaterials'), resultMaterials: document.querySelector('#resultMaterials'),
  progressionTitle: document.querySelector('#progressionTitle'), progressionEyebrow: document.querySelector('#progressionEyebrow'),
  progressionMaterials: document.querySelector('#progressionMaterials'), progressionContext: document.querySelector('#progressionContext'), progressionRows: document.querySelector('#progressionRows'),
  resultTitle: document.querySelector('#resultTitle'), resultText: document.querySelector('#resultText'),
  healthText: document.querySelector('#healthText'), healthBar: document.querySelector('#healthBar'),
  armorText: document.querySelector('#armorText'), scrapText: document.querySelector('#scrapText'),
  missionText: document.querySelector('#missionText'), killText: document.querySelector('#killText'), comboText: document.querySelector('#comboText'),
  weaponName: document.querySelector('#weaponName'), ammoText: document.querySelector('#ammoText'), ammoBar: document.querySelector('#ammoBar'),
  levelText: document.querySelector('#levelText'), xpText: document.querySelector('#xpText'), xpBar: document.querySelector('#xpBar'),
  bossHud: document.querySelector('#bossHud'), bossName: document.querySelector('#bossName'), bossBar: document.querySelector('#bossBar'),
  upgrade: document.querySelector('#upgradeScreen'), upgradeEyebrow: document.querySelector('#upgradeEyebrow'), upgradeTitle: document.querySelector('#upgradeTitle'),
  upgradeContext: document.querySelector('#upgradeContext'), upgradeCards: document.querySelector('#upgradeCards'), upgradeSequence: document.querySelector('#upgradeSequence'),
  upgradeRefresh: document.querySelector('#upgradeRefreshButton'),
  damage: document.querySelector('#damageFlash'), message: document.querySelector('#message'), lookHint: document.querySelector('#lookHint'),
  stickBase: document.querySelector('#stickBase'), stickKnob: document.querySelector('#stickKnob'),
  jump: document.querySelector('#jumpButton'), roll: document.querySelector('#rollButton'), fire: document.querySelector('#fireButton'),
};

const AUDIO_PATH={
  combat:'assets/music/combat_loop_seamless.wav',boss:'assets/music/boss_loop.mp3',win:'assets/music/win_jingle_safari.wav',gameover:'assets/music/game_over.mp3',
  alarm:'assets/sfx/boss_alarm.wav',button:'assets/sfx/ui_button_thump.wav',gun:'assets/sfx/optimized/gun_short.wav',sniper:'assets/sfx/optimized/sniper_short.wav',
  shotgun:'assets/sfx/optimized/shotgun_short.wav',laser:'assets/sfx/optimized/laser_short.wav',flame:'assets/sfx/optimized/flame_short.wav',grenade:'assets/sfx/optimized/grenade_short.wav',
};
const audio={};let audioUnlocked=false,currentBgm='';const lastSfx={};
const BGM_KEYS=['combat','boss','win','gameover'];
const SFX_KEYS=['alarm','button','gun','sniper','shotgun','laser','flame','grenade'];
// Several source files contain long tails (gun: 2 s, flame: 7.7 s). Playing
// the complete file for every bullet left dozens of decoders and voices alive,
// which caused a frame hitch followed by a delayed, heavily layered sound.
// Only the useful attack portion is played and every sound has a strict voice
// budget, so sustained automatic fire has stable CPU/audio cost.
const SFX_POLICY={
  alarm:{duration:3.2,voices:1},button:{duration:.16,voices:1},gun:{duration:.13,voices:3},
  sniper:{duration:.72,voices:1},shotgun:{duration:.55,voices:1},laser:{duration:.22,voices:2},
  flame:{duration:.19,voices:2},grenade:{duration:.28,voices:1},
};
const sfxBuffers={};const sfxActive={};let sfxContext=null;let sfxLoadPromise=Promise.resolve();
// Safari blocks local file pages from loading media and ES modules reliably.
// Keep all audio work lazy and guarded so a media failure can never stop the UI.
try{
  // Music remains streamed, while short effects use one predecoded WebAudio
  // buffer. This prevents HTMLAudio from decoding the same shot on demand.
  for(const key of BGM_KEYS){const a=new Audio(AUDIO_PATH[key]);a.preload='auto';a.playsInline=true;audio[key]=a;a.load();}
  for(const key of ['combat','boss'])if(audio[key])audio[key].loop=true;
  if(audio.combat)audio.combat.volume=.14;if(audio.boss)audio.boss.volume=.18;if(audio.win)audio.win.volume=.42;if(audio.gameover)audio.gameover.volume=.30;
  const AudioContextClass=window.AudioContext||window.webkitAudioContext;
  if(AudioContextClass){
    sfxContext=new AudioContextClass({latencyHint:'interactive'});
    for(const key of SFX_KEYS)sfxActive[key]=[];
    sfxLoadPromise=Promise.all(SFX_KEYS.map(async key=>{
      const response=await fetch(AUDIO_PATH[key],{cache:'force-cache'});if(!response.ok)throw Error(String(response.status));
      sfxBuffers[key]=await sfxContext.decodeAudioData(await response.arrayBuffer());
    })).catch(error=>console.warn('Sound effect preload skipped:',error));
  }
}catch(error){console.warn('Audio setup skipped:',error);}
function unlockAudio(){if(audioUnlocked)return;audioUnlocked=true;sfxContext?.resume().catch(()=>{});if(playing)setBgm(boss?'boss':'combat');}
function stopSfxVoice(voice){
  if(!voice||!sfxContext)return;const t=sfxContext.currentTime;
  try{voice.gain.gain.cancelScheduledValues(t);voice.gain.gain.setValueAtTime(voice.gain.gain.value,t);voice.gain.gain.linearRampToValueAtTime(0,t+.008);voice.source.stop(t+.01);}catch{}
}
function playSfx(kind,volume=.2,minGap=.04){
  try{
    if(!audioUnlocked)return;const now=performance.now()/1000;if(now-(lastSfx[kind]||-99)<minGap)return;lastSfx[kind]=now;
    const buffer=sfxBuffers[kind];if(!sfxContext||!buffer)return;
    if(sfxContext.state==='suspended')sfxContext.resume().catch(()=>{});
    const policy=SFX_POLICY[kind]||{duration:.25,voices:1};const active=sfxActive[kind]||(sfxActive[kind]=[]);
    while(active.length>=policy.voices)stopSfxVoice(active.shift());
    const source=sfxContext.createBufferSource(),gain=sfxContext.createGain(),voice={source,gain};
    source.buffer=buffer;gain.gain.setValueAtTime(volume,sfxContext.currentTime);source.connect(gain).connect(sfxContext.destination);active.push(voice);
    source.onended=()=>{const index=active.indexOf(voice);if(index>=0)active.splice(index,1);try{source.disconnect();gain.disconnect();}catch{}};
    source.start(0,0,Math.min(policy.duration,buffer.duration));
  }catch{}
}
function setBgm(kind){try{if(currentBgm===kind)return;for(const key of ['combat','boss','win','gameover']){const a=audio[key];if(a&&key!==kind){a.pause();a.currentTime=0;}}currentBgm=kind||'';if(audioUnlocked&&kind&&audio[kind]){const a=audio[kind];a.currentTime=0;a.play().catch(()=>{});}}catch{currentBgm=kind||'';}}
addEventListener('pointerdown',unlockAudio,{once:true,capture:true});addEventListener('keydown',unlockAudio,{once:true,capture:true});
document.addEventListener('pointerdown',e=>{if(e.target.closest('button'))playSfx('button',.34,.045);},{capture:true});
document.addEventListener('click',e=>{if(e.detail===0&&e.target.closest('button'))playSfx('button',.34,.045);});

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x111719);
scene.fog = new THREE.FogExp2(0x101719, 0.018);
const camera = new THREE.PerspectiveCamera(64, innerWidth / innerHeight, 0.08, 260);
scene.add(camera);
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio, TOUCH_MODE ? 1 : 1.25));
renderer.setSize(innerWidth, innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
// Hundreds of ruined-city pieces are visible at once. Dynamic shadows on every
// fragment are much more expensive than the stylised baked lighting used here.
renderer.shadowMap.enabled = false;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;

scene.add(new THREE.HemisphereLight(0x8fabb2, 0x261b15, 1.75));
const sun = new THREE.DirectionalLight(0xffd6a0, 3.2);
sun.position.set(-28, 44, 18); sun.castShadow = false;
scene.add(sun);

const C = {
  rust: 0x9d472a, amber: 0xffc64b, cyan: 0x3be0d2, dark: 0x151a1a,
  metal: 0x343b3c, skin: 0xc99b73, cloth: 0x496347, red: 0xb12b2b,
};
const mats = new Map();
function mat(color, roughness = .76, metalness = .12, emissive = 0x000000) {
  const key = `${color}-${roughness}-${metalness}-${emissive}`;
  if (!mats.has(key)) mats.set(key, new THREE.MeshStandardMaterial({ color, roughness, metalness, emissive, emissiveIntensity: emissive ? .7 : 0 }));
  return mats.get(key);
}
function mesh(geometry, material, parent, pos = [0,0,0], rot = [0,0,0], shadow = true) {
  const m = new THREE.Mesh(geometry, material); m.position.set(...pos); m.rotation.set(...rot);
  m.castShadow = shadow; m.receiveShadow = shadow; parent.add(m); return m;
}
function box(parent, size, pos, material, rot = [0,0,0]) { return mesh(new THREE.BoxGeometry(...size), material, parent, pos, rot); }
function cyl(parent, r1, r2, h, pos, material, rot = [0,0,0], sides = 8) { return mesh(new THREE.CylinderGeometry(r1, r2, h, sides), material, parent, pos, rot); }
function sphere(parent, radius, pos, material, seg = 12) { return mesh(new THREE.SphereGeometry(radius, seg, Math.max(6, seg >> 1)), material, parent, pos); }

const obstacles = [];
const worldSize = 150;
function registerObstacle(object, padding = 0) {
  object.updateMatrixWorld(true);
  const bounds = new THREE.Box3().setFromObject(object).expandByScalar(padding);
  obstacles.push({ object, bounds });
}
function seeded(n) { const x = Math.sin(n * 1287.31) * 43758.5453; return x - Math.floor(x); }

function makeBuilding(x, z, w, d, h, seed, collapsed = false) {
  const g = new THREE.Group(); g.position.set(x, 0, z); scene.add(g);
  const concrete = mat(seed % 2 ? 0x4c5150 : 0x57534d, .96, .02);
  const dark = mat(0x111819, .92, .05);
  const floors = collapsed ? Math.max(1, Math.floor(h / 4)) : Math.max(2, Math.floor(h / 3.4));
  for (let i = 0; i < floors; i++) {
    const floorH = collapsed && i === floors - 1 ? 1.4 + seeded(seed + i) * 2 : 3.2;
    const shrink = collapsed ? i * .32 : 0;
    const slab = box(g, [Math.max(2,w-shrink), floorH, Math.max(2,d-shrink)], [0, i*3.25 + floorH/2, 0], concrete);
    if (collapsed && i === floors - 1) slab.rotation.z = (seeded(seed*2)-.5) * .32;
    // One recessed window band per floor keeps the ruined silhouette while
    // replacing hundreds of separate window draw calls.
    box(g, [Math.max(1.2,w-1.5), .82, .08], [0, i*3.25 + 1.8, -d/2-.05], dark, [0,0,0], false);
  }
  if (collapsed) {
    for (let i = 0; i < 9; i++) {
      const s = .35 + seeded(seed*17+i)*1.1;
      box(g, [s*1.7,s,s], [(seeded(seed+i*3)-.5)*(w+3), s/2, (seeded(seed+i*5)-.5)*(d+3)], concrete, [seeded(i)*.5, seeded(i+4)*2, seeded(i+9)*.5]);
    }
  }
  registerObstacle(g, .18);
}

function makeBarricade(x, z, rot = 0) {
  const g = new THREE.Group(); g.position.set(x,0,z); g.rotation.y = rot; scene.add(g);
  const concrete = mat(0x66635c, .92, .03);
  box(g,[4.2,1.15,1.15],[0,.57,0],concrete);
  box(g,[4.4,.18,1.3],[0,1.08,0],mat(C.rust,.7,.35));
  registerObstacle(g,.12);
}

function makeWreck(x,z,rot=0) {
  const g = new THREE.Group(); g.position.set(x,0,z); g.rotation.y=rot; scene.add(g);
  const body = mat(0x49372c,.8,.28); const tire = mat(0x111111,.96,0);
  box(g,[3.6,.75,1.7],[0,.65,0],body); box(g,[1.8,.65,1.5],[-.35,1.25,0],mat(0x20292a,.7,.2));
  [[-1.15,.35,-.95],[1.15,.35,-.95],[-1.15,.35,.95],[1.15,.35,.95]].forEach(p=>cyl(g,.43,.43,.28,p,tire,[Math.PI/2,0,0],12));
  registerObstacle(g,.15);
}

function buildWorld() {
  const groundMat = new THREE.MeshStandardMaterial({ color:0x242a29, roughness:1, metalness:0 });
  const ground = mesh(new THREE.PlaneGeometry(worldSize,worldSize,30,30), groundMat, scene, [0,0,0],[-Math.PI/2,0,0]);
  ground.receiveShadow = true;
  // Broken roads and faded lane markings.
  box(scene,[16,.035,worldSize],[0,.025,0],mat(0x151a1b,.98,0),[0,0,0],false);
  box(scene,[worldSize,.03,13],[0,.026,-27],mat(0x171b1c,.98,0),[0,0,0],false);
  for (let z=-68; z<69; z+=6) box(scene,[.16,.042,2.8],[0,.055,z],mat(0xb0a163,.9,0),[0,0,0],false);
  for (let x=-68; x<69; x+=6) box(scene,[2.8,.04,.16],[x,.055,-27],mat(0x8f8355,.9,0),[0,0,0],false);

  const layouts = [
    [-53,-52,15,13,14,1,1],[-31,-52,13,12,21,2,0],[28,-52,15,14,16,3,1],[53,-53,16,12,23,4,0],
    [-53,-21,14,13,19,5,0],[-29,-19,13,11,12,6,1],[30,-19,16,12,18,7,1],[55,-19,13,13,14,8,0],
    [-53,12,15,14,17,9,1],[-29,14,13,13,21,10,0],[29,14,14,13,13,11,1],[54,13,16,14,20,12,0],
    [-54,48,16,15,22,13,0],[-30,49,12,13,14,14,1],[29,48,16,13,20,15,0],[54,50,14,14,15,16,1],
  ];
  layouts.forEach(v=>makeBuilding(...v));
  [[-9,-13,0],[10,-41,1.4],[-11,30,.3],[14,42,2.1],[-2,61,.2]].forEach(v=>makeBarricade(...v));
  [[-8,-53,.7],[9,-17,-.4],[-10,7,1.1],[10,55,-1.2]].forEach(v=>makeWreck(...v));

  // Dust, ash and distant skyline.
  const ashGeo = new THREE.BufferGeometry(); const ash = [];
  for(let i=0;i<420;i++) ash.push((Math.random()-.5)*150, Math.random()*28, (Math.random()-.5)*150);
  ashGeo.setAttribute('position',new THREE.Float32BufferAttribute(ash,3));
  scene.add(new THREE.Points(ashGeo,new THREE.PointsMaterial({color:0xb8ae91,size:.055,transparent:true,opacity:.34,depthWrite:false})));
}

const WEAPONS = [
  {key:'pistol',name:'手枪',damage:18,mag:10,rate:8/60,reload:3,spread:.012,cost:0,color:0xb8c0c2},
  {key:'rifle',name:'突击步枪',damage:7,mag:30,rate:6/60,reload:2,spread:.015,cost:30,color:0x738b8f},
  {key:'sniper',name:'狙击枪',damage:150,mag:10,rate:60/60,reload:5,spread:.001,cost:90,color:0x343b3c,pierce:3},
  {key:'shotgun',name:'霰弹枪',damage:14,mag:15,rate:18/60,reload:4,spread:.065,cost:160,pellets:4,color:0x6d4b30},
  {key:'smg',name:'冲锋枪',damage:5,mag:45,rate:2/60,reload:2.5,spread:.025,cost:130,color:0x57656b},
  {key:'flamethrower',name:'喷火枪',damage:2,mag:70,rate:3/60,reload:4,spread:.055,cost:190,pellets:4,range:24,color:0xd15b22,flame:true},
  {key:'grenade',name:'榴弹发射器',damage:48,mag:8,rate:28/60,reload:4.5,spread:.006,cost:230,color:0x536a48,grenade:true},
  {key:'laser',name:'激光枪',damage:5,mag:30,rate:2/60,reload:3.5,spread:.002,cost:220,color:0x35d9e5,pierce:99,laser:true},
  {key:'crossbow',name:'弩',damage:23,mag:20,rate:24/60,reload:3.5,spread:.007,cost:100,color:0x8e623b,pierce:3},
];

const MATERIAL_INFO={
  alloy:{name:'废土合金',icon:'◆',image:'scrap-alloy-icon.png',color:'#d9a56f'},
  energy:{name:'能量核心',icon:'◉',image:'energy-core-icon.png',color:'#5de7ed'},
  bio:{name:'生体样本',icon:'⬢',image:'bio-sample-icon.png',color:'#80d36a'},
};
const STAGE_MATERIAL=['alloy','alloy','energy','alloy','energy','energy','bio','alloy','bio','energy'];
const WEAPON_MATERIAL={pistol:'alloy',rifle:'alloy',sniper:'energy',shotgun:'alloy',smg:'alloy',flamethrower:'bio',grenade:'alloy',laser:'energy',crossbow:'bio'};
const PROFILE_KEY='wz3d-profile-v1';
function freshProfile(){
  return {
    scrap:0,ownedWeapons:['pistol'],materials:{alloy:0,energy:0,bio:0},talents:{hp:0,speed:0,armor:0},weaponUpgrades:Object.fromEntries(WEAPONS.map(w=>[w.key,{damage:0,mag:0,durability:0}])),
  };
}
function loadProfile(){
  const base=freshProfile();
  try{
    const saved=JSON.parse(localStorage.getItem(PROFILE_KEY)||'{}');
    base.scrap=Math.max(0,Number(saved.scrap)||0);
    const validWeapons=new Set(WEAPONS.map(w=>w.key));
    base.ownedWeapons=Array.isArray(saved.ownedWeapons)?saved.ownedWeapons.filter(key=>validWeapons.has(key)):['pistol'];
    if(!base.ownedWeapons.includes('pistol'))base.ownedWeapons.unshift('pistol');
    for(const key of Object.keys(base.materials))base.materials[key]=Math.max(0,Number(saved.materials?.[key])||0);
    for(const key of Object.keys(base.talents))base.talents[key]=THREE.MathUtils.clamp(Number(saved.talents?.[key])||0,0,10);
    for(const w of WEAPONS)for(const key of Object.keys(base.weaponUpgrades[w.key]))base.weaponUpgrades[w.key][key]=THREE.MathUtils.clamp(Number(saved.weaponUpgrades?.[w.key]?.[key])||0,0,5);
  }catch{}
  return base;
}
const profile=loadProfile();
function saveProfile(){localStorage.setItem(PROFILE_KEY,JSON.stringify(profile));}
function weaponStats(index){
  const base=WEAPONS[index],up=profile.weaponUpgrades[base.key];
  const permanentDamage=base.key==='laser'?0:up.damage;
  let damage=base.damage+permanentDamage+run.weaponDamage;
  let pellets=(base.pellets||1)+run.weaponPellets;
  let pierce=(base.pierce||1)+run.pierceBonus+run.weaponPierce;
  let range=(base.range||90)+run.weaponRange;
  let mag=Math.floor((base.mag+up.mag*2+run.magAdd)*(run.magMult||1));
  let reload=Math.max(.4,(base.reload*Math.pow(.95,up.durability)+run.reloadAdd)*run.reloadMult);
  let rate=Math.max(.025,base.rate*run.rateMult);
  let blastRadius=6+run.weaponBlast;
  if(run.ultimate==='barrage'){
    const extra={pistol:2,rifle:3,smg:3,shotgun:6,sniper:1,crossbow:1,flamethrower:3,grenade:2,laser:2}[base.key]||1;
    const penalty={pistol:2,rifle:2,smg:1,shotgun:4,sniper:22,crossbow:4,flamethrower:1,grenade:10,laser:1}[base.key]||1;
    pellets+=extra;damage=Math.max(1,damage-penalty);
  }else if(run.ultimate==='overcharge'){
    damage+=base.key==='laser'?3:8;pierce+=5;if(base.key==='grenade')blastRadius=Math.max(blastRadius,9.5);
  }else if(run.ultimate==='storm'){
    rate*=.6;reload*=.6;
  }else if(run.ultimate==='fortress'){
    mag=Math.floor(mag*1.5);
  }else if(run.ultimate==='ranger'){
    pierce+=3;range+=80;
  }
  return {...base,damage,mag:Math.max(1,mag),reload,rate,pellets,pierce,range,blastRadius,spread:base.spread*run.spreadMult,beamWidth:run.weaponBeamWidth,beamLife:run.weaponBeamLife};
}

function makeWeaponModel(key) {
  const g = new THREE.Group(); g.name = key;
  const steel = mat(0x4d595c,.42,.72), bright=mat(0x8f9b9d,.3,.82), dark = mat(0x202527,.65,.42), black=mat(0x0f1314,.72,.3), wood = mat(0x71492d,.78,.08), cyan = mat(0x4de9ed,.28,.55,0x1c8e96), brass=mat(0xb98b42,.42,.62);
  const receiver = (length=.9, width=.18, height=.22, material=steel) => box(g,[width,height,length],[0,0,-length*.5],material);
  const barrel = (length=.9, radius=.045, material=dark, x=0,y=.02,z=-1) => cyl(g,radius,radius,length,[x,y,z],material,[Math.PI/2,0,0],10);
  const rail=(z0,z1,y=.18,width=.16)=>{for(let z=z0;z>=z1;z-=.11)box(g,[width,.035,.055],[0,y,z],bright);};
  const muzzleBrake=(z,r=.075)=>{cyl(g,r,r*.82,.18,[0,.04,z],bright,[Math.PI/2,0,0],12);for(const side of [-1,1])box(g,[.035,.055,.08],[side*r*.72,.04,z],black);};
  const ironSight=(z,y=.2)=>{box(g,[.12,.035,.06],[0,y,z],black);box(g,[.025,.11,.035],[-.045,y+.05,z],black);box(g,[.025,.11,.035],[.045,y+.05,z],black);};
  const rivet=(x,y,z,r=.018)=>sphere(g,r,[x,y,z],brass,8);
  const segment=(a,b,r=.012,material=steel)=>{const av=new THREE.Vector3(...a),bv=new THREE.Vector3(...b),mid=av.clone().add(bv).multiplyScalar(.5),dir=bv.clone().sub(av);const part=mesh(new THREE.CylinderGeometry(r,r,dir.length(),6),material,g,mid.toArray());part.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),dir.normalize());return part;};
  if(key==='pistol') { receiver(.62,.22,.25); barrel(.36,.045,dark,0,.03,-.72); box(g,[.18,.48,.19],[0,-.28,-.18],wood,[.16,0,0]); }
  if(key==='rifle') { receiver(1.05,.23,.3); barrel(.82,.045,dark,0,.04,-1.32); box(g,[.18,.3,.5],[0,-.1,.3],dark,[.25,0,0]); box(g,[.19,.42,.2],[0,-.31,-.54],dark,[.12,0,0]); }
  if(key==='sniper') { receiver(1.28,.2,.24,dark); barrel(1.35,.038,steel,0,.04,-1.78); cyl(g,.09,.09,.58,[0,.25,-.55],dark,[Math.PI/2,0,0],12); box(g,[.2,.34,.72],[0,-.07,.42],wood,[.08,0,0]); }
  if(key==='shotgun') { receiver(.9,.21,.25,dark); barrel(1.25,.052,steel,0,.05,-1.44); box(g,[.22,.2,.52],[0,-.03,-1.0],wood); box(g,[.2,.34,.7],[0,-.1,.45],wood,[.08,0,0]); }
  if(key==='smg') { receiver(.82,.27,.34,dark); barrel(.5,.055,steel,0,.04,-.84); box(g,[.2,.5,.18],[0,-.32,-.36],dark,[.08,0,0]); box(g,[.18,.26,.46],[0,-.03,.22],steel); }
  if(key==='flamethrower') { receiver(1.1,.3,.32,dark); barrel(.72,.09,steel,0,.05,-1.18); cyl(g,.25,.25,.72,[0,-.34,-.42],mat(0x805129,.6,.4),[Math.PI/2,0,0],12); box(g,[.18,.42,.2],[0,-.25,-.75],dark); }
  if(key==='grenade') { receiver(.92,.32,.38,mat(0x4d6848,.7,.25)); barrel(.72,.13,dark,0,.03,-1.05); cyl(g,.2,.2,.5,[0,-.25,-.44],dark,[Math.PI/2,0,0],10); }
  if(key==='laser') { receiver(1.12,.27,.28,dark); barrel(.92,.07,cyan,0,.04,-1.37); box(g,[.18,.4,.22],[0,-.28,-.45],dark,[.08,0,0]); sphere(g,.1,[0,.1,-.5],cyan,12); }
  if(key==='crossbow') { box(g,[.16,.18,1.42],[0,0,-.62],wood); barrel(.95,.022,steel,0,.08,-.92); box(g,[1.4,.08,.12],[0,.05,-1.04],wood,[0,0,.05]); box(g,[.18,.38,.22],[0,-.26,-.34],wood,[.1,0,0]); }
  // Secondary silhouettes and small mechanical details make every weapon
  // recognisable from the first-person angle rather than reading as a block.
  if(key==='pistol'){
    box(g,[.205,.055,.5],[0,.145,-.31],bright);rail(-.08,-.46,.18,.13);ironSight(-.12,.19);muzzleBrake(-.91,.052);
    mesh(new THREE.TorusGeometry(.12,.022,6,16,Math.PI*1.25),black,g,[0,-.18,-.24],[0,0,.42]);
    for(const z of [-.28,-.39,-.5])box(g,[.226,.035,.025],[0,.08,z],black);
  }
  if(key==='rifle'){
    rail(-.16,-1.12,.22,.19);ironSight(-1.5,.16);muzzleBrake(-1.73,.07);
    box(g,[.32,.12,.7],[0,.03,-.98],dark);for(const z of [-.74,-.88,-1.02,-1.16])box(g,[.335,.025,.055],[0,.09,z],bright);
    segment([-.09,.03,.28],[-.17,.03,.64],.028,dark);segment([.09,.03,.28],[.17,.03,.64],.028,dark);box(g,[.42,.2,.12],[0,.03,.67],dark);
    for(const x of [-.105,.105])rivet(x,.12,-.35);
  }
  if(key==='sniper'){
    rail(-.1,-1.18,.18,.15);muzzleBrake(-2.48,.07);box(g,[.25,.09,.55],[0,.22,-.55],black);
    cyl(g,.105,.105,.7,[0,.28,-.55],black,[Math.PI/2,0,0],16);for(const z of [-.28,-.78])cyl(g,.13,.13,.055,[0,.28,z],bright,[Math.PI/2,0,0],12);
    cyl(g,.035,.035,.22,[.18,.06,-.45],bright,[0,0,Math.PI/2],8);sphere(g,.06,[.31,.06,-.45],black,10);
    segment([-.11,-.02,-1.25],[-.28,-.65,-1.42],.025,bright);segment([.11,-.02,-1.25],[.28,-.65,-1.42],.025,bright);
  }
  if(key==='shotgun'){
    barrel(1.08,.032,bright,0,-.04,-1.35);muzzleBrake(-2.07,.06);ironSight(-1.92,.13);
    for(const z of [-.78,-.89,-1,-1.11,-1.22])box(g,[.235,.035,.045],[0,.1,z],dark);
    mesh(new THREE.TorusGeometry(.115,.018,6,18,Math.PI*1.35),black,g,[0,-.16,-.3],[0,0,.35]);
    for(const x of [-.105,.105])rivet(x,.08,-.42);
  }
  if(key==='smg'){
    rail(-.05,-.72,.25,.2);muzzleBrake(-1.13,.08);ironSight(-.86,.22);
    segment([-.12,.02,.2],[-.28,.02,.62],.024,bright);segment([.12,.02,.2],[.28,.02,.62],.024,bright);box(g,[.62,.13,.11],[0,.02,.64],dark);
    for(const z of [-.18,-.32,-.46,-.6])box(g,[.29,.035,.04],[0,.12,z],bright);
  }
  if(key==='flamethrower'){
    for(const z of [-.92,-1.18,-1.42])cyl(g,.14,.14,.055,[0,.05,z],brass,[Math.PI/2,0,0],14);
    cyl(g,.06,.1,.24,[0,.05,-1.62],bright,[Math.PI/2,0,0],12);sphere(g,.055,[.11,.08,-1.54],mat(0xff6b19,.24,.25,0xff4010),10);
    segment([-.15,-.24,-.52],[-.24,-.42,-.9],.028,black);for(const x of [-.13,.13])rivet(x,.08,-.32,.025);
  }
  if(key==='grenade'){
    rail(-.08,-.72,.26,.22);muzzleBrake(-1.43,.145);box(g,[.18,.26,.62],[0,-.02,.28],dark,[.12,0,0]);
    for(let a=0;a<8;a++){const ang=a/8*Math.PI*2;box(g,[.035,.25,.14],[Math.sin(ang)*.205,-.24+Math.cos(ang)*.06,-.45],bright,[0,0,ang]);}
    box(g,[.2,.14,.24],[0,.29,-.35],black);sphere(g,.045,[0,.35,-.48],mat(0xffb329,.2,.25,0xff7b18),10);
  }
  if(key==='laser'){
    rail(-.12,-.88,.21,.2);for(const z of [-.92,-1.14,-1.36,-1.58])cyl(g,.115,.115,.06,[0,.04,z],cyan,[Math.PI/2,0,0],14);
    for(const side of [-1,1]){box(g,[.05,.3,.64],[side*.18,.05,-.72],cyan,[0,0,side*.12]);sphere(g,.055,[side*.2,.05,-.38],cyan,10);}
    cyl(g,.035,.07,.18,[0,.04,-1.9],cyan,[Math.PI/2,0,0],12);box(g,[.16,.1,.28],[0,.25,-.45],black);sphere(g,.04,[0,.3,-.56],cyan,8);
  }
  if(key==='crossbow'){
    const bowPoints=[[-.78,.05,-1.04],[-.52,.12,-1.18],[0,.16,-1.28],[.52,.12,-1.18],[.78,.05,-1.04]];
    for(let i=0;i<bowPoints.length-1;i++)segment(bowPoints[i],bowPoints[i+1],.035,wood);
    segment([-.78,.05,-1.04],[0,.09,-.28],.009,bright);segment([.78,.05,-1.04],[0,.09,-.28],.009,bright);
    box(g,[.08,.055,.92],[0,.14,-.9],bright);mesh(new THREE.ConeGeometry(.055,.22,5),bright,g,[0,.14,-1.5],[Math.PI/2,0,0]);
    rail(-.22,-.68,.22,.13);ironSight(-.78,.2);
  }
  const magazineSpecs={
    pistol:[.12,.34,.16,0,-.26,-.13], rifle:[.18,.42,.20,0,-.31,-.54],
    sniper:[.17,.24,.22,0,-.19,-.56], smg:[.17,.48,.17,0,-.31,-.38],
    flamethrower:[.28,.46,.28,0,-.34,-.43], grenade:[.27,.32,.27,0,-.26,-.45],
    laser:[.16,.36,.18,0,-.27,-.46],
  };
  if(magazineSpecs[key]){
    const [mw,mh,md,mx,my,mz]=magazineSpecs[key];
    const cell=box(g,[mw,mh,md],[mx,my,mz],key==='laser'?cyan:key==='flamethrower'?mat(0x805129,.6,.4):dark,[.08,0,0]);
    cell.name='magazine';
  }
  if(key==='shotgun'||key==='crossbow'){
    const action=box(g,key==='shotgun'?[.16,.12,.38]:[.08,.08,.48],[0,.12,key==='shotgun'?-.62:-.82],steel);
    action.name='action';
  }
  g.scale.setScalar(.78); return g;
}
const weaponModels = new Map(WEAPONS.map(w=>[w.key,makeWeaponModel(w.key)]));

function makePlayer() {
  const g = new THREE.Group(); g.position.set(0,0,12); scene.add(g);
  const armor = mat(0x435c43,.75,.16), fabric=mat(0x202727,.92,.02), skin=mat(C.skin,.9,.02), boot=mat(0x16191a,.9,.05);
  const torso=box(g,[.82,1.05,.42],[0,1.75,0],armor); box(g,[.9,.22,.48],[0,2.18,0],mat(0x35463a,.7,.25));
  sphere(g,.34,[0,2.58,-.03],skin,16); box(g,[.55,.13,.42],[0,2.83,-.02],mat(0x24352c,.8,.12));
  const legL=new THREE.Group(), legR=new THREE.Group(); legL.position.set(-.22,1.18,0); legR.position.set(.22,1.18,0); g.add(legL,legR);
  box(legL,[.28,.9,.3],[0,-.42,0],fabric); box(legR,[.28,.9,.3],[0,-.42,0],fabric); box(legL,[.31,.2,.5],[0,-.9,-.09],boot); box(legR,[.31,.2,.5],[0,-.9,-.09],boot);
  const armL=new THREE.Group(), armR=new THREE.Group(); armL.position.set(-.51,2.1,0); armR.position.set(.51,2.1,0); g.add(armL,armR);
  box(armL,[.25,.82,.25],[0,-.35,-.19],armor,[1.18,0,-.08]); box(armR,[.25,.82,.25],[0,-.35,-.19],armor,[1.12,0,.08]);
  const socket=new THREE.Group(); socket.position.set(0,1.88,-.58); g.add(socket);
  const muzzle=new THREE.Object3D(); muzzle.position.set(0,.05,-1.7); socket.add(muzzle);
  return {group:g,torso,legL,legR,armL,armR,socket,muzzle};
}

function makeFirstPersonRig(){
  const rig=new THREE.Group();rig.position.set(.34,-.45,-.86);camera.add(rig);
  const sleeve=mat(0x31483a,.84,.1),sleeveDark=mat(0x1b2722,.9,.04),glove=mat(0x202625,.68,.22),armor=mat(0x607366,.48,.38),edge=mat(0x18201d,.66,.28),screenMat=mat(0x28d9ca,.22,.34,0x28d9ca);
  const leftArm=new THREE.Group(),rightArm=new THREE.Group();rig.add(leftArm,rightArm);
  leftArm.position.set(-.33,-.10,.12);rightArm.position.set(.28,-.18,.20);
  // Layered survivor sleeves and forearm armor.  The silhouette follows the
  // green overhead player from the 2D release instead of looking like bare
  // cylinders floating beside the weapon.
  cyl(leftArm,.115,.15,.46,[0,-.12,.05],sleeve,[1.18,0,-.18],12);
  cyl(leftArm,.095,.115,.38,[.02,-.27,-.25],sleeveDark,[1.40,0,-.12],12);
  box(leftArm,[.22,.13,.31],[.01,-.16,-.12],armor,[.35,-.08,-.1]);
  box(leftArm,[.16,.06,.22],[.01,-.145,-.23],edge,[.35,-.08,-.1]);
  cyl(rightArm,.125,.16,.48,[0,-.14,.10],sleeve,[1.05,0,.18],12);
  cyl(rightArm,.098,.12,.38,[-.01,-.29,-.20],sleeveDark,[1.36,0,.13],12);
  box(rightArm,[.25,.17,.34],[0,-.03,.06],armor,[.18,0,.08]);
  box(rightArm,[.16,.035,.18],[0,-.12,-.08],screenMat,[.18,0,.08]);

  const makeHand=(parent,handed)=>{
    const hand=new THREE.Group();hand.position.set(handed*.015,-.34,-.43);parent.add(hand);
    const palm=box(hand,[.17,.115,.24],[0,0,0],glove,[.18,0,handed*.08]);
    box(hand,[.18,.045,.17],[0,.055,-.015],armor,[.18,0,handed*.08]);
    for(let i=0;i<4;i++){
      const x=(i-1.5)*.038;
      const finger=box(hand,[.032,.042,.17],[x,-.025,-.145],glove,[.24,handed*.03,handed*.025]);
      box(hand,[.035,.018,.052],[x,.004,-.13],edge,[.24,handed*.03,handed*.025]);
      finger.name='finger';
    }
    box(hand,[.048,.05,.14],[handed*.105,-.005,-.045],glove,[.55,0,-handed*.62]);
    return {hand,palm};
  };
  const leftHand=makeHand(leftArm,-1),rightHand=makeHand(rightArm,1);
  const socket=new THREE.Group();socket.position.set(0,0,0);rig.add(socket);
  const muzzle=new THREE.Object3D();muzzle.position.set(0,.05,-1.7);socket.add(muzzle);
  return {group:rig,leftArm,rightArm,leftHand:leftHand.hand,rightHand:rightHand.hand,socket,muzzle,magazine:null,action:null};
}

function catModel(type='basic') {
  const g=new THREE.Group();
  const spec={
    basic:{fur:0xa62029,accent:0xff343a,scale:1,width:1,armor:0x34383b,eye:0xffe37a},
    fast:{fur:0xd55218,accent:0xffa12f,scale:.82,width:.78,armor:0x33383a,eye:0x8ff6ff},
    tank:{fur:0x651c22,accent:0xb72e32,scale:1.5,width:1.3,armor:0x41484a,eye:0xffd76b},
    scout:{fur:0x277f8c,accent:0x59dbe2,scale:.94,width:.84,armor:0x30494d,eye:0xbaffff},
    brute:{fur:0x8f371d,accent:0xe7782f,scale:1.28,width:1.16,armor:0x4b4039,eye:0xffc457},
    mini:{fur:0x772055,accent:0xc94b9f,scale:.72,width:.82,armor:0x39313c,eye:0xffb9ef},
    boss:{fur:0x451458,accent:0xb84fe0,scale:2.35,width:1.22,armor:0x242330,eye:0xffcf43},
  }[type]||null;
  const s=spec.scale,w=spec.width;
  const fur=mat(spec.fur,.9,.02),furDark=mat(new THREE.Color(spec.fur).multiplyScalar(.48).getHex(),.94,.02);
  const armor=mat(spec.armor,.48,.64),armorDark=mat(0x171b1e,.68,.48),accent=mat(spec.accent,.38,.48,spec.accent);
  const eye=mat(spec.eye,.22,.25,spec.eye),claw=mat(0xb8b9b5,.38,.72),nose=mat(0x1a0d11,.82,.05);

  const ellipsoid=(scale,pos,material,segments=18)=>{const part=sphere(g,1,pos,material,segments);part.scale.set(scale[0],scale[1],scale[2]);return part;};
  const tubeBetween=(parent,a,b,r1,r2,material,sides=10)=>{const start=new THREE.Vector3(...a),end=new THREE.Vector3(...b),mid=start.clone().add(end).multiplyScalar(.5),dir=end.clone().sub(start);const part=mesh(new THREE.CylinderGeometry(r1,r2,dir.length(),sides),material,parent,mid.toArray());part.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),dir.normalize());return part;};

  // Feline silhouette: long low torso, raised shoulders, tapered neck and a
  // broad cat head.  These proportions follow the approved overhead models.
  const body=ellipsoid([.62*s*w,.48*s,.92*s],[0,.88*s,.16*s],fur,22);
  const chest=ellipsoid([.58*s*w,.55*s,.52*s],[0,.92*s,-.42*s],fur,20);
  const neck=ellipsoid([.38*s,.38*s,.38*s],[0,1.12*s,-.72*s],furDark,16);
  const head=ellipsoid([.49*s,.41*s,.43*s],[0,1.18*s,-.98*s],fur,22);
  const muzzle=ellipsoid([.3*s,.2*s,.24*s],[0,1.03*s,-1.34*s],furDark,16);
  ellipsoid([.16*s,.13*s,.12*s],[-.23*s,1.08*s,-1.27*s],fur,12);
  ellipsoid([.16*s,.13*s,.12*s],[.23*s,1.08*s,-1.27*s],fur,12);
  ellipsoid([.06*s,.045*s,.05*s],[0,1.1*s,-1.55*s],nose,10);
  // A readable face matters far more than raw polygon count in first person:
  // pupils, jaw, teeth and cheek vents keep the monsters from looking like
  // moving primitive shapes when they rush the camera.
  const pupil=mat(0x050707,.7,.1),tooth=mat(0xe8dfc4,.34,.5),mouth=mat(0x2b080d,.9,.02);
  ellipsoid([.035*s,.06*s,.025*s],[-.19*s,1.25*s,-1.415*s],pupil,8);
  ellipsoid([.035*s,.06*s,.025*s],[.19*s,1.25*s,-1.415*s],pupil,8);
  box(g,[.35*s,.035*s,.12*s],[0,.96*s,-1.48*s],mouth,[.12,0,0]);
  for(const side of [-1,1]){
    mesh(new THREE.ConeGeometry(.035*s,.15*s,6),tooth,g,[side*.12*s,.92*s,-1.54*s],[Math.PI,0,0]);
    box(g,[.08*s,.13*s,.08*s],[side*.37*s,1.16*s,-1.37*s],armorDark,[0,side*.18,side*.2]);
    for(let v=0;v<2;v++)box(g,[.018*s,.045*s,.075*s],[side*(.36+.05*v)*s,1.17*s,-1.415*s],accent);
  }

  const ears=[];
  const earGeo=new THREE.ConeGeometry(.22*s,.5*s,4);
  const earL=mesh(earGeo,fur,g,[-.27*s,1.6*s,-.98*s],[0,.08,.08]);
  const earR=mesh(earGeo,fur,g,[.27*s,1.6*s,-.98*s],[0,-.08,-.08]);
  ears.push(earL,earR);
  const innerEar=mat(type==='boss'?0xb43c8e:0x69242b,.88,.02);
  mesh(new THREE.ConeGeometry(.11*s,.3*s,4),innerEar,g,[-.27*s,1.61*s,-1.01*s],[0,.08,.08]);
  mesh(new THREE.ConeGeometry(.11*s,.3*s,4),innerEar,g,[.27*s,1.61*s,-1.01*s],[0,-.08,-.08]);

  // Eyes, brow armour and small face plates reproduce the mechanical-cat look
  // from the 2D art instead of relying on a plain coloured animal mesh.
  ellipsoid([.1*s,.055*s,.035*s],[-.19*s,1.25*s,-1.38*s],eye,10);
  ellipsoid([.1*s,.055*s,.035*s],[.19*s,1.25*s,-1.38*s],eye,10);
  box(g,[.22*s,.08*s,.19*s],[-.19*s,1.4*s,-1.34*s],armor,[0,0,-.18]);
  box(g,[.22*s,.08*s,.19*s],[.19*s,1.4*s,-1.34*s],armor,[0,0,.18]);
  box(g,[.2*s,.09*s,.22*s],[0,1.48*s,-1.16*s],armor);
  const browCore=mesh(new THREE.OctahedronGeometry(.09*s,0),accent,g,[0,1.5*s,-1.31*s]);
  browCore.rotation.z=Math.PI/4;
  for(const side of [-1,1]){
    tubeBetween(g,[side*.19*s,1.03*s,-1.5*s],[side*.53*s,1.02*s,-1.7*s],.012*s,.006*s,claw,6);
    tubeBetween(g,[side*.2*s,.98*s,-1.49*s],[side*.57*s,.93*s,-1.62*s],.012*s,.006*s,claw,6);
  }

  // Articulated legs have upper/lower segments, joints, paws and claws. Their
  // roots are animated in updateEnemies, so the cats actually run in 3D.
  const legs=[];
  const legPoints=[[-.38,-.34], [.38,-.34],[-.4,.52],[.4,.52]];
  legPoints.forEach(([x,z],i)=>{
    const leg=new THREE.Group();leg.position.set(x*s*w,.82*s,z*s);g.add(leg);legs.push(leg);
    const side=i%2===0?-1:1,front=i<2;
    tubeBetween(leg,[0,.08*s,0],[side*.035*s,-.34*s,(front?-.1:.12)*s],.13*s,.1*s,furDark,10);
    const joint=ellipsoid([.13*s,.12*s,.13*s],[x*s*w+side*.035*s,.48*s,(z+(front?-.1:.12))*s],armorDark,12);
    joint.rotation.y=side*.2;
    tubeBetween(leg,[side*.035*s,-.34*s,(front?-.1:.12)*s],[side*.02*s,-.7*s,(front?-.23:.3)*s],.1*s,.075*s,fur,9);
    const paw=new THREE.Group();paw.position.set(side*.02*s,-.72*s,(front?-.28:.34)*s);leg.add(paw);
    const pawMesh=mesh(new THREE.SphereGeometry(.15*s,12,8),fur,paw,[0,0,-.02*s]);pawMesh.scale.set(1.15,.62,1.45);
    for(let c=-1;c<=1;c++)tubeBetween(paw,[c*.07*s,-.02*s,-.16*s],[c*.075*s,-.03*s,-.29*s],.018*s,.006*s,claw,6);
  });

  // Layered spine armour and side harness match the metal exoskeleton visible
  // on every approved 2D cat variant.
  const plateCount=type==='fast'?3:type==='tank'||type==='boss'?6:4;
  for(let i=0;i<plateCount;i++){
    const z=.62*s-i*(1.18*s/(plateCount-1));
    const plate=box(g,[.58*s*w,.105*s,.26*s],[0,1.27*s,z],i%2?armor:accent,[0,0,0]);
    plate.scale.x=1-Math.abs(i-(plateCount-1)/2)*.06;
  }
  for(const side of [-1,1]){
    tubeBetween(g,[side*.5*s*w,1.12*s,.55*s],[side*.54*s*w,1.14*s,-.57*s],.055*s,.055*s,armorDark,8);
    cyl(g,.13*s,.13*s,.12*s,[side*.57*s*w,1.08*s,-.36*s],accent,[0,0,Math.PI/2],12);
    // Layered shoulder guard, hip plate and two hydraulic pistons.
    box(g,[.26*s,.22*s,.4*s],[side*.53*s*w,1.25*s,-.43*s],armor,[0,0,side*.18]);
    box(g,[.23*s,.16*s,.34*s],[side*.54*s*w,1.2*s,.52*s],armorDark,[0,0,-side*.14]);
    tubeBetween(g,[side*.48*s*w,1.16*s,.38*s],[side*.43*s*w,.84*s,.62*s],.028*s,.022*s,claw,7);
    tubeBetween(g,[side*.48*s*w,1.18*s,-.42*s],[side*.4*s*w,.82*s,-.62*s],.028*s,.022*s,claw,7);
  }
  // Chest harness and an illuminated identity core carry the 2D mechanical
  // monster language into the full 3D silhouette.
  box(g,[.68*s*w,.12*s,.15*s],[0,1.23*s,-.63*s],armorDark,[.28,0,0]);
  box(g,[.68*s*w,.12*s,.15*s],[0,1.23*s,.42*s],armorDark,[-.2,0,0]);
  cyl(g,.12*s,.12*s,.12*s,[0,1.34*s,-.35*s],accent,[Math.PI/2,0,0],14);

  const tail=new THREE.Group();tail.position.set(0,1.05*s,.93*s);g.add(tail);
  const tailPath=[[0,0,0],[.04*s,.13*s,.28*s],[-.05*s,.35*s,.5*s],[.08*s,.62*s,.62*s],[-.04*s,.9*s,.55*s],[.03*s,1.12*s,.35*s]];
  for(let i=0;i<tailPath.length-1;i++)tubeBetween(tail,tailPath[i],tailPath[i+1],(.11-i*.009)*s,(.105-i*.01)*s,i%2?furDark:fur,10);
  for(let i=1;i<tailPath.length-1;i+=2)cyl(tail,.13*s,.13*s,.1*s,tailPath[i],armor,[0,0,Math.PI/2],10);

  // Variant-specific equipment makes silhouettes readable before colour does.
  if(type==='tank'){
    for(const side of [-1,1]){const shield=box(g,[.22*s,.75*s,.85*s],[side*.65*s*w,1.02*s,.05*s],armor,[0,0,side*.16]);shield.scale.z=1.12;}
    box(g,[.84*s,.2*s,.72*s],[0,1.43*s,.1*s],armorDark);
  }
  if(type==='fast'){
    for(const side of [-1,1]){cyl(g,.14*s,.2*s,.42*s,[side*.44*s,1.23*s,.34*s],accent,[Math.PI/2,0,0],12);cyl(g,.08*s,.13*s,.12*s,[side*.44*s,1.23*s,.62*s],eye,[Math.PI/2,0,0],10);}
    for(let i=0;i<4;i++)mesh(new THREE.ConeGeometry(.07*s,.34*s,5),claw,g,[0,1.55*s,.52*s-i*.35*s],[Math.PI/2,0,0]);
  }
  if(type==='scout'){
    const mast=cyl(g,.045*s,.055*s,.48*s,[0,1.65*s,-.08*s],armor,[0,0,0],8);
    sphere(g,.14*s,[0,1.92*s,-.08*s],accent,14);tubeBetween(g,[0,1.88*s,-.08*s],[.28*s,2.12*s,-.08*s],.018*s,.008*s,claw,6);
    // Compact reconnaissance rifle and optic mounted to the flank.
    box(g,[.16*s,.18*s,.82*s],[.56*s,1.23*s,-.12*s],armorDark,[0,0,-.05]);
    cyl(g,.035*s,.04*s,.62*s,[.56*s,1.25*s,-.83*s],claw,[Math.PI/2,0,0],8);
    cyl(g,.08*s,.08*s,.25*s,[.56*s,1.43*s,-.25*s],accent,[Math.PI/2,0,0],10);
    mast.userData.pulse=true;
  }
  if(type==='brute'){
    for(const side of [-1,1]){mesh(new THREE.ConeGeometry(.12*s,.5*s,6),claw,g,[side*.66*s,1.35*s,-.15*s],[0,0,side*.55]);box(g,[.3*s,.4*s,.5*s],[side*.58*s,1.05*s,-.28*s],armor);}
    // The brute carries a full axe rather than an unreadable dark stick.
    const axe=new THREE.Group();axe.position.set(.72*s,1.23*s,.15*s);axe.rotation.set(.1,0,-.55);g.add(axe);
    cyl(axe,.035*s,.045*s,1.15*s,[0,0,0],furDark,[0,0,0],8);
    mesh(new THREE.CylinderGeometry(.08*s,.32*s,.48*s,4),claw,axe,[0,.62*s,0],[0,0,Math.PI/2]);
  }
  if(type==='mini'){
    const collar=mesh(new THREE.TorusGeometry(.36*s,.045*s,7,20),armor,g,[0,1.13*s,-.72*s],[Math.PI/2,0,0]);
    collar.scale.z=.8;sphere(g,.1*s,[0,.88*s,-1.04*s],accent,12);
  }
  let aura=null;
  if(type==='boss'){
    aura=mesh(new THREE.TorusGeometry(3.2,.065,8,56),accent,g,[0,.08,0],[Math.PI/2,0,0]);
    for(const side of [-1,1])mesh(new THREE.ConeGeometry(.16*s,.72*s,6),armor,g,[side*.43*s,1.92*s,-.82*s],[0,0,side*.22]);
    sphere(g,.2*s,[0,1.26*s,-1.48*s],eye,14);
    box(g,[1.05*s,.18*s,.78*s],[0,1.46*s,.16*s],armorDark);
    // Crown-like command array, shoulder reactors and jaw armour distinguish
    // the boss even in silhouette and make its second phase feel deliberate.
    for(let i=-2;i<=2;i++)mesh(new THREE.ConeGeometry(.065*s,(.3+Math.abs(i)*.05)*s,5),i===0?accent:claw,g,[i*.14*s,1.88*s,-1.08*s],[0,0,-i*.08]);
    for(const side of [-1,1]){
      cyl(g,.2*s,.25*s,.48*s,[side*.58*s,1.5*s,.32*s],armorDark,[Math.PI/2,0,0],12);
      cyl(g,.11*s,.14*s,.13*s,[side*.58*s,1.5*s,.61*s],eye,[Math.PI/2,0,0],10);
      box(g,[.3*s,.24*s,.26*s],[side*.4*s,1.03*s,-1.22*s],armor,[.1,0,side*.16]);
    }
  }
  const shadowMaterial=new THREE.MeshBasicMaterial({color:0x000000,transparent:true,opacity:type==='boss'?.48:.34,depthWrite:false,toneMapped:false});
  const shadow=mesh(new THREE.CircleGeometry(1,28),shadowMaterial,g,[0,.025,.12*s],[-Math.PI/2,0,0],false);
  shadow.scale.set(.68*s*w,1.05*s,1);
  g.userData={legs,ears,head,body,tail,aura,shadow};
  return g;
}

const ENEMIES={
  basic:{hp:80,speed:5.4,damage:10,radius:.72}, tank:{hp:240,speed:4.5,damage:5,radius:1.12}, fast:{hp:40,speed:6.84,damage:5,radius:.55},
  scout:{hp:65,speed:6.03,damage:7,radius:.65}, brute:{hp:150,speed:4.86,damage:8,radius:.9}, mini:{hp:80,speed:3.6,damage:2,radius:.62},
};

const HEALTH_BAR_SPEC={
  basic:{width:1.5,height:2.45},fast:{width:1.25,height:2.05},tank:{width:2.25,height:3.6},
  scout:{width:1.45,height:2.45},brute:{width:1.95,height:3.15},mini:{width:1.05,height:1.8},boss:{width:3.8,height:6.4},
};
function makeEnemyHealthBar(type){
  const spec=HEALTH_BAR_SPEC[type]||HEALTH_BAR_SPEC.basic;
  const group=new THREE.Group();group.renderOrder=50;scene.add(group);
  const frameMat=new THREE.MeshBasicMaterial({color:0x0a1010,transparent:true,opacity:.92,depthTest:false,depthWrite:false,toneMapped:false});
  const backMat=new THREE.MeshBasicMaterial({color:0x351416,transparent:true,opacity:.96,depthTest:false,depthWrite:false,toneMapped:false});
  const fillMat=new THREE.MeshBasicMaterial({color:type==='boss'?0xffb52f:0x68e876,transparent:true,opacity:1,depthTest:false,depthWrite:false,toneMapped:false});
  const frame=mesh(new THREE.PlaneGeometry(spec.width+.16,.22),frameMat,group,[0,0,0],[0,0,0],false);frame.renderOrder=50;
  const back=mesh(new THREE.PlaneGeometry(spec.width,.105),backMat,group,[0,0,.002],[0,0,0],false);back.renderOrder=51;
  const fillGeo=new THREE.PlaneGeometry(spec.width,.105);fillGeo.translate(spec.width*.5,0,0);
  const fill=mesh(fillGeo,fillMat,group,[-spec.width*.5,0,.004],[0,0,0],false);fill.renderOrder=52;
  const cap=mesh(new THREE.PlaneGeometry(.04,.16),new THREE.MeshBasicMaterial({color:0xe9cf83,depthTest:false,depthWrite:false,toneMapped:false}),group,[-spec.width*.5-.035,0,.006],[0,0,0],false);cap.renderOrder=53;
  group.userData={fill,height:spec.height,materials:[frameMat,backMat,fillMat,cap.material]};
  return group;
}

const playerModel=makeFirstPersonRig();
function freshRun(){return {
  speed:0,hpBonus:0,armorBonus:0,magAdd:0,magMult:1,reloadAdd:0,reloadMult:1,rateMult:1,spreadMult:1,
  particleBoost:0,pierceBonus:0,chainChance:0,chillChance:0,pushChance:0,killLeech:false,adrenaline:false,
  autoLoader:false,reserveReload:0,shieldReady:false,fieldMedic:false,coinFinder:false,decoy:false,drone:false,
  mine:false,timeRipple:false,ration:false,scavenge:false,killCounter:0,lastHit:performance.now()/1000,droneTimer:2,mineTimer:5,rationTimer:0,
  weaponDamage:0,weaponPellets:0,weaponPierce:0,weaponRange:0,weaponBlast:0,weaponBeamWidth:0,weaponBeamLife:0,
  weaponUpgradeCount:0,ultimate:null,ultimateWeapon:null,
};}
let run=freshRun();
const player={
  pos:new THREE.Vector3(0,0,12), yaw:0, pitch:-.12, velocity:new THREE.Vector3(), yVel:0, grounded:true,
  hp:100,maxHp:100,armor:0,baseSpeed:7.2,speed:7.2,rolling:0,rollTime:0,rollCd:0,invuln:0,reloading:0,weaponIndex:0,ammo:10,lastShot:0,
};
function applyProfileToPlayer(refill=false){
  player.maxHp=100+profile.talents.hp*10+run.hpBonus;player.armor=profile.talents.armor+run.armorBonus;player.baseSpeed=7.2+profile.talents.speed*.27+run.speed;player.speed=player.baseSpeed;
  player.hp=refill?player.maxHp:Math.min(player.hp,player.maxHp);
}
applyProfileToPlayer(true);
let equippedModel=null;
function equipWeapon(index) {
  index=Math.max(0,Math.min(WEAPONS.length-1,index)); player.weaponIndex=index; player.reloading=0;
  if(equippedModel) playerModel.socket.remove(equippedModel);
  equippedModel=weaponModels.get(WEAPONS[index].key).clone(true); playerModel.socket.add(equippedModel);
  playerModel.magazine=equippedModel.getObjectByName('magazine');playerModel.action=equippedModel.getObjectByName('action');
  if(playerModel.magazine){playerModel.magazine.userData.home=playerModel.magazine.position.clone();playerModel.magazine.userData.homeRot=playerModel.magazine.rotation.clone();}
  if(playerModel.action)playerModel.action.userData.home=playerModel.action.position.clone();
  const stats=weaponStats(index);player.ammo=Math.min(player.ammo || stats.mag,stats.mag); if(player.ammo<=0) player.ammo=stats.mag;
  playerModel.muzzle.position.z=-(WEAPONS[index].key==='sniper'?2.45:WEAPONS[index].key==='crossbow'?1.62:1.7);
  if(ui.menuWeaponName)ui.menuWeaponName.textContent=WEAPONS[index].name;
  updateHud(); showMessage(WEAPONS[index].name,700);
}

const STAGE_QUOTAS=[30,40,50,60,1,75,92,112,135,160];
const STAGE_LIVE_LIMITS=[
  {basic:12},{basic:10,tank:4},{basic:10,fast:6},{basic:10,tank:4,fast:6},{basic:1},
  {basic:11,tank:4,fast:5,scout:4,brute:2},{basic:12,tank:5,fast:6,scout:5,brute:3},
  {basic:12,tank:6,fast:7,scout:6,brute:4},{basic:13,tank:7,fast:8,scout:7,brute:5},
  {basic:14,tank:8,fast:9,scout:8,brute:6},
];
const enemies=[]; const projectiles=[]; const effects=[];
let stage=1, kills=0, quota=STAGE_QUOTAS[0], scrap=profile.scrap, runScrap=0, combo=0, comboTimer=0, spawnTimer=0, boss=null, playing=false, gameEnded=false;
let xp=0,xpNeed=5,upgradeLevel=0,upgradePaused=false,currentUpgradeCards=[],upgradeRefreshLeft=2,prebossChoicesLeft=0,prebossComplete=false,pendingBoss=false,queuedUpgrade=false,timeRippleTimer=0;
let materialsGained={alloy:0,energy:0,bio:0};
let maxUnlocked=Math.max(1,Math.min(10,Number(localStorage.getItem('wz3d-unlocked')||1)));
const keys=new Set(); let firing=false, pointerLocked=false, dragLook=false, messageTimer=0, lookHintTimer=0;
const moveInput={x:0,y:0};
equipWeapon(0);

const GENERIC_UPGRADES=[
  {name:'机动伺服器',desc:'本次行动中，基础移动速度提高 1。',tier:'普通',func:'speed'},
  {name:'生命强化组件',desc:'最大生命值提高 25，并立即恢复 25 点生命。',tier:'普通',func:'hp25'},
  {name:'扩容供弹机构',desc:'当前武器弹匣容量增加 5 发，不会补满现有弹匣。',tier:'普通',func:'mag5'},
  {name:'快速装填组件',desc:'当前武器装填时间缩短 0.3 秒。',tier:'普通',func:'reload'},
  {name:'扳机响应校准',desc:'当前武器射击间隔缩短 8%。',tier:'普通',func:'rate'},
  {name:'战地急救包',desc:'立即恢复 30 点生命。',tier:'普通',func:'heal30'},
  {name:'弹道稳定器',desc:'当前武器弹道散布降低 15%。',tier:'普通',func:'accuracy'},
  {name:'轻型复合护甲',desc:'本次行动中，受到的每次伤害减少 2 点。',tier:'普通',func:'armor'},
  {name:'弹药回收协议',desc:'击败敌人时有 15% 概率回收 2 发弹药。',tier:'普通',func:'scavenge'},
  {name:'持续补给协议',desc:'连续 8 秒未受伤时，恢复 10 点生命。',tier:'普通',func:'ration'},
  {name:'穿透弹药组件',desc:'弹药可额外穿透 2 个目标。',tier:'稀有',func:'pierce'},
  {name:'链式伤害模块',desc:'命中后有 30% 概率向下一目标传导；每次传导重新判定。',tier:'稀有',func:'chain'},
  {name:'低温弹药',desc:'命中时有 35% 概率使目标显著减速 2 秒。',tier:'普通',func:'chill'},
  {name:'动能击退装置',desc:'命中时有 25% 概率将目标向后击退。',tier:'普通',func:'push'},
  {name:'战地复苏模块',desc:'每击败 5 名敌人时，有 50% 概率恢复 10 点生命。',tier:'稀有',func:'leech'},
  {name:'自动补弹系统',desc:'每击败 8 名敌人，自动补充 2 发弹药。',tier:'稀有',func:'autoload'},
  {name:'临界防护协议',desc:'生命低于 35% 时，自动触发一次 2 秒无敌护盾。',tier:'史诗',func:'shield'},
  {name:'肾上腺素回路',desc:'生命低于 45% 时，移动速度额外提高 1.5。',tier:'史诗',func:'adrenaline'},
  {name:'防御无人机',desc:'每 2 秒对最近的敌人造成 8 点支援伤害。',tier:'史诗',func:'drone'},
  {name:'感应地雷',desc:'每 5 秒在附近目标脚下引爆一枚 24 伤害地雷。',tier:'稀有',func:'mine'},
  {name:'时间减速场',desc:'每击败 10 名敌人后，使全场敌人减速 4 秒。',tier:'史诗',func:'time'},
  {name:'强化生命框架',desc:'最大生命值提高 50，并立即恢复 50 点生命。',tier:'稀有',func:'hp50'},
  {name:'堡垒弹匣',desc:'当前武器弹匣容量提高 50%，不会补满现有弹匣。',tier:'稀有',func:'maghalf'},
];
const WEAPON_MODULES={
  pistol:[['手枪：穿甲套件','额外穿透 1 个目标。','weapon_pierce'],['手枪：稳定握把','弹道散布降低 15%。','weapon_stability'],['手枪：长程枪管','有效射程增加 20。','weapon_range']],
  rifle:[['突击步枪：穿甲弹芯','额外穿透 1 个目标。','weapon_pierce'],['突击步枪：平衡枪托','弹道散布降低 15%。','weapon_stability'],['突击步枪：延程组件','有效射程增加 20。','weapon_range']],
  sniper:[['狙击枪：高穿深弹','额外穿透 1 个目标。','weapon_pierce'],['狙击枪：精密导轨','弹道散布降低 15%。','weapon_stability'],['狙击枪：超程弹体','有效射程增加 20。','weapon_range']],
  shotgun:[['霰弹枪：簇射供弹','每次额外发射 1 枚弹丸。','weapon_pellet'],['霰弹枪：收束器','弹道散布降低 15%。','weapon_stability'],['霰弹枪：破障弹','额外穿透 1 个目标。','weapon_pierce']],
  smg:[['冲锋枪：高速弹芯','额外穿透 1 个目标。','weapon_pierce'],['冲锋枪：控枪模组','弹道散布降低 15%。','weapon_stability'],['冲锋枪：长程机匣','有效射程增加 20。','weapon_range']],
  flamethrower:[['喷火枪：增压喷口','火焰有效射程增加 20。','weapon_range'],['喷火枪：分流喷嘴','每次额外喷出 1 团火焰。','weapon_pellet'],['喷火枪：收束火焰','火焰散布降低 15%。','weapon_stability']],
  grenade:[['榴弹发射器：破片外壳','爆炸半径增加 1.5 米。','weapon_blast'],['榴弹发射器：延程装药','榴弹有效射程增加 20。','weapon_range'],['榴弹发射器：集束装填','每次额外发射 1 枚榴弹。','weapon_pellet']],
  laser:[['激光枪：棱镜扩束','激光束视觉宽度提高。','weapon_beam_width'],['激光枪：持续电容','激光束残留时间延长。','weapon_beam_life'],['激光枪：折射镜组','激光束散布降低 15%。','weapon_stability']],
  crossbow:[['弩：重型箭簇','弩箭额外穿透 1 个目标。','weapon_pierce'],['弩：稳固弓臂','弩箭散布降低 15%。','weapon_stability'],['弩：延程箭杆','有效射程增加 20。','weapon_range']],
};
const ULTIMATE_LABELS={
  pistol:['双重速射','穿甲超载','疾速扳机'],rifle:['三连火网','战术超穿','突击回路'],sniper:['双重狙击','反器材超载','迅捷枪机'],
  shotgun:['分裂弹幕','破障超载','暴风供弹'],smg:['密集弹幕','高速穿甲','狂飙机匣'],flamethrower:['三重喷流','高温超载','涡轮供油'],
  grenade:['集束榴弹','重爆超载','自动装填'],laser:['三棱折射','聚焦超载','脉冲回路'],crossbow:['双矢齐发','贯穿箭簇','滑轮回路'],
};
function ultimateCards(){
  const w=WEAPONS[player.weaponIndex],labels=ULTIMATE_LABELS[w.key],defs=[
    {name:`${w.name}：终极 I｜${labels[0]}`,desc:'额外发射弹丸，并以适度单发伤害降低作为平衡。',tier:'史诗',func:'ultimate_barrage'},
    {name:`${w.name}：终极 II｜${labels[1]}`,desc:w.key==='laser'?'激光伤害增加 3，并显著加宽光束。':'伤害增加 8，并额外穿透 5 个目标。',tier:'史诗',func:'ultimate_overcharge'},
    {name:`${w.name}：终极 III｜${labels[2]}`,desc:'射击间隔与装填时间均缩短 40%。',tier:'史诗',func:'ultimate_storm'},
    {name:`${w.name}：终极 IV｜堡垒弹仓`,desc:'弹匣容量提高 50%，并获得 2 点护甲。',tier:'史诗',func:'ultimate_fortress'},
    {name:`${w.name}：终极 V｜远征穿透`,desc:'额外穿透 3 个目标，有效射程增加 80。',tier:'史诗',func:'ultimate_ranger'},
  ];
  return defs.sort(()=>Math.random()-.5).slice(0,3);
}
function generateUpgradeCards(){
  if(!run.ultimate&&run.weaponUpgradeCount>=2)return ultimateCards();
  const w=WEAPONS[player.weaponIndex],weighted=[...GENERIC_UPGRADES,...GENERIC_UPGRADES];
  const handling=[
    {name:`${w.name}：快速机件`,desc:'当前武器射击间隔进一步缩短。',tier:'普通',func:'weapon_rate'},
    {name:`${w.name}：扩容组件`,desc:'当前武器弹匣容量增加 8 发。',tier:'普通',func:'weapon_mag'},
    {name:`${w.name}：速装机构`,desc:'当前武器装填时间减少 1 秒。',tier:'稀有',func:'weapon_reload'},
  ];
  const specific=WEAPON_MODULES[w.key].map(([name,desc,func])=>({name,desc,tier:func==='weapon_blast'||func==='weapon_pellet'?'稀有':'普通',func}));
  for(let i=0;i<4;i++)weighted.push(...handling,...specific);
  if(w.damage<=12&&w.key!=='laser')for(let i=0;i<4;i++)weighted.push({name:`${w.name}：强化弹头`,desc:'当前武器单次伤害增加 1。',tier:'稀有',func:'weapon_damage'});
  const chosen=[];while(chosen.length<3){const card=weighted[Math.floor(Math.random()*weighted.length)];if(!chosen.some(c=>c.name===card.name))chosen.push(card);}return chosen;
}
function applyUpgrade(card){
  const oldMag=weaponStats(player.weaponIndex).mag;
  switch(card.func){
    case'speed':run.speed+=1;break;case'hp25':run.hpBonus+=25;player.hp+=25;break;case'hp50':run.hpBonus+=50;player.hp+=50;break;
    case'mag5':run.magAdd+=5;break;case'maghalf':run.magMult*=1.5;break;case'reload':run.reloadAdd-=.3;break;case'rate':run.rateMult*=.92;break;
    case'heal30':player.hp=Math.min(player.maxHp,player.hp+30);break;case'accuracy':run.spreadMult*=.85;break;case'armor':run.armorBonus+=2;break;
    case'scavenge':run.scavenge=true;break;case'ration':run.ration=true;run.lastHit=performance.now()/1000;break;case'pierce':run.pierceBonus+=2;break;
    case'chain':run.chainChance=.3;break;case'chill':run.chillChance=.35;break;case'push':run.pushChance=.25;break;case'leech':run.killLeech=true;break;
    case'autoload':run.autoLoader=true;break;case'shield':run.shieldReady=true;break;case'adrenaline':run.adrenaline=true;break;case'drone':run.drone=true;break;
    case'mine':run.mine=true;break;case'time':run.timeRipple=true;break;
    case'weapon_rate':run.rateMult*=.86;break;case'weapon_mag':run.magAdd+=8;break;case'weapon_reload':run.reloadAdd-=1;break;
    case'weapon_pierce':run.weaponPierce+=1;break;case'weapon_stability':run.spreadMult*=.85;break;case'weapon_range':run.weaponRange+=20;break;
    case'weapon_pellet':run.weaponPellets+=1;break;case'weapon_blast':run.weaponBlast+=1.5;break;case'weapon_beam_width':run.weaponBeamWidth+=2;break;
    case'weapon_beam_life':run.weaponBeamLife+=1;break;case'weapon_damage':run.weaponDamage+=1;break;
    case'ultimate_barrage':run.ultimate='barrage';break;case'ultimate_overcharge':run.ultimate='overcharge';break;case'ultimate_storm':run.ultimate='storm';break;
    case'ultimate_fortress':run.ultimate='fortress';run.armorBonus+=2;break;case'ultimate_ranger':run.ultimate='ranger';break;
  }
  if(card.func.startsWith('weapon_'))run.weaponUpgradeCount++;
  if(card.func.startsWith('ultimate_'))run.ultimateWeapon=WEAPONS[player.weaponIndex].key;
  applyProfileToPlayer(false);player.hp=Math.min(player.maxHp,player.hp);player.ammo=Math.min(player.ammo,Math.max(oldMag,weaponStats(player.weaponIndex).mag));
}
function renderUpgradeCards(cards){
  const ultimate=cards.every(c=>c.func.startsWith('ultimate_'));currentUpgradeCards=cards;ui.upgradeCards.replaceChildren();
  ui.upgrade.classList.remove('ultimate-charging','ultimate-ready');ui.upgradeEyebrow.textContent=ultimate?'EXCLUSIVE WEAPON CORE':'TACTICAL AUGMENTATION';
  ui.upgradeTitle.textContent=ultimate?'终极分支选择':'战术强化终端';ui.upgradeContext.textContent=ultimate?'高压核心正在展开：本次行动仅可锁定一个终极分支':'从废土补给中选择一项作战模块';
  ui.upgradeSequence.textContent=pendingBoss?`首领战前整备 · 剩余 ${prebossChoicesLeft} 次选择`:`战术等级 ${upgradeLevel+1} · 当前武器 ${WEAPONS[player.weaponIndex].name}`;
  ui.upgradeRefresh.textContent=`刷新（剩余 ${upgradeRefreshLeft}/2）`;ui.upgradeRefresh.disabled=true;
  const reveal=()=>{cards.forEach((card,index)=>{const button=document.createElement('button');button.className=`upgrade-card ${card.tier==='史诗'?'epic':card.tier==='稀有'?'rare':''}`;button.style.setProperty('--delay',`${index*.08}s`);button.innerHTML=`<span class="mod-code">MOD-${String(index+1).padStart(2,'0')}</span><h3>${card.name}</h3><p>${card.desc}</p><span class="tier">[${card.tier} 模组]</span>`;button.addEventListener('click',()=>chooseUpgrade(card),{once:true});ui.upgradeCards.append(button);});ui.upgradeRefresh.disabled=upgradeRefreshLeft<=0;};
  if(ultimate){ui.upgrade.classList.add('ultimate-charging');setTimeout(()=>{ui.upgrade.classList.remove('ultimate-charging');ui.upgrade.classList.add('ultimate-ready');reveal();},760);}else reveal();
}
function openUpgrade(cards=generateUpgradeCards()){
  if(gameEnded)return;upgradeRefreshLeft=2;upgradePaused=true;firing=false;document.exitPointerLock?.();ui.upgrade.classList.add('active');renderUpgradeCards(cards);
}
function closeUpgrade(){ui.upgrade.classList.remove('active','ultimate-charging','ultimate-ready');ui.upgradeCards.replaceChildren();upgradePaused=false;updateHud();}
function chooseUpgrade(card){
  if(!upgradePaused)return;ui.upgradeCards.querySelectorAll('button').forEach(b=>b.disabled=true);applyUpgrade(card);showMessage(`已安装：${card.name}`,1100);
  if(pendingBoss){prebossChoicesLeft--;if(prebossChoicesLeft>0){upgradeRefreshLeft=2;setTimeout(()=>renderUpgradeCards(generateUpgradeCards()),260);return;}pendingBoss=false;prebossComplete=true;closeUpgrade();spawnBoss(1);return;}
  closeUpgrade();if(xp>=xpNeed)setTimeout(processXpUpgrade,180);
}
function processXpUpgrade(){
  if(upgradePaused||gameEnded||xp<xpNeed)return;xp-=xpNeed;upgradeLevel++;xpNeed=upgradeLevel===1?8:8+(upgradeLevel-1)*4;openUpgrade();updateHud();
}
function gainXp(amount){xp+=amount;updateHud();if(xp>=xpNeed&&!upgradePaused)setTimeout(processXpUpgrade,120);}
function beginPrebossUpgrades(){pendingBoss=true;prebossChoicesLeft=5;showMessage('首领战前整备',1000);openUpgrade();}
function refreshUpgradeCards(){if(!upgradePaused||upgradeRefreshLeft<=0)return;upgradeRefreshLeft--;renderUpgradeCards(generateUpgradeCards());}

function isBlocked(x,z,r=.45) {
  if(Math.abs(x)>worldSize/2-1||Math.abs(z)>worldSize/2-1) return true;
  for(const o of obstacles) if(x+r>o.bounds.min.x&&x-r<o.bounds.max.x&&z+r>o.bounds.min.z&&z-r<o.bounds.max.z) return true;
  return false;
}
function moveWithCollision(pos,dx,dz,r=.45) {
  if(!isBlocked(pos.x+dx,pos.z,r)) pos.x+=dx;
  if(!isBlocked(pos.x,pos.z+dz,r)) pos.z+=dz;
}
function randomSpawn(radiusMin=22,radiusMax=42) {
  for(let i=0;i<30;i++) {
    const a=Math.random()*Math.PI*2, r=radiusMin+Math.random()*(radiusMax-radiusMin);
    const x=THREE.MathUtils.clamp(player.pos.x+Math.sin(a)*r,-70,70), z=THREE.MathUtils.clamp(player.pos.z-Math.cos(a)*r,-70,70);
    if(!isBlocked(x,z,1.1)) return new THREE.Vector3(x,0,z);
  }
  return new THREE.Vector3(0,0,-35);
}
function spawnEnemy(type='basic',at=null) {
  const cfg=ENEMIES[type], group=catModel(type); group.position.copy(at||randomSpawn()); scene.add(group);
  const stageHp=stage>1?Math.round(cfg.hp*1.25):cfg.hp;
  const e={type,group,pos:group.position,hp:stageHp,maxHp:stageHp,speed:cfg.speed,damage:cfg.damage,radius:cfg.radius,attackCd:0,hit:0,phase:Math.random()*6.28,dead:false,healthBar:makeEnemyHealthBar(type)};
  enemies.push(e); return e;
}
function spawnBoss(phase=2) {
  const group=catModel('boss'); const at=randomSpawn(24,30); group.position.copy(at); scene.add(group);
  const finalPhaseOne=stage===5&&phase===1;const combatStage=finalPhaseOne?1:stage;
  let maxHp=360+combatStage*220;if(finalPhaseOne)maxHp*=2;else if(combatStage>1)maxHp=Math.round(maxHp*1.4);if(stage===5)maxHp=Math.round(maxHp*1.6);
  boss={type:'boss',group,pos:group.position,hp:maxHp,maxHp,speed:(.63+combatStage*.15)*1.8,damage:10,radius:2.5,attackCd:0,hit:0,phase,dead:false,teleport:5,summon:8,stage,healthBar:makeEnemyHealthBar('boss')};
  enemies.push(boss); ui.bossHud.classList.remove('hidden'); ui.bossName.textContent=`第 ${stage} 战区首领 · 废土猫王`; showMessage('⚠ 首领来袭',1800);
  playSfx('alarm',.48,.5);setBgm('boss');
}

function addMaterial(type,amount){
  profile.materials[type]+=amount;materialsGained[type]+=amount;saveProfile();renderMaterialSummaries();
  showMessage(`${MATERIAL_INFO[type].name} +${amount}`,900);
}

function removeEnemy(e) {
  if(e.dead)return; e.dead=true; const i=enemies.indexOf(e); if(i>=0)enemies.splice(i,1);
  if(e.healthBar){scene.remove(e.healthBar);e.healthBar.traverse(part=>part.geometry?.dispose());for(const material of e.healthBar.userData.materials||[])material.dispose();e.healthBar=null;}
  // Keep the original illustration visible for a short fall/fade instead of
  // popping it out of existence on the killing hit.
  effects.push({object:e.group,life:.42,max:.42,death:true});
  const scrapDrop=e.type==='boss'?20:e.type==='tank'?3:1;
  kills++; scrap+=scrapDrop;runScrap+=scrapDrop;profile.scrap=scrap;saveProfile();combo++; comboTimer=3;run.killCounter++;
  if(e.type!=='boss')gainXp(['tank','brute'].includes(e.type)?2:1);
  if(run.killLeech&&run.killCounter%5===0&&Math.random()<.5)player.hp=Math.min(player.maxHp,player.hp+10);
  if(run.autoLoader&&run.killCounter%8===0)player.ammo=Math.min(weaponStats(player.weaponIndex).mag,player.ammo+2);
  if(run.coinFinder&&run.killCounter%5===0){scrap+=2;runScrap+=2;profile.scrap=scrap;saveProfile();}
  if(run.fieldMedic&&['tank','brute'].includes(e.type))player.hp=Math.min(player.maxHp,player.hp+5);
  if(run.scavenge&&Math.random()<.15)player.ammo=Math.min(weaponStats(player.weaponIndex).mag,player.ammo+2);
  if(run.timeRipple&&run.killCounter%10===0){timeRippleTimer=4;showMessage('时间减速场启动',900);}
  if(e.type!=='boss'&&e.type!=='mini'&&Math.random()<.16)addMaterial(STAGE_MATERIAL[stage-1],1);
  if(e===boss) {
    const defeatedPhase=e.phase;boss=null;ui.bossHud.classList.add('hidden');
    if(stage===5&&defeatedPhase===1){
      // 立即登记并生成第二阶段，避免过渡期间的刷怪检查再次生成第一阶段。
      showMessage('猫王进入第二阶段',1800);
      spawnBoss(2);
    }
    else{addMaterial(STAGE_MATERIAL[stage-1],2+Math.floor(stage/3));maxUnlocked=Math.max(maxUnlocked,Math.min(10,stage+1));localStorage.setItem('wz3d-unlocked',String(maxUnlocked));finish(true);}
  }
  updateHud();
}
function damageEnemy(e,amount,point=null,canProc=true) {
  if(!e||e.dead)return; e.hp-=amount; e.hit=.12; e.group.scale.setScalar(1.12);
  if(e.healthBar?.userData.fill)e.healthBar.userData.fill.scale.x=THREE.MathUtils.clamp(e.hp/e.maxHp,0,1);
  if(e.group.userData.artMaterial)e.group.userData.artMaterial.color.setHex(0xff7777);
  burst(point||e.pos.clone().add(new THREE.Vector3(0,1,0)),e.type==='boss'?0xffc64b:0xff6b35,Math.min(16,5+Math.floor(amount/12)));
  if(canProc&&run.chillChance&&Math.random()<run.chillChance)e.slowTimer=2;
  if(canProc&&run.pushChance&&Math.random()<run.pushChance){const away=e.pos.clone().sub(player.pos).setY(0).normalize();moveWithCollision(e.pos,away.x*1.6,away.z*1.6,e.radius*.65);}
  if(canProc&&run.chainChance&&Math.random()<run.chainChance)chainDamage(e,Math.max(1,amount*.5),new Set([e]));
  if(e.hp<=0)removeEnemy(e);
}
function chainDamage(from,amount,visited){
  const next=enemies.filter(e=>!e.dead&&!visited.has(e)).sort((a,b)=>a.pos.distanceToSquared(from.pos)-b.pos.distanceToSquared(from.pos))[0];
  if(!next||next.pos.distanceTo(from.pos)>24)return;visited.add(next);tracerTube(from.pos.clone().add(new THREE.Vector3(0,1,0)),next.pos.clone().add(new THREE.Vector3(0,1,0)),.028,0x82eaff,.95,.16);damageEnemy(next,amount,next.pos.clone().add(new THREE.Vector3(0,1,0)),false);if(Math.random()<run.chainChance)chainDamage(next,Math.max(1,amount*.8),visited);
}
function hurt(amount) {
  if(player.invuln>0||gameEnded)return; const reduced=Math.max(1,amount-player.armor); player.hp-=reduced; player.invuln=.42;
  run.lastHit=performance.now()/1000;run.rationTimer=0;if(run.shieldReady&&player.hp/player.maxHp<.35){run.shieldReady=false;player.invuln=2;showMessage('临界护盾启动',1000);}
  ui.damage.style.opacity='.8'; setTimeout(()=>ui.damage.style.opacity='0',90); if(player.hp<=0)finish(false); updateHud();
}

function raySphere(origin,dir,center,radius) {
  const oc=center.clone().sub(origin), t=oc.dot(dir); if(t<0)return Infinity;
  const d2=oc.lengthSq()-t*t; if(d2>radius*radius)return Infinity;
  return t-Math.sqrt(Math.max(0,radius*radius-d2));
}
function obstacleDistance(origin,dir,maxDist) {
  let nearest=maxDist; const ray=new THREE.Ray(origin,dir); const hit=new THREE.Vector3();
  for(const o of obstacles) if(ray.intersectBox(o.bounds,hit)) nearest=Math.min(nearest,hit.distanceTo(origin));
  return nearest;
}
function tracerTube(start,end,radius,color,opacity,life){
  const dir=end.clone().sub(start),length=dir.length();if(length<.02)return null;
  const material=new THREE.MeshBasicMaterial({color,transparent:true,opacity,depthWrite:false,toneMapped:false,blending:THREE.AdditiveBlending});
  const tube=new THREE.Mesh(new THREE.CylinderGeometry(radius,radius*.72,length,6),material);
  tube.position.copy(start).add(end).multiplyScalar(.5);tube.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),dir.normalize());tube.renderOrder=12;scene.add(tube);
  effects.push({object:tube,life,max:life,dispose:true,beam:true});return tube;
}
function tracer(start,end,kind='bullet') {
  const distance=start.distanceTo(end),dir=end.clone().sub(start).normalize();
  if(kind==='flamethrower'){
    const maxEnd=start.clone().addScaledVector(dir,Math.min(distance,24));const length=start.distanceTo(maxEnd),steps=Math.max(5,Math.floor(length/1.35));
    for(let i=1;i<=steps;i++){
      const t=i/steps,p=maxEnd.clone().lerp(start,1-t);p.x+=(Math.random()-.5)*(.15+t*.42);p.y+=(Math.random()-.5)*(.1+t*.28);p.z+=(Math.random()-.5)*(.15+t*.42);
      const hot=t<.3?0xffe08a:t<.7?0xff781f:0xc7260f;const material=new THREE.MeshBasicMaterial({color:hot,transparent:true,opacity:.92,depthWrite:false,toneMapped:false,blending:THREE.AdditiveBlending});
      const flame=new THREE.Mesh(new THREE.SphereGeometry(.08+t*.16,7,5),material);flame.position.copy(p);flame.userData.vel=dir.clone().multiplyScalar(2.2+Math.random()*2).add(new THREE.Vector3((Math.random()-.5)*.8,.5+Math.random(),(Math.random()-.5)*.8));scene.add(flame);effects.push({object:flame,life:.18+Math.random()*.16,max:.34,particle:true,dispose:true});
    }
    return;
  }
  if(kind==='laser'){
    const width=.085+run.weaponBeamWidth*.012,life=.18+run.weaponBeamLife*.035;tracerTube(start,end,width,0x2bd5ff,.18,life);tracerTube(start,end,.022+run.weaponBeamWidth*.004,0xc8ffff,1,life);return;
  }
  if(kind==='sniper'){
    tracerTube(start,end,.045,0xff9f38,.24,.22);tracerTube(start,end,.013,0xfff0b5,1,.22);return;
  }
  if(kind==='crossbow'){
    tracerTube(start,end,.026,0xd8aa63,.98,.28);tracerTube(start,end,.009,0xf4e8bf,1,.28);return;
  }
  const isShotgun=kind==='shotgun';const isSmg=kind==='smg';
  tracerTube(start,end,isShotgun ? 0.014 : (isSmg ? 0.016 : 0.021),isShotgun ? 0xffbd61 : 0xffd783,isSmg ? 0.74 : 0.92,isSmg ? 0.12 : (isShotgun ? 0.16 : 0.18));
}
function burst(pos,color,count=7) {
  for(let i=0;i<count;i++) {
    const p=sphere(scene,.035+Math.random()*.045,pos.clone().toArray(),mat(color,.4,.1,color),6); p.userData.vel=new THREE.Vector3((Math.random()-.5)*3,Math.random()*3,(Math.random()-.5)*3); effects.push({object:p,life:.25+Math.random()*.22,max:.45,particle:true});
  }
}
function hitscan(weapon,dir,damage) {
  const origin=camera.position.clone(), maxDist=weapon.range||90, wallDist=obstacleDistance(origin,dir,maxDist);
  const hits=enemies.filter(e=>!e.dead).map(e=>({e,t:raySphere(origin,dir,e.pos.clone().add(new THREE.Vector3(0,e.type==='boss'?2.4:1.0,0)),e.radius)})).filter(h=>h.t<wallDist).sort((a,b)=>a.t-b.t);
  const pierce=weapon.pierce||1; for(let i=0;i<Math.min(pierce,hits.length);i++)damageEnemy(hits[i].e,damage,origin.clone().addScaledVector(dir,hits[i].t));
  const end=origin.clone().addScaledVector(dir,hits.length?Math.min(wallDist,hits[Math.min(pierce,hits.length)-1].t):wallDist);
  tracer(playerModel.muzzle.getWorldPosition(new THREE.Vector3()),end,weapon.key);
}
function fireWeapon(now) {
  const w=weaponStats(player.weaponIndex); if(player.reloading>0||now-player.lastShot<w.rate||player.rolling>0)return;
  if(player.ammo<=0){startReload();return;} player.lastShot=now;player.ammo--;
  const soundKind=w.laser?'laser':w.flame?'flame':w.grenade?'grenade':w.key==='sniper'?'sniper':w.key==='shotgun'?'shotgun':'gun';
  const soundVolume=w.key==='smg'?.13:w.laser?.25:w.key==='sniper'?.30:w.key==='shotgun'?.25:.20;playSfx(soundKind,soundVolume,Math.max(.035,w.rate*.7));
  playerModel.socket.position.z=.055; setTimeout(()=>{if(player.reloading<=0)playerModel.socket.position.z=0;},45);
  const muzzle=playerModel.muzzle.getWorldPosition(new THREE.Vector3()); burst(muzzle,w.flame?0xff6a1b:w.laser?0x46f2ff:0xffc75a,w.flame?5:3);
  if(w.grenade){
    for(let i=0;i<w.pellets;i++){const dir=new THREE.Vector3();camera.getWorldDirection(dir);dir.x+=(Math.random()-.5)*w.spread;dir.y+=(Math.random()-.5)*w.spread;dir.normalize();const ball=sphere(scene,.16,muzzle.toArray(),mat(0x4d6947,.6,.4),10);projectiles.push({object:ball,vel:dir.multiplyScalar(24).add(new THREE.Vector3(0,3.5,0)),life:2.2,damage:w.damage,blastRadius:w.blastRadius});}
  }else{
    const pellets=w.pellets||1;for(let i=0;i<pellets;i++){const dir=new THREE.Vector3();camera.getWorldDirection(dir);dir.x+=(Math.random()-.5)*w.spread;dir.y+=(Math.random()-.5)*w.spread;dir.z+=(Math.random()-.5)*w.spread;dir.normalize();hitscan(w,dir,w.damage);}
  }
  updateHud();
}
function startReload(){const w=weaponStats(player.weaponIndex);if(player.reloading>0||player.ammo===w.mag)return;player.reloading=w.reload;showMessage('换弹中',500);}

function updatePlayer(dt,time) {
  let x=(keys.has('KeyD')?1:0)-(keys.has('KeyA')?1:0)+moveInput.x, z=(keys.has('KeyS')?1:0)-(keys.has('KeyW')?1:0)+moveInput.y;
  const len=Math.hypot(x,z);if(len>1){x/=len;z/=len;}
  // Three.js cameras look down local -Z. After a Y-axis yaw, the horizontal
  // forward vector is (-sin(yaw), 0, -cos(yaw)); using +sin made movement
  // mirror the view after turning left or right.
  const forward=new THREE.Vector3(-Math.sin(player.yaw),0,-Math.cos(player.yaw));
  const right=new THREE.Vector3(Math.cos(player.yaw),0,-Math.sin(player.yaw));
  const dir=forward.multiplyScalar(-z).add(right.multiplyScalar(x));
  player.speed=player.baseSpeed+(run.adrenaline&&player.hp/player.maxHp<=.45?1.5:0);let speed=player.speed;if(player.rolling>0)speed=17;
  if(player.rolling>0){player.rolling-=dt;dir.copy(player.velocity);} else if(dir.lengthSq()>.01){dir.normalize();player.velocity.copy(dir);} else dir.set(0,0,0);
  moveWithCollision(player.pos,dir.x*speed*dt,dir.z*speed*dt,.46);
  player.yVel-=19*dt;player.pos.y+=player.yVel*dt;if(player.pos.y<=0){player.pos.y=0;player.yVel=0;player.grounded=true;}
  player.rollCd=Math.max(0,player.rollCd-dt);player.invuln=Math.max(0,player.invuln-dt);
  if(run.ration&&performance.now()/1000-run.lastHit>=8){run.rationTimer+=dt;if(run.rationTimer>=8){run.rationTimer=0;player.hp=Math.min(player.maxHp,player.hp+10);updateHud();}}
  if(run.drone){run.droneTimer-=dt;if(run.droneTimer<=0){run.droneTimer=2;const target=enemies.filter(e=>!e.dead).sort((a,b)=>a.pos.distanceToSquared(player.pos)-b.pos.distanceToSquared(player.pos))[0];if(target){tracerTube(player.pos.clone().add(new THREE.Vector3(0,1.4,0)),target.pos.clone().add(new THREE.Vector3(0,1,0)),.018,0x62e9ff,.9,.2);damageEnemy(target,8,target.pos.clone().add(new THREE.Vector3(0,1,0)),false);}}}
  if(run.mine){run.mineTimer-=dt;if(run.mineTimer<=0){run.mineTimer=5;const target=enemies.filter(e=>!e.dead&&e.pos.distanceTo(player.pos)<18).sort((a,b)=>a.pos.distanceToSquared(player.pos)-b.pos.distanceToSquared(player.pos))[0];if(target){burst(target.pos.clone().add(new THREE.Vector3(0,.2,0)),0xff9c32,18);for(const enemy of [...enemies])if(enemy.pos.distanceTo(target.pos)<4)damageEnemy(enemy,24,target.pos,false);}}}
  const moving=dir.lengthSq()>.01;
  const walkWave=moving&&player.grounded?Math.sin(time*9.5):0;
  playerModel.group.position.set(.34+walkWave*.018,-.43+Math.abs(walkWave)*.012,-.82);
  playerModel.group.rotation.set(walkWave*.008,walkWave*.012,walkWave*.006);
  playerModel.leftArm.position.set(-.33,-.10,.12);playerModel.leftArm.rotation.set(0,0,0);
  playerModel.rightArm.position.set(.28,-.18,.20);playerModel.rightArm.rotation.set(0,0,0);
  if(player.reloading>0){
    player.reloading-=dt;const w=weaponStats(player.weaponIndex);const progress=THREE.MathUtils.clamp(1-player.reloading/w.reload,0,1);const arc=Math.sin(progress*Math.PI);
    playerModel.socket.rotation.x=arc*.34;playerModel.socket.rotation.z=-arc*.16;
    playerModel.socket.position.y=-arc*.08;playerModel.leftArm.rotation.x=-arc*.75;playerModel.leftArm.rotation.z=arc*.34;playerModel.leftArm.position.y-=arc*.18;
    if(playerModel.magazine){
      const home=playerModel.magazine.userData.home;let travel;
      if(progress<.38)travel=THREE.MathUtils.smoothstep(progress/.38,0,1);
      else if(progress<.62)travel=1;
      else travel=1-THREE.MathUtils.smoothstep((progress-.62)/.38,0,1);
      playerModel.magazine.position.copy(home);playerModel.magazine.position.y-=travel*.66;playerModel.magazine.position.z+=travel*.16;playerModel.magazine.rotation.z=travel*.18;
      playerModel.leftArm.position.x+=travel*.13;playerModel.leftArm.position.z-=travel*.24;
    }else if(playerModel.action){
      const home=playerModel.action.userData.home;playerModel.action.position.copy(home);playerModel.action.position.z+=Math.max(0,Math.sin(progress*Math.PI*2))*.32;
      playerModel.leftArm.position.z+=Math.sin(progress*Math.PI*2)*.22;
    }
    if(player.reloading<=0){
      player.ammo=w.mag;playerModel.socket.rotation.set(0,0,0);playerModel.socket.position.set(0,0,0);
      if(playerModel.magazine){playerModel.magazine.position.copy(playerModel.magazine.userData.home);playerModel.magazine.rotation.copy(playerModel.magazine.userData.homeRot);}
      if(playerModel.action)playerModel.action.position.copy(playerModel.action.userData.home);updateHud();
    }
  }
  if(firing)fireWeapon(time);
}

function updateEnemies(dt,time) {
  spawnTimer-=dt;
  const limits=STAGE_LIVE_LIMITS[stage-1],normalEnemies=enemies.filter(e=>e.type!=='boss'&&e.type!=='mini');
  const maxLive=Object.values(limits).reduce((a,b)=>a+b,0);
  if(!boss&&kills<quota&&spawnTimer<=0&&normalEnemies.length<maxLive){
    const candidates=Object.keys(limits).filter(type=>normalEnemies.filter(e=>e.type===type).length<limits[type]);
    if(candidates.length)spawnEnemy(candidates[Math.floor(Math.random()*candidates.length)]);spawnTimer=Math.max(.38,1.15-stage*.055);
  }
  if(!boss&&kills>=quota&&!enemies.length&&!upgradePaused){if(stage===5&&!prebossComplete&&!pendingBoss)beginPrebossUpgrades();else if(!pendingBoss)spawnBoss(stage===5?1:2);}
  for(const e of [...enemies]){
    e.attackCd=Math.max(0,e.attackCd-dt);e.hit=Math.max(0,e.hit-dt);e.slowTimer=Math.max(0,(e.slowTimer||0)-dt);if(e.hit<=0){e.group.scale.lerp(new THREE.Vector3(1,1,1),Math.min(1,dt*15));if(e.group.userData.artMaterial)e.group.userData.artMaterial.color.setHex(0xffffff);}
    const to=player.pos.clone().sub(e.pos);to.y=0;const dist=to.length();if(dist>.01)to.divideScalar(dist);e.group.rotation.y=Math.atan2(to.x,to.z)+Math.PI;
    if(e.healthBar){e.healthBar.position.set(e.pos.x,e.pos.y+e.healthBar.userData.height,e.pos.z);e.healthBar.quaternion.copy(camera.quaternion);e.healthBar.visible=dist<58;}
    if(e.type==='boss'){
      e.teleport-=dt;e.summon-=dt;if(e.teleport<=0){e.teleport=Math.max(2.2,5.3-stage*.18);const p=randomSpawn(15,24);e.pos.copy(p);burst(e.pos.clone().add(new THREE.Vector3(0,2,0)),0xbb62e8,18);}
      if(e.summon<=0){e.summon=Math.max(4.5,9-stage*.25);for(let i=0;i<Math.min(4,1+Math.floor(stage/3));i++)spawnEnemy('mini',e.pos.clone().add(new THREE.Vector3((Math.random()-.5)*3,0,(Math.random()-.5)*3)));}
      if([2,5,6,8,9,10].includes(stage)&&dist<8.5){player.speed=player.baseSpeed*.7;}else player.speed=player.baseSpeed;
      if(e.group.userData.aura)e.group.userData.aura.rotation.z+=dt*.4;
    }
    const enemySpeed=e.speed*(e.slowTimer>0?.55:1)*(timeRippleTimer>0?.45:1);if(dist>e.radius+.55){const dx=to.x*enemySpeed*dt,dz=to.z*enemySpeed*dt;moveWithCollision(e.pos,dx,dz,e.radius*.65);}else if(e.attackCd<=0){hurt(e.damage);e.attackCd=.72;}
    const legs=e.group.userData.legs||[];legs.forEach((leg,i)=>leg.rotation.x=Math.sin(time*9*e.speed+(i%2)*Math.PI)*.42);if(e.group.userData.tail)e.group.userData.tail.rotation.z=Math.sin(time*3+e.phase)*.18;
    const stride=Math.sin(time*(e.type==='fast'?12:8)+e.phase);
    if(e.group.userData.body)e.group.userData.body.position.y+=((.88*(e.type==='boss'?2.35:e.type==='tank'?1.5:e.type==='brute'?1.28:e.type==='fast'?.82:e.type==='scout'?.94:e.type==='mini'?.72:1))+Math.abs(stride)*.035-e.group.userData.body.position.y)*Math.min(1,dt*12);
    if(e.group.userData.shadow){const base=e.type==='boss'?2.35:e.type==='tank'?1.5:e.type==='brute'?1.28:e.type==='fast'?.82:e.type==='scout'?.94:e.type==='mini'?.72:1;e.group.userData.shadow.scale.y+=(1.05*base*(1-Math.abs(stride)*.04)-e.group.userData.shadow.scale.y)*Math.min(1,dt*12);}
    (e.group.userData.ears||[]).forEach((ear,i)=>ear.rotation.z+=(Math.sin(time*2.4+e.phase+i)-ear.rotation.z)*dt*.8);
    e.group.traverse(part=>{if(part.userData.pulse){const pulse=1+Math.sin(time*5+e.phase)*.08;part.scale.setScalar(pulse);}});
  }
  if(!boss)player.speed=player.baseSpeed;
}

function updateProjectiles(dt){
  for(let i=projectiles.length-1;i>=0;i--){
    const p=projectiles[i];p.life-=dt;p.vel.y-=11*dt;p.object.position.addScaledVector(p.vel,dt);p.object.rotation.x+=dt*8;p.object.rotation.z+=dt*5;
    if(Math.random()<dt*18){
      const smokeMat=new THREE.MeshBasicMaterial({color:Math.random()<.35?0xb86b35:0x4b4b46,transparent:true,opacity:.48,depthWrite:false,toneMapped:false});
      const smoke=new THREE.Mesh(new THREE.SphereGeometry(.08+Math.random()*.07,6,4),smokeMat);smoke.position.copy(p.object.position);smoke.userData.vel=new THREE.Vector3((Math.random()-.5)*.35,.3+Math.random()*.35,(Math.random()-.5)*.35);scene.add(smoke);effects.push({object:smoke,life:.34,max:.34,smoke:true,dispose:true});
    }
    let explode=p.life<=0||p.object.position.y<.15||isBlocked(p.object.position.x,p.object.position.z,.2);for(const e of enemies)if(p.object.position.distanceTo(e.pos)<e.radius+.3)explode=true;
    if(explode){const radius=p.blastRadius||6;burst(p.object.position,0xff792f,24);for(const e of [...enemies]){const d=p.object.position.distanceTo(e.pos);if(d<radius)damageEnemy(e,p.damage*Math.max(.15,1-d/(radius+1)),p.object.position);}scene.remove(p.object);p.object.geometry?.dispose();projectiles.splice(i,1);}
  }
}
function updateEffects(dt){
  for(let i=effects.length-1;i>=0;i--){
    const e=effects[i];e.life-=dt;const remain=Math.max(0,e.life/e.max);
    if(e.death){e.object.rotation.z+=(1-remain)*dt*7;e.object.position.y-=dt*.28;e.object.scale.setScalar(.62+.38*remain);const art=e.object.userData.artMaterial;if(art)art.opacity=remain;}
    else if(e.smoke){e.object.position.addScaledVector(e.object.userData.vel,dt);e.object.scale.multiplyScalar(1+dt*2.4);e.object.material.opacity=remain*.48;}
    else if(e.particle){e.object.position.addScaledVector(e.object.userData.vel,dt);e.object.userData.vel.y-=8*dt;e.object.scale.setScalar(Math.max(.01,remain));if(e.object.material?.transparent)e.object.material.opacity=remain;}
    else if(e.object.material)e.object.material.opacity=remain;
    if(e.life<=0){scene.remove(e.object);e.object.geometry?.dispose();if(e.dispose)e.object.material?.dispose();effects.splice(i,1);}
  }
}

function updateCamera(dt) {
  const moveBob=player.grounded&&player.velocity.lengthSq()>.01&&player.rolling<=0?Math.abs(Math.sin(clock.elapsedTime*9.5))*.035:0;
  const rollProgress=player.rolling>0&&player.rollTime>0?1-player.rolling/player.rollTime:0;
  const rollDip=player.rolling>0?Math.sin(rollProgress*Math.PI)*.72:0;
  const desired=new THREE.Vector3(player.pos.x,player.pos.y+1.68+moveBob-rollDip,player.pos.z);
  camera.position.lerp(desired,1-Math.exp(-dt*22));camera.rotation.order='YXZ';camera.rotation.x=player.pitch;camera.rotation.y=player.yaw;camera.rotation.z=player.rolling>0?Math.sin(rollProgress*Math.PI*2)*.055:0;
}
function updateHud(){
  ui.healthText.textContent=`${Math.max(0,Math.ceil(player.hp))} / ${player.maxHp}`;ui.healthBar.style.width=`${Math.max(0,player.hp/player.maxHp*100)}%`;ui.armorText.textContent=player.armor;ui.scrapText.textContent=scrap;
  ui.missionText.textContent=`战区 ${String(stage).padStart(2,'0')} · ${boss?'击败首领':'清除感染体'}`;ui.killText.textContent=boss?'首领战':`${Math.min(kills,quota)} / ${quota}`;ui.comboText.textContent=combo;
  const w=weaponStats(player.weaponIndex);ui.weaponName.textContent=w.name;ui.ammoText.textContent=player.reloading>0?'换弹中':`${player.ammo} / ${w.mag}`;ui.ammoBar.style.width=`${player.ammo/w.mag*100}%`;
  ui.levelText.textContent=`战术等级 ${upgradeLevel+1}`;ui.xpText.textContent=`经验块 ${xp} / ${xpNeed}`;ui.xpBar.style.width=`${Math.min(100,xp/xpNeed*100)}%`;
  if(boss)ui.bossBar.style.width=`${Math.max(0,boss.hp/boss.maxHp*100)}%`;
}
function showMessage(text,ms=900){ui.message.textContent=text;ui.message.classList.add('show');clearTimeout(messageTimer);messageTimer=setTimeout(()=>ui.message.classList.remove('show'),ms);}
function renderResultMaterials(){
  ui.resultMaterials.innerHTML=Object.entries(MATERIAL_INFO).map(([key,info])=>`<div class="material-chip" style="--material:${info.color}"><b><img src="assets/materials/${info.image}" alt="${info.name}"></b><span>${info.name}</span><strong>+${materialsGained[key]}</strong></div>`).join('');
}
function finish(win){gameEnded=true;playing=false;firing=false;upgradePaused=false;setBgm(win?'win':'gameover');ui.upgrade.classList.remove('active','ultimate-charging','ultimate-ready');document.body.classList.remove('playing');document.exitPointerLock?.();ui.lookHint.classList.remove('show');ui.resultTitle.textContent=win?'战区已净化':'作战失败';ui.resultText.textContent=win?`第 ${stage} 战区作战目标已完成，本次回收 ${runScrap} 份废料。`:`已清除 ${Math.min(kills,quota)} 个目标。整备后再次出击。`;renderResultMaterials();ui.result.classList.add('active');}
function resetGame(){for(const e of [...enemies]){scene.remove(e.group);if(e.healthBar)scene.remove(e.healthBar);}enemies.length=0;for(const p of projectiles)scene.remove(p.object);projectiles.length=0;for(const effect of effects)scene.remove(effect.object);effects.length=0;run=freshRun();xp=0;xpNeed=5;upgradeLevel=0;upgradePaused=false;upgradeRefreshLeft=2;prebossChoicesLeft=0;prebossComplete=false;pendingBoss=false;timeRippleTimer=0;ui.upgrade.classList.remove('active','ultimate-charging','ultimate-ready');kills=0;quota=STAGE_QUOTAS[stage-1];scrap=profile.scrap;runScrap=0;combo=0;boss=null;materialsGained={alloy:0,energy:0,bio:0};applyProfileToPlayer(true);player.pos.set(0,0,12);player.yVel=0;player.reloading=0;player.rolling=0;player.ammo=weaponStats(player.weaponIndex).mag;gameEnded=false;spawnTimer=.2;playerModel.socket.position.set(0,0,0);playerModel.socket.rotation.set(0,0,0);ui.bossHud.classList.add('hidden');updateHud();}

const WEAPON_IMAGE={pistol:'pistol.png',rifle:'rifle.png',sniper:'sniper.png',shotgun:'shotgun.png',smg:'smg.png',flamethrower:'flamethrower.png',grenade:'grenade.png',laser:'laser.png',crossbow:'crossbow.png'};
function renderStageGrid(){
  ui.stageGrid.replaceChildren();
  for(let n=1;n<=10;n++){
    const button=document.createElement('button');const unlocked=n<=maxUnlocked;button.className=`stage-button${unlocked?'':' locked'}`;
    button.innerHTML=`<small>区域 ${String(n).padStart(2,'0')}</small><strong>${unlocked?`第${n}关`:'未解锁'}</strong>`;button.disabled=!unlocked;
    if(unlocked)button.addEventListener('click',()=>startStage(n));ui.stageGrid.append(button);
  }
}
function renderWeaponGrid(){
  ui.weaponGrid.replaceChildren();
  WEAPONS.forEach((w,index)=>{
    const stats=weaponStats(index),up=profile.weaponUpgrades[w.key];
    const owned=profile.ownedWeapons.includes(w.key),equipped=owned&&index===player.weaponIndex;
    const card=document.createElement('button');card.className=`weapon-card${equipped?' equipped':''}${owned?'':' locked'}`;
    const preview=WEAPON_IMAGE[w.key]?`<img src="assets/weapons/${WEAPON_IMAGE[w.key]}" alt="${w.name}">`:`<span class="weapon-preview">弩</span>`;
    const status=equipped?'已装备':owned?'点击装备':scrap>=w.cost?`购买 · ${w.cost} 废料`:`未解锁 · 需要 ${w.cost} 废料`;
    card.innerHTML=`${preview}<div><h3>${w.name}</h3><p>伤害 <b>${stats.damage}</b> · 弹匣 <b>${stats.mag}</b></p><p>装填 <b>${stats.reload.toFixed(2)}秒</b> · 改造等级 ${up.damage+up.mag+up.durability}/15</p><p class="weapon-status">${status}</p></div>`;
    card.addEventListener('click',()=>{
      if(playing)return;
      if(!owned){
        if(scrap<w.cost){showMessage(`废料不足 · 还需 ${w.cost-scrap}`,1100);return;}
        scrap-=w.cost;profile.scrap=scrap;profile.ownedWeapons.push(w.key);saveProfile();ui.menuScrap.textContent=scrap;showMessage(`${w.name} 已解锁`,1000);
      }
      equipWeapon(index);localStorage.setItem('wz3d-weapon',w.key);renderWeaponGrid();
    });ui.weaponGrid.append(card);
  });
}
function materialChipMarkup(values=profile.materials){return Object.entries(MATERIAL_INFO).map(([key,info])=>`<div class="material-chip" style="--material:${info.color}"><b><img src="assets/materials/${info.image}" alt="${info.name}"></b><span>${info.name}</span><strong>${values[key]||0}</strong></div>`).join('');}
function renderMaterialSummaries(){if(ui.menuMaterials)ui.menuMaterials.innerHTML=materialChipMarkup();if(ui.progressionMaterials)ui.progressionMaterials.innerHTML=materialChipMarkup();}
function upgradeButton(label,material,cost,disabled,onClick){
  const button=document.createElement('button');button.className='metal-button progression-upgrade';button.disabled=disabled;button.textContent=label;button.addEventListener('click',onClick);return button;
}
function renderProgression(kind){
  renderMaterialSummaries();ui.progressionRows.replaceChildren();
  if(kind==='talent'){
    ui.progressionEyebrow.textContent='SURVIVOR DEVELOPMENT';ui.progressionTitle.textContent='生存者天赋';ui.progressionContext.textContent='使用战区材料永久强化生命、机动与防护。每项最高 10 级。';
    const defs={hp:{name:'强健体魄',desc:'每级最大生命值 +10',material:'bio'},speed:{name:'机动训练',desc:'每级基础移动速度 +0.27',material:'energy'},armor:{name:'防护训练',desc:'每级受到伤害 -1',material:'alloy'}};
    Object.entries(defs).forEach(([key,def])=>{
      const level=profile.talents[key],cost=2+level,row=document.createElement('article');row.className='progression-row';
      row.innerHTML=`<div class="progression-icon" style="--material:${MATERIAL_INFO[def.material].color}"><img src="assets/materials/${MATERIAL_INFO[def.material].image}" alt="${MATERIAL_INFO[def.material].name}"></div><div><h3>${def.name}<small>等级 ${level}/10</small></h3><p>${def.desc}</p><div class="level-pips">${Array.from({length:10},(_,i)=>`<i class="${i<level?'filled':''}"></i>`).join('')}</div></div><div class="upgrade-slot"></div>`;
      const disabled=level>=10||profile.materials[def.material]<cost,label=level>=10?'已满级':`${MATERIAL_INFO[def.material].name} ${cost}`;
      row.querySelector('.upgrade-slot').append(upgradeButton(label,def.material,cost,disabled,()=>{profile.materials[def.material]-=cost;profile.talents[key]++;saveProfile();applyProfileToPlayer(true);renderProgression('talent');updateHud();}));ui.progressionRows.append(row);
    });
  }else{
    const w=WEAPONS[player.weaponIndex],up=profile.weaponUpgrades[w.key],material=WEAPON_MATERIAL[w.key],info=MATERIAL_INFO[material];
    ui.progressionEyebrow.textContent='WEAPON MODIFICATION';ui.progressionTitle.textContent=`${w.name} · 武器改造`;ui.progressionContext.textContent=`当前只改造已装备武器；使用专属材料“${info.name}”，每项最高 5 级。`;
    const defs={damage:{name:'基础攻击',desc:'每级基础伤害 +1'},mag:{name:'扩容弹匣',desc:'每级弹匣容量 +2'},durability:{name:'可靠机构',desc:'每级换弹时间 -5%'}};
    Object.entries(defs).forEach(([key,def])=>{
      const level=up[key],cost=2+level,locked=w.key==='laser'&&key==='damage',row=document.createElement('article');row.className='progression-row';
      row.innerHTML=`<div class="progression-icon" style="--material:${info.color}"><img src="assets/materials/${info.image}" alt="${info.name}"></div><div><h3>${def.name}<small>等级 ${level}/5</small></h3><p>${locked?'激光核心功率固定，不接受伤害改造。':def.desc}</p><div class="level-pips">${Array.from({length:5},(_,i)=>`<i class="${i<level?'filled':''}"></i>`).join('')}</div></div><div class="upgrade-slot"></div>`;
      const disabled=locked||level>=5||profile.materials[material]<cost,label=locked?'核心锁定':level>=5?'已满级':`${info.name} ${cost}`;
      row.querySelector('.upgrade-slot').append(upgradeButton(label,material,cost,disabled,()=>{profile.materials[material]-=cost;up[key]++;saveProfile();const stats=weaponStats(player.weaponIndex);player.ammo=Math.min(player.ammo,stats.mag);renderProgression('weapon');renderWeaponGrid();updateHud();}));ui.progressionRows.append(row);
    });
  }
}
function openProgression(kind){ui.command.classList.remove('active');ui.equipment.classList.remove('active');ui.result.classList.remove('active');ui.progression.classList.add('active');renderProgression(kind);}
function showCommand(){playing=false;gameEnded=false;firing=false;upgradePaused=false;setBgm(null);run=freshRun();applyProfileToPlayer(false);ui.upgrade.classList.remove('active','ultimate-charging','ultimate-ready');document.body.classList.remove('playing');document.exitPointerLock?.();ui.lookHint.classList.remove('show');ui.result.classList.remove('active');ui.equipment.classList.remove('active');ui.progression.classList.remove('active');ui.command.classList.add('active');scrap=profile.scrap;ui.menuScrap.textContent=scrap;renderMaterialSummaries();renderStageGrid();renderWeaponGrid();}
function startStage(stageNumber){stage=stageNumber;ui.command.classList.remove('active');ui.equipment.classList.remove('active');ui.progression.classList.remove('active');ui.result.classList.remove('active');resetGame();playing=true;setBgm('combat');document.body.classList.add('playing');ui.lookHint.textContent=TOUCH_MODE?'左侧摇杆移动 · 滑动战场转向 · 右侧按键战斗':'点击战场锁定鼠标 · 移动鼠标转向 · 右键拖动也可观察';ui.lookHint.classList.add('show');clearTimeout(lookHintTimer);lookHintTimer=setTimeout(()=>ui.lookHint.classList.remove('show'),3200);showMessage(`战区 ${String(stage).padStart(2,'0')} · 行动开始`,1500);}

function jump(){if(player.grounded&&player.rolling<=0){player.yVel=8.2;player.grounded=false;}}
function roll(){if(player.rollCd<=0&&player.grounded){player.rollTime=.48;player.rolling=player.rollTime;player.rollCd=1.15;player.invuln=.55;const forward=new THREE.Vector3(-Math.sin(player.yaw),0,-Math.cos(player.yaw));player.velocity.lengthSq()<.1?player.velocity.copy(forward):player.velocity.normalize();}}

addEventListener('keydown',e=>{if(!playing||upgradePaused)return;keys.add(e.code);if(e.code==='Space'){e.preventDefault();jump();}if(e.code==='KeyE')roll();if(e.code==='KeyR')startReload();});
addEventListener('keyup',e=>keys.delete(e.code));
let dragX=0,dragY=0,touchLookId=null;
function applyLook(dx,dy){player.yaw-=dx*.00235;player.pitch=THREE.MathUtils.clamp(player.pitch-dy*.0017,-.72,.52);}
addEventListener('mousedown',e=>{
  if(e.button===0&&playing&&!upgradePaused){firing=true;fireWeapon(clock.elapsedTime);if(!pointerLocked)canvas.requestPointerLock?.();}
  if(e.button===2&&playing&&!upgradePaused){dragLook=true;dragX=e.clientX;dragY=e.clientY;ui.lookHint.textContent='右键拖动：自由观察视角';ui.lookHint.classList.add('show');}
});
addEventListener('mouseup',e=>{if(e.button===0)firing=false;if(e.button===2){dragLook=false;ui.lookHint.classList.remove('show');}});
addEventListener('mousemove',e=>{if(!playing)return;if(pointerLocked)applyLook(e.movementX,e.movementY);else if(dragLook){applyLook(e.clientX-dragX,e.clientY-dragY);dragX=e.clientX;dragY=e.clientY;}});
document.addEventListener('pointerlockchange',()=>{pointerLocked=document.pointerLockElement===canvas;if(pointerLocked){ui.lookHint.textContent='鼠标已锁定 · 移动鼠标转向 · 按 Esc 释放';ui.lookHint.classList.add('show');clearTimeout(lookHintTimer);lookHintTimer=setTimeout(()=>ui.lookHint.classList.remove('show'),1400);}});
canvas.addEventListener('contextmenu',e=>e.preventDefault());
canvas.addEventListener('click',()=>{if(playing&&!upgradePaused&&!pointerLocked)canvas.requestPointerLock?.();});
canvas.addEventListener('pointerdown',e=>{if(e.pointerType==='touch'&&playing&&!upgradePaused){e.preventDefault();touchLookId=e.pointerId;dragX=e.clientX;dragY=e.clientY;canvas.setPointerCapture(e.pointerId);}});
canvas.addEventListener('pointermove',e=>{if(e.pointerId===touchLookId&&playing&&!upgradePaused){e.preventDefault();applyLook((e.clientX-dragX)*1.15,(e.clientY-dragY)*1.15);dragX=e.clientX;dragY=e.clientY;}});
function stopTouchLook(e){if(e.pointerId===touchLookId)touchLookId=null;}canvas.addEventListener('pointerup',stopTouchLook);canvas.addEventListener('pointercancel',stopTouchLook);
ui.equipmentButton.addEventListener('click',()=>{ui.command.classList.remove('active');ui.equipment.classList.add('active');renderWeaponGrid();});
ui.talentButton.addEventListener('click',()=>openProgression('talent'));ui.weaponLabButton.addEventListener('click',()=>openProgression('weapon'));ui.progressionBackButton.addEventListener('click',showCommand);
ui.equipmentBackButton.addEventListener('click',showCommand);ui.returnMenuButton.addEventListener('click',showCommand);
ui.upgradeRefresh.addEventListener('click',refreshUpgradeCards);
ui.restartButton.addEventListener('click',()=>{ui.result.classList.remove('active');resetGame();playing=true;setBgm('combat');document.body.classList.add('playing');ui.lookHint.textContent=TOUCH_MODE?'左侧摇杆移动 · 滑动战场转向 · 右侧按键战斗':'点击战场锁定鼠标 · 移动鼠标转向';ui.lookHint.classList.add('show');});
ui.jump.addEventListener('pointerdown',e=>{e.preventDefault();e.stopPropagation();if(!upgradePaused)jump();});ui.roll.addEventListener('pointerdown',e=>{e.preventDefault();e.stopPropagation();if(!upgradePaused)roll();});
let firePointerId=null;
ui.fire.addEventListener('pointerdown',e=>{e.preventDefault();e.stopPropagation();if(!upgradePaused){firePointerId=e.pointerId;ui.fire.setPointerCapture?.(e.pointerId);firing=true;fireWeapon(clock.elapsedTime);}});
function stopMobileFire(e){if(firePointerId===null||!e||e.pointerId===firePointerId){firePointerId=null;firing=false;}}
ui.fire.addEventListener('pointerup',stopMobileFire);ui.fire.addEventListener('pointercancel',stopMobileFire);ui.fire.addEventListener('lostpointercapture',stopMobileFire);

let stickId=null;
function updateStick(e){const rect=ui.stickBase.getBoundingClientRect(),m=42;let x=e.clientX-(rect.left+rect.width/2),y=e.clientY-(rect.top+rect.height/2);const l=Math.hypot(x,y);if(l>m){x=x/l*m;y=y/l*m;}moveInput.x=x/m;moveInput.y=y/m;ui.stickKnob.style.transform=`translate(${x}px,${y}px)`;}
ui.stickBase.addEventListener('pointerdown',e=>{e.preventDefault();e.stopPropagation();stickId=e.pointerId;ui.stickBase.setPointerCapture(e.pointerId);updateStick(e);});
ui.stickBase.addEventListener('pointermove',e=>{if(e.pointerId!==stickId)return;e.preventDefault();updateStick(e);});
function resetStick(e){if(e.pointerId!==stickId)return;stickId=null;moveInput.x=moveInput.y=0;ui.stickKnob.style.transform='';}ui.stickBase.addEventListener('pointerup',resetStick);ui.stickBase.addEventListener('pointercancel',resetStick);

addEventListener('resize',()=>{camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();renderer.setPixelRatio(Math.min(devicePixelRatio,TOUCH_MODE?1:1.25));renderer.setSize(innerWidth,innerHeight);});

const savedWeaponKey=localStorage.getItem('wz3d-weapon');
const savedWeaponIndex=WEAPONS.findIndex(w=>w.key===savedWeaponKey);
if(savedWeaponIndex>=0&&profile.ownedWeapons.includes(savedWeaponKey))equipWeapon(savedWeaponIndex);
buildWorld();updateHud();renderMaterialSummaries();renderStageGrid();renderWeaponGrid();
const clock=new THREE.Clock();
function animate(){requestAnimationFrame(animate);const dt=Math.min(.033,clock.getDelta()),time=clock.elapsedTime;if(playing&&!gameEnded&&!upgradePaused){timeRippleTimer=Math.max(0,timeRippleTimer-dt);updatePlayer(dt,time);updateEnemies(dt,time);updateProjectiles(dt);updateEffects(dt);updateCamera(dt);comboTimer-=dt;if(comboTimer<=0&&combo){combo=0;updateHud();}if(boss)updateHud();}else updateCamera(dt);renderer.render(scene,camera);}
camera.position.set(0,4,19);camera.lookAt(0,1,5);animate();
