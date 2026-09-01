// billing.js — Firestore helpers for billing system
import { db } from './firebase.js';
import {
  collection, doc, addDoc, getDoc, getDocs,
  updateDoc, deleteDoc, query, where, orderBy, serverTimestamp
} from 'https://www.gstatic.com/firebasejs/10.12.0/firebase-firestore.js';

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
    return snap.docs.map(d => ({ id: d.id, ...d.data() }));
  }
}

export async function deleteBill(id) {
  return deleteDoc(doc(db, 'bills', id));
}

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
  return addDoc(collection(db, 'billing_customers'), { ...data, visit_count: 0, created_at: serverTimestamp() });
}

export async function updateBillingCustomer(id, data) {
  return updateDoc(doc(db, 'billing_customers', id), data);
}

export async function deleteBillingCustomer(id) {
  return deleteDoc(doc(db, 'billing_customers', id));
}
