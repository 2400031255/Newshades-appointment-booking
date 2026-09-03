const { onCall, HttpsError } = require("firebase-functions/v2/https");
const { initializeApp } = require("firebase-admin/app");
const { getAuth } = require("firebase-admin/auth");
const { getFirestore } = require("firebase-admin/firestore");

initializeApp();

exports.deleteEmployeeAccount = onCall(async (request) => {
  if (!request.auth) throw new HttpsError("unauthenticated", "Not signed in.");

  const callerUid = request.auth.uid;
  const db = getFirestore();
  const callerDoc = await db.collection("users").doc(callerUid).get();
  if (!callerDoc.exists || !callerDoc.data().is_admin) {
    throw new HttpsError("permission-denied", "Admins only.");
  }

  const { uid } = request.data;
  if (!uid) throw new HttpsError("invalid-argument", "uid is required.");

  // Delete Auth user and Firestore doc atomically
  await getAuth().deleteUser(uid);
  await db.collection("employees").doc(uid).delete();
  return { success: true };
});
