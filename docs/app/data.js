const DB = {
  get(k) { try { return JSON.parse(localStorage.getItem('ns_'+k)||'null'); } catch { return null; } },
  set(k,v) { localStorage.setItem('ns_'+k, JSON.stringify(v)); },
  getServices()  { return this.get('services') || defaultServices(); },
  saveServices(s){ this.set('services',s); },
  getCustomers() { return this.get('customers') || {}; },
  saveCustomers(c){ this.set('customers',c); },
  getBills()     { return this.get('bills') || {}; },
  saveBills(b)   { this.set('bills',b); },
  getAuth()      { return this.get('auth') || {role:null}; },
  setAuth(a)     { this.set('auth',a); },
  getAdmin()     { return this.get('admin') || {username:'admin',password:'salon123',empPassword:''}; },
  saveAdmin(a)   { this.set('admin',a); }
};

function defaultServices() {
  return {
    '1': {name:'Haircut',price:200,category:'Hair'},
    '2': {name:'Hair Wash',price:150,category:'Hair'},
    '3': {name:'Hair Coloring',price:800,category:'Hair'},
    '4': {name:'Hair Spa',price:600,category:'Hair'},
    '5': {name:'Facial',price:500,category:'Skin'},
    '6': {name:'Cleanup',price:300,category:'Skin'},
    '7': {name:'Eyebrow Threading',price:50,category:'Threading'},
    '8': {name:'Upper Lip Threading',price:30,category:'Threading'},
    '9': {name:'Waxing (Full Arms)',price:250,category:'Waxing'},
    '10':{name:'Waxing (Full Legs)',price:350,category:'Waxing'},
    '11':{name:'Manicure',price:300,category:'Nails'},
    '12':{name:'Pedicure',price:350,category:'Nails'},
    '13':{name:'Bridal Makeup',price:3000,category:'Makeup'},
    '14':{name:'Party Makeup',price:1500,category:'Makeup'},
    '15':{name:'Head Massage',price:200,category:'Wellness'}
  };
}

function genId(p){ return p+Math.random().toString(36).slice(2,8).toUpperCase(); }
function todayStr(){ return new Date().toISOString().slice(0,10); }
function nowISO(){ return new Date().toISOString(); }
function esc(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
