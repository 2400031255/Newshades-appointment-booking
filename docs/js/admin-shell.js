// Shared admin shell: sidebar toggle + auth guard
export function initAdminShell(activeLink) {
  const sidebar = document.getElementById('adminSidebar');
  const overlay = document.getElementById('sidebarOverlay');
  const toggleBtn = document.getElementById('sidebarToggle');
  if (toggleBtn) toggleBtn.addEventListener('click', () => { sidebar.classList.add('open'); overlay.classList.add('show'); document.body.style.overflow = 'hidden'; });
  if (overlay) overlay.addEventListener('click', () => { sidebar.classList.remove('open'); overlay.classList.remove('show'); document.body.style.overflow = ''; });
  if (activeLink) { const a = document.querySelector(`.sidebar-nav a[href="${activeLink}"]`); if (a) a.classList.add('active'); }
}

export function adminSidebarHTML(active) {
  const links = [
    ['dashboard.html','fas fa-tachometer-alt','Dashboard'],
    ['services.html','fas fa-concierge-bell','Services'],
    ['enquiries.html','fas fa-clipboard-list','Enquiries'],
    ['customers.html','fas fa-users','Customers'],
    ['employees.html','fas fa-user-tie','Employees'],
    ['attendance.html','fas fa-calendar-check','Attendance'],
    ['payroll.html','fas fa-money-bill-wave','Payroll'],
    ['leave_requests.html','fas fa-calendar-minus','Leave Requests'],
    ['settings.html','fab fa-whatsapp','Settings'],
    ['gallery.html','fas fa-images','Gallery'],
    ['reviews.html','fas fa-star','Reviews'],
  ];
  return `<div class="sidebar-overlay" id="sidebarOverlay"></div>
  <div class="admin-sidebar" id="adminSidebar">
    <div class="brand d-flex align-items-center gap-2"><img src="../images/logo.jpeg" alt="NS" class="admin-brand-logo"/><div><h4>New Shades</h4><small style="color:rgba(255,255,255,0.4);font-size:0.75rem;">Admin Panel</small></div></div>
    <nav class="sidebar-nav">
      ${links.map(([href,icon,label]) => `<a href="${href}"${href===active?' class="active"':''}><span class="sidebar-nav-label"><i class="${icon}"${icon.includes('whatsapp')?' style="color:#25d366;"':''}></i> ${label}</span></a>`).join('')}
      <a href="#" id="logoutBtn" style="margin-top:auto;color:#ff6b6b;"><span class="sidebar-nav-label"><i class="fas fa-sign-out-alt"></i> Logout</span></a>
    </nav>
  </div>`;
}
