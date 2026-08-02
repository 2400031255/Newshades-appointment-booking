import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js";
import { getAuth, signInWithEmailAndPassword, signOut, onAuthStateChanged } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js";
import { getFirestore, collection, doc, getDoc, getDocs, addDoc, updateDoc, deleteDoc, query, where, orderBy, limit, onSnapshot, serverTimestamp, enableIndexedDbPersistence } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-firestore.js";

export const firebaseConfig = {
  apiKey: "AIzaSyD1u6cOGWmrrJ-JbBDSFJ5eJ11XPTDbCWk",
  authDomain: "newshadeseluru-ec450.firebaseapp.com",
  projectId: "newshadeseluru-ec450",
  storageBucket: "newshadeseluru-ec450.firebasestorage.app",
  messagingSenderId: "5209377015",
  appId: "1:5209377015:web:f363707d7fcfbdd095abf2"
};

const app  = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const db   = getFirestore(app);
export { collection, query, where, getDocs, orderBy, limit, onSnapshot, serverTimestamp };

// ── Offline persistence (cache-first on repeat visits) ────────────────────
enableIndexedDbPersistence(db).catch(() => {});

// ── Session cache for profile (avoids repeat Firestore reads) ─────────────
const _cache = {};
function cacheSet(key, val) { try { sessionStorage.setItem(key, JSON.stringify(val)); } catch{} _cache[key] = val; }
function cacheGet(key) { if (_cache[key]) return _cache[key]; try { const v = sessionStorage.getItem(key); return v ? JSON.parse(v) : null; } catch{ return null; } }
function cacheClear() { try { sessionStorage.clear(); } catch{} Object.keys(_cache).forEach(k => delete _cache[k]); }

// ── Auth ───────────────────────────────────────────────────────────────────
export async function loginUser(email, password) {
  return signInWithEmailAndPassword(auth, email, password);
}
export async function logoutUser() {
  cacheClear();
  await signOut(auth);
  const depth = window.location.pathname.split('/').filter(Boolean).length;
  const prefix = depth >= 2 ? '../' : '';
  window.location.href = prefix + 'login.html';
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
      const [profile, emp] = await Promise.all([getUserProfile(user.uid), getEmployeeProfile(user.uid)]);
      if (profile?.is_admin) { window.location.href = "admin/dashboard.html"; return; }
      if (emp) { window.location.href = "employee/dashboard.html"; return; }
      window.location.href = "index.html";
    });
  });
}

// ── User profiles (session-cached) ────────────────────────────────────────
export async function getUserProfile(uid) {
  const key = `up_${uid}`;
  const hit = cacheGet(key); if (hit) return hit;
  const snap = await getDoc(doc(db, "users", uid));
  const val = snap.exists() ? { id: snap.id, ...snap.data() } : null;
  if (val) cacheSet(key, val);
  return val;
}
export async function getEmployeeProfile(uid) {
  const key = `ep_${uid}`;
  const hit = cacheGet(key); if (hit) return hit;
  const snap = await getDoc(doc(db, "employees", uid));
  const val = snap.exists() ? { id: snap.id, ...snap.data() } : null;
  if (val) cacheSet(key, val);
  return val;
}
export async function updateUserProfile(uid, data) {
  cacheSet(`up_${uid}`, null);
  return updateDoc(doc(db, "users", uid), data);
}

// ── Settings ──────────────────────────────────────────────────────────────
export async function getSettings() {
  const snap = await getDoc(doc(db, "settings", "shop"));
  return snap.exists() ? snap.data() : {};
}
export async function saveSettings(data) {
  const { setDoc } = await import('https://www.gstatic.com/firebasejs/10.12.0/firebase-firestore.js');
  return setDoc(doc(db, "settings", "shop"), data, { merge: true });
}

// ── Services ──────────────────────────────────────────────────────────────
export async function getServices(activeOnly = false) {
  const snap = await getDocs(collection(db, "services"));
  const all = snap.docs.map(d => ({ id: d.id, ...d.data() }));
  if (!activeOnly) return all;
  // Accept both is_active===1 (number) and is_active===true (boolean)
  return all.filter(s => s.is_active === 1 || s.is_active === true);
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
  let q = activeOnly
    ? query(collection(db, "employees"), where("is_active", "==", 1))
    : collection(db, "employees");
  const snap = await getDocs(q);
  return snap.docs.map(d => ({ id: d.id, ...d.data() }));
}
export async function createEmployee(data) {
  return addDoc(collection(db, "employees"), { ...data, created_at: serverTimestamp() });
}
export async function updateEmployee(id, data) { return updateDoc(doc(db, "employees", id), data); }
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
  const q = query(collection(db, "offers"), where("is_active", "==", 1));
  const snap = await getDocs(q);
  return snap.docs.map(d => ({ id: d.id, ...d.data() }))
    .filter(o => (!o.valid_from || o.valid_from <= today) && (!o.valid_until || o.valid_until >= today));
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
  const snap = await getDocs(collection(db, "gallery"));
  return snap.docs.map(d => ({ id: d.id, ...d.data() }));
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
  return addDoc(collection(db, "payroll"), { ...data, created_at: serverTimestamp() });
}

// ── Utilities ─────────────────────────────────────────────────────────────
export function today() { return new Date().toISOString().slice(0, 10); }

export function to12hr(t) {
  if (!t) return "—";
  const [h, m] = t.split(":").map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
}

export function showToast(msg, type = "success") {
  const colors = { success: "#25d366", danger: "#ff6b6b", warning: "#ffc107", info: "#63b3ff" };
  const icons  = { success: "fa-check-circle", danger: "fa-times-circle", warning: "fa-exclamation-triangle", info: "fa-info-circle" };
  const t = document.createElement("div");
  t.style.cssText = `position:fixed;top:24px;right:24px;z-index:99999;display:flex;align-items:center;gap:12px;
    padding:14px 20px;border-radius:14px;background:#0e0b14;border:1px solid ${colors[type]}55;
    color:#fff;font-size:0.9rem;box-shadow:0 24px 70px rgba(0,0,0,0.7);min-width:280px;max-width:380px;`;
  t.innerHTML = `<i class="fas ${icons[type]}" style="color:${colors[type]};font-size:1.1rem;flex-shrink:0;"></i><span>${msg}</span>`;
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
