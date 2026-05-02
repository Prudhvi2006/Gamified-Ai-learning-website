# Firebase Setup Guide for GAL Platform

## Overview
The GAL platform now supports Firebase Realtime Database for real-time data synchronization across both client and server.

---

## Frontend Setup (index.html & dashboard.html)

### 1. Get Firebase Config
1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Create a new project or select existing
3. Enable **Realtime Database** (start in test mode)
4. Copy your Firebase config values

### 2. Update Frontend Config
In both `index.html` and `dashboard.html`, find:
```javascript
const FIREBASE_CONFIG = {
  apiKey: "YOUR_API_KEY",
  authDomain: "YOUR_PROJECT.firebaseapp.com",
  databaseURL: "https://YOUR_PROJECT.firebaseio.com",
  projectId: "YOUR_PROJECT_ID",
  storageBucket: "YOUR_PROJECT.appspot.com",
  messagingSenderId: "YOUR_MESSAGING_SENDER_ID",
  appId: "YOUR_APP_ID"
};
```

Replace with your actual Firebase project credentials.

---

## Backend Setup (app.py)

### 1. Install Firebase Admin SDK
```bash
pip install firebase-admin
```

### 2. Get Service Account Key
1. In Firebase Console → Project Settings → Service Accounts
2. Click "Generate New Private Key"
3. Save as `serviceAccountKey.json` in your project root (same folder as `app.py`)

### 3. Set Environment Variables
Option A: Create a `.env` file in the project root:
```
FIREBASE_CRED_PATH=serviceAccountKey.json
FIREBASE_DB_URL=https://YOUR_PROJECT.firebaseio.com
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/gal
MONGODB_DB=gal
```

Option B: Set system environment variables:
```bash
# PowerShell
$env:FIREBASE_CRED_PATH="serviceAccountKey.json"
$env:FIREBASE_DB_URL="https://YOUR_PROJECT.firebaseio.com"
```

### 4. Verify Firebase Connection
Start the Flask app—look for:
```
Firebase Admin SDK initialized
```

If you see:
```
Firebase not available: No module named 'firebase_admin'
```

Install the package: `pip install firebase-admin`

---

## Firebase Realtime Database Rules

### Development (Test Mode)
```json
{
  "rules": {
    ".read": true,
    ".write": true
  }
}
```

### Production (Recommended)
```json
{
  "rules": {
    "gal": {
      "users": {
        "$uid": {
          ".read": "$uid === auth.uid || root.child('admin').child(auth.uid).exists()",
          ".write": "$uid === auth.uid"
        }
      },
      "leaderboard": {
        ".read": true,
        "$uid": {
          ".write": "root.child('gal/users').child($uid).exists()"
        }
      }
    }
  }
}
```

---

## Features Enabled

✅ **Frontend**
- User registration/login syncs to Firebase
- Profile data writes to Firebase in real-time
- Leaderboard watches Firebase for live updates

✅ **Backend**
- `/api/register` and `/api/login` write users to Firebase
- `/api/update_stats` syncs stats to Firebase leaderboard
- `/api/leaderboard` fetches from Firebase (fallback to local DB)

---

## Fallback Behavior

If Firebase is not configured:
- App continues to use **MongoDB** (if MONGODB_URI set) or **local JSON** (data/db.json)
- No realtime sync, but everything still works
- Safe to deploy without Firebase

---

## Database Structure

### Users Path
```
gal/users/{uid}
  ├─ uid
  ├─ name
  ├─ email
  ├─ level
  ├─ score
  ├─ xp
  ├─ streak
  └─ updated (timestamp)
```

### Leaderboard Path
```
gal/leaderboard/{uid}
  ├─ uid
  ├─ name
  ├─ score
  ├─ level
  ├─ rooms_cleared
  └─ updated (timestamp)
```

---

## Troubleshooting

### "Firebase not available: No module named 'firebase_admin'"
```bash
pip install firebase-admin
pip install python-dotenv  # Optional: for .env support
```

### "Certificate file not found"
Ensure `serviceAccountKey.json` is in the project root, or set:
```bash
export FIREBASE_CRED_PATH="path/to/serviceAccountKey.json"
```

### "Permission denied" on Firebase writes
Check your Realtime Database rules (see above for recommended rules).

### Frontend not updating in real-time
1. Verify `FIREBASE_CONFIG.databaseURL` is correct
2. Check browser console for Firebase errors
3. Ensure Firebase Realtime Database is enabled in console

---

## Next Steps

1. ✅ Update `FIREBASE_CONFIG` in `index.html` and `dashboard.html`
2. ✅ Download `serviceAccountKey.json` from Firebase
3. ✅ Set environment variables or `.env` file
4. ✅ Install `firebase-admin`: `pip install firebase-admin`
5. ✅ Restart Flask app: `python app.py`
6. ✅ Test registration/login at `http://localhost:5050`

Leaderboard updates should now sync in real-time across all connected clients! 🚀
