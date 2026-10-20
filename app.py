from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash, abort, Response, stream_with_context
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from google import genai
from google.genai import types
import sqlite3
import os
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

import smtplib
from email.mime.text import MIMEText
import random
import json  # Required for storing floor lists in the database
import uuid  # Add this to your imports at the very top

app = Flask(__name__)
app.secret_key = 'pune_smart_hospital_network_secret_key'

# --- SECURITY: PREVENT BROWSER CACHING ---
@app.after_request
def add_header(response):
    """
    Prevent the browser from caching pages. 
    If a user clicks the 'Back' button, it forces a fresh request to the server, 
    ensuring all session security checks are run again.
    """
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# --- EMAIL CONFIGURATION ---
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_EMAIL = "academicuse20@gmail.com" 
SMTP_PASSWORD = "ipsbxeigfnrwwavw" # You must generate a 16-digit App Password in your Google Account and paste it here

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
        print(f"SIMULATED EMAIL TO: {to_email}")
        print(f"SUBJECT: {subject}")
        print(f"BODY:\n{body}")
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
        "image": "https://images.unsplash.com/photo-1587351021759-3e566b6af7cc?q=80&w=800&auto=format&fit=crop",
        "specialties": "Cardiology, Oncology, Neurosurgery, Renal Care"
    },
    {
        "id": "ruby-sasoon",
        "name": "Ruby Hall Clinic (Sasoon Road)",
        "area": "Sasoon Rd, Sangamvadi",
        "rating": "4.5",
        "contact": "+91 20 6645 5100",
        "image": "https://images.unsplash.com/photo-1519494026892-80bbd2d6fd0d?q=80&w=800&auto=format&fit=crop",
        "specialties": "Quaternary Care, ICU, Cardiology, Organ Transplant"
    },
    {
        "id": "ruby-pcmc",
        "name": "Ruby Hall Clinic PCMC",
        "area": "Pimple Saudagar",
        "rating": "3.7",
        "contact": "+91 20 2720 1717",
        "image": "https://images.unsplash.com/photo-1629909613654-28e377c37b09?q=80&w=800&auto=format&fit=crop",
        "specialties": "Outpatient Care, Day-Care Surgeries, Diagnostics"
    },
    {
        "id": "ruby-hinjawadi",
        "name": "Ruby Hall Clinic (Hinjawadi)",
        "area": "Phase 1, Hinjawadi",
        "rating": "3.8",
        "contact": "+91 20 6699 9999",
        "image": "https://images.unsplash.com/photo-1516549655169-df83a0774514?q=80&w=800&auto=format&fit=crop",
        "specialties": "Emergency Response, Trauma, Critical Care"
    },
    {
        "id": "ruby-wanowrie",
        "name": "Ruby Hall Clinic (Wanowrie)",
        "area": "Wanowrie, Pune",
        "rating": "4.4",
        "contact": "+91 20 6649 4949",
        "image": "https://images.unsplash.com/photo-1512678080530-7760d81faba6?q=80&w=800&auto=format&fit=crop",
        "specialties": "General Medicine, Diagnostics, Trauma"
    },
    {
        "id": "aditya-birla",
        "name": "Aditya Birla Memorial Hospital",
        "area": "Chinchwad, PCMC",
        "rating": "4.3",
        "contact": "+91 98811 23006",
        "image": "https://images.unsplash.com/photo-1586773860418-d37222d8fce3?q=80&w=800&auto=format&fit=crop",
        "specialties": "Tertiary Care, Oncology, High-Capacity ICU"
    },
    {
        "id": "sancheti",
        "name": "Sancheti Hospital",
        "area": "Shivajinagar",
        "rating": "4.6",
        "contact": "+91 88888 08845",
        "image": "https://images.unsplash.com/photo-1538108149393-fbbd81895907?q=80&w=800&auto=format&fit=crop",
        "specialties": "Orthopaedics, Joint Replacement, Spine, Trauma"
    },
    {
        "id": "sahyadri-deccan",
        "name": "Sahyadri Super Speciality Hospital",
        "area": "Deccan Gymkhana",
        "rating": "4.7",
        "contact": "+91 20 4713 8766",
        "image": "https://images.unsplash.com/photo-1505751172876-fa1923c5c528?q=80&w=800&auto=format&fit=crop",
        "specialties": "Neurosciences, Organ Transplants, Critical Care"
    },
    {
        "id": "apollo-swargate",
        "name": "Apollo Hospitals (Swargate)",
        "area": "Shankar Sheth Rd, Swargate",
        "rating": "4.6",
        "contact": "+91 80 6297 2814",
        "image": "https://images.unsplash.com/photo-1587351021759-3e566b6af7cc?q=80&w=800&auto=format&fit=crop",
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
    }
]

def get_db_connection():
    db_path = os.path.join("/tmp", "my_database.db")
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Hospitals Registry
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
    
    # Staff table with staff_id, status, and assigned_floors
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
            assigned_floors TEXT DEFAULT '[]',
            UNIQUE(hospital_id, username),
            FOREIGN KEY (hospital_id) REFERENCES hospitals(id)
        )
    ''')
    
    # Beds table with strict hospital isolation
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
    
    # Populate default hospitals
    for h in HOSPITALS_SEED:
        cursor.execute('''
            INSERT OR REPLACE INTO hospitals (id, name, area, rating, contact, image, specialties)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (h['id'], h['name'], h['area'], h['rating'], h['contact'], h['image'], h['specialties']))
        
        # Default staff user for each hospital
        hashed_pw = generate_password_hash('password123')
        cursor.execute('''
            INSERT OR IGNORE INTO staff (hospital_id, username, password, name, email, staff_id, status, assigned_floors)
            VALUES (?, 'admin', ?, 'Chief Nursing Officer', ?, 'ADMIN-001', 'approved', '[]')
        ''', (h['id'], hashed_pw, f"admin@{h['id']}.hospital.in"))
        
        # Seed default sample beds if hospital has no beds
        cursor.execute('SELECT COUNT(*) FROM beds WHERE hospital_id = ?', (h['id'],))
        if cursor.fetchone()[0] == 0:
            sample_beds = [
                (h['id'], 'ICU-101', '1', '1st Floor - Intensive Care', 'Ventilator', 'Available', '', '', ''),
                (h['id'], 'ICU-102', '1', '1st Floor - Intensive Care', 'Oxygen Bed', 'Occupied', 'Ramesh P.', '58', 'Acute Respiratory'),
                (h['id'], 'GEN-201', '2', '2nd Floor - General Ward', 'Standard Bed', 'Available', '', '', ''),
                (h['id'], 'GEN-202', '2', '2nd Floor - General Ward', 'Standard Bed', 'Cleaning', '', '', '')
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
    
    # Aggregate stats per hospital
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

# --- HOSPITAL SPECIFIC AUTHENTICATION ---

@app.route('/hospital/<hospital_id>/login', methods=['GET', 'POST'])
def hospital_login(hospital_id):
    # Prevent returning to the login page if already authenticated
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
            # Block login based on pending or revoked status
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
                VALUES (?, ?, ?, ?, ?, ?, 'pending', '[]')
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

# --- ADMINISTRATIVE PORTAL SECURITY & ROUTES ---

@app.route('/hospital/<hospital_id>/admin/login', methods=['GET', 'POST'])
def admin_login(hospital_id):
    # Prevent returning to the admin login page if already authenticated
    if session.get('admin_logged_in') and session.get('admin_hospital_id') == hospital_id:
        return redirect(url_for('hospital_admin', hospital_id=hospital_id))

    hospital = get_hospital_or_404(hospital_id)
    
    if request.method == 'POST':
        admin_id = request.form.get('admin_id')
        password = request.form.get('password')
        
        # Get the unique ID for this specific form submission
        captcha_id = request.form.get('captcha_id')
        captcha_input = request.form.get('captcha', '').strip()
        
        # Look up the answer linked specifically to this form load
        session_key = f'captcha_ans_{captcha_id}'
        stored_captcha = session.get(session_key)
        
        if not captcha_input or not stored_captcha or captcha_input != stored_captcha:
            flash('Incorrect Security CAPTCHA. Please try again.', 'error')
            return redirect(url_for('admin_login', hospital_id=hospital_id))
            
        if admin_id == 'admin' and password == 'admin123':
            session['admin_logged_in'] = True
            session['admin_hospital_id'] = hospital_id
            
            # Clean up the used captcha from the session
            session.pop(session_key, None) 
            
            return redirect(url_for('hospital_admin', hospital_id=hospital_id))
        else:
            flash('Access Denied: Invalid Admin ID or Password.', 'error')
            return redirect(url_for('admin_login', hospital_id=hospital_id))

    # --- GET REQUEST (Page Load) ---
    num1 = random.randint(1, 9)
    num2 = random.randint(1, 9)
    
    # Generate a unique ID for THIS specific tab/page load
    captcha_id = str(uuid.uuid4())
    
    # Store the answer using the unique ID
    session[f'captcha_ans_{captcha_id}'] = str(num1 + num2)
    captcha_text = f"{num1} + {num2} = ?"
    
    # Pass the unique ID to the HTML template
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
    
    # 1. Get Bed Summary
    stats = conn.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'Available' THEN 1 ELSE 0 END) as avail,
            SUM(CASE WHEN status = 'Occupied' THEN 1 ELSE 0 END) as occ
        FROM beds WHERE hospital_id = ?
    ''', (hospital_id,)).fetchone()
    
    # 2. Get Pending Staff
    pending_staff = conn.execute("SELECT * FROM staff WHERE hospital_id = ? AND status = 'pending'", (hospital_id,)).fetchall()
    
    # 3. Get Active Staff (Parse JSON assigned_floors for template)
    active_staff_raw = conn.execute("SELECT * FROM staff WHERE hospital_id = ? AND status = 'approved'", (hospital_id,)).fetchall()
    active_staff = []
    for staff in active_staff_raw:
        s_dict = dict(staff)
        s_dict['assigned_floors'] = json.loads(s_dict['assigned_floors']) if s_dict['assigned_floors'] else []
        active_staff.append(s_dict)
        
    # 4. Get Revoked Staff 
    revoked_staff_raw = conn.execute("SELECT * FROM staff WHERE hospital_id = ? AND status = 'revoked'", (hospital_id,)).fetchall()
    revoked_staff = [dict(s) for s in revoked_staff_raw]
        
    # 5. Get All Distinct Floors for this hospital
    all_beds = conn.execute("SELECT DISTINCT floor_num, floor_name FROM beds WHERE hospital_id = ?", (hospital_id,)).fetchall()
    all_floors = [{'floor': str(b['floor_num']), 'name': b['floor_name']} for b in all_beds]
    
    conn.close()
    
    return render_template('admin.html', hospital=hospital, stats=stats, pending_staff=pending_staff, active_staff=active_staff, revoked_staff=revoked_staff, all_floors=all_floors)

@app.route('/hospital/<hospital_id>/admin/staff/<username>/<action>', methods=['POST'])
def manage_staff(hospital_id, username, action):
    # Ensure only admins can trigger this route
    if not session.get('admin_logged_in') or session.get('admin_hospital_id') != hospital_id:
        abort(403)
        
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM staff WHERE hospital_id = ? AND username = ?", (hospital_id, username)).fetchone()
    
    if user:
        if action == 'approve':
            conn.execute("UPDATE staff SET status = 'approved' WHERE hospital_id = ? AND username = ?", (hospital_id, username))
            send_system_email(user['email'], "Account Approved - CARE Network", f"Hello {user['name']},\n\nYour staff account (ID: {user['staff_id']}) has been APPROVED by administration. You may now log in to the portal.")
            flash(f"Staff member {user['name']} has been approved.", "success")
            
        elif action == 'reject':
            # Hard delete for rejected pending users OR permanently deleted revoked users
            conn.execute("DELETE FROM staff WHERE hospital_id = ? AND username = ?", (hospital_id, username))
            if user['status'] == 'pending':
                send_system_email(user['email'], "Account Rejected - CARE Network", f"Hello {user['name']},\n\nYour staff account registration was REJECTED by administration. Please contact your supervisor for details.")
            flash(f"Staff registration for {user['name']} was permanently removed.", "error")
            
        elif action == 'revoke':
            # Soft delete / Suspend
            conn.execute("UPDATE staff SET status = 'revoked' WHERE hospital_id = ? AND username = ?", (hospital_id, username))
            
            # Send email notification for suspension
            revoke_msg = f"Hello {user['name']},\n\nYour staff account (ID: {user['staff_id']}) has been SUSPENDED by administration. Your access to the hospital portal is temporarily revoked.\n\nPlease contact your supervisor or IT department for further details."
            send_system_email(user['email'], "Account Suspended - CARE Network", revoke_msg)
            
            flash(f"Staff account for {user['name']} has been suspended.", "success")
            
        elif action == 'restore':
            # Restore a suspended user
            conn.execute("UPDATE staff SET status = 'approved' WHERE hospital_id = ? AND username = ?", (hospital_id, username))
            
            # Send email notification for restoration
            restore_msg = f"Hello {user['name']},\n\nYour staff account (ID: {user['staff_id']}) has been RESTORED by administration. Your access to the hospital portal is now active again."
            send_system_email(user['email'], "Account Restored - CARE Network", restore_msg)
            
            flash(f"Staff account for {user['name']} has been restored.", "success")
            
        elif action == 'assign_floors':
            # Retrieve array from multi-select dropdown / chips
            selected_floors = request.form.getlist('assigned_floors')
            conn.execute("UPDATE staff SET assigned_floors = ? WHERE hospital_id = ? AND username = ?", 
                         (json.dumps(selected_floors), hospital_id, username))
            flash(f"Updated floor permissions for {user['name']}.", "success")
            
        conn.commit()
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

# --- HOSPITAL SPECIFIC PORTALS ---

@app.route('/hospital/<hospital_id>/nursing')
def hospital_nursing(hospital_id):
    hospital = get_hospital_or_404(hospital_id)
    
    if not session.get('logged_in') or session.get('hospital_id') != hospital_id:
        flash("You must authenticate with staff credentials for this facility.", "error")
        return redirect(url_for('hospital_login', hospital_id=hospital_id))
        
    # INSTANT REVOCATION CHECK
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

# --- HOSPITAL SCOPED REST APIS ---

@app.route('/api/<hospital_id>/beds')
def get_hospital_beds(hospital_id):
    conn = get_db_connection()
    beds = conn.execute(
        'SELECT * FROM beds WHERE hospital_id = ? ORDER BY floor_num, bed_id',
        (hospital_id,)
    ).fetchall()
    
    # RBAC FILTERING LOGIC: Find out if user is a logged-in nurse, and what floors they have
    is_staff = session.get('logged_in') and session.get('hospital_id') == hospital_id
    username = session.get('username')
    allowed_floors = None
    
    if is_staff:
        # Check status & assigned floors simultaneously
        user = conn.execute('SELECT status, assigned_floors FROM staff WHERE hospital_id = ? AND username = ?', (hospital_id, username)).fetchone()
        
        # INSTANT REVOKE CHECK
        if user and user['status'] == 'approved' and user['assigned_floors']:
            allowed_floors = json.loads(user['assigned_floors'])
        else:
            allowed_floors = [] # Restricted completely if revoked or empty

    conn.close()
    
    hospital_data = {}
    for row in beds:
        floor_num = str(row['floor_num'])
        
        # If user is a staff member, skip processing any floors they aren't assigned to.
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
    
    # INSTANT REVOKE CHECK
    user = conn.execute("SELECT status FROM staff WHERE hospital_id = ? AND username = ?", (hospital_id, username)).fetchone()
    if not user or user['status'] != 'approved':
        conn.close()
        return jsonify({"success": False, "error": "Account suspended"}), 403
        
    data = request.json
    floor_num = str(data['floor_num'])
    
    try:
        # Create the bed
        conn.execute('''
            INSERT INTO beds (hospital_id, bed_id, floor_num, floor_name, bed_type, status, patient_name, patient_age, diagnosis)
            VALUES (?, ?, ?, ?, ?, 'Available', '', '', '')
        ''', (hospital_id, data['bed_id'], floor_num, data['floor_name'], data['bed_type']))
        
        # AUTOMATIC PERMISSION UPDATE
        # If the nurse created a completely new floor, add it to their assigned floors automatically
        user_db = conn.execute('SELECT assigned_floors FROM staff WHERE hospital_id = ? AND username = ?', (hospital_id, username)).fetchone()
        if user_db:
            user_floors = json.loads(user_db['assigned_floors']) if user_db['assigned_floors'] else []
            if floor_num not in user_floors:
                user_floors.append(floor_num)
                conn.execute('UPDATE staff SET assigned_floors = ? WHERE hospital_id = ? AND username = ?', 
                             (json.dumps(user_floors), hospital_id, username))
        
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    finally:
        conn.close()
    
    if success:
        socketio.emit('system_refresh', {'hospital_id': hospital_id}, room=hospital_id)
        socketio.emit('global_network_refresh', broadcast=True)
    return jsonify({"success": success})

@app.route('/api/<hospital_id>/delete_bed', methods=['POST'])
def delete_hospital_bed(hospital_id):
    if not session.get('logged_in') or session.get('hospital_id') != hospital_id:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
        
    username = session.get('username')
    conn = get_db_connection()
    
    # INSTANT REVOKE CHECK
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
        socketio.emit('global_network_refresh', broadcast=True)
    return jsonify({"success": success})

# --- ADVANCED AI CHATBOT INTEGRATION ---
@app.route('/api/chat', methods=['POST'])
def chat_bot():
    data = request.json
    user_message = data.get('message', '')

    try:
        # 1. Fetch live DB context
        conn = get_db_connection()
        hospitals = conn.execute('SELECT * FROM hospitals').fetchall()
        db_context = "CURRENT PUNE NETWORK DATABASE STATUS:\n"
        for h in hospitals:
            stats = conn.execute('''
                SELECT COUNT(*) as total, SUM(CASE WHEN status = 'Available' THEN 1 ELSE 0 END) as avail
                FROM beds WHERE hospital_id = ?
            ''', (h['id'],)).fetchone()
            avail = stats['avail'] or 0
            total = stats['total'] or 0
            db_context += f"- {h['name']} ({h['area']}): {avail} vacant beds out of {total} total beds. Contact: {h['contact']}, Rating: {h['rating']}, Specialties: {h['specialties']}\n"
        conn.close()

        # 2. Configure Gemini securely
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return jsonify({"response": "<b>System Alert:</b> Missing API Key in .env file."})
        
        client = genai.Client(api_key=api_key)

        # 3. Apply System Prompt
        system_instruction = f"""ROLE: Advanced Real-Time AI Assistant
CRITICAL RULE: YOU MUST BE CONCISE AND ANSWER ONLY WHAT THE USER ASKS. 
- If the user asks ONLY about bed availability for a hospital, provide ONLY the bed count.
- Answer directly in 1-2 sentences.
- Use HTML tags (<b>, <br>) for formatting. Do not use markdown.
REAL-TIME LOCAL DATABASE CONTEXT:
{db_context}
"""

        # Generate standard full response instantly using GEMINI 3.8 FLASH
        response = client.models.generate_content(
            model='gemini-3.8-flash',
            contents=user_message,
            config=types.GenerateContentConfig(system_instruction=system_instruction)
        )
        ai_reply = response.text

    except Exception as e:
        print(f"Chatbot LLM Error: {e}")
        ai_reply = f"<b>System Alert:</b> Internal Server Error.<br><i>{str(e)}</i>"

    return jsonify({"response": ai_reply})
    
# --- WEBSOCKETS (ROOM ISOLATION) ---

@socketio.on('join_hospital')
def on_join(data):
    hospital_id = data.get('hospital_id')
    if hospital_id:
        join_room(hospital_id)

@socketio.on('update_bed_status')
def handle_bed_update(data):
    hospital_id = data.get('hospital_id')
    
    # INSTANT REVOKE CHECK OVER WEBSOCKET
    if not session.get('logged_in') or session.get('hospital_id') != hospital_id:
        return # Ignore unauthorized socket events
        
    username = session.get('username')
    conn = get_db_connection()
    user = conn.execute("SELECT status FROM staff WHERE hospital_id = ? AND username = ?", (hospital_id, username)).fetchone()
    
    if not user or user['status'] != 'approved':
        conn.close()
        return # Block update if suspended
        
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
    emit('global_network_refresh', broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8080, debug=False)