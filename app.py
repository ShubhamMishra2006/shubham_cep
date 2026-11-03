from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash, abort, Response, stream_with_context
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from google import genai
from google.genai import types
import sqlite3
import os
from dotenv import load_dotenv
import time # Added for time-based access control
import smtplib
from email.mime.text import MIMEText
import random
import json  # Required for storing floor lists in the database
import uuid  # Add this to your imports at the very top

# Load environment variables from the .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = 'pune_smart_hospital_network_secret_key'

# --- SECURITY: PREVENT BROWSER CACHING ---
@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# --- EMAIL CONFIGURATION ---
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_EMAIL = "academicuse20@gmail.com" 
SMTP_PASSWORD = "ipsbxeigfnrwwavw"

def send_system_email(to_email, subject, body):
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = f"PICT Hospital Mainframe <{SMTP_EMAIL}>"
        msg['To'] = to_email
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        server.quit()
    except Exception as e:
        print("\n" + "="*50)
        print(f"FAILED TO SEND EMAIL (Check SMTP settings).")
        print("="*50 + "\n")

socketio = SocketIO(app, cors_allowed_origins="*")
DB_FILE = 'hospital_network.db'

HOSPITALS_SEED = [
    {
        "id": "manipal-baner",
        "name": "Manipal Hospitals Baner",
        "area": "Baner - Mahalunge Rd",
        "rating": "4.7",
        "contact": "+91 20 6813 8888",
        "image": "static/manipal.jpg",
        "specialties": "Cardiology, Oncology, Neurosurgery, Renal Care"
    },
    {
        "id": "ruby-sasoon",
        "name": "Ruby Hall Clinic (Sasoon Road)",
        "area": "Sasoon Rd, Sangamvadi",
        "rating": "4.5",
        "contact": "+91 20 6645 5100",
        "image": "static/ruby hall sasoon.jpg",
        "specialties": "Quaternary Care, ICU, Cardiology, Organ Transplant"
    },
    {
        "id": "ruby-pcmc",
        "name": "Ruby Hall Clinic PCMC",
        "area": "Pimple Saudagar",
        "rating": "3.7",
        "contact": "+91 20 2720 1717",
        "image": "static/ruby hall pcmc.jpg",
        "specialties": "Outpatient Care, Day-Care Surgeries, Diagnostics"
    },
    {
        "id": "aditya-birla",
        "name": "Aditya Birla Memorial Hospital",
        "area": "Chinchwad, PCMC",
        "rating": "4.3",
        "contact": "+91 98811 23006",
        "image": "static/Aditya Birla Memorial Hospital.png",
        "specialties": "Tertiary Care, Oncology, High-Capacity ICU"
    },
    {
        "id": "sancheti",
        "name": "Sancheti Hospital",
        "area": "Shivajinagar",
        "rating": "4.6",
        "contact": "+91 88888 08845",
        "image": "static/Sancheti Hospital.jpg",
        "specialties": "Orthopaedics, Joint Replacement, Spine, Trauma"
    },
    {
        "id": "sahyadri-deccan",
        "name": "Sahyadri Super Speciality Hospital",
        "area": "Deccan Gymkhana",
        "rating": "4.7",
        "contact": "+91 20 4713 8766",
        "image": "static/Sahyadri Super Speciality Hospital.avif",
        "specialties": "Neurosciences, Organ Transplants, Critical Care"
    },
    {
        "id": "apollo-swargate",
        "name": "Apollo Hospitals (Swargate)",
        "area": "Shankar Sheth Rd, Swargate",
        "rating": "4.6",
        "contact": "+91 80 6297 2814",
        "image": "static/Apollo Hospitals (Swargate).jpg",
        "specialties": "Quaternary Care, Robotic Surgery, Neuro-ICU"
    },
    {
        "id": "apollo-spectra",
        "name": "Apollo Spectra Hospitals",
        "area": "Sadashiv Peth",
        "rating": "4.6",
        "contact": "+91 40 6914 6071",
        "image": "https://images.unsplash.com/photo-1519494026892-80bbd2d6fd0d?q=80&w=800&auto=format&fit=crop",
        "specialties": "Short-Stay Surgeries, General Medicine, ENT"
    },
    {
        "id": "sassoon-general",
        "name": "Sassoon General Hospital",
        "area": "Near Pune Station",
        "rating": "4.2",
        "contact": "+91 20 2612 8000",
        "image": "static/SASOON HOSPITAL.png",
        "specialties": "Government Facility, General Surgery, Trauma Care, Pediatrics"
    },
    {
        "id": "kamla-nehru",
        "name": "Kamala Nehru Hospital",
        "area": "Mangalwar Peth",
        "rating": "4.0",
        "contact": "+91 20 2550 1423",
        "image": "static/Kamla nehru hospital.jpg",
        "specialties": "Maternity Care, General Medicine, PMC Hospital, Pediatrics"
    }
]

def get_db_connection():
    db_path = os.path.join("/tmp", "my_database.db")
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# --- NEW: TIME-BASED ACCESS HELPER ---
def get_active_floors(assigned_floors_json):
    """
    Parses assigned floors JSON and filters out any floors whose time has expired.
    Automatically migrates legacy array formats to dictionary format.
    Returns: dict { "floor_num": expiry_timestamp }
    """
    if not assigned_floors_json:
        return {}
    
    try:
        floors_data = json.loads(assigned_floors_json)
    except:
        return {}

    # Handle legacy array format (e.g. ["1", "2"]) -> convert to permanent dict format
    if isinstance(floors_data, list):
        return {str(f): -1 for f in floors_data}
    
    active_floors = {}
    current_time = time.time()
    
    for floor, expiry in floors_data.items():
        # -1 means permanent access. Otherwise, verify timestamp hasn't elapsed.
        if expiry == -1 or expiry > current_time:
            active_floors[floor] = expiry
            
    return active_floors

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hospitals (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            area TEXT NOT NULL,
            rating TEXT,
            contact TEXT,
            image TEXT,
            specialties TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS staff (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hospital_id TEXT NOT NULL,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            name TEXT,
            email TEXT,
            staff_id TEXT,
            status TEXT DEFAULT 'pending',
            assigned_floors TEXT DEFAULT '{}',
            UNIQUE(hospital_id, username),
            FOREIGN KEY (hospital_id) REFERENCES hospitals(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS beds (
            hospital_id TEXT NOT NULL,
            bed_id TEXT NOT NULL,
            floor_num TEXT,
            floor_name TEXT,
            bed_type TEXT,
            status TEXT,
            patient_name TEXT,
            patient_age TEXT,
            diagnosis TEXT,
            PRIMARY KEY (hospital_id, bed_id),
            FOREIGN KEY (hospital_id) REFERENCES hospitals(id)
        )
    ''')
    
    for h in HOSPITALS_SEED:
        cursor.execute('''
            INSERT OR REPLACE INTO hospitals (id, name, area, rating, contact, image, specialties)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (h['id'], h['name'], h['area'], h['rating'], h['contact'], h['image'], h['specialties']))
        
        hashed_pw = generate_password_hash('password123')
        cursor.execute('''
            INSERT OR IGNORE INTO staff (hospital_id, username, password, name, email, staff_id, status, assigned_floors)
            VALUES (?, 'admin', ?, 'Chief Nursing Officer', ?, 'ADMIN-001', 'approved', '{}')
        ''', (h['id'], hashed_pw, f"admin@{h['id']}.hospital.in"))
        
        cursor.execute('SELECT COUNT(*) FROM beds WHERE hospital_id = ?', (h['id'],))
        if cursor.fetchone()[0] == 0:
            sample_beds = [
                (h['id'], '101', '1', '1st Floor - Intensive Care', 'Ventilator', 'Available', '', '', ''),
                (h['id'], '102', '1', '1st Floor - Intensive Care', 'Oxygen Bed', 'Occupied', 'Ramesh P.', '58', 'Acute Respiratory'),
                (h['id'], '201', '2', '2nd Floor - General Ward', 'General Bed', 'Available', '', '', ''),
                (h['id'], '202', '2', '2nd Floor - General Ward', 'General Bed', 'Cleaning', '', '', '')
            ]
            cursor.executemany('''
                INSERT INTO beds (hospital_id, bed_id, floor_num, floor_name, bed_type, status, patient_name, patient_age, diagnosis)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', sample_beds)
            
    conn.commit()
    conn.close()

init_db()

# --- HELPER ---
def get_hospital_or_404(hospital_id):
    conn = get_db_connection()
    h = conn.execute('SELECT * FROM hospitals WHERE id = ?', (hospital_id,)).fetchone()
    conn.close()
    if not h:
        abort(404, description="Hospital not found.")
    return dict(h)

# --- ROUTES ---
@app.route('/')
def home():
    conn = get_db_connection()
    hospitals = conn.execute('SELECT * FROM hospitals').fetchall()
    
    h_list = []
    for h in hospitals:
        h_dict = dict(h)
        stats = conn.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'Available' THEN 1 ELSE 0 END) as avail,
                SUM(CASE WHEN status = 'Occupied' THEN 1 ELSE 0 END) as occ
            FROM beds WHERE hospital_id = ?
        ''', (h['id'],)).fetchone()
        
        h_dict['total_beds'] = stats['total'] or 0
        h_dict['avail_beds'] = stats['avail'] or 0
        h_dict['occ_beds'] = stats['occ'] or 0
        h_list.append(h_dict)
        
    conn.close()
    return render_template('index.html', hospitals=h_list)

@app.route('/hospital/<hospital_id>/login', methods=['GET', 'POST'])
def hospital_login(hospital_id):
    if session.get('logged_in') and session.get('hospital_id') == hospital_id:
        return redirect(url_for('hospital_nursing', hospital_id=hospital_id))

    hospital = get_hospital_or_404(hospital_id)
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM staff WHERE hospital_id = ? AND username = ?', (hospital_id, username)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            if user['status'] == 'pending':
                flash('Your account is currently pending verification by hospital administration.', 'error')
                return render_template('login.html', hospital=hospital, show_otp=False, show_reset_otp=False)
            elif user['status'] == 'revoked':
                flash('Your account access has been suspended. Please contact the administrator.', 'error')
                return render_template('login.html', hospital=hospital, show_otp=False, show_reset_otp=False)
                
            session['logged_in'] = True
            session['hospital_id'] = hospital_id
            session['username'] = username
            return redirect(url_for('hospital_nursing', hospital_id=hospital_id))
        else:
            flash('Invalid credentials. Please try again.', 'error')
            
    return render_template('login.html', hospital=hospital, show_otp=False, show_reset_otp=False)

@app.route('/hospital/<hospital_id>/register', methods=['POST'])
def hospital_register(hospital_id):
    hospital = get_hospital_or_404(hospital_id)
    name = request.form.get('name')
    email = request.form.get('email')
    staff_id = request.form.get('staff_id') 
    username = request.form.get('username')
    password = request.form.get('password')
    
    session['reg_data'] = {
        'hospital_id': hospital_id,
        'name': name,
        'email': email,
        'staff_id': staff_id,
        'username': username,
        'password': generate_password_hash(password)
    }
    
    otp = str(random.randint(100000, 999999))
    session['otp'] = otp
    
    email_body = f"Hello {name},\n\nYour OTP for registering a staff account at {hospital_id} is: {otp}\n\nNote: After verification, your account will require administrative approval before you can log in."
    send_system_email(email, "Verification OTP - Hospital Mainframe", email_body)
    
    flash('An OTP has been sent to your email address.', 'success')
    return render_template('login.html', hospital=hospital, show_otp=True, show_reset_otp=False)

@app.route('/hospital/<hospital_id>/verify_otp', methods=['POST'])
def verify_otp(hospital_id):
    user_otp = request.form.get('otp_code')
    
    if 'otp' in session and user_otp == session['otp']:
        reg_data = session['reg_data']
        conn = get_db_connection()
        try:
            conn.execute('''
                INSERT INTO staff (hospital_id, username, password, name, email, staff_id, status, assigned_floors)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', '{}')
            ''', (reg_data['hospital_id'], reg_data['username'], reg_data['password'], reg_data['name'], reg_data['email'], reg_data['staff_id']))
            conn.commit()
            flash('Email verified! Your account is now PENDING administrative approval.', 'success')
        except sqlite3.IntegrityError:
            flash(f'Username "{reg_data["username"]}" is already registered.', 'error')
        finally:
            conn.close()
            
        session.pop('otp', None)
        session.pop('reg_data', None)
        
        hospital = get_hospital_or_404(hospital_id)
        return render_template('login.html', hospital=hospital, show_otp=False, show_reset_otp=False)
    else:
        flash('Invalid OTP Code. Please try again.', 'error')
        hospital = get_hospital_or_404(hospital_id)
        return render_template('login.html', hospital=hospital, show_otp=True, show_reset_otp=False)

@app.route('/hospital/<hospital_id>/admin/login', methods=['GET', 'POST'])
def admin_login(hospital_id):
    if session.get('admin_logged_in') and session.get('admin_hospital_id') == hospital_id:
        return redirect(url_for('hospital_admin', hospital_id=hospital_id))

    hospital = get_hospital_or_404(hospital_id)
    
    if request.method == 'POST':
        admin_id = request.form.get('admin_id')
        password = request.form.get('password')
        captcha_id = request.form.get('captcha_id')
        captcha_input = request.form.get('captcha', '').strip()
        
        session_key = f'captcha_ans_{captcha_id}'
        stored_captcha = session.get(session_key)
        
        if not captcha_input or not stored_captcha or captcha_input != stored_captcha:
            flash('Incorrect Security CAPTCHA. Please try again.', 'error')
            return redirect(url_for('admin_login', hospital_id=hospital_id))
            
        if admin_id == 'admin' and password == 'admin123':
            session['admin_logged_in'] = True
            session['admin_hospital_id'] = hospital_id
            session.pop(session_key, None) 
            return redirect(url_for('hospital_admin', hospital_id=hospital_id))
        else:
            flash('Access Denied: Invalid Admin ID or Password.', 'error')
            return redirect(url_for('admin_login', hospital_id=hospital_id))

    num1 = random.randint(1, 9)
    num2 = random.randint(1, 9)
    captcha_id = str(uuid.uuid4())
    session[f'captcha_ans_{captcha_id}'] = str(num1 + num2)
    captcha_text = f"{num1} + {num2} = ?"
    
    return render_template('admin_login.html', hospital=hospital, captcha_text=captcha_text, captcha_id=captcha_id)

@app.route('/hospital/<hospital_id>/admin/logout')
def admin_logout(hospital_id):
    session.pop('admin_logged_in', None)
    session.pop('admin_hospital_id', None)
    flash('Admin securely logged out.', 'success')
    return redirect(url_for('admin_login', hospital_id=hospital_id))

@app.route('/hospital/<hospital_id>/admin')
def hospital_admin(hospital_id):
    if not session.get('admin_logged_in') or session.get('admin_hospital_id') != hospital_id:
        flash('Restricted Area: Please log in with Administrative credentials.', 'error')
        return redirect(url_for('admin_login', hospital_id=hospital_id))
        
    hospital = get_hospital_or_404(hospital_id)
    conn = get_db_connection()
    
    stats = conn.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'Available' THEN 1 ELSE 0 END) as avail,
            SUM(CASE WHEN status = 'Occupied' THEN 1 ELSE 0 END) as occ
        FROM beds WHERE hospital_id = ?
    ''', (hospital_id,)).fetchone()
    
    pending_staff = conn.execute("SELECT * FROM staff WHERE hospital_id = ? AND status = 'pending'", (hospital_id,)).fetchall()
    
    active_staff_raw = conn.execute("SELECT * FROM staff WHERE hospital_id = ? AND status = 'approved'", (hospital_id,)).fetchall()
    active_staff = []
    for staff in active_staff_raw:
        s_dict = dict(staff)
        s_dict['assigned_floors'] = get_active_floors(s_dict['assigned_floors'])
        active_staff.append(s_dict)
        
    revoked_staff_raw = conn.execute("SELECT * FROM staff WHERE hospital_id = ? AND status = 'revoked'", (hospital_id,)).fetchall()
    revoked_staff = [dict(s) for s in revoked_staff_raw]
        
    all_beds = conn.execute("SELECT DISTINCT floor_num, floor_name FROM beds WHERE hospital_id = ? ORDER BY floor_num", (hospital_id,)).fetchall()
    all_floors = [{'floor': str(b['floor_num']), 'name': b['floor_name']} for b in all_beds]
    
    conn.close()
    
    return render_template('admin.html', hospital=hospital, stats=stats, pending_staff=pending_staff, active_staff=active_staff, revoked_staff=revoked_staff, all_floors=all_floors)

@app.route('/hospital/<hospital_id>/admin/staff/<username>/<action>', methods=['POST'])
def manage_staff(hospital_id, username, action):
    if not session.get('admin_logged_in') or session.get('admin_hospital_id') != hospital_id:
        abort(403)
        
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM staff WHERE hospital_id = ? AND username = ?", (hospital_id, username)).fetchone()
    
    if user:
        if action == 'approve':
            conn.execute("UPDATE staff SET status = 'approved' WHERE hospital_id = ? AND username = ?", (hospital_id, username))
            flash(f"Staff member {user['name']} has been approved.", "success")
            
        elif action == 'reject':
            conn.execute("DELETE FROM staff WHERE hospital_id = ? AND username = ?", (hospital_id, username))
            flash(f"Staff registration for {user['name']} was permanently removed.", "error")
            
        elif action == 'revoke':
            conn.execute("UPDATE staff SET status = 'revoked' WHERE hospital_id = ? AND username = ?", (hospital_id, username))
            flash(f"Staff account for {user['name']} has been suspended.", "success")
            
        elif action == 'restore':
            conn.execute("UPDATE staff SET status = 'approved' WHERE hospital_id = ? AND username = ?", (hospital_id, username))
            flash(f"Staff account for {user['name']} has been restored.", "success")
            
        elif action == 'assign_floors':
            # --- TIME-BASED ACCESS CONTROL LOGIC ---
            duration_type = request.form.get('access_duration', 'permanent')
            current_time = time.time()
            
            if duration_type == '8h':
                expiry = current_time + (8 * 3600)
            elif duration_type == '12h':
                expiry = current_time + (12 * 3600)
            elif duration_type == 'custom':
                try:
                    custom_hours = float(request.form.get('custom_hours', 0) or 0)
                    custom_minutes = float(request.form.get('custom_minutes', 0) or 0)
                    custom_seconds = float(request.form.get('custom_seconds', 0) or 0)
                    
                    total_seconds = (custom_hours * 3600) + (custom_minutes * 60) + custom_seconds
                    
                    if total_seconds > 0:
                        expiry = current_time + total_seconds
                    else:
                        expiry = -1 # Fallback to permanent if 0 time is entered
                except ValueError:
                    expiry = -1
            elif duration_type == 'remove':
                expiry = 0
            else:
                expiry = -1

            if duration_type == 'remove':
                new_floors = {}
            else:
                selected_floors = request.form.getlist('assigned_floors')
                new_floors = {str(f): expiry for f in selected_floors}

            conn.execute("UPDATE staff SET assigned_floors = ? WHERE hospital_id = ? AND username = ?", 
                         (json.dumps(new_floors), hospital_id, username))
            
            if duration_type != 'remove':
                flash(f"Updated floor permissions for {user['name']}.", "success")
            
        conn.commit()
    conn.close()

    # Handle AJAX Background Submissions
    if request.headers.get('Accept') == 'application/json':
        return jsonify({"success": True})
        
    return redirect(url_for('hospital_admin', hospital_id=hospital_id))

# --- NEW ROUTE: SILENT AUTO-FETCHER FOR STAFF UI ---
@app.route('/hospital/<hospital_id>/admin/api/staff_matrix')
def api_staff_matrix(hospital_id):
    if not session.get('admin_logged_in') or session.get('admin_hospital_id') != hospital_id:
        return jsonify({"error": "Unauthorized"}), 401
        
    conn = get_db_connection()
    active_staff_raw = conn.execute("SELECT username, assigned_floors FROM staff WHERE hospital_id = ? AND status = 'approved'", (hospital_id,)).fetchall()
    conn.close()
    
    staff_data = {}
    for staff in active_staff_raw:
        active_floors_dict = get_active_floors(staff['assigned_floors'])
        staff_data[staff['username']] = active_floors_dict
        
    return jsonify(staff_data)

# --- NEW ROUTE: SILENT AUTO-FETCHER FOR BED STATS ---
@app.route('/hospital/<hospital_id>/admin/api/stats')
def api_hospital_stats(hospital_id):
    if not session.get('admin_logged_in') or session.get('admin_hospital_id') != hospital_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    conn = get_db_connection()
    stats = conn.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'Available' THEN 1 ELSE 0 END) as avail,
            SUM(CASE WHEN status = 'Occupied' THEN 1 ELSE 0 END) as occ
        FROM beds WHERE hospital_id = ?
    ''', (hospital_id,)).fetchone()
    conn.close()
    
    return jsonify({
        "total": stats['total'] or 0,
        "avail": stats['avail'] or 0,
        "occ": stats['occ'] or 0
    })

@app.route('/hospital/<hospital_id>/admin/manage_floor', methods=['POST'])
def admin_manage_floor(hospital_id):
    if not session.get('admin_logged_in') or session.get('admin_hospital_id') != hospital_id:
        abort(403)
        
    action = request.form.get('action')
    conn = get_db_connection()
    
    try:
        if action == 'add':
            floor_num = request.form.get('add_floor_num', '').strip()
            floor_name = request.form.get('add_floor_name', '').strip()
            try:
                bed_count = int(request.form.get('add_bed_count', 0))
            except ValueError:
                bed_count = 0
            bed_type = request.form.get('add_bed_type', 'General Bed')
            
            if not floor_num or not floor_name or bed_count < 1:
                flash("Invalid floor details provided.", "error")
            else:
                existing_beds = conn.execute("SELECT bed_id FROM beds WHERE hospital_id = ? AND floor_num = ?", (hospital_id, floor_num)).fetchall()
                existing_ids = [b['bed_id'] for b in existing_beds if str(b['bed_id']).startswith(floor_num)]
                
                max_suffix = 0
                for eid in existing_ids:
                    suffix = str(eid)[len(floor_num):]
                    if suffix.isdigit():
                        max_suffix = max(max_suffix, int(suffix))
                        
                start_idx = max_suffix + 1
                beds_to_insert = []
                for i in range(bed_count):
                    bed_id = f"{floor_num}{(start_idx + i):02d}"
                    beds_to_insert.append((hospital_id, bed_id, floor_num, floor_name, bed_type, 'Available', '', '', ''))
                    
                conn.executemany('''
                    INSERT INTO beds (hospital_id, bed_id, floor_num, floor_name, bed_type, status, patient_name, patient_age, diagnosis)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', beds_to_insert)
                conn.commit()
                flash(f"Successfully added Floor {floor_num} ({floor_name}) with {bed_count} new beds.", "success")
                socketio.emit('system_refresh', {'hospital_id': hospital_id}, room=hospital_id)
                socketio.emit('global_network_refresh')
                
        elif action == 'edit':
            old_floor_num = request.form.get('edit_old_floor_num', '').strip()
            new_floor_num = request.form.get('edit_new_floor_num', '').strip()
            new_floor_name = request.form.get('edit_new_floor_name', '').strip()
            new_bed_type = request.form.get('edit_new_bed_type', '').strip()
            
            if not old_floor_num or not new_floor_num or not new_floor_name:
                flash("Invalid floor details provided for update.", "error")
            else:
                if old_floor_num != new_floor_num:
                    existing = conn.execute("SELECT COUNT(*) FROM beds WHERE hospital_id = ? AND floor_num = ?", (hospital_id, new_floor_num)).fetchone()[0]
                    if existing > 0:
                        flash(f"Cannot change floor number to '{new_floor_num}' because that floor already exists.", "error")
                        conn.close()
                        return redirect(url_for('hospital_admin', hospital_id=hospital_id))
                        
                    staff_members = conn.execute("SELECT username, assigned_floors FROM staff WHERE hospital_id = ?", (hospital_id,)).fetchall()
                    for staff in staff_members:
                        if staff['assigned_floors']:
                            floors_dict = get_active_floors(staff['assigned_floors'])
                            if old_floor_num in floors_dict:
                                expiry = floors_dict.pop(old_floor_num)
                                floors_dict[new_floor_num] = expiry
                                conn.execute("UPDATE staff SET assigned_floors = ? WHERE hospital_id = ? AND username = ?", (json.dumps(floors_dict), hospital_id, staff['username']))

                beds = conn.execute("SELECT bed_id FROM beds WHERE hospital_id = ? AND floor_num = ?", (hospital_id, old_floor_num)).fetchall()
                for b in beds:
                    old_id = b['bed_id']
                    new_id = old_id
                    if old_id.startswith(old_floor_num) and old_floor_num != new_floor_num:
                        new_id = new_floor_num + old_id[len(old_floor_num):]
                        
                    if new_bed_type:
                        conn.execute('UPDATE beds SET bed_id = ?, floor_num = ?, floor_name = ?, bed_type = ? WHERE hospital_id = ? AND bed_id = ?', 
                                     (new_id, new_floor_num, new_floor_name, new_bed_type, hospital_id, old_id))
                    else:
                        conn.execute('UPDATE beds SET bed_id = ?, floor_num = ?, floor_name = ? WHERE hospital_id = ? AND bed_id = ?', 
                                     (new_id, new_floor_num, new_floor_name, hospital_id, old_id))

                conn.commit()
                flash(f"Successfully updated Floor '{old_floor_num}' to Floor '{new_floor_num}' ({new_floor_name}) across all beds.", "success")
                socketio.emit('system_refresh', {'hospital_id': hospital_id}, room=hospital_id)
                socketio.emit('global_network_refresh')
                
        elif action == 'delete':
            floor_num = request.form.get('delete_floor_num', '').strip()
            if not floor_num:
                flash("Invalid floor details provided for deletion.", "error")
            else:
                conn.execute('DELETE FROM beds WHERE hospital_id = ? AND floor_num = ?', (hospital_id, floor_num))
                staff_members = conn.execute("SELECT username, assigned_floors FROM staff WHERE hospital_id = ?", (hospital_id,)).fetchall()
                for staff in staff_members:
                    if staff['assigned_floors']:
                        floors_dict = get_active_floors(staff['assigned_floors'])
                        if floor_num in floors_dict:
                            del floors_dict[floor_num]
                            conn.execute("UPDATE staff SET assigned_floors = ? WHERE hospital_id = ? AND username = ?", (json.dumps(floors_dict), hospital_id, staff['username']))
                conn.commit()
                flash(f"Successfully deleted Floor {floor_num} and all its associated beds.", "success")
                socketio.emit('system_refresh', {'hospital_id': hospital_id}, room=hospital_id)
                socketio.emit('global_network_refresh')
                
        else:
            flash("Unknown management action.", "error")
            
    except sqlite3.IntegrityError:
        flash("Database integrity error. One of the beds being generated or edited may already exist.", "error")
    except Exception as e:
        flash(f"Error modifying floor: {str(e)}", "error")
    finally:
        conn.close()
        
    return redirect(url_for('hospital_admin', hospital_id=hospital_id))

@app.route('/hospital/<hospital_id>/forgot_password_request', methods=['POST'])
def hospital_forgot_password_request(hospital_id):
    get_hospital_or_404(hospital_id)
    username = request.form.get('username')
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM staff WHERE hospital_id = ? AND username = ?', (hospital_id, username)).fetchone()
    conn.close()
    
    if user and user['email']:
        otp = str(random.randint(100000, 999999))
        session['reset_otp'] = otp
        session['reset_username'] = username
        
        email_body = f"Hello {user['name']},\n\nYour OTP for resetting your password at {hospital_id} is: {otp}\n\nIf you did not request this, please ignore this email and contact administration."
        send_system_email(user['email'], "Password Reset OTP - Hospital Mainframe", email_body)
        
        flash('An OTP has been sent to the email registered with this username.', 'success')
        hospital = get_hospital_or_404(hospital_id)
        return render_template('login.html', hospital=hospital, show_otp=False, show_reset_otp=True)
    else:
        flash(f'No account found with username "{username}" or no email registered.', 'error')
        return redirect(url_for('hospital_login', hospital_id=hospital_id))

@app.route('/hospital/<hospital_id>/forgot_password_verify', methods=['POST'])
def hospital_forgot_password_verify(hospital_id):
    user_otp = request.form.get('otp_code')
    new_password = request.form.get('new_password')
    
    if 'reset_otp' in session and user_otp == session['reset_otp']:
        username = session.get('reset_username')
        hashed_pw = generate_password_hash(new_password)
        
        conn = get_db_connection()
        conn.execute('UPDATE staff SET password = ? WHERE hospital_id = ? AND username = ?', (hashed_pw, hospital_id, username))
        conn.commit()
        conn.close()
        
        session.pop('reset_otp', None)
        session.pop('reset_username', None)
        
        flash('Password updated successfully! You can now log in with your new password.', 'success')
        return redirect(url_for('hospital_login', hospital_id=hospital_id))
    else:
        flash('Invalid OTP Code. Please request a new one or try again.', 'error')
        hospital = get_hospital_or_404(hospital_id)
        return render_template('login.html', hospital=hospital, show_otp=False, show_reset_otp=True)

@app.route('/logout')
def logout():
    h_id = session.get('hospital_id')
    session.clear()
    if h_id:
        return redirect(url_for('hospital_login', hospital_id=h_id))
    return redirect(url_for('home'))

@app.route('/hospital/<hospital_id>/nursing')
def hospital_nursing(hospital_id):
    hospital = get_hospital_or_404(hospital_id)
    
    if not session.get('logged_in') or session.get('hospital_id') != hospital_id:
        flash("You must authenticate with staff credentials for this facility.", "error")
        return redirect(url_for('hospital_login', hospital_id=hospital_id))
        
    conn = get_db_connection()
    user = conn.execute("SELECT status FROM staff WHERE hospital_id = ? AND username = ?", (hospital_id, session.get('username'))).fetchone()
    conn.close()
    
    if not user or user['status'] != 'approved':
        session.clear()
        flash("Your account access has been suspended. Please contact the administrator.", "error")
        return redirect(url_for('hospital_login', hospital_id=hospital_id))
        
    return render_template('nursing.html', hospital=hospital, username=session.get('username'))

@app.route('/hospital/<hospital_id>/counter')
def hospital_counter(hospital_id):
    hospital = get_hospital_or_404(hospital_id)
    return render_template('counter.html', hospital=hospital)

@app.route('/api/<hospital_id>/beds')
def get_hospital_beds(hospital_id):
    conn = get_db_connection()
    beds = conn.execute(
        'SELECT * FROM beds WHERE hospital_id = ? ORDER BY floor_num, bed_id',
        (hospital_id,)
    ).fetchall()
    
    is_staff = session.get('logged_in') and session.get('hospital_id') == hospital_id
    is_admin = session.get('admin_logged_in') and session.get('admin_hospital_id') == hospital_id
    username = session.get('username')
    
    allowed_floors = None
    referer = request.referrer or ""
    
    # 1. Strictly enforce staff permissions on the Nursing dashboard to prevent admin session bleed
    if '/nursing' in referer and is_staff:
        user = conn.execute('SELECT status, assigned_floors FROM staff WHERE hospital_id = ? AND username = ?', (hospital_id, username)).fetchone()
        
        if user and user['status'] == 'approved' and user['assigned_floors']:
            allowed_floors = list(get_active_floors(user['assigned_floors']).keys())
        else:
            allowed_floors = [] 
            
    # 2. Grant full access if specifically requested by an active Admin session
    elif is_admin:
        allowed_floors = None
        
    # 3. Fallback restriction for staff members hitting other endpoints (like /counter)
    elif is_staff:
        user = conn.execute('SELECT status, assigned_floors FROM staff WHERE hospital_id = ? AND username = ?', (hospital_id, username)).fetchone()
        
        if user and user['status'] == 'approved' and user['assigned_floors']:
            allowed_floors = list(get_active_floors(user['assigned_floors']).keys())
        else:
            allowed_floors = [] 

    conn.close()
    
    hospital_data = {}
    for row in beds:
        floor_num = str(row['floor_num'])
        
        if allowed_floors is not None and floor_num not in allowed_floors:
            continue
            
        if floor_num not in hospital_data:
            hospital_data[floor_num] = {"floor": floor_num, "name": row['floor_name'], "beds": []}
            
        hospital_data[floor_num]["beds"].append({
            "id": row['bed_id'],
            "type": row['bed_type'],
            "status": row['status'],
            "patient_name": row['patient_name'],
            "patient_age": row['patient_age'],
            "diagnosis": row['diagnosis']
        })
        
    return jsonify(list(hospital_data.values()))

@app.route('/api/<hospital_id>/add_bed', methods=['POST'])
def add_hospital_bed(hospital_id):
    if not session.get('logged_in') or session.get('hospital_id') != hospital_id:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
        
    username = session.get('username')
    conn = get_db_connection()
    
    user = conn.execute("SELECT status FROM staff WHERE hospital_id = ? AND username = ?", (hospital_id, username)).fetchone()
    if not user or user['status'] != 'approved':
        conn.close()
        return jsonify({"success": False, "error": "Account suspended"}), 403
        
    data = request.json
    floor_num = str(data['floor_num'])
    bed_id = str(data['bed_id'])
    
    if not bed_id.startswith(floor_num):
        conn.close()
        return jsonify({"success": False, "error": f"Invalid format: Bed ID must start with the Floor Number ({floor_num})."}), 400

    try:
        conn.execute('''
            INSERT INTO beds (hospital_id, bed_id, floor_num, floor_name, bed_type, status, patient_name, patient_age, diagnosis)
            VALUES (?, ?, ?, ?, ?, 'Available', '', '', '')
        ''', (hospital_id, bed_id, floor_num, data['floor_name'], data['bed_type']))
        
        user_db = conn.execute('SELECT assigned_floors FROM staff WHERE hospital_id = ? AND username = ?', (hospital_id, username)).fetchone()
        if user_db:
            user_floors_dict = get_active_floors(user_db['assigned_floors'])
            if floor_num not in user_floors_dict:
                user_floors_dict[floor_num] = -1
                conn.execute('UPDATE staff SET assigned_floors = ? WHERE hospital_id = ? AND username = ?', 
                             (json.dumps(user_floors_dict), hospital_id, username))
        
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    finally:
        conn.close()
    
    if success:
        socketio.emit('system_refresh', {'hospital_id': hospital_id}, room=hospital_id)
        socketio.emit('global_network_refresh')
    return jsonify({"success": success})

@app.route('/api/<hospital_id>/delete_bed', methods=['POST'])
def delete_hospital_bed(hospital_id):
    if not session.get('logged_in') or session.get('hospital_id') != hospital_id:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
        
    username = session.get('username')
    conn = get_db_connection()
    
    user = conn.execute("SELECT status FROM staff WHERE hospital_id = ? AND username = ?", (hospital_id, username)).fetchone()
    if not user or user['status'] != 'approved':
        conn.close()
        return jsonify({"success": False, "error": "Account suspended"}), 403
        
    data = request.json
    try:
        conn.execute('DELETE FROM beds WHERE hospital_id = ? AND bed_id = ?', (hospital_id, data['bed_id']))
        conn.commit()
        success = True
    except Exception as e:
        success = False
    finally:
        conn.close()
    
    if success:
        socketio.emit('system_refresh', {'hospital_id': hospital_id}, room=hospital_id)
        socketio.emit('global_network_refresh')
    return jsonify({"success": success})

# =====================================================================
# CHATBOT SPEED OPTIMIZATION (NEW FEATURE)
# 1. Bed-status context is built with ONE database query (was 1 + N queries)
#    and cached for a few seconds, so repeated chat messages skip the DB.
# 2. The Gemini client is created once and reused for every request.
# 3. The last model that worked is remembered and tried first, so a broken
#    or overloaded model is not retried on every single message.
# =====================================================================
import threading

CHAT_CONTEXT_TTL_SECONDS = 5  # How long the bed-status context stays cached
_chat_context_cache = {"text": None, "time": 0.0}
_chat_context_lock = threading.Lock()

_gemini_client_cache = {"key": None, "client": None}
_gemini_client_lock = threading.Lock()

CHAT_MODELS = ['gemini-3.8-flash', 'gemini-2.5-flash', 'gemini-2.5-flash-lite']
_preferred_chat_model = {"name": None}

def get_chat_db_context():
    """Returns the hospital bed-status text for the AI, cached for a few seconds."""
    now = time.time()
    with _chat_context_lock:
        if _chat_context_cache["text"] and (now - _chat_context_cache["time"]) < CHAT_CONTEXT_TTL_SECONDS:
            return _chat_context_cache["text"]

    conn = get_db_connection()
    rows = conn.execute('''
        SELECT h.id, h.name, h.area, h.contact, h.rating, h.specialties,
               COUNT(b.bed_id) AS total,
               SUM(CASE WHEN b.status = 'Available' THEN 1 ELSE 0 END) AS avail
        FROM hospitals h
        LEFT JOIN beds b ON b.hospital_id = h.id
        GROUP BY h.id
    ''').fetchall()
    conn.close()

    db_context = "CURRENT PUNE NETWORK DATABASE STATUS:\n"
    for h in rows:
        avail = h['avail'] or 0
        total = h['total'] or 0
        db_context += f"- {h['name']} ({h['area']}): {avail} vacant beds out of {total} total beds. Contact: {h['contact']}, Rating: {h['rating']}, Specialties: {h['specialties']}\n"

    with _chat_context_lock:
        _chat_context_cache["text"] = db_context
        _chat_context_cache["time"] = time.time()
    return db_context

def get_gemini_client(api_key):
    """Creates the Gemini client once and reuses it (recreated only if the key changes)."""
    with _gemini_client_lock:
        if _gemini_client_cache["client"] is None or _gemini_client_cache["key"] != api_key:
            _gemini_client_cache["client"] = genai.Client(api_key=api_key)
            _gemini_client_cache["key"] = api_key
        return _gemini_client_cache["client"]

@app.route('/api/chat', methods=['POST'])
def chat_bot():
    data = request.json
    user_message = data.get('message', '')

    def generate():
        try:
            db_context = get_chat_db_context()

            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                yield f"data: {json.dumps({'error': 'Missing API Key in .env file.'})}\n\n"
                return
            
            client = get_gemini_client(api_key)

            system_instruction = f"""ROLE: Advanced Real-Time AI Assistant
CRITICAL RULE: YOU MUST BE CONCISE AND ANSWER ONLY WHAT THE USER ASKS. 
- If the user asks ONLY about bed availability for a hospital, provide ONLY the bed count.
- Answer directly in 1-2 sentences.
- Use HTML tags (<b>, <br>) for formatting. Do not use markdown.
REAL-TIME LOCAL DATABASE CONTEXT:
{db_context}
"""
            # Models are tried in order. If one is overloaded or not found, the next is used.
            # The model that worked last time is tried first to save time.
            models_to_try = list(CHAT_MODELS)
            preferred = _preferred_chat_model["name"]
            if preferred in models_to_try:
                models_to_try.remove(preferred)
                models_to_try.insert(0, preferred)
            max_attempts_per_model = 3

            for model_name in models_to_try:
                for attempt in range(max_attempts_per_model):
                    sent_any = False
                    try:
                        # Stream the response back in real-time chunks
                        response = client.models.generate_content_stream(
                            model=model_name,
                            contents=user_message,
                            config=types.GenerateContentConfig(system_instruction=system_instruction)
                        )
                        for chunk in response:
                            if chunk.text:
                                sent_any = True
                                yield f"data: {json.dumps({'text': chunk.text})}\n\n"
                        _preferred_chat_model["name"] = model_name  # Remember the working model
                        return  # Finished successfully

                    except Exception as e:
                        err = str(e)
                        print(f"Chatbot LLM Error ({model_name}, attempt {attempt + 1}): {err}")

                        # If text was already streamed, we can't safely retry without duplicating it
                        if sent_any:
                            yield f"data: {json.dumps({'error': 'The assistant was interrupted. Please try again.'})}\n\n"
                            return

                        # Temporary overload / rate limit -> retry with backoff, then move to next model
                        if any(code in err for code in ('503', 'UNAVAILABLE', '429', 'RESOURCE_EXHAUSTED')):
                            if attempt < max_attempts_per_model - 1:
                                time.sleep(2 ** attempt)  # 1s, 2s
                                continue
                            break

                        # Model name not found / unsupported -> skip straight to next model
                        if '404' in err or 'NOT_FOUND' in err:
                            break

                        # Any other error is unexpected, so let the outer handler deal with it
                        raise

            # All models and retries failed
            yield f"data: {json.dumps({'error': 'The assistant is busy right now. Please try again in a minute.'})}\n\n"

        except Exception as e:
            print(f"Chatbot LLM Error: {e}")
            yield f"data: {json.dumps({'error': 'Sorry, the assistant is having trouble right now. Please try again shortly.'})}\n\n"

    # Return as an Event Stream so the frontend types it out live
    return Response(stream_with_context(generate()), content_type='text/event-stream')

@socketio.on('join_hospital')
def on_join(data):
    hospital_id = data.get('hospital_id')
    if hospital_id:
        join_room(hospital_id)

@socketio.on('update_bed_status')
def handle_bed_update(data):
    hospital_id = data.get('hospital_id')
    
    if not session.get('logged_in') or session.get('hospital_id') != hospital_id:
        return 
        
    username = session.get('username')
    conn = get_db_connection()
    user = conn.execute("SELECT status FROM staff WHERE hospital_id = ? AND username = ?", (hospital_id, username)).fetchone()
    
    if not user or user['status'] != 'approved':
        conn.close()
        return 
        
    bed_id = data.get('bed_id')
    new_status = data.get('status')
    
    if new_status in ['Occupied', 'Discharge Hold']:
        p_name = data.get('patient_name', '')
        p_age = data.get('patient_age', '')
        p_diag = data.get('diagnosis', '')
    else:
        p_name, p_age, p_diag = "", "", ""
        
    conn.execute('''
        UPDATE beds 
        SET status = ?, patient_name = ?, patient_age = ?, diagnosis = ? 
        WHERE hospital_id = ? AND bed_id = ?
    ''', (new_status, p_name, p_age, p_diag, hospital_id, bed_id))
    conn.commit()
    conn.close()
    
    emit('bed_updated', data, room=hospital_id)
    socketio.emit('global_network_refresh')

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8080, debug=False)