// ── Auth ──────────────────────────────────────────────────────────────────────
let currentRole = null;
let loginTab = 'admin';

function setLoginTab(tab) {
  loginTab = tab;
  document.getElementById('adminLoginForm').style.display = tab === 'admin' ? '' : 'none';
  document.getElementById('empLoginForm').style.display   = tab === 'employee' ? '' : 'none';
  document.getElementById('tabAdmin').style.background = tab === 'admin' ? '#7b3f6e' : '#fff';
  document.getElementById('tabAdmin').style.color      = tab === 'admin' ? '#fff' : '#7b3f6e';
  document.getElementById('tabEmp').style.background   = tab === 'employee' ? '#7b3f6e' : '#fff';
  document.getElementById('tabEmp').style.color        = tab === 'employee' ? '#fff' : '#7b3f6e';
}

function doLogin() {
  const admin = DB.getAdmin();
  const err = document.getElementById('loginErr');
  if (loginTab === 'admin') {
    const u = document.getElementById('loginUser').value.trim();
    const p = document.getElementById('loginPass').value;
    if (u === admin.username && p === admin.password) {
      DB.setAuth({role:'admin'}); currentRole = 'admin'; showApp();
    } else { err.textContent = 'Invalid username or password.'; err.style.display = ''; }
  } else {
    const p = document.getElementById('loginEmpPass').value;
    if (!admin.empPassword || p === admin.empPassword) {
      DB.setAuth({role:'employee'}); currentRole = 'employee'; showApp();
    } else { err.textContent = 'Incorrect employee password.'; err.style.display = ''; }
  }
}

function doLogout() {
  DB.setAuth({role:null}); currentRole = null;
  document.getElementById('loginOverlay').style.display = 'flex';
  document.getElementById('loginErr').style.display = 'none';
  document.getElementById('loginUser') && (document.getElementById('loginUser').value = '');
  document.getElementById('loginPass') && (document.getElementById('loginPass').value = '');
}

function showApp() {
  document.getElementById('loginOverlay').style.display = 'none';
  updateSidebarRole();
  navigate('dashboard');
}

function updateSidebarRole() {
  const isAdmin = currentRole === 'admin';
  const isEmp   = currentRole === 'employee' || isAdmin;
  document.querySelectorAll('.role-admin').forEach(el => el.style.display = isAdmin ? '' : 'none');
  document.querySelectorAll('.role-emp').forEach(el => el.style.display = isEmp ? '' : 'none');
  const badge = document.getElementById('roleBadge');
  badge.textContent = isAdmin ? 'Admin' : 'Employee';
  badge.className = 'role-badge ' + (isAdmin ? 'admin' : 'employee');
}

// ── Router ────────────────────────────────────────────────────────────────────
let currentPage = '';
function navigate(page, params) {
  closeSidebar();
  currentPage = page;
  document.querySelectorAll('nav a').forEach(a => a.classList.remove('active'));
  const navEl = document.getElementById('nav-' + page);
  if (navEl) navEl.classList.add('active');
  const container = document.getElementById('pageContainer');
  container.innerHTML = '';
  const pages = {
    dashboard:   renderDashboard,
    newbill:     renderNewBill,
    customers:   renderCustomers,
    addcustomer: renderAddCustomer,
    history:     renderHistory,
    report:      renderReport,
    revenue:     renderRevenue,
    services:    renderServices,
    monthly:     renderMonthly,
    profile:     renderProfile,
    receipt:     renderReceipt
  };
  if (pages[page]) pages[page](container, params);
}

// ── Flash ─────────────────────────────────────────────────────────────────────
function flash(msg, type) {
  const box = document.getElementById('alertBox');
  const el = document.createElement('div');
  el.className = 'alert ' + (type || 'success');
  el.textContent = msg;
  box.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 400); }, 3000);
}

// ── Sidebar ───────────────────────────────────────────────────────────────────
function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
  document.getElementById('sidebarOverlay').classList.toggle('open');
}
function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebarOverlay').classList.remove('open');
}

// ── Boot ──────────────────────────────────────────────────────────────────────
(function boot() {
  const auth = DB.getAuth();
  if (auth && auth.role) {
    currentRole = auth.role;
    showApp();
  } else {
    document.getElementById('loginOverlay').style.display = 'flex';
  }
})();
