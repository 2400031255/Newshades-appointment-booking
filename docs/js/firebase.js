import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js";
import { getAuth, signInWithEmailAndPassword, signOut, onAuthStateChanged, browserSessionPersistence, setPersistence } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js";
import { getFirestore, initializeFirestore, persistentLocalCache, collection, doc, getDoc, getDocs, addDoc, updateDoc, deleteDoc, query, where, orderBy, limit, onSnapshot, serverTimestamp } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-firestore.js";

import { firebaseConfig } from './config.js';
export { firebaseConfig };

const app  = initializeApp(firebaseConfig);
export const auth = getAuth(app);
// Use persistent cache (v10 way) — snapshots fire from IndexedDB instantly on repeat visits
export const db = initializeFirestore(app, { localCache: persistentLocalCache() });
setPersistence(auth, browserSessionPersistence).catch(() => {});
export { collection, query, where, getDocs, orderBy, limit, onSnapshot, serverTimestamp };

// ── Upload file to Firebase Storage with progress callback ────────────────
export async function uploadFile(path, file, onProgress) {
  const { getStorage, ref, uploadBytesResumable, getDownloadURL } = await import('https://www.gstatic.com/firebasejs/10.12.0/firebase-storage.js');
  const storage = getStorage(app);
  return new Promise((resolve, reject) => {
    const task = uploadBytesResumable(ref(storage, path), file);
    task.on('state_changed',
      snap => onProgress && onProgress(Math.round(snap.bytesTransferred / snap.totalBytes * 100)),
      reject,
      () => getDownloadURL(task.snapshot.ref).then(resolve).catch(reject)
    );
  });
}

// ── Session cache for profile (avoids repeat Firestore reads) ─────────────
const _cache = {};
function cacheSet(key, val, ttlMs = 0) {
  const entry = ttlMs ? { val, exp: Date.now() + ttlMs } : { val };
  try { sessionStorage.setItem(key, JSON.stringify(entry)); } catch{}
  _cache[key] = entry;
}
function cacheGet(key) {
  const entry = _cache[key] || (() => { try { const v = sessionStorage.getItem(key); return v ? JSON.parse(v) : null; } catch{ return null; } })();
  if (!entry) return null;
  if (entry.exp && Date.now() > entry.exp) { try { sessionStorage.removeItem(key); } catch{} delete _cache[key]; return null; }
  return entry.val;
}
function cacheClear() { try { sessionStorage.clear(); } catch{} Object.keys(_cache).forEach(k => delete _cache[k]); }

// ── Auth ───────────────────────────────────────────────────────────────────
export async function loginUser(email, password) {
  return signInWithEmailAndPassword(auth, email, password);
}
export async function logoutUser() {
  cacheClear();
  await signOut(auth);
  // Always redirect to login relative to current path depth
  const parts = window.location.pathname.split('/').filter(Boolean);
  const inSubfolder = parts.length >= 2 && ['admin','employee','customer'].includes(parts[parts.length-2]);
  window.location.href = inSubfolder ? '../login.html' : 'login.html';
}
export function onAuth(cb) { return onAuthStateChanged(auth, cb); }
export function currentUser() { return auth.currentUser; }

// ── Guard: redirect to login if not authenticated ─────────────────────────
export function requireAuth(redirectTo = "/login.html") {
  if (auth.currentUser) return Promise.resolve(auth.currentUser);
  return new Promise(resolve => {
    const unsub = onAuthStateChanged(auth, user => {
      unsub();
      if (!user) { window.location.href = redirectTo; return; }
      resolve(user);
    });
  });
}

// ── Guard: redirect to dashboard if already logged in ────────────────────
export function requireGuest() {
  return new Promise(resolve => {
    const unsub = onAuthStateChanged(auth, async user => {
      unsub();
      if (!user) { resolve(null); return; }
      const [profile, emp] = await Promise.all([getUserProfile(user.uid), getEmployeeProfile(user.uid, true)]); // bypass cache for active check
      if (profile?.is_admin) { window.location.href = 'admin/dashboard.html'; return; }
      // Block deactivated employees from logging in
      if (emp) {
        if (emp.deleted || emp.is_active === 0 || emp.is_active === false) {
          await import('https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js').then(m => m.signOut(auth));
          window.location.href = 'login.html?error=deactivated';
          return;
        }
        window.location.href = 'employee/dashboard.html';
        return;
      }
      // No profile and no employee record — orphaned auth user, sign out
      if (!profile) {
        await import('https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js').then(m => m.signOut(auth));
        resolve(null);
        return;
      }
      window.location.href = 'customer/dashboard.html';
    });
  });
}

// ── User profiles (session-cached) ────────────────────────────────────────
export async function getUserProfile(uid) {
  const key = `up_${uid}`;
  const hit = cacheGet(key); if (hit) return hit;
  try {
    const snap = await getDoc(doc(db, "users", uid));
    const val = snap.exists() ? { id: snap.id, ...snap.data() } : null;
    if (val) cacheSet(key, val);
    return val;
  } catch { return null; }
}
export async function getEmployeeProfile(uid, bypassCache = false) {
  const key = `ep_${uid}`;
  if (!bypassCache) { const hit = cacheGet(key); if (hit) return hit; }
  try {
    const snap = await getDoc(doc(db, "employees", uid));
    const val = snap.exists() ? { id: snap.id, ...snap.data() } : null;
    if (val) cacheSet(key, val);
    return val;
  } catch { return null; }
}
export async function updateUserProfile(uid, data) {
  try { sessionStorage.removeItem(`up_${uid}`); } catch{}
  delete _cache[`up_${uid}`];
  return updateDoc(doc(db, "users", uid), data);
}

// ── Settings (session-cached) ─────────────────────────────────────────────
export async function getSettings() {
  const hit = cacheGet('settings_shop'); if (hit) return hit;
  const snap = await getDoc(doc(db, "settings", "shop"));
  const val = snap.exists() ? snap.data() : {};
  cacheSet('settings_shop', val);
  return val;
}
export async function saveSettings(data) {
  const { setDoc } = await import('https://www.gstatic.com/firebasejs/10.12.0/firebase-firestore.js');
  try { sessionStorage.removeItem('settings_shop'); } catch{}
  delete _cache['settings_shop'];
  return setDoc(doc(db, "settings", "shop"), data, { merge: true });
}
export async function getAppSettings() {
  const hit = cacheGet('settings_app'); if (hit) return hit;
  const snap = await getDoc(doc(db, "settings", "app"));
  const val = snap.exists() ? snap.data() : {};
  cacheSet('settings_app', val);
  return val;
}
export async function saveAppSettings(data, adminName) {
  const { setDoc } = await import('https://www.gstatic.com/firebasejs/10.12.0/firebase-firestore.js');
  try { sessionStorage.removeItem('settings_app'); } catch{}
  delete _cache['settings_app'];
  return setDoc(doc(db, "settings", "app"), { ...data, lastUpdated: serverTimestamp(), updatedBy: adminName }, { merge: true });
}

// ── Services ──────────────────────────────────────────────────────────────
export async function getServices(activeOnly = false) {
  const snap = await getDocs(collection(db, "services"));
  const all = snap.docs.map(d => ({ id: d.id, ...d.data() }));
  if (!activeOnly) return all;
  return all.filter(s => s.is_active === 1 || s.is_active === true || s.is_active === '1');
}
export async function getServiceById(id) {
  const snap = await getDoc(doc(db, "services", id));
  return snap.exists() ? { id: snap.id, ...snap.data() } : null;
}
export async function createService(data) {
  return addDoc(collection(db, "services"), { ...data, created_at: serverTimestamp() });
}
export async function updateService(id, data) { return updateDoc(doc(db, "services", id), data); }
export async function deleteService(id) { return deleteDoc(doc(db, "services", id)); }
export function listenServices(cb, activeOnly = false) {
  return onSnapshot(collection(db, 'services'), snap => {
    let docs = snap.docs.map(d => ({ id: d.id, ...d.data() }));
    if (activeOnly) docs = docs.filter(s => s.is_active === 1 || s.is_active === true || s.is_active === '1');
    cb(docs);
  });
}

// ── Enquiries ─────────────────────────────────────────────────────────────
export async function getAllEnquiries(statusFilter = "") {
  let q = statusFilter
    ? query(collection(db, "enquiries"), where("status", "==", statusFilter))
    : collection(db, "enquiries");
  const snap = await getDocs(q);
  return snap.docs.map(d => ({ id: d.id, ...d.data() }))
    .sort((a, b) => (b.created_at?.seconds || 0) - (a.created_at?.seconds || 0));
}
export async function getEnquiriesForUser(uid) {
  const q = query(collection(db, "enquiries"), where("user_id", "==", uid));
  const snap = await getDocs(q);
  return snap.docs.map(d => ({ id: d.id, ...d.data() }))
    .sort((a, b) => (b.created_at?.seconds || 0) - (a.created_at?.seconds || 0));
}
export async function createEnquiry(data) {
  return addDoc(collection(db, "enquiries"), { ...data, status: "Pending", created_at: serverTimestamp() });
}
export async function updateEnquiry(id, data) { return updateDoc(doc(db, "enquiries", id), data); }
export async function deleteEnquiry(id) { return deleteDoc(doc(db, "enquiries", id)); }
export function listenEnquiries(cb) {
  const q = query(collection(db, "enquiries"), orderBy("created_at", "desc"), limit(100));
  return onSnapshot(q, snap => cb(snap.docs.map(d => ({ id: d.id, ...d.data() }))));
}

// ── Customers ─────────────────────────────────────────────────────────────
export async function getAllCustomers() {
  const snap = await getDocs(collection(db, "users"));
  return snap.docs.map(d => ({ id: d.id, ...d.data() })).filter(u => !u.is_admin);
}

// ── Employees ─────────────────────────────────────────────────────────────
export async function getAllEmployees(activeOnly = false) {
  const snap = await getDocs(collection(db, "employees"));
  const all = snap.docs.map(d => ({ id: d.id, ...d.data() }));
  if (!activeOnly) return all;
  return all.filter(e => e.is_active === 1 || e.is_active === true);
}
export function listenEmployees(cb) {
  return onSnapshot(collection(db, 'employees'), snap => {
    cb(snap.docs.map(d => ({ id: d.id, ...d.data() })));
  });
}
export async function createEmployee(data) {
  return addDoc(collection(db, "employees"), { ...data, created_at: serverTimestamp() });
}
export async function updateEmployee(id, data) {
  try { sessionStorage.removeItem(`ep_${id}`); } catch{}
  delete _cache[`ep_${id}`];
  return updateDoc(doc(db, "employees", id), data);
}

// Guard: require active employee — always fetches fresh from Firestore (bypasses cache)
export async function requireActiveEmployee(redirectTo = '../login.html') {
  const { auth: _auth } = await Promise.resolve({ auth });
  return new Promise(resolve => {
    const unsub = onAuthStateChanged(auth, async user => {
      unsub();
      if (!user) { window.location.href = redirectTo; return; }
      const emp = await getEmployeeProfile(user.uid, true); // bypass cache
      if (!emp || emp.is_active === 0 || emp.is_active === false) {
        await signOut(auth);
        window.location.href = redirectTo + '?error=deactivated';
        return;
      }
      resolve({ user, emp });
    });
  });
}
export async function deleteEmployee(id) { return deleteDoc(doc(db, "employees", id)); }

// ── Attendance ────────────────────────────────────────────────────────────
export async function getAttendance(date) {
  const q = query(collection(db, "attendance"), where("date", "==", date));
  const snap = await getDocs(q);
  return snap.docs.map(d => ({ id: d.id, ...d.data() }));
}
export async function markAttendance(data) {
  const q = query(collection(db, "attendance"), where("employee_id", "==", data.employee_id), where("date", "==", data.date));
  const snap = await getDocs(q);
  if (!snap.empty) return updateDoc(snap.docs[0].ref, data);
  return addDoc(collection(db, "attendance"), { ...data, created_at: serverTimestamp() });
}

// ── Reviews ───────────────────────────────────────────────────────────────
export async function getReviews(lim = 6) {
  const q = query(collection(db, "reviews"), orderBy("created_at", "desc"), limit(lim));
  const snap = await getDocs(q);
  return snap.docs.map(d => ({ id: d.id, ...d.data() }));
}
export async function createReview(data) {
  return addDoc(collection(db, "reviews"), { ...data, created_at: serverTimestamp() });
}
export async function updateReview(id, data) { return updateDoc(doc(db, "reviews", id), data); }
export async function getReviewByUser(uid) {
  const q = query(collection(db, "reviews"), where("user_id", "==", uid), limit(1));
  const snap = await getDocs(q);
  return snap.empty ? null : { id: snap.docs[0].id, ...snap.docs[0].data() };
}

// ── Offers ────────────────────────────────────────────────────────────────
export async function getActiveOffers() {
  const today = new Date().toISOString().slice(0, 10);
  const snap = await getDocs(collection(db, "offers"));
  return snap.docs.map(d => ({ id: d.id, ...d.data() }))
    .filter(o => (o.is_active === 1 || o.is_active === true)
      && (!o.valid_from || o.valid_from <= today)
      && (!o.valid_until || o.valid_until >= today));
}
export async function getAllOffers() {
  const snap = await getDocs(collection(db, "offers"));
  return snap.docs.map(d => ({ id: d.id, ...d.data() }));
}
export async function createOffer(data) {
  return addDoc(collection(db, "offers"), { ...data, created_at: serverTimestamp() });
}
export async function updateOffer(id, data) { return updateDoc(doc(db, "offers", id), data); }
export async function deleteOffer(id) { return deleteDoc(doc(db, "offers", id)); }

// ── Gallery ───────────────────────────────────────────────────────────────
export async function getGallery() {
  try {
    const snap = await getDocs(query(collection(db, "gallery"), orderBy("created_at", "desc")));
    return snap.docs.map(d => ({ id: d.id, ...d.data() }));
  } catch {
    const snap = await getDocs(collection(db, "gallery"));
    return snap.docs.map(d => ({ id: d.id, ...d.data() }));
  }
}
export async function addGalleryPhoto(data) {
  return addDoc(collection(db, "gallery"), { ...data, created_at: serverTimestamp() });
}
export async function deleteGalleryPhoto(id) { return deleteDoc(doc(db, "gallery", id)); }

// ── Leave Requests ────────────────────────────────────────────────────────
export async function getLeaveRequests(uid = null) {
  const q = uid
    ? query(collection(db, "leave_requests"), where("employee_id", "==", uid))
    : collection(db, "leave_requests");
  const snap = await getDocs(q);
  return snap.docs.map(d => ({ id: d.id, ...d.data() }));
}
export async function createLeaveRequest(data) {
  return addDoc(collection(db, "leave_requests"), { ...data, status: "Pending", created_at: serverTimestamp() });
}
export async function updateLeaveRequest(id, data) { return updateDoc(doc(db, "leave_requests", id), data); }

// ── Payroll ───────────────────────────────────────────────────────────────
export async function getPayroll(month) {
  const q = query(collection(db, "payroll"), where("month", "==", month));
  const snap = await getDocs(q);
  return snap.docs.map(d => ({ id: d.id, ...d.data() }));
}
export async function savePayroll(data) {
  const q = query(collection(db, "payroll"), where("employee_id", "==", data.employee_id), where("month", "==", data.month));
  const snap = await getDocs(q);
  if (!snap.empty) return updateDoc(snap.docs[0].ref, data);
  return addDoc(collection(db, "payroll"), { ...data, created_at: serverTimestamp() });
}

// ── Utilities ─────────────────────────────────────────────────────────────
export function esc(s) { return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

export function today() { return new Date().toISOString().slice(0, 10); }

export function to12hr(t) {
  if (!t) return "—";
  const [h, m] = t.split(":").map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
}

export function showToast(msg, type = "success") {
  const colors = { success: "#25d366", danger: "#ff6b6b", warning: "#ffc107", info: "#63b3ff" };
  const icons  = { success: "fa-check-circle", danger: "fa-times-circle", warning: "fa-exclamation-triangle", info: "fa-info-circle" };
  const isMobile = window.innerWidth < 768;
  const t = document.createElement("div");
  t.style.cssText = `position:fixed;top:${isMobile ? 72 : 24}px;right:${isMobile ? 12 : 24}px;${isMobile ? 'left:12px;' : ''}z-index:99999;display:flex;align-items:center;gap:12px;
    padding:14px 20px;border-radius:14px;background:#0e0b14;border:1px solid ${colors[type]}55;
    color:#fff;font-size:0.9rem;box-shadow:0 24px 70px rgba(0,0,0,0.7);min-width:${isMobile ? 'unset' : '280px'};max-width:${isMobile ? '100%' : '380px'};`;
  const msgEl = document.createElement('span');
  msgEl.textContent = msg;
  t.innerHTML = `<i class="fas ${icons[type]}" style="color:${colors[type]};font-size:1.1rem;flex-shrink:0;"></i>`;
  t.appendChild(msgEl);
  document.body.appendChild(t);
  setTimeout(() => { t.style.opacity = "0"; t.style.transition = "opacity 0.3s"; setTimeout(() => t.remove(), 300); }, 3500);
}

export function formatDate(d) {
  if (!d) return "—";
  const s = d?.toDate ? d.toDate().toISOString().slice(0,10) : String(d).slice(0,10);
  const [y, mo, day] = s.split("-");
  const months = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${parseInt(day)} ${months[parseInt(mo)]} ${y}`;
}

export function statusBadge(status) {
  const map = {
    Pending:   "background:rgba(255,170,77,0.16);color:#ffc36b;",
    Contacted: "background:rgba(105,152,255,0.16);color:#9dc0ff;",
    Confirmed: "background:rgba(37,211,102,0.16);color:#7ce0aa;",
    Closed:    "background:rgba(150,150,150,0.14);color:rgba(240,230,211,0.5);"
  };
  return `<span style="padding:4px 12px;border-radius:999px;font-size:0.75rem;font-weight:700;${map[status]||map.Pending}">${status}</span>`;
}
