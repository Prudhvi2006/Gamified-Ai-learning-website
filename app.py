"""
GAL — Gamified AI Learning Platform
Flask Backend API — FIXED VERSION
"""
from flask import Flask, request, jsonify, send_from_directory
import json, os, time, hashlib, secrets, re
from datetime import datetime

# Firebase Admin SDK (optional)
fb_enabled = False
fb_db = None
try:
    import firebase_admin
    from firebase_admin import db
    firebase_cred_path = os.environ.get('FIREBASE_CRED_PATH', 'serviceAccountKey.json')
    if os.path.exists(firebase_cred_path):
        firebase_admin.initialize_app(
            firebase_admin.credentials.Certificate(firebase_cred_path),
            {'databaseURL': os.environ.get('FIREBASE_DB_URL', '')}
        )
        fb_db = db
        fb_enabled = True
        print('Firebase Admin SDK initialized')
except Exception as e:
    print('Firebase not available:', e)

# ── Serve static files from the SAME folder as app.py ──────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=BASE_DIR, static_url_path='')
app.secret_key = secrets.token_hex(32)

DB_PATH = os.path.join(BASE_DIR, 'data', 'db.json')
MONGODB_URI = os.environ.get('MONGODB_URI', '').strip()
MONGODB_DB = os.environ.get('MONGODB_DB', 'gal')

mongo_client = None
users_col = None
sessions_col = None
leaderboard_col = None

if MONGODB_URI:
    try:
        from pymongo import MongoClient
        mongo_client = MongoClient(MONGODB_URI)
        mongo_db = mongo_client[MONGODB_DB]
        users_col = mongo_db['users']
        sessions_col = mongo_db['sessions']
        leaderboard_col = mongo_db['leaderboard']
        users_col.create_index('email', unique=True)
        sessions_col.create_index('_id', unique=True)
        leaderboard_col.create_index('_id', unique=True)
        print('MongoDB connected:', MONGODB_URI)
    except Exception as e:
        print('Warning: Could not connect to MongoDB:', e)
        mongo_client = None

# ── DB helpers ───────────────────────────────────────────────────
def _use_mongo():
    return mongo_client is not None


def dictify(doc):
    if not doc:
        return None
    d = dict(doc)
    d.pop('_id', None)
    return d


def load_db():
    if not os.path.exists(DB_PATH):
        return {'users': {}, 'sessions': {}, 'leaderboard': []}
    try:
        with open(DB_PATH) as f:
            return json.load(f)
    except Exception:
        return {'users': {}, 'sessions': {}, 'leaderboard': []}


def save_db(db):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with open(DB_PATH, 'w') as f:
        json.dump(db, f, indent=2)


def hash_pass(p):
    return hashlib.sha256(p.encode()).hexdigest()


def find_user(email):
    if _use_mongo():
        return dictify(users_col.find_one({'email': email}))
    db = load_db()
    return db['users'].get(email)


def save_user(user):
    if _use_mongo():
        users_col.replace_one({'email': user['email']}, user, upsert=True)
        return
    db = load_db()
    db['users'][user['email']] = user
    save_db(db)


def find_session(token):
    if _use_mongo():
        return dictify(sessions_col.find_one({'_id': token}))
    db = load_db()
    return db['sessions'].get(token)


def save_session(token, email):
    if _use_mongo():
        sessions_col.replace_one({'_id': token}, {'email': email, 'ts': int(time.time())}, upsert=True)
        return
    db = load_db()
    db['sessions'][token] = {'email': email, 'ts': int(time.time())}
    save_db(db)


def all_users():
    if _use_mongo():
        return [dictify(u) for u in users_col.find()]
    db = load_db()
    return list(db['users'].values())


def get_leaderboard_entries(limit=20):
    if _use_mongo():
        return [dictify(e) for e in leaderboard_col.find().sort('score', -1).limit(limit)]
    db = load_db()
    return db.get('leaderboard', [])[:limit]


def save_leaderboard_entry(entry):
    if _use_mongo():
        leaderboard_col.replace_one({'_id': entry['uid']}, entry, upsert=True)
        _prune_leaderboard()
        return
    db = load_db()
    lb = db.setdefault('leaderboard', [])
    existing = next((e for e in lb if e.get('uid') == entry['uid']), None)
    if existing:
        existing.update(entry)
    else:
        lb.append(entry)
    lb.sort(key=lambda e: e.get('score', 0), reverse=True)
    db['leaderboard'] = lb[:100]
    save_db(db)


def _prune_leaderboard():
    if not _use_mongo():
        return
    count = leaderboard_col.count_documents({})
    if count <= 100:
        return
    extras = leaderboard_col.find().sort('score', 1).limit(count - 100)
    for doc in extras:
        leaderboard_col.delete_one({'_id': doc['_id']})

# ── FIREBASE HELPERS ─────────────────────────────────────────────
def fb_write_user(user):
    if not fb_enabled or not fb_db:
        return
    try:
        fb_db.reference(f'gal/users/{user.get("uid")}').update({
            'uid': user.get('uid'),
            'name': user.get('name'),
            'email': user.get('email'),
            'level': user.get('level', 1),
            'score': user.get('score', 0),
            'xp': user.get('xp', 0),
            'streak': user.get('streak', 0),
            'updated': int(time.time())
        })
    except Exception as e:
        print(f'Firebase write_user error: {e}')

def fb_write_leaderboard(user):
    if not fb_enabled or not fb_db:
        return
    try:
        fb_db.reference(f'gal/leaderboard/{user.get("uid")}').update({
            'uid': user.get('uid'),
            'name': user.get('name'),
            'score': user.get('score', 0),
            'level': user.get('level', 1),
            'rooms_cleared': user.get('rooms_cleared', 0),
            'updated': int(time.time())
        })
    except Exception as e:
        print(f'Firebase write_leaderboard error: {e}')

def fb_fetch_leaderboard():
    if not fb_enabled or not fb_db:
        return None
    try:
        snap = fb_db.reference('gal/leaderboard').get()
        if snap.val():
            entries = snap.val().values()
            return sorted(entries, key=lambda e: e.get('score', 0), reverse=True)[:20]
    except Exception as e:
        print(f'Firebase fetch_leaderboard error: {e}')
    return None

# ── CORS (allow all origins so browser fetches work) ────────────
@app.after_request
def add_cors(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return resp

@app.route('/api/<path:p>', methods=['OPTIONS'])
def options(p=''):
    from flask import Response
    r = Response('', 200)
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    r.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return r

# ── SERVE HTML PAGES ─────────────────────────────────────────────
@app.route('/')
@app.route('/index.html')
def index():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/dashboard.html')
def dashboard():
    return send_from_directory(BASE_DIR, 'dashboard.html')

@app.route('/hauntedmansion.html')
def game():
    return send_from_directory(BASE_DIR, 'hauntedmansion.html')

# ── REGISTER ─────────────────────────────────────────────────────
@app.route('/api/register', methods=['POST'])
def register():
    data       = request.get_json() or {}
    name       = data.get('name', '').strip()
    email      = data.get('email', '').strip().lower()
    password   = data.get('password', '')
    class_name = data.get('class_name', '').strip()
    grade      = data.get('grade', '').strip()

    if not name or not email or not password:
        return jsonify({"ok": False, "msg": "All fields required"}), 400
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({"ok": False, "msg": "Invalid email address"}), 400
    if len(password) < 8:
        return jsonify({"ok": False, "msg": "Password must be at least 8 characters"}), 400

    if find_user(email):
        return jsonify({"ok": False, "msg": "An account with this email already exists"}), 409

    uid   = 'u_' + secrets.token_hex(8)
    token = secrets.token_hex(24)
    today = datetime.now().strftime('%Y-%m-%d')

    user = {
        "uid": uid, "name": name, "email": email,
        "hash": hash_pass(password),
        "class_name": class_name, "grade": grade,
        "joined": int(time.time()),
        "xp": 250,           # Welcome bonus XP
        "level": 1,
        "streak": 1,         # First login streak
        "last_active": int(time.time()),
        "rooms_cleared": 0,
        "missions_done": 0,
        "score": 0,
        "accuracy": 0,
        "hints_used": 0,
        "best_combo": 1,
        "achievements": [],
        "activity": [{"msg": "Account created — Welcome to GAL! 🚀", "xp": 250, "ts": int(time.time()), "diff": "system"}],
        "streak_days": [today]
    }
    save_user(user)
    save_session(token, email)
    fb_write_user(user)

    return jsonify({"ok": True, "token": token, "uid": uid, "name": name})

# ── LOGIN ─────────────────────────────────────────────────────────
@app.route('/api/login', methods=['POST'])
def login():
    data     = request.get_json() or {}
    email    = data.get('email', '').strip().lower()
    password = data.get('password', '')

    user = find_user(email)
    if not user or user['hash'] != hash_pass(password):
        return jsonify({"ok": False, "msg": "Invalid email or password"}), 401

    # Issue new token
    token = secrets.token_hex(24)
    save_session(token, email)

    # Update streak on login
    today = datetime.now().strftime('%Y-%m-%d')
    days  = user.setdefault('streak_days', [])
    if today not in days:
        days.append(today)
        user['streak_days'] = sorted(days)[-60:]
        user['streak'] = _calc_streak(user['streak_days'])
        # Add login activity
        act = user.setdefault('activity', [])
        act.insert(0, {"msg": f"Daily login streak: {user['streak']} days 🔥", "xp": 0, "ts": int(time.time()), "diff": "system"})
        user['activity'] = act[:20]

    user['last_active'] = int(time.time())
    save_user(user)
    fb_write_user(user)

    return jsonify({"ok": True, "token": token, "name": user['name'], "uid": user['uid']})

def _calc_streak(days):
    if not days:
        return 0
    sorted_d = sorted(days, reverse=True)
    # Check if today or yesterday is in the list (allow 1 day gap for timezone)
    today = datetime.now().strftime('%Y-%m-%d')
    if sorted_d[0] != today:
        yesterday = datetime.fromtimestamp(time.time() - 86400).strftime('%Y-%m-%d')
        if sorted_d[0] != yesterday:
            return 1  # Streak broken, reset to 1 for today's login
    streak = 1
    for i in range(1, len(sorted_d)):
        d1 = datetime.strptime(sorted_d[i - 1], '%Y-%m-%d')
        d2 = datetime.strptime(sorted_d[i],     '%Y-%m-%d')
        if (d1 - d2).days == 1:
            streak += 1
        else:
            break
    return streak

def get_user_from_token(token):
    if not token:
        return None
    sess = find_session(token)
    if not sess:
        return None
    return find_user(sess['email'])

# ── PROFILE ───────────────────────────────────────────────────────
@app.route('/api/profile', methods=['GET'])
def profile():
    token = request.headers.get('Authorization', '').replace('Bearer ', '').strip()
    user = get_user_from_token(token)
    if not user:
        return jsonify({"ok": False, "msg": "Unauthorized"}), 401

    if _use_mongo():
        total_users = users_col.count_documents({})
        rank = users_col.count_documents({"score": {"$gt": user.get('score', 0)}}) + 1
    else:
        all_users = list(all_users())
        all_users.sort(key=lambda u: u.get('score', 0), reverse=True)
        total_users = len(all_users)
        rank = next((i + 1 for i, u in enumerate(all_users) if u['uid'] == user['uid']), 0)

    return jsonify({
        "ok":           True,
        "name":         user['name'],
        "email":        user['email'],
        "class_name":   user.get('class_name', ''),
        "grade":        user.get('grade', ''),
        "xp":           user.get('xp', 0),
        "level":        user.get('level', 1),
        "streak":       user.get('streak', 0),
        "rooms_cleared":user.get('rooms_cleared', 0),
        "missions_done":user.get('missions_done', 0),
        "score":        user.get('score', 0),
        "accuracy":     user.get('accuracy', 0),
        "hints_used":   user.get('hints_used', 0),
        "best_combo":   user.get('best_combo', 1),
        "achievements": user.get('achievements', []),
        "activity":     user.get('activity', [])[-10:],
        "streak_days":  user.get('streak_days', [])[-28:],
        "rank":         rank,
        "total_users":  len(all_users),
        "joined":       user.get('joined', 0)
    })

# ── UPDATE STATS (called after game session) ──────────────────────
@app.route('/api/update_stats', methods=['POST'])
def update_stats():
    token = request.headers.get('Authorization', '').replace('Bearer ', '').strip()
    user = get_user_from_token(token)
    if not user:
        return jsonify({"ok": False, "msg": "Unauthorized"}), 401

    data         = request.get_json() or {}
    score        = int(data.get('score', 0))
    rooms        = int(data.get('rooms_cleared', 0))
    accuracy     = float(data.get('accuracy', 0))
    hints        = int(data.get('hints_used', 0))
    combo        = int(data.get('best_combo', 1))
    difficulty   = data.get('difficulty', 'haunted')
    xp_earned    = int(data.get('xp_earned', max(score, 1)))
    activity_msg = data.get('activity_msg', f'Game session: +{xp_earned} XP, {rooms} rooms cleared')

    # Update stats
    user['xp']            = user.get('xp', 0) + xp_earned
    user['level']         = max(1, user['xp'] // 5000 + 1)
    user['score']         = max(user.get('score', 0), score)
    user['rooms_cleared'] = user.get('rooms_cleared', 0) + rooms
    user['missions_done'] = user.get('missions_done', 0) + (1 if rooms > 0 else 0)
    user['hints_used']    = user.get('hints_used', 0) + hints
    user['best_combo']    = max(user.get('best_combo', 1), combo)

    # Rolling accuracy average
    if accuracy > 0:
        old_acc  = user.get('accuracy', 0)
        sessions = max(1, user.get('missions_done', 1))
        user['accuracy'] = round((old_acc * (sessions - 1) + accuracy) / sessions, 1)

    # Activity log
    act = user.setdefault('activity', [])
    act.insert(0, {
        "msg":  activity_msg,
        "xp":   xp_earned,
        "ts":   int(time.time()),
        "diff": difficulty
    })
    user['activity'] = act[:20]

    # Streak
    today = datetime.now().strftime('%Y-%m-%d')
    days  = user.setdefault('streak_days', [])
    if today not in days:
        days.append(today)
        user['streak_days'] = sorted(days)[-60:]
        user['streak'] = _calc_streak(user['streak_days'])

    save_user(user)

    entry = {
        "uid":        user['uid'],
        "name":       user['name'],
        "score":      user['score'],
        "level":      user['level'],
        "difficulty": difficulty,
        "rooms":      user['rooms_cleared'],
        "date":       datetime.now().strftime('%Y-%m-%d')
    }
    save_leaderboard_entry(entry)
    fb_write_user(user)
    fb_write_leaderboard(user)

    return jsonify({"ok": True, "xp": user['xp'], "level": user['level']})

# ── LEADERBOARD ───────────────────────────────────────────────────
@app.route('/api/leaderboard', methods=['GET'])
def leaderboard():
    if fb_enabled:
        fb_lb = fb_fetch_leaderboard()
        if fb_lb:
            return jsonify({"ok": True, "leaderboard": fb_lb})
    lb = get_leaderboard_entries(20)
    return jsonify({"ok": True, "leaderboard": lb})

if __name__ == '__main__':
    print("\n" + "=" * 52)
    print("  GAL — Gamified AI Learning Platform")
    print("  ► http://localhost:5050")
    print("=" * 52 + "\n")
    print("  Put all HTML files in the SAME folder as app.py")
    print("  then open: http://localhost:5050\n")
    app.run(debug=True, port=5050, host='0.0.0.0')