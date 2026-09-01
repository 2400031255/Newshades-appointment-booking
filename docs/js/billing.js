// billing.js — Advanced Billing System for Newshades Family Salon
import { db } from './firebase.js';
import {
  collection, doc, addDoc, getDoc, getDocs,
  updateDoc, deleteDoc, query, where, orderBy, serverTimestamp
} from 'https://www.gstatic.com/firebasejs/10.12.0/firebase-firestore.js';

// ── Bills ─────────────────────────────────────────────────────────────────
export async function createBill(data) {
  return addDoc(collection(db, 'bills'), { ...data, created_at: serverTimestamp() });
}
export async function getBill(id) {
  const snap = await getDoc(doc(db, 'bills', id));
  return snap.exists() ? { id: snap.id, ...snap.data() } : null;
}
export async function getAllBills() {
  try {
    const snap = await getDocs(query(collection(db, 'bills'), orderBy('created_at', 'desc')));
    return snap.docs.map(d => ({ id: d.id, ...d.data() }));
  } catch {
    const snap = await getDocs(collection(db, 'bills'));
    return snap.docs.map(d => ({ id: d.id, ...d.data() })).sort((a,b)=>(b.date||'').localeCompare(a.date||''));
  }
}
export async function getBillsByDate(from, to) {
  const all = await getAllBills();
  return all.filter(b => (!from || b.date >= from) && (!to || b.date <= to));
}
export async function deleteBill(id) {
  return deleteDoc(doc(db, 'bills', id));
}
export async function updateBill(id, data) {
  return updateDoc(doc(db, 'bills', id), data);
}

// ── Billing Services (reads from main 'services' collection) ─────────────
export async function getBillingServices(activeOnly = false) {
  const snap = await getDocs(collection(db, 'services'));
  const all = snap.docs.map(d => ({ id: d.id, ...d.data() }));
  if (!activeOnly) return all;
  return all.filter(s => s.is_active === true || s.is_active === 1 || s.is_active == null);
}
export async function createBillingService(data) {
  return addDoc(collection(db, 'services'), { ...data, created_at: serverTimestamp() });
}
export async function updateBillingService(id, data) {
  return updateDoc(doc(db, 'services', id), data);
}
export async function deleteBillingService(id) {
  return deleteDoc(doc(db, 'services', id));
}

// ── Billing Customers ─────────────────────────────────────────────────────
export async function getBillingCustomers() {
  const snap = await getDocs(collection(db, 'billing_customers'));
  return snap.docs.map(d => ({ id: d.id, ...d.data() }));
}
export async function findCustomerByPhone(phone) {
  const q = query(collection(db, 'billing_customers'), where('phone', '==', phone));
  const snap = await getDocs(q);
  return snap.empty ? null : { id: snap.docs[0].id, ...snap.docs[0].data() };
}
export async function createBillingCustomer(data) {
  return addDoc(collection(db, 'billing_customers'), {
    ...data, visit_count: 0, total_spent: 0, created_at: serverTimestamp()
  });
}
export async function updateBillingCustomer(id, data) {
  return updateDoc(doc(db, 'billing_customers', id), data);
}
export async function deleteBillingCustomer(id) {
  return deleteDoc(doc(db, 'billing_customers', id));
}

// ── Coupons ───────────────────────────────────────────────────────────────
export async function getAllCoupons() {
  const snap = await getDocs(collection(db, 'coupons'));
  return snap.docs.map(d => ({ id: d.id, ...d.data() }));
}
export async function findCoupon(code) {
  const q = query(collection(db, 'coupons'), where('code', '==', code.toUpperCase()));
  const snap = await getDocs(q);
  if (snap.empty) return null;
  const c = { id: snap.docs[0].id, ...snap.docs[0].data() };
  const today = new Date().toISOString().slice(0,10);
  if (!c.is_active) return null;
  if (c.valid_until && c.valid_until < today) return null;
  if (c.usage_limit && (c.used_count || 0) >= c.usage_limit) return null;
  return c;
}
export async function createCoupon(data) {
  return addDoc(collection(db, 'coupons'), {
    ...data, code: data.code.toUpperCase(), used_count: 0, is_active: true, created_at: serverTimestamp()
  });
}
export async function updateCoupon(id, data) {
  return updateDoc(doc(db, 'coupons', id), data);
}
export async function deleteCoupon(id) {
  return deleteDoc(doc(db, 'coupons', id));
}
export async function incrementCouponUsage(id) {
  const snap = await getDoc(doc(db, 'coupons', id));
  if (snap.exists()) {
    return updateDoc(doc(db, 'coupons', id), { used_count: (snap.data().used_count || 0) + 1 });
  }
}

// ── Analytics helpers ─────────────────────────────────────────────────────
export function calcBillAnalytics(bills) {
  const today = new Date().toISOString().slice(0,10);
  const month = today.slice(0,7);
  const week  = (() => { const d = new Date(); d.setDate(d.getDate()-6); return d.toISOString().slice(0,10); })();

  const todayBills  = bills.filter(b => b.date === today);
  const monthBills  = bills.filter(b => (b.date||'').startsWith(month));
  const weekBills   = bills.filter(b => b.date >= week);

  const sum = arr => arr.reduce((s,b) => s + (b.total||0), 0);

  // Payment breakdown
  const payMap = {};
  bills.forEach(b => { payMap[b.payment] = (payMap[b.payment]||0) + (b.total||0); });

  // Top services
  const svcMap = {};
  bills.forEach(b => (b.items||[]).forEach(i => {
    if (!svcMap[i.name]) svcMap[i.name] = { count: 0, revenue: 0 };
    svcMap[i.name].count   += i.qty || 1;
    svcMap[i.name].revenue += (i.price||0) * (i.qty||1);
  }));
  const topServices = Object.entries(svcMap).sort((a,b)=>b[1].count-a[1].count).slice(0,8);

  // Daily revenue for last 14 days
  const dailyMap = {};
  for (let i=13; i>=0; i--) {
    const d = new Date(); d.setDate(d.getDate()-i);
    dailyMap[d.toISOString().slice(0,10)] = 0;
  }
  bills.forEach(b => { if (dailyMap[b.date] !== undefined) dailyMap[b.date] += (b.total||0); });

  // GST collected
  const gstTotal = bills.reduce((s,b) => s + (b.gst_amount||0), 0);

  return {
    todayRev: sum(todayBills), todayCount: todayBills.length,
    monthRev: sum(monthBills), monthCount: monthBills.length,
    weekRev:  sum(weekBills),  weekCount:  weekBills.length,
    totalRev: sum(bills),      totalCount: bills.length,
    payMap, topServices, dailyMap, gstTotal,
    avgBill: bills.length ? Math.round(sum(bills)/bills.length) : 0
  };
}

// ── GST calculation ───────────────────────────────────────────────────────
export function calcGST(amount, gstPct = 18) {
  const gst = Math.round(amount * gstPct / 100);
  return { base: amount, gst_amount: gst, total: amount + gst, gst_pct: gstPct };
}

// ── Bill number generator ─────────────────────────────────────────────────
export function generateBillNo(id, date) {
  const yr = date ? String(date).slice(2,4) : new Date().getFullYear().toString().slice(-2);
  return 'NS' + yr + id.slice(-6).toUpperCase();
}
