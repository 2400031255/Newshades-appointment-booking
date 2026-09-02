
// ── Dashboard ─────────────────────────────────────────────────────────────────
function renderDashboard(el) {
  const bills = DB.getBills();
  const customers = DB.getCustomers();
  const t = todayStr();
  const todayBills = Object.values(bills).filter(b => b.date && b.date.startsWith(t));
  const revenue = todayBills.reduce((s,b) => s + (b.total||0), 0);
  const payMap = {};
  todayBills.forEach(b => { payMap[b.payment] = (payMap[b.payment]||0) + b.total; });
  const svcCount = {};
  todayBills.forEach(b => (b.items||[]).forEach(i => { svcCount[i.name] = (svcCount[i.name]||0) + i.qty; }));
  const topSvcs = Object.entries(svcCount).sort((a,b)=>b[1]-a[1]).slice(0,5);
  const recent = Object.entries(bills).filter(([,b])=>b.date&&b.date.startsWith(t))
    .sort((a,b)=>b[1].date.localeCompare(a[1].date)).slice(0,8);
  const isAdmin = currentRole==='admin';
  const isEmp = isAdmin || currentRole==='employee';

  let recentRows = '';
  recent.forEach(([bid,b]) => {
    const custs = DB.getCustomers();
    const c = custs[b.customer_id];
    const name = c ? c.name : 'Walk-in';
    recentRows += '<tr><td><span class="cust-avatar">'+name[0]+'</span> '+esc(name)+'</td>'
      +'<td class="muted">'+(b.date||'').slice(11,16)+'</td>'
      +'<td><strong>&#8377;'+b.total+'</strong></td>'
      +'<td><span class="pay-badge '+(b.payment||'').toLowerCase()+'">'+esc(b.payment)+'</span></td></tr>';
  });

  let topSvcHtml = '';
  topSvcs.forEach(([n,c]) => {
    topSvcHtml += '<div class="service-bar-row"><span class="sb-name">'+esc(n)+'</span>'
      +'<div class="sb-bar-wrap"><div class="sb-bar" style="width:'+Math.round(c/topSvcs[0][1]*100)+'%"></div></div>'
      +'<span class="sb-count">'+c+'x</span></div>';
  });

  let payHtml = '';
  Object.entries(payMap).forEach(([m,a]) => {
    payHtml += '<div class="pay-row"><span class="pay-badge '+m.toLowerCase()+'">'+m+'</span><span class="pay-amount">&#8377;'+a+'</span></div>';
  });

  el.innerHTML = '<div class="dash-header">'
    +'<div><h1 class="page-title" style="margin-bottom:4px;">'+(isAdmin?'Admin':'Employee')+' Dashboard</h1>'
    +'<p class="dash-date">'+t+'</p></div>'
    +(isEmp?'<a href="#" onclick="navigate(\'newbill\')" class="btn-new-bill">+ New Bill</a>':'')
    +'</div>'
    +'<div class="clock-banner">'
    +'<div class="clock-banner-left"><div class="cb-day" id="lcw-day">---</div><div class="cb-date" id="lcw-date">-- --- ----</div></div>'
    +'<div class="clock-banner-center"><span class="cb-time" id="lcw-time">--:--:--</span><span class="cb-ampm" id="lcw-ampm">--</span></div>'
    +'<div class="clock-banner-right"><div class="cb-label">Newshades Family Salon</div><div class="cb-sub">Beauty &middot; Wellness &middot; Care</div></div>'
    +'</div>'
    +'<div class="dash-stats">'
    +'<div class="dash-stat-card purple"><div class="ds-icon">&#128101;</div><div class="ds-info"><div class="ds-value">'+Object.keys(customers).length+'</div><div class="ds-label">Total Customers</div></div></div>'
    +'<div class="dash-stat-card rose"><div class="ds-icon">&#128221;</div><div class="ds-info"><div class="ds-value">'+todayBills.length+'</div><div class="ds-label">Bills Today</div></div></div>'
    +(isAdmin?'<div class="dash-stat-card gold"><div class="ds-icon">&#8377;</div><div class="ds-info"><div class="ds-value">&#8377;'+revenue+'</div><div class="ds-label">Revenue Today</div></div></div>':'')
    +'</div>'
    +'<div class="dash-grid">'
    +'<div class="dash-card"><div class="dash-card-header"><span>Today\'s Bills</span>'
    +(isAdmin?'<a href="#" onclick="navigate(\'report\')" class="view-all">View Report &rarr;</a>':'')
    +'</div>'
    +(recent.length?'<div class="dash-table-wrap"><table class="dash-table"><thead><tr><th>Customer</th><th>Time</th><th>Amount</th><th>Payment</th></tr></thead><tbody>'+recentRows+'</tbody></table></div>'
    :'<div class="dash-empty"><p>No bills today</p><a href="#" onclick="navigate(\'newbill\')" class="btn btn-primary" style="margin-top:12px;">Create First Bill</a></div>')
    +'</div>'
    +'<div class="dash-right-col">'
    +(isAdmin&&topSvcs.length?'<div class="dash-card"><div class="dash-card-header"><span>Top Services Today</span></div>'+topSvcHtml+'</div>':'')
    +(isAdmin&&Object.keys(payMap).length?'<div class="dash-card"><div class="dash-card-header"><span>Payment Breakdown</span></div>'+payHtml+'</div>':'')
    +'<div class="dash-card"><div class="dash-card-header"><span>Quick Actions</span></div>'
    +'<div class="quick-grid">'
    +'<a href="#" onclick="navigate(\'newbill\')" class="quick-btn purple">&#128221;<span>New Bill</span></a>'
    +'<a href="#" onclick="navigate(\'customers\')" class="quick-btn rose">&#128101;<span>Customers</span></a>'
    +(isAdmin?'<a href="#" onclick="navigate(\'report\')" class="quick-btn gold">&#128202;<span>Report</span></a>'
    +'<a href="#" onclick="navigate(\'services\')" class="quick-btn green">&#9881;<span>Services</span></a>':'')
    +'</div></div></div></div>';

  (function tick(){
    const n=new Date(),h24=n.getHours(),ampm=h24>=12?'PM':'AM',h12=h24%12||12;
    const pad=x=>String(x).padStart(2,'0');
    const days=['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
    const months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const te=document.getElementById('lcw-time');
    if(te){
      te.textContent=pad(h12)+':'+pad(n.getMinutes())+':'+pad(n.getSeconds());
      document.getElementById('lcw-ampm').textContent=ampm;
      document.getElementById('lcw-day').textContent=days[n.getDay()];
      document.getElementById('lcw-date').textContent=n.getDate()+' '+months[n.getMonth()]+' '+n.getFullYear();
      setTimeout(tick,1000);
    }
  })();
}

// ── New Bill ──────────────────────────────────────────────────────────────────
let billSelected = {};

function renderNewBill(el, params) {
  billSelected = {};
  const services = DB.getServices();
  const cats = [...new Set(Object.values(services).map(s=>s.category))].sort();
  let gridHtml = '';
  Object.entries(services).forEach(([sid,svc]) => {
    gridHtml += '<label class="svc-card" id="svc-label-'+sid+'" data-name="'+esc(svc.name.toLowerCase())+'" data-category="'+esc((svc.category||'').toLowerCase().replace(/ /g,'_'))+'">'
      +'<input type="checkbox" onchange="onSvcToggle(this,\''+sid+'\',\''+esc(svc.name)+'\','+svc.price+')">'
      +'<div class="svc-card-inner"><span class="svc-card-name">'+esc(svc.name)+'</span>'
      +'<span class="svc-card-price">&#8377;'+svc.price+'</span></div>'
      +'<input type="number" id="qty-'+sid+'" value="1" min="1" class="qty-input" onclick="event.stopPropagation()" oninput="updateSummary()">'
      +'</label>';
  });

  const phoneVal = (params && params.phone) ? params.phone : '';

  el.innerHTML = '<h1 class="page-title">&#128221; New Bill</h1>'
    +'<div class="nb-layout">'
    +'<form class="nb-form" id="billForm" onsubmit="submitBill(event)">'
    +'<div class="nb-card"><div class="nb-card-title">&#128100; Customer</div>'
    +'<div class="nb-row">'
    +'<div class="nb-field"><input type="text" id="billPhone" placeholder="Phone Number" maxlength="10" oninput="this.value=this.value.replace(/[^0-9]/g,\'\');validatePhone(this)" value="'+esc(phoneVal)+'"><small id="phone-msg"></small></div>'
    +'<div class="nb-field"><input type="text" id="billName" placeholder="Name (if new customer)"></div>'
    +'</div></div>'
    +'<div class="nb-card"><div class="nb-card-title">&#9986; Services <span id="sel-count" class="sel-badge" style="display:none">0 selected</span></div>'
    +'<div class="svc-search-wrap"><span class="svc-search-icon">&#128269;</span>'
    +'<input type="text" id="svcSearch" placeholder="Search services..." oninput="filterBillSvcs()" autocomplete="off">'
    +'<button type="button" id="clearSvcSearch" onclick="clearBillSearch()" style="display:none;position:absolute;right:10px;top:50%;transform:translateY(-50%);background:none;border:none;cursor:pointer;color:#aaa;">&#10005;</button>'
    +'</div>'
    +'<div id="selectedChips" class="chips-wrap" style="display:none"></div>'
    +'<div class="svc-tabs"><button type="button" class="svc-tab active" onclick="switchBillTab(\'all\',this)">All</button>'
    +cats.map(c=>'<button type="button" class="svc-tab" onclick="switchBillTab(\''+esc(c.toLowerCase().replace(/ /g,'_'))+'\',this)">'+esc(c)+'</button>').join('')
    +'</div>'
    +'<div class="svc-grid" id="svcGrid">'+gridHtml+'</div>'
    +'<div id="noSvcResults" class="no-results" style="display:none">No services found</div>'
    +'</div>'
    +'<div class="nb-card"><div class="nb-card-title">&#128179; Payment</div>'
    +'<div class="nb-row">'
    +'<div class="nb-field"><input type="number" id="billDiscount" placeholder="Discount %" min="0" max="100" step="0.1" oninput="updateSummary()"></div>'
    +'<div class="nb-field"><select id="billPayment"><option value="Cash">&#128181; Cash</option><option value="UPI">&#128241; UPI</option><option value="Card">&#128179; Card</option></select></div>'
    +'</div></div>'
    +'<button type="submit" class="nb-submit">Generate Bill &rarr;</button>'
    +'</form>'
    +'<div class="nb-summary" id="nbSummary">'
    +'<div class="nbs-title">&#128221; Bill Summary</div>'
    +'<div id="nbs-empty" class="nbs-empty">No services selected</div>'
    +'<div id="nbs-list" class="nbs-list"></div>'
    +'<div id="nbs-footer" class="nbs-footer" style="display:none">'
    +'<div class="nbs-row" id="nbs-subtotal-row" style="display:none"><span>Subtotal</span><span id="nbs-subtotal"></span></div>'
    +'<div class="nbs-row" id="nbs-discount-row" style="display:none"><span id="nbs-disc-label">Discount</span><span id="nbs-discount" style="color:#c0394a"></span></div>'
    +'<div class="nbs-total"><span>Total</span><span id="nbs-total">&#8377;0</span></div>'
    +'</div></div></div>';

  if (phoneVal) validatePhone(document.getElementById('billPhone'));
}

let billActiveTab = 'all';
function switchBillTab(tab, btn) {
  billActiveTab = tab;
  document.querySelectorAll('.svc-tab').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  applyBillFilter();
}
function applyBillFilter() {
  const q = (document.getElementById('svcSearch')||{value:''}).value.toLowerCase();
  const cards = document.querySelectorAll('.svc-card');
  let vis = 0;
  cards.forEach(card => {
    const nm = !q || card.dataset.name.includes(q);
    const tm = billActiveTab==='all' || card.dataset.category===billActiveTab;
    card.style.display = (nm&&tm)?'':'none';
    if(nm&&tm) vis++;
  });
  const nr = document.getElementById('noSvcResults');
  if(nr) nr.style.display = vis===0?'block':'none';
}
function filterBillSvcs() {
  const q = document.getElementById('svcSearch').value;
  const cb = document.getElementById('clearSvcSearch');
  if(cb) cb.style.display = q?'block':'none';
  applyBillFilter();
}
function clearBillSearch() {
  document.getElementById('svcSearch').value='';
  filterBillSvcs();
}
function onSvcToggle(cb, sid, name, price) {
  const label = document.getElementById('svc-label-'+sid);
  if(cb.checked){ billSelected[sid]={name,price}; label.classList.add('checked'); }
  else { delete billSelected[sid]; label.classList.remove('checked'); }
  renderChips(); updateSummary();
}
function renderChips() {
  const wrap = document.getElementById('selectedChips');
  const badge = document.getElementById('sel-count');
  const count = Object.keys(billSelected).length;
  if(!wrap) return;
  wrap.style.display = count?'flex':'none';
  if(badge){ badge.style.display=count?'inline-block':'none'; badge.textContent=count+' selected'; }
  wrap.innerHTML = Object.entries(billSelected).map(([sid,s])=>
    '<div class="chip"><span class="chip-name">'+esc(s.name)+'</span>'
    +'<span class="chip-price">&#8377;'+s.price+'</span>'
    +'<span class="chip-remove" onclick="removeSvc(\''+sid+'\')">&#10005;</span></div>'
  ).join('');
}
function removeSvc(sid) {
  const cb = document.querySelector('input[onchange*="\''+sid+'\'"]');
  if(cb){ cb.checked=false; }
  const label = document.getElementById('svc-label-'+sid);
  if(label) label.classList.remove('checked');
  delete billSelected[sid];
  renderChips(); updateSummary();
}
function updateSummary() {
  const disc = parseFloat((document.getElementById('billDiscount')||{value:0}).value)||0;
  const list = document.getElementById('nbs-list');
  const empty = document.getElementById('nbs-empty');
  const footer = document.getElementById('nbs-footer');
  const keys = Object.keys(billSelected);
  if(!list) return;
  if(!keys.length){ list.innerHTML=''; if(empty)empty.style.display=''; if(footer)footer.style.display='none'; return; }
  if(empty) empty.style.display='none';
  if(footer) footer.style.display='';
  let sub=0;
  list.innerHTML = keys.map(sid=>{
    const s=billSelected[sid];
    const qty=parseInt((document.getElementById('qty-'+sid)||{value:1}).value)||1;
    const amt=s.price*qty; sub+=amt;
    return '<div class="nbs-item"><span class="nbs-item-name">'+esc(s.name)+(qty>1?' x'+qty:'')+'</span><span class="nbs-item-price">&#8377;'+amt+'</span></div>';
  }).join('');
  const discAmt=sub*disc/100, total=sub-discAmt;
  const sr=document.getElementById('nbs-subtotal-row'), dr=document.getElementById('nbs-discount-row');
  if(sr) sr.style.display=disc>0?'':'none';
  if(dr) dr.style.display=disc>0?'':'none';
  if(disc>0){
    const ns=document.getElementById('nbs-subtotal'); if(ns) ns.textContent='&#8377;'+sub;
    const dl=document.getElementById('nbs-disc-label'); if(dl) dl.textContent='Discount ('+disc+'%)';
    const nd=document.getElementById('nbs-discount'); if(nd) nd.textContent='-&#8377;'+discAmt.toFixed(0);
  }
  const nt=document.getElementById('nbs-total'); if(nt) nt.textContent='&#8377;'+total.toFixed(0);
}
function validatePhone(el) {
  el.value=el.value.replace(/[^0-9]/g,'');
  const msg=document.getElementById('phone-msg');
  if(!msg) return;
  if(el.value.length===10){ el.style.borderColor='#28a745'; msg.textContent='&#10003; Valid'; msg.style.color='#28a745'; }
  else if(el.value.length>0){ el.style.borderColor='#dc3545'; msg.textContent=(10-el.value.length)+' more digits needed'; msg.style.color='#dc3545'; }
  else { el.style.borderColor=''; msg.textContent=''; }
}
function submitBill(e) {
  e.preventDefault();
  const phone = document.getElementById('billPhone').value.trim();
  const name  = document.getElementById('billName').value.trim();
  const items = Object.entries(billSelected);
  if(!phone||phone.length!==10){ flash('Enter valid 10-digit phone','error'); return; }
  if(!items.length){ flash('Select at least one service','error'); return; }
  const customers = DB.getCustomers();
  let cid = Object.keys(customers).find(k=>customers[k].phone===phone);
  if(!cid){
    if(!name){ flash('Enter customer name for new customer','error'); return; }
    cid = genId('C');
    customers[cid] = {name, phone, visits:[]};
    DB.saveCustomers(customers);
  }
  const disc = parseFloat(document.getElementById('billDiscount').value)||0;
  const payment = document.getElementById('billPayment').value;
  const billItems = items.map(([sid,s])=>{
    const qty=parseInt((document.getElementById('qty-'+sid)||{value:1}).value)||1;
    return {sid, name:s.name, price:s.price, qty};
  });
  const sub = billItems.reduce((s,i)=>s+i.price*i.qty,0);
  const total = Math.round(sub - sub*disc/100);
  const bid = genId('B');
  const dateISO = nowISO();
  const bills = DB.getBills();
  bills[bid] = {customer_id:cid, items:billItems, payment, discount:disc, subtotal:sub, total, date:dateISO};
  DB.saveBills(bills);
  const custs = DB.getCustomers();
  custs[cid].visits = custs[cid].visits||[];
  custs[cid].visits.push({bill_id:bid, date:todayStr(), total, payment});
  DB.saveCustomers(custs);
  flash('Bill generated!','success');
  navigate('receipt', {bid});
}

// ── Receipt ───────────────────────────────────────────────────────────────────
function renderReceipt(el, params) {
  const bid = params && params.bid;
  const bills = DB.getBills();
  const b = bills[bid];
  if(!b){ el.innerHTML='<p class="empty-state">Bill not found.</p>'; return; }
  const custs = DB.getCustomers();
  const c = custs[b.customer_id];
  const sub = b.subtotal||b.items.reduce((s,i)=>s+i.price*i.qty,0);
  const discAmt = sub*(b.discount||0)/100;
  const dateStr = b.date ? b.date.slice(0,10) : todayStr();
  const timeStr = b.date ? b.date.slice(11,16) : '';

  let itemRows = b.items.map(i=>'<div class="t-item"><span class="t-item-name">'+esc(i.name)+(i.qty>1?' <small>x'+i.qty+'</small>':'')+'</span><span class="t-item-price">&#8377;'+Math.round(i.price*i.qty)+'</span></div>').join('');
  let discRows = '';
  if(b.discount>0){
    discRows = '<div class="t-total-row"><span>Subtotal</span><span>&#8377;'+Math.round(sub)+'</span></div>'
      +'<div class="t-total-row"><span>Discount ('+b.discount+'%)</span><span>- &#8377;'+Math.round(discAmt)+'</span></div>';
  }

  el.innerHTML = '<div class="receipt-page">'
    +'<div class="receipt-actions no-print">'
    +'<button onclick="window.print()" class="btn-print">&#128424; Print Bill</button>'
    +'<a href="#" onclick="navigate(\'newbill\')" class="btn-new no-print">+ New Bill</a>'
    +'</div>'
    +'<div class="thermal-wrap"><div class="thermal-receipt" id="receipt">'
    +'<div class="t-header">'
    +'<div class="t-salon-name">Newshades Family Salon</div>'
    +'<div class="t-tagline">Look Beautiful, Feel Beautiful</div>'
    +'<div class="t-dots">&middot; &middot; &middot; &middot; &middot; &middot; &middot; &middot; &middot; &middot;</div>'
    +'<div class="t-receipt-title">PAYMENT RECEIPT</div>'
    +'<div class="t-dots">&middot; &middot; &middot; &middot; &middot; &middot; &middot; &middot; &middot; &middot;</div>'
    +'</div>'
    +'<div class="t-info">'
    +'<div class="t-row"><span>Bill No</span><span>'+esc(bid)+'</span></div>'
    +'<div class="t-row"><span>Date</span><span>'+dateStr+'</span></div>'
    +'<div class="t-row"><span>Time</span><span>'+timeStr+'</span></div>'
    +'<div class="t-row"><span>Customer</span><span>'+(c?esc(c.name):'Walk-in')+'</span></div>'
    +'<div class="t-row"><span>Mobile</span><span>'+(c?esc(c.phone):'&mdash;')+'</span></div>'
    +'</div>'
    +'<div class="t-dashed"></div>'
    +'<div class="t-table-head"><span>SERVICE</span><span>AMOUNT</span></div>'
    +'<div class="t-dashed"></div>'
    +itemRows
    +'<div class="t-dashed"></div>'
    +discRows
    +'<div class="t-grand-line"><div class="t-solid"></div>'
    +'<div class="t-grand"><span>TOTAL AMOUNT</span><span>&#8377;'+Math.round(b.total)+'</span></div>'
    +'<div class="t-solid"></div></div>'
    +'<div class="t-payment">'
    +'<div class="t-row"><span>Payment Mode</span><span>'+esc(b.payment)+'</span></div>'
    +'<div class="t-row"><span>Status</span><span class="t-paid">&#10003; Paid</span></div>'
    +'</div>'
    +'<div class="t-dashed"></div>'
    +'<div class="t-footer">'
    +'<div class="t-thankyou">Thank You! Visit Again &#128522;</div>'
    +'<div class="t-footer-sub">Newshades Family Salon</div>'
    +'<div class="t-footer-sub">Look Beautiful, Feel Beautiful</div>'
    +'</div></div></div></div>';
}

// ── Customers ─────────────────────────────────────────────────────────────────
function renderCustomers(el) {
  const customers = DB.getCustomers();
  const list = Object.entries(customers);
  const isAdmin = currentRole==='admin';
  const isEmp = isAdmin||currentRole==='employee';

  let rows = list.map(([cid,c])=>{
    return '<tr>'
      +'<td><span class="cust-av">'+esc(c.name[0])+'</span> '+esc(c.name)+'</td>'
      +'<td>'+esc(c.phone)+'</td>'
      +'<td><span class="visit-badge">'+((c.visits||[]).length)+'</span></td>'
      +'<td style="display:flex;gap:8px;flex-wrap:wrap;">'
      +'<a href="#" onclick="navigate(\'history\',{cid:\''+cid+'\'})" class="btn btn-sm">&#128203; History</a>'
      +(isEmp?'<a href="#" onclick="navigate(\'newbill\',{phone:\''+esc(c.phone)+'\'})" class="btn btn-sm" style="background:#f0fff4;color:#1a6b3a;border:1px solid #c8e6c9;">&#128221; Bill</a>':'')
      +(isAdmin?'<button onclick="deleteCustomer(\''+cid+'\',\''+esc(c.name)+'\')" class="btn btn-sm" style="background:#fde8ec;color:#c0394a;border:1px solid #f5c0c8;">&#128465;</button>':'')
      +'</td></tr>';
  }).join('');

  el.innerHTML = '<div class="page-header"><h1 class="page-title">&#128101; Customers</h1>'
    +(isEmp?'<a href="#" onclick="navigate(\'addcustomer\')" class="btn btn-primary">&#10133; Add Customer</a>':'')
    +'</div>'
    +'<div class="search-wrap"><span class="search-icon">&#128269;</span>'
    +'<input type="text" id="custSearchInput" placeholder="Search by name or phone..." oninput="filterCustomers()" autocomplete="off"/>'
    +'</div>'
    +(list.length?'<table class="data-table" id="custTable"><thead><tr><th>Name</th><th>Phone</th><th>Visits</th><th>Action</th></tr></thead><tbody id="custBody">'+rows+'</tbody></table>'
    :'<p class="empty-state">No customers yet. <a href="#" onclick="navigate(\'addcustomer\')">Add one!</a></p>');
}

function filterCustomers() {
  const q = document.getElementById('custSearchInput').value.toLowerCase();
  const customers = DB.getCustomers();
  const tbody = document.getElementById('custBody');
  if(!tbody) return;
  const isAdmin = currentRole==='admin';
  const isEmp = isAdmin||currentRole==='employee';
  let rows = '';
  Object.entries(customers).forEach(([cid,c])=>{
    if(!c.name.toLowerCase().includes(q) && !c.phone.includes(q)) return;
    rows += '<tr>'
      +'<td><span class="cust-av">'+esc(c.name[0])+'</span> '+esc(c.name)+'</td>'
      +'<td>'+esc(c.phone)+'</td>'
      +'<td><span class="visit-badge">'+((c.visits||[]).length)+'</span></td>'
      +'<td style="display:flex;gap:8px;flex-wrap:wrap;">'
      +'<a href="#" onclick="navigate(\'history\',{cid:\''+cid+'\'})" class="btn btn-sm">&#128203; History</a>'
      +(isEmp?'<a href="#" onclick="navigate(\'newbill\',{phone:\''+esc(c.phone)+'\'})" class="btn btn-sm" style="background:#f0fff4;color:#1a6b3a;border:1px solid #c8e6c9;">&#128221; Bill</a>':'')
      +(isAdmin?'<button onclick="deleteCustomer(\''+cid+'\',\''+esc(c.name)+'\')" class="btn btn-sm" style="background:#fde8ec;color:#c0394a;border:1px solid #f5c0c8;">&#128465;</button>':'')
      +'</td></tr>';
  });
  tbody.innerHTML = rows || '<tr><td colspan="4" class="empty-state">No customers found.</td></tr>';
}

function deleteCustomer(cid, name) {
  if(!confirm('Delete '+name+'?')) return;
  const c = DB.getCustomers(); delete c[cid]; DB.saveCustomers(c);
  flash('Customer deleted.','success'); navigate('customers');
}

function renderAddCustomer(el) {
  el.innerHTML = '<div class="page-header"><h1 class="page-title">&#10133; Add Customer</h1>'
    +'<a href="#" onclick="navigate(\'customers\')" class="btn btn-secondary">&larr; Back</a></div>'
    +'<div class="simple-form">'
    +'<input type="text" id="acName" placeholder="Full Name" style="display:block;width:100%;padding:10px 14px;margin-bottom:12px;border:1.5px solid #e8dce4;border-radius:10px;font-size:14px;outline:none;box-sizing:border-box;"/>'
    +'<input type="text" id="acPhone" placeholder="Phone Number" maxlength="10" oninput="this.value=this.value.replace(/[^0-9]/g,\'\')" style="display:block;width:100%;padding:10px 14px;margin-bottom:16px;border:1.5px solid #e8dce4;border-radius:10px;font-size:14px;outline:none;box-sizing:border-box;"/>'
    +'<button onclick="saveNewCustomer()" class="btn btn-primary">Save Customer</button>'
    +'</div>';
}

function saveNewCustomer() {
  const name = document.getElementById('acName').value.trim();
  const phone = document.getElementById('acPhone').value.trim();
  if(!name){ flash('Enter name','error'); return; }
  if(phone.length!==10){ flash('Enter valid 10-digit phone','error'); return; }
  const c = DB.getCustomers();
  if(Object.values(c).find(x=>x.phone===phone)){ flash('Customer with this phone already exists','error'); return; }
  const cid = genId('C');
  c[cid] = {name, phone, visits:[]};
  DB.saveCustomers(c);
  flash('Customer added!','success');
  navigate('customers');
}

function renderHistory(el, params) {
  const cid = params && params.cid;
  const c = DB.getCustomers()[cid];
  if(!c){ el.innerHTML='<p class="empty-state">Customer not found.</p>'; return; }
  const visits = c.visits||[];
  const isAdmin = currentRole==='admin';
  let rows = visits.slice().reverse().map(v=>'<tr>'
    +'<td>'+esc(v.bill_id)+'</td>'
    +'<td>'+esc(v.date)+'</td>'
    +'<td>&#8377;'+v.total+'</td>'
    +'<td>'+esc(v.payment)+'</td>'
    +(isAdmin?'<td><button onclick="deleteVisit(\''+cid+'\',\''+v.bill_id+'\')" class="btn btn-sm" style="background:#fde8ec;color:#c0394a;border:1px solid #f5c0c8;">&#128465; Delete</button></td>':'')
    +'</tr>').join('');

  el.innerHTML = '<div class="page-header"><h1 class="page-title">'+esc(c.name)+'\'s History</h1>'
    +'<a href="#" onclick="navigate(\'customers\')" class="btn btn-secondary">&larr; Back</a></div>'
    +'<p class="subtitle">&#128222; '+esc(c.phone)+' &nbsp;|&nbsp; '+visits.length+' visits</p>'
    +(visits.length?'<table class="data-table"><thead><tr><th>Bill ID</th><th>Date</th><th>Total</th><th>Payment</th>'+(isAdmin?'<th>Action</th>':'')+'</tr></thead><tbody>'+rows+'</tbody></table>'
    :'<p class="empty-state">No visits recorded yet.</p>');
}

function deleteVisit(cid, bid) {
  if(!confirm('Delete this visit record?')) return;
  const c = DB.getCustomers();
  c[cid].visits = (c[cid].visits||[]).filter(v=>v.bill_id!==bid);
  DB.saveCustomers(c);
  const bills = DB.getBills(); delete bills[bid]; DB.saveBills(bills);
  flash('Visit deleted.','success');
  navigate('history',{cid});
}

// ── Services ──────────────────────────────────────────────────────────────────
function renderServices(el) {
  const services = DB.getServices();
  const cats = [...new Set(Object.values(services).map(s=>s.category))].sort();
  let rows = Object.entries(services).map(([sid,s],i)=>'<tr id="row-'+sid+'" data-name="'+esc((s.name||'').toLowerCase())+'" data-category="'+esc((s.category||'').toLowerCase().replace(/ /g,'_'))+'">'
    +'<td class="sv-id">'+(i+1)+'</td>'
    +'<td class="sv-name">'+esc(s.name)+'</td>'
    +'<td><span class="sv-cat-badge">'+esc(s.category)+'</span></td>'
    +'<td class="sv-price">&#8377;'+s.price+'</td>'
    +'<td class="sv-actions">'
    +'<button class="sv-btn edit" onclick="openEditSvc(\''+sid+'\',\''+esc(s.name)+'\',\''+esc(s.category)+'\','+s.price+')">&#9999; Edit</button>'
    +'<button class="sv-btn del" onclick="deleteSvc(\''+sid+'\',\''+esc(s.name)+'\')">&#128465;</button>'
    +'</td></tr>'
  ).join('');

  el.innerHTML = '<h1 class="page-title">&#9881; Manage Services</h1>'
    +'<div class="sv-card" style="margin-bottom:20px;">'
    +'<div class="sv-card-title">&#10133; Add New Service</div>'
    +'<div class="add-form" style="margin-top:12px;">'
    +'<input type="text" id="newSvcName" placeholder="Service name" style="flex:2;min-width:140px;padding:10px 14px;border:1.5px solid #e8dce4;border-radius:10px;font-size:14px;outline:none;background:#fafafa;"/>'
    +'<input type="text" id="newSvcCat" placeholder="Category (e.g. Hair)" style="flex:2;min-width:120px;padding:10px 14px;border:1.5px solid #e8dce4;border-radius:10px;font-size:14px;outline:none;background:#fafafa;"/>'
    +'<div class="price-wrap"><span class="rupee">&#8377;</span><input type="number" id="newSvcPrice" placeholder="Price" min="0" step="0.01"/></div>'
    +'<button onclick="addService()" class="btn-add">+ Add</button>'
    +'</div></div>'
    +'<div class="sv-card">'
    +'<div class="sv-card-title" style="margin-bottom:14px;">&#128203; All Services <span class="svc-total-badge">'+Object.keys(services).length+'</span></div>'
    +'<div class="sv-search-wrap"><span>&#128269;</span>'
    +'<input type="text" id="svSearch" placeholder="Search services..." oninput="filterSvcs()">'
    +'<button type="button" id="svClear" onclick="clearSvSearch()" style="display:none;position:absolute;right:10px;background:none;border:none;cursor:pointer;color:#aaa;">&#10005;</button>'
    +'</div>'
    +'<div class="sv-tabs"><button class="sv-tab active" onclick="showSvcTab(\'all\',this)">All</button>'
    +cats.map(c=>'<button class="sv-tab" onclick="showSvcTab(\''+esc(c.toLowerCase().replace(/ /g,'_'))+'\',this)">'+esc(c)+'</button>').join('')
    +'</div>'
    +'<div class="sv-table-wrap"><table class="sv-table"><thead><tr><th>#</th><th>Service Name</th><th>Category</th><th>Price</th><th style="text-align:right">Actions</th></tr></thead>'
    +'<tbody id="svBody">'+rows+'</tbody></table>'
    +'<div id="svNoResults" class="sv-empty" style="display:none">No services found</div>'
    +'</div></div>'
    +'<div id="editSvcModal" class="modal-overlay" style="display:none" onclick="closeEditSvcModal(event)">'
    +'<div class="modal-box">'
    +'<div class="modal-title">&#9999; Edit Service</div>'
    +'<div class="modal-field"><label>Service Name</label><input type="text" id="editSvcName"/></div>'
    +'<div class="modal-field"><label>Category</label><input type="text" id="editSvcCat"/></div>'
    +'<div class="modal-field"><label>Price (&#8377;)</label><div class="price-wrap"><span class="rupee">&#8377;</span><input type="number" id="editSvcPrice" min="0" step="0.01"/></div></div>'
    +'<div class="modal-actions">'
    +'<button onclick="saveEditSvc()" class="sv-btn save">&#10003; Save Changes</button>'
    +'<button onclick="document.getElementById(\'editSvcModal\').style.display=\'none\'" class="sv-btn cancel">&#10005; Cancel</button>'
    +'</div></div></div>';
}

let editSvcId = null;
let svcActiveTab = 'all';

function showSvcTab(tab, btn) {
  svcActiveTab = tab;
  document.querySelectorAll('.sv-tab').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  applySvcFilter();
}
function filterSvcs() {
  const cl = document.getElementById('svClear');
  if(cl) cl.style.display = document.getElementById('svSearch').value?'block':'none';
  applySvcFilter();
}
function clearSvSearch() {
  document.getElementById('svSearch').value='';
  filterSvcs();
}
function applySvcFilter() {
  const q = document.getElementById('svSearch').value.toLowerCase();
  const rows = document.querySelectorAll('#svBody tr');
  let vis=0;
  rows.forEach(row=>{
    const nm = !q||row.dataset.name.includes(q);
    const tm = svcActiveTab==='all'||row.dataset.category===svcActiveTab;
    row.style.display=(nm&&tm)?'':'none';
    if(nm&&tm) vis++;
  });
  const nr=document.getElementById('svNoResults');
  if(nr) nr.style.display=vis===0?'block':'none';
}
function addService() {
  const name = document.getElementById('newSvcName').value.trim();
  const cat  = document.getElementById('newSvcCat').value.trim();
  const price= parseFloat(document.getElementById('newSvcPrice').value)||0;
  if(!name||!cat){ flash('Enter name and category','error'); return; }
  const svcs = DB.getServices();
  const nextId = String(Math.max(0,...Object.keys(svcs).map(Number))+1);
  svcs[nextId] = {name, category:cat, price};
  DB.saveServices(svcs);
  flash('Service "'+name+'" added.','success');
  navigate('services');
}
function openEditSvc(sid, name, cat, price) {
  editSvcId = sid;
  document.getElementById('editSvcName').value = name;
  document.getElementById('editSvcCat').value  = cat;
  document.getElementById('editSvcPrice').value= price;
  document.getElementById('editSvcModal').style.display='flex';
}
function closeEditSvcModal(e) {
  if(e.target===document.getElementById('editSvcModal'))
    document.getElementById('editSvcModal').style.display='none';
}
function saveEditSvc() {
  const name  = document.getElementById('editSvcName').value.trim();
  const cat   = document.getElementById('editSvcCat').value.trim();
  const price = parseFloat(document.getElementById('editSvcPrice').value)||0;
  if(!name||!cat){ flash('Fill all fields','error'); return; }
  const svcs = DB.getServices();
  svcs[editSvcId] = {name, category:cat, price};
  DB.saveServices(svcs);
  document.getElementById('editSvcModal').style.display='none';
  flash('Service updated.','success');
  navigate('services');
}
function deleteSvc(sid, name) {
  if(!confirm('Delete "'+name+'"?')) return;
  const svcs = DB.getServices();
  delete svcs[sid];
  DB.saveServices(svcs);
  flash('Service deleted.','success');
  navigate('services');
}

// ── Reports ───────────────────────────────────────────────────────────────────
function renderReport(el) {
  const t = todayStr();
  el.innerHTML = '<div class="page-header"><h1 class="page-title">&#128202; Daily Report</h1>'
    +'<a href="#" onclick="navigate(\'monthly\')" class="btn btn-secondary">&#128197; Monthly Report</a></div>'
    +'<div class="date-form" style="margin-bottom:24px;">'
    +'<input type="date" id="reportDate" value="'+t+'"/>'
    +'<button onclick="loadDailyReport()" class="btn btn-primary">View</button>'
    +'</div>'
    +'<div id="reportContent"></div>';
  loadDailyReport();
}

function loadDailyReport() {
  const date = document.getElementById('reportDate').value;
  const bills = DB.getBills();
  const filtered = Object.entries(bills).filter(([,b])=>b.date&&b.date.startsWith(date));
  const revenue = filtered.reduce((s,[,b])=>s+(b.total||0),0);
  const payMap = {};
  filtered.forEach(([,b])=>{ payMap[b.payment]=(payMap[b.payment]||0)+b.total; });
  const custs = DB.getCustomers();

  let rows = filtered.map(([bid,b])=>{
    const c = custs[b.customer_id];
    return '<tr><td><a href="#" onclick="navigate(\'receipt\',{bid:\''+bid+'\'})" style="color:#7b3f6e;font-weight:600;">'+esc(bid)+'</a></td>'
      +'<td>'+(c?esc(c.name):'Walk-in')+'</td>'
      +'<td>&#8377;'+b.total+'</td>'
      +'<td><span class="pay-badge '+(b.payment||'').toLowerCase()+'">'+esc(b.payment)+'</span></td></tr>';
  }).join('');

  let payRows = Object.entries(payMap).map(([m,a])=>'<tr><td><span class="pay-badge '+m.toLowerCase()+'">'+m+'</span></td><td>&#8377;'+a+'</td></tr>').join('');

  document.getElementById('reportContent').innerHTML =
    '<div class="report-summary">'
    +'<div class="stat-card"><div class="stat-icon">&#128221;</div><div class="stat-value">'+filtered.length+'</div><div class="stat-label">Total Bills</div></div>'
    +'<div class="stat-card"><div class="stat-icon">&#128176;</div><div class="stat-value">&#8377;'+revenue+'</div><div class="stat-label">Total Revenue</div></div>'
    +'</div>'
    +(payRows?'<h3 style="margin:20px 0 12px;color:#3d1a3a;">&#128179; Payment Breakdown</h3><table class="data-table" style="max-width:400px;margin-bottom:24px;"><thead><tr><th>Method</th><th>Amount</th></tr></thead><tbody>'+payRows+'</tbody></table>':'')
    +(rows?'<h3 style="margin:0 0 12px;color:#3d1a3a;">&#128221; Bills</h3><table class="data-table"><thead><tr><th>Bill ID</th><th>Customer</th><th>Total</th><th>Payment</th></tr></thead><tbody>'+rows+'</tbody></table>'
    :'<p class="empty-state">No bills found for '+date+'.</p>');
}

function renderRevenue(el) {
  const bills = DB.getBills();
  const daily = {};
  Object.values(bills).forEach(b=>{
    const day = (b.date||'').slice(0,10);
    if(!day) return;
    if(!daily[day]) daily[day]={total:0,bills:0,payment:{}};
    daily[day].total += b.total||0;
    daily[day].bills++;
    daily[day].payment[b.payment]=(daily[day].payment[b.payment]||0)+(b.total||0);
  });
  const sorted = Object.entries(daily).sort((a,b)=>b[0].localeCompare(a[0]));
  const grand = sorted.reduce((s,[,v])=>s+v.total,0);

  let rows = sorted.map(([day,info],i)=>'<tr>'
    +'<td>'+(i+1)+'</td><td>'+day+'</td><td>'+info.bills+'</td>'
    +'<td>&#8377;'+(info.payment['Cash']||0).toFixed(2)+'</td>'
    +'<td>&#8377;'+((info.payment['UPI']||0)+(info.payment['Card']||0)).toFixed(2)+'</td>'
    +'<td><strong>&#8377;'+info.total.toFixed(2)+'</strong></td></tr>'
  ).join('');

  el.innerHTML = '<div class="page-header"><h1 class="page-title">&#128200; Revenue List</h1>'
    +'<button onclick="window.print()" class="btn btn-primary no-print">&#128424; Print</button></div>'
    +(sorted.length?'<table class="data-table"><thead><tr><th>#</th><th>Date</th><th>Bills</th><th>Cash</th><th>UPI/Card</th><th>Total Revenue</th></tr></thead><tbody>'+rows+'</tbody>'
    +'<tfoot><tr class="grand-total-row"><td colspan="5"><strong>Grand Total</strong></td><td><strong>&#8377;'+grand.toFixed(2)+'</strong></td></tr></tfoot></table>'
    :'<p class="empty-state">No revenue data found.</p>');
}

function renderMonthly(el) {
  const now = new Date();
  const defMonth = now.getFullYear()+'-'+String(now.getMonth()+1).padStart(2,'0');
  el.innerHTML = '<div class="page-header"><h1 class="page-title">&#128197; Monthly Report</h1>'
    +'<a href="#" onclick="navigate(\'report\')" class="btn btn-secondary">&#128202; Daily Report</a></div>'
    +'<div class="date-form" style="margin-bottom:24px;">'
    +'<input type="month" id="monthInput" value="'+defMonth+'"/>'
    +'<button onclick="loadMonthly()" class="btn btn-primary">View</button>'
    +'</div><div id="monthlyContent"></div>';
  loadMonthly();
}

function loadMonthly() {
  const month = document.getElementById('monthInput').value;
  const bills = DB.getBills();
  const filtered = Object.values(bills).filter(b=>b.date&&b.date.startsWith(month));
  const revenue = filtered.reduce((s,b)=>s+(b.total||0),0);
  const payMap={}, svcMap={}, dailyMap={};
  filtered.forEach(b=>{
    payMap[b.payment]=(payMap[b.payment]||0)+b.total;
    const day=(b.date||'').slice(0,10);
    dailyMap[day]=(dailyMap[day]||0)+b.total;
    (b.items||[]).forEach(i=>{ svcMap[i.name]=(svcMap[i.name]||0)+i.qty; });
  });
  const topSvcs=Object.entries(svcMap).sort((a,b)=>b[1]-a[1]).slice(0,10);
  const dailySorted=Object.entries(dailyMap).sort((a,b)=>a[0].localeCompare(b[0]));
  const avg=filtered.length?Math.round(revenue/filtered.length):0;

  let payRows=Object.entries(payMap).map(([m,a])=>'<tr><td>'+m+'</td><td>&#8377;'+a+'</td></tr>').join('');
  let svcBars=topSvcs.map(([n,c])=>'<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;">'
    +'<span style="width:140px;font-size:13px;color:#3d1a3a;">'+esc(n)+'</span>'
    +'<div style="flex:1;background:#f0e8f8;border-radius:20px;height:8px;overflow:hidden;">'
    +'<div style="width:'+Math.round(c/topSvcs[0][1]*100)+'%;height:100%;background:linear-gradient(90deg,#7b3f6e,#e8a0b0);border-radius:20px;"></div></div>'
    +'<span style="font-size:12px;font-weight:600;color:#7b3f6e;">'+c+'x</span></div>').join('');
  let dailyRows=dailySorted.map(([d,a])=>'<tr><td>'+d+'</td><td>&#8377;'+a+'</td></tr>').join('');

  document.getElementById('monthlyContent').innerHTML =
    '<div class="stats-grid" style="margin-bottom:24px;">'
    +'<div class="stat-card"><div class="stat-icon">&#128221;</div><div class="stat-value">'+filtered.length+'</div><div class="stat-label">Total Bills</div></div>'
    +'<div class="stat-card"><div class="stat-icon">&#128176;</div><div class="stat-value">&#8377;'+revenue+'</div><div class="stat-label">Total Revenue</div></div>'
    +'<div class="stat-card"><div class="stat-icon">&#128200;</div><div class="stat-value">&#8377;'+avg+'</div><div class="stat-label">Avg per Bill</div></div>'
    +'</div>'
    +(payRows?'<h3 style="margin:0 0 12px;color:#3d1a3a;">&#128179; Payment Breakdown</h3><table class="data-table" style="max-width:400px;margin-bottom:24px;"><thead><tr><th>Method</th><th>Amount</th></tr></thead><tbody>'+payRows+'</tbody></table>':'')
    +(svcBars?'<h3 style="margin:0 0 12px;color:#3d1a3a;">&#11088; Top Services</h3><div style="background:#fff;border-radius:12px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,0.08);margin-bottom:24px;">'+svcBars+'</div>':'')
    +(dailyRows?'<h3 style="margin:0 0 12px;color:#3d1a3a;">&#128198; Daily Revenue</h3><table class="data-table" style="margin-bottom:24px;"><thead><tr><th>Date</th><th>Revenue</th></tr></thead><tbody>'+dailyRows+'</tbody></table>':'')
    +(!filtered.length?'<p class="empty-state">No bills found for '+month+'.</p>':'');
}

// ── Profile ───────────────────────────────────────────────────────────────────
function renderProfile(el) {
  const admin = DB.getAdmin();
  el.innerHTML = '<h1 class="page-title">&#128100; My Profile</h1>'
    +'<div class="simple-form" style="max-width:500px;">'
    +'<h3 style="margin-bottom:16px;color:#3d1a3a;">Change Admin Password</h3>'
    +'<input type="text" id="profUser" placeholder="Username" value="'+esc(admin.username)+'" style="display:block;width:100%;padding:10px 14px;margin-bottom:12px;border:1.5px solid #e8dce4;border-radius:10px;font-size:14px;outline:none;box-sizing:border-box;"/>'
    +'<input type="password" id="profCurr" placeholder="Current Password" style="display:block;width:100%;padding:10px 14px;margin-bottom:12px;border:1.5px solid #e8dce4;border-radius:10px;font-size:14px;outline:none;box-sizing:border-box;"/>'
    +'<input type="password" id="profNew" placeholder="New Password" style="display:block;width:100%;padding:10px 14px;margin-bottom:12px;border:1.5px solid #e8dce4;border-radius:10px;font-size:14px;outline:none;box-sizing:border-box;"/>'
    +'<input type="password" id="profConf" placeholder="Confirm New Password" style="display:block;width:100%;padding:10px 14px;margin-bottom:16px;border:1.5px solid #e8dce4;border-radius:10px;font-size:14px;outline:none;box-sizing:border-box;"/>'
    +'<button onclick="saveProfile()" class="btn btn-primary" style="margin-bottom:24px;">Save Changes</button>'
    +'<hr style="margin-bottom:20px;border-color:#f0e8f8;"/>'
    +'<h3 style="margin-bottom:16px;color:#3d1a3a;">Employee Password</h3>'
    +'<input type="password" id="profEmp" placeholder="Employee Password (leave blank to disable)" style="display:block;width:100%;padding:10px 14px;margin-bottom:16px;border:1.5px solid #e8dce4;border-radius:10px;font-size:14px;outline:none;box-sizing:border-box;"/>'
    +'<button onclick="saveEmpPass()" class="btn btn-secondary">Save Employee Password</button>'
    +'</div>';
}

function saveProfile() {
  const admin = DB.getAdmin();
  const user = document.getElementById('profUser').value.trim();
  const curr = document.getElementById('profCurr').value;
  const newp = document.getElementById('profNew').value;
  const conf = document.getElementById('profConf').value;
  if(curr !== admin.password){ flash('Current password incorrect','error'); return; }
  if(!user){ flash('Username cannot be empty','error'); return; }
  if(newp && newp!==conf){ flash('New passwords do not match','error'); return; }
  admin.username = user;
  if(newp) admin.password = newp;
  DB.saveAdmin(admin);
  flash('Profile updated!','success');
}

function saveEmpPass() {
  const admin = DB.getAdmin();
  admin.empPassword = document.getElementById('profEmp').value;
  DB.saveAdmin(admin);
  flash('Employee password updated!','success');
}
