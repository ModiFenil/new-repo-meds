from flask import Flask, render_template, request, redirect, session, url_for, make_response, flash
from werkzeug.utils import secure_filename
import pymysql
import hashlib
from config import config
# from datetime import datetime, date, time
from datetime import datetime, date
import time
import os
import io
import csv
import calendar
from flask_apscheduler import APScheduler
from flask import flash,get_flashed_messages


import pytz
from datetime import timezone, timedelta

# DEFINE IST TIMEZONE
IST = pytz.timezone('Asia/Kolkata')

# CREATE IST HELPER FUNCTIONS
def get_ist_now():
    """Get current datetime in IST as string for database"""
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

def get_ist_date():
    """Get current date in IST"""
    return datetime.now(IST).date()

def get_ist_time_for_display():
    """Get current time in IST for display"""
    return datetime.now(IST).strftime("%I:%M %p")

# Initialize scheduler at module level
scheduler = APScheduler()   

def create_app(config_name=None):
    app = Flask(__name__)
    # Get config name from environment or use default
    config_name = config_name or os.environ.get('APP_ENV', 'default')
    # Apply configuration
    app.config.from_object(config[config_name])
    # Initialize app with config
    config[config_name].init_app(app)
    
    # ADD THIS LINE - Configure scheduler timezone
    app.config['SCHEDULER_TIMEZONE'] = 'Asia/Kolkata'
    
    # Initialize scheduler with app
    scheduler.init_app(app)
    return app


app = create_app()

# def get_db_connection():
#     conn = pymysql.connect(
#         host=app.config['MYSQL_HOST_NAME'],
#         user=app.config['MYSQL_USER_NAME'],
#         password=app.config['MYSQL_PASSWORD_NAME'],
#         db=app.config['MYSQL_DB_NAME'],
#         cursorclass=pymysql.cursors.DictCursor,
#         autocommit=True
#     )
    
#     # Set database session to IST
#     with conn.cursor() as cursor:
#         cursor.execute("SET time_zone = '+05:30'")
    
#     return conn

def get_db_connection(max_retries=3):
    for attempt in range(max_retries):
        try:
            # Get password from config (already handled in config.py)
            password = app.config['MYSQL_PASSWORD_NAME']
            
            # Debug output (remove in production)
            print(f"🔍 Connection attempt {attempt + 1}:")
            print(f"  Host: {app.config['MYSQL_HOST_NAME']}")
            print(f"  User: {app.config['MYSQL_USER_NAME']}")
            print(f"  Password: {'None (no password)' if password is None else 'Set'}")
            print(f"  Database: {app.config['MYSQL_DB_NAME']}")
            
            conn = pymysql.connect(
                host=app.config['MYSQL_HOST_NAME'],
                user=app.config['MYSQL_USER_NAME'],
                password=password,  # This will be None for empty passwords
                db=app.config['MYSQL_DB_NAME'],
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,
                connect_timeout=30
            )
            
            # Set timezone
            with conn.cursor() as cursor:
                cursor.execute("SET time_zone = '+05:30'")
            
            print("✅ Connection successful!")
            return conn
            
        except Exception as e:
            print(f"❌ Database connection attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)  # Wait 2 seconds before retry
            else:
                print(f"❌ All {max_retries} connection attempts failed")
                return None


# SHA256 password hashing functions
def hash_password(password):
    """Hash password using SHA256"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def verify_password(password, hashed_password):
    """Verify password against SHA256 hash"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest() == hashed_password

@app.template_filter('datetimeformat')
def datetimeformat(value, format='%d-%b-%Y %I:%M %p'):
    if not value:
        return ''
    if isinstance(value, str):
        value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
    return value.strftime(format)

@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password']
        
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, password, firstname, lastname, role FROM t_users_hr WHERE email=%s AND is_active=1", (email,))
            user = cursor.fetchone()
            
            # SHA256 password verification
            if user and verify_password(password, user['password']):
                session['user_id'] = user['id']
                session['firstname'] = user['firstname']
                session['lastname'] = user['lastname']
                session['role'] = user['role']
                
                if user['role'] == 2:  # admin
                    return redirect('/admin_dashboard')
                else:
                    return redirect('/user_dashboard')
            else:
                error = 'Invalid email or password.'
        conn.close()
    
    return render_template('login.html', error=error)

@app.route('/test_time')
def test_time():
    try:
        ist_time = get_ist_now()
        ist_date = get_ist_date()
        server_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Calculate the difference
        ist_dt = datetime.now(IST)
        server_dt = datetime.now()
        diff_hours = (ist_dt - server_dt.replace(tzinfo=pytz.UTC)).total_seconds() / 3600
        
        return f"""
        <h2>Time Comparison</h2>
        <p><strong>IST Time:</strong> {ist_time}</p>
        <p><strong>IST Date:</strong> {ist_date}</p>
        <p><strong>Server Time:</strong> {server_time}</p>
        <p><strong>Time Difference:</strong> {diff_hours:.1f} hours</p>
        <p><strong>Status:</strong> {'✅ IST Working' if abs(diff_hours - 5.5) < 0.1 else '❌ IST Not Working'}</p>
        """
    except Exception as e:
        return f"<h2>Error</h2><p>{str(e)}</p><p>IST helper functions not working!</p>"



@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user_id' not in session or session.get('role') != 2:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    # Get date filter from query parameters
    selected_date_str = request.args.get('date')
    status_filter = request.args.get('status')
    
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = date.today()
    else:
        selected_date = date.today()
    
    try:
        with conn.cursor() as cursor:
            # Check if new columns exist, if not use old columns
            try:
                cursor.execute("SHOW COLUMNS FROM t_attendance_hr LIKE 'check_in_latitude'")
                new_columns_exist = cursor.fetchone() is not None
            except Exception as e:
                print(f"Column check error: {e}")
                new_columns_exist = False
            
            if new_columns_exist:
                # Use new column structure
                query = """
                SELECT 
                    u.id as user_id,
                    u.firstname, 
                    u.lastname,
                    a.checkin_time,
                    a.checkout_time,
                    a.work_duration,
                    a.check_in_latitude,
                    a.check_in_longitude,
                    a.check_in_location_name,
                    a.check_out_latitude,
                    a.check_out_longitude,
                    a.check_out_location_name,
                    a.auto_checkout
                FROM t_users_hr u
                LEFT JOIN t_attendance_hr a ON u.id = a.user_id 
                    AND DATE(a.checkin_time) = %s
                WHERE u.role = 1 AND u.is_active = 1
                """
            else:
                # Use old column structure with aliases to match template expectations
                query = """
                SELECT 
                    u.id as user_id,
                    u.firstname, 
                    u.lastname,
                    a.checkin_time,
                    a.checkout_time,
                    a.work_duration,
                    a.latitude as check_in_latitude,
                    a.longitude as check_in_longitude,
                    a.location_name as check_in_location_name,
                    NULL as check_out_latitude,
                    NULL as check_out_longitude,
                    NULL as check_out_location_name,
                    a.auto_checkout
                FROM t_users_hr u
                LEFT JOIN t_attendance_hr a ON u.id = a.user_id 
                    AND DATE(a.checkin_time) = %s
                WHERE u.role = 1 AND u.is_active = 1
                """
            
            # Add status filter if specified
            if status_filter == 'present':
                query += " AND a.checkout_time IS NOT NULL AND a.work_duration IS NOT NULL"
            elif status_filter == 'absent':
                query += " AND a.checkin_time IS NULL"
            elif status_filter == 'in_progress':
                query += " AND a.checkin_time IS NOT NULL AND a.checkout_time IS NULL"
                
            query += " ORDER BY u.firstname, u.lastname"
            
            cursor.execute(query, (selected_date,))
            records = cursor.fetchall()
            
            # Calculate summary statistics - ADDED auto-checkout count
            cursor.execute("""
            SELECT 
                COUNT(DISTINCT u.id) as total_users,
                COUNT(DISTINCT CASE WHEN a.checkout_time IS NOT NULL THEN u.id END) as total_present,
                COUNT(DISTINCT CASE WHEN a.checkin_time IS NOT NULL AND a.checkout_time IS NULL THEN u.id END) as in_progress,
                COUNT(DISTINCT CASE WHEN a.checkin_time IS NULL THEN u.id END) as total_absent,
                COUNT(DISTINCT CASE WHEN a.auto_checkout = 1 THEN u.id END) as auto_checkout_count
            FROM t_users_hr u
            LEFT JOIN t_attendance_hr a ON u.id = a.user_id 
                AND DATE(a.checkin_time) = %s
            WHERE u.role = 1 AND u.is_active = 1
            """, (selected_date,))
            
            summary = cursor.fetchone()
            
            # Get pending checkouts with error handling
            try:
                pending_checkouts = check_pending_checkouts()
            except Exception as e:
                print(f"Error getting pending checkouts: {e}")
                pending_checkouts = []
                
    except Exception as e:
        print(f"Error in admin dashboard: {e}")
        records = []
        summary = {'total_users': 0, 'total_present': 0, 'in_progress': 0, 'total_absent': 0, 'auto_checkout_count': 0}
        pending_checkouts = []
    
    finally:
        conn.close()
    
    return render_template(
        'dashboard_admin.html', 
        records=records,
        selected_date=selected_date,
        today_date=date.today(),
        summary=summary,
        pending_checkouts=pending_checkouts
    )

def check_pending_checkouts():
    """Check for users who need auto-checkout"""
    conn = get_db_connection()
    
    try:
        with conn.cursor() as cursor:
            today = datetime.now().date()
            
            # Check if new columns exist
            try:
                cursor.execute("SHOW COLUMNS FROM t_attendance_hr LIKE 'check_in_location_name'")
                new_columns_exist = cursor.fetchone() is not None
            except Exception as e:
                print(f"Column check error in pending checkouts: {e}")
                new_columns_exist = False
            
            if new_columns_exist:
                cursor.execute("""
                SELECT a.user_id, u.firstname, u.lastname, a.checkin_time,
                       a.check_in_location_name
                FROM t_attendance_hr a
                JOIN t_users_hr u ON a.user_id = u.id
                WHERE DATE(a.checkin_time) = %s 
                AND a.checkout_time IS NULL
                AND u.role = 1 AND u.is_active = 1
                ORDER BY a.checkin_time
                """, (today,))
            else:
                cursor.execute("""
                SELECT a.user_id, u.firstname, u.lastname, a.checkin_time,
                       a.location_name as check_in_location_name
                FROM t_attendance_hr a
                JOIN t_users_hr u ON a.user_id = u.id
                WHERE DATE(a.checkin_time) = %s 
                AND a.checkout_time IS NULL
                AND u.role = 1 AND u.is_active = 1
                ORDER BY a.checkin_time
                """, (today,))
            
            return cursor.fetchall()
            
    except Exception as e:
        print(f"Error checking pending checkouts: {e}")
        return []
    finally:
        conn.close()

@app.route('/manual_auto_checkout', methods=['POST'])
def manual_auto_checkout():
    """Manual trigger for auto-checkout (admin only) - Does NOT set auto_checkout=1"""
    if session.get('role') != 2:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    try:
        with conn.cursor() as cursor:
            today = datetime.now().date()
            auto_checkout_time = datetime.combine(today, datetime.min.time().replace(hour=23, minute=59, second=59))
            
            # Check if new columns exist
            try:
                cursor.execute("SHOW COLUMNS FROM t_attendance_hr LIKE 'check_in_latitude'")
                new_columns_exist = cursor.fetchone() is not None
            except:
                new_columns_exist = False
            
            # Count pending checkouts
            cursor.execute("""
            SELECT COUNT(*) as count
            FROM t_attendance_hr a
            JOIN t_users_hr u ON a.user_id = u.id
            WHERE DATE(a.checkin_time) = %s 
            AND a.checkout_time IS NULL
            AND u.role = 1
            """, (today,))
            
            count = cursor.fetchone()['count']
            
            if count > 0:
                if new_columns_exist:
                    # Use new column structure - auto_checkout remains 0 (manual trigger)
                    cursor.execute("""
                    UPDATE t_attendance_hr a
                    JOIN t_users_hr u ON a.user_id = u.id
                    SET a.checkout_time = %s, 
                        a.work_duration = TIMEDIFF(%s, a.checkin_time),
                        a.check_out_latitude = a.check_in_latitude,
                        a.check_out_longitude = a.check_in_longitude,
                        a.check_out_location_name = CONCAT('Manual Auto-checkout by Admin: ', COALESCE(a.check_in_location_name, 'Unknown Location'))
                    WHERE DATE(a.checkin_time) = %s 
                    AND a.checkout_time IS NULL
                    AND u.role = 1
                    """, (auto_checkout_time, auto_checkout_time, today))
                else:
                    # Use old column structure - auto_checkout remains 0 (manual trigger)
                    cursor.execute("""
                    UPDATE t_attendance_hr a
                    JOIN t_users_hr u ON a.user_id = u.id
                    SET a.checkout_time = %s, 
                        a.work_duration = TIMEDIFF(%s, a.checkin_time)
                    WHERE DATE(a.checkin_time) = %s 
                    AND a.checkout_time IS NULL
                    AND u.role = 1
                    """, (auto_checkout_time, auto_checkout_time, today))
                
                conn.commit()
                return redirect(url_for('admin_dashboard', msg=f'Successfully auto-checked out {count} users'))
            else:
                return redirect(url_for('admin_dashboard', msg='No pending checkouts found'))
                
    except Exception as e:
        return redirect(url_for('admin_dashboard', error=f'Auto-checkout failed: {e}'))
    finally:
        conn.close()

# SCHEDULED AUTO-CHECKOUT FUNCTION - Sets auto_checkout=1
@scheduler.task('cron', id='auto_checkout_job', hour=23, minute=59, second=59, timezone='Asia/Kolkata')
def scheduled_auto_checkout():
    """Automatically checkout users at 11:59:59 PM IST and set auto_checkout=1"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            today = get_ist_date()  # Use IST date instead of date.today()
            checkout_time = get_ist_now()  # Use IST time
            
            # Check if new columns exist
            try:
                cursor.execute("SHOW COLUMNS FROM t_attendance_hr LIKE 'check_in_latitude'")
                new_columns_exist = cursor.fetchone() is not None
            except:
                new_columns_exist = False
            
            # Count pending users first
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM t_attendance_hr a
                JOIN t_users_hr u ON u.id = a.user_id
                WHERE DATE(a.checkin_time) = %s 
                AND a.checkout_time IS NULL
                AND u.role = 1 AND u.is_active = 1
            """, (today,))
            
            count_result = cursor.fetchone()
            count = count_result['count'] if count_result else 0
            
            if count > 0:
                if new_columns_exist:
                    # Use new column structure and set auto_checkout = 1
                    cursor.execute("""
                        UPDATE t_attendance_hr a
                        JOIN t_users_hr u ON u.id = a.user_id
                        SET a.checkout_time = %s,
                            a.work_duration = TIMEDIFF(%s, a.checkin_time),
                            a.auto_checkout = 1,
                            a.check_out_latitude = a.check_in_latitude,
                            a.check_out_longitude = a.check_in_longitude,
                            a.check_out_location_name = CONCAT('Scheduled Auto-checkout: ', COALESCE(a.check_in_location_name, 'System'))
                        WHERE DATE(a.checkin_time) = %s 
                        AND a.checkout_time IS NULL
                        AND u.role = 1 AND u.is_active = 1
                    """, (checkout_time, checkout_time, today))
                else:
                    # Use old column structure and set auto_checkout = 1
                    cursor.execute("""
                        UPDATE t_attendance_hr a
                        JOIN t_users_hr u ON u.id = a.user_id
                        SET a.checkout_time = %s,
                            a.work_duration = TIMEDIFF(%s, a.checkin_time),
                            a.auto_checkout = 1
                        WHERE DATE(a.checkin_time) = %s 
                        AND a.checkout_time IS NULL
                        AND u.role = 1 AND u.is_active = 1
                    """, (checkout_time, checkout_time, today))
                
                conn.commit()
                print(f"Scheduled auto-checkout completed for {count} users at {datetime.now()}")
            else:
                print(f"No pending checkouts found at {datetime.now()}")
                
    except Exception as e:
        print(f"Scheduled auto-checkout error: {e}")
    finally:
        conn.close()

@app.route('/add_user', methods=['GET', 'POST'])
def add_user():
    if session.get('role') != 2:  # Only admin can add users
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        firstname = request.form['firstname'].strip()
        lastname = request.form['lastname'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        role = int(request.form['role'])
        gender = request.form['gender']
        phone = request.form['phone'].strip()
        department = request.form['department'].strip()
        location = request.form['location'].strip()
        designation = request.form['designation'].strip()
        joining_date = request.form['date_of_joining'].strip()

        # Validation
        if not all([firstname, lastname, email, password, role, gender, phone, department, location, designation, joining_date]):
            return render_template('add_user.html', 
                                 error="All fields are required", 
                                 roles=get_roles())
        
        if gender not in ['male', 'female']:
            return render_template('add_user.html', 
                                 error="Invalid gender selection", 
                                 roles=get_roles())
                
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # Check if email already exists
                cursor.execute("SELECT id FROM t_users_hr WHERE email = %s", (email,))
                if cursor.fetchone():
                    return render_template('add_user.html', 
                                         error="Email already exists", 
                                         roles=get_roles())
                
                # Hash password
                hashed_password = hash_password(password)
                
                # Insert new user
                cursor.execute("""
                    INSERT INTO t_users_hr 
                    (firstname, lastname, email, password, role, gender, is_active, phone, department, location, designation,joining_date) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (firstname, lastname, email, hashed_password, role, gender, 1, phone, department, location, designation,joining_date))
                
                return render_template('add_user.html', 
                                     success=f"User {firstname} {lastname} added successfully!", 
                                     roles=get_roles())
                
        except Exception as e:
            return render_template('add_user.html', 
                                 error=f"Error adding user: {str(e)}", 
                                 roles=get_roles())
        finally:
            conn.close()
    
    return render_template('add_user.html', roles=get_roles())

def get_roles():
    """Helper function to get all roles"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT role, role_name FROM roles_hr")
            return cursor.fetchall()
    finally:
        conn.close()

@app.route('/user_list')
def user_list():
    if session.get('role') != 2:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute('''SELECT u.id, u.firstname, u.lastname, u.email, r.role_name, u.is_active
        FROM t_users_hr u
        LEFT JOIN roles_hr r ON u.role = r.role
        ORDER BY u.firstname, u.lastname''')
        users = cursor.fetchall()
    conn.close()
    
    return render_template('user_list.html', users=users)

@app.route('/toggle_user_status/<int:user_id>', methods=['POST'])
def toggle_user_status(user_id):
    """Toggle user active/inactive status"""
    if session.get('role') != 2:
        return redirect(url_for('login'))
    
    # Prevent admin from deactivating themselves
    if user_id == session.get('user_id'):
        return redirect(url_for('user_list', error='Cannot deactivate your own account'))
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Get current status
            cursor.execute("SELECT is_active, firstname, lastname FROM t_users_hr WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            
            if not user:
                return redirect(url_for('user_list', error='User not found'))
            
            # Toggle status (1 -> 0, 0 -> 1)
            new_status = 0 if user['is_active'] == 1 else 1
            
            # Update user status
            cursor.execute("UPDATE t_users_hr SET is_active = %s WHERE id = %s", (new_status, user_id))
            
            # Success message
            action = "activated" if new_status == 1 else "deactivated"
            success_msg = f"User {user['firstname']} {user['lastname']} has been {action} successfully."
            
            return redirect(url_for('user_list', success=success_msg))
            
    except Exception as e:
        return redirect(url_for('user_list', error=f'Error updating user status: {e}'))
    finally:
        conn.close()


# @app.route('/user_dashboard', methods=['GET', 'POST'])
# def user_dashboard():
#     if 'user_id' not in session or session.get('role') == 2:
#         return redirect(url_for('login'))

#     user_id = session['user_id']
#     conn = get_db_connection()
#     # msg = None
#     msg = request.args.get('msg')

#     if request.method == 'POST':
#         action = request.form.get('action')
#         now = get_ist_now()  # Use IST time
        
#         latitude = request.form.get('latitude')
#         longitude = request.form.get('longitude')
#         location_name = request.form.get('location_name')

#         check_in_latitude = float(latitude) if latitude else None
#         check_in_longitude = float(longitude) if longitude else None

#         with conn.cursor() as cursor:
#             if action == 'checkin':
#                 cursor.execute("SELECT id FROM t_attendance_hr WHERE user_id=%s AND DATE(checkin_time) = %s", 
#                              (user_id, get_ist_date()))
                
#                 if cursor.fetchone():
#                     msg = "You have already checked in today."
#                 else:
#                     cursor.execute(
#                         "INSERT INTO t_attendance_hr (user_id, checkin_time, check_in_latitude, check_in_longitude, check_in_location_name) VALUES (%s, %s, %s, %s, %s)",
#                         (user_id, now, check_in_latitude, check_in_longitude, location_name)
#                     )
#                     msg = f"Checked in successfully at {get_ist_time_for_display()}."

#             elif action == 'checkout':
#                 cursor.execute(
#                     "SELECT id, checkin_time FROM t_attendance_hr WHERE user_id=%s AND DATE(checkin_time) = %s AND checkout_time IS NULL",
#                     (user_id, get_ist_date())
#                 )
                
#                 attendance = cursor.fetchone()
#                 if attendance:
#                     check_out_latitude = float(latitude) if latitude else None
#                     check_out_longitude = float(longitude) if longitude else None

#                     cursor.execute(
#                         "UPDATE t_attendance_hr SET checkout_time=%s, work_duration=TIMEDIFF(%s, checkin_time), check_out_longitude=%s, check_out_latitude=%s, check_out_location_name=%s WHERE id=%s",
#                         (now, now, check_out_longitude, check_out_latitude, location_name, attendance['id'])
#                     )
#                     msg = f"Checked out successfully at {get_ist_time_for_display()}."
#                 else:
#                     msg = "You must check in first or have already checked out."

#     # Get user details
#     with conn.cursor() as cursor:
#         cursor.execute("SELECT firstname, lastname FROM t_users_hr WHERE id = %s", (user_id,))
#         user = cursor.fetchone()

#     # Get attendance history
#     with conn.cursor() as cursor:
#         cursor.execute("""
#         SELECT checkin_time, checkout_time, work_duration,
#                check_in_location_name, check_out_location_name, auto_checkout
#         FROM t_attendance_hr 
#         WHERE user_id = %s 
#         ORDER BY checkin_time DESC 
#         LIMIT 10
#         """, (user_id,))
#         history = cursor.fetchall()

#     conn.close()

#     return render_template(
#         'dashboard_user.html',
#         firstname=user['firstname'] if user else '',
#         lastname=user['lastname'] if user else '',
#         history=history,
#         msg=msg,
#         current_year=get_ist_date().year
#     )

# working
# @app.route('/user_dashboard', methods=['GET', 'POST'])
# def user_dashboard():
#     if 'user_id' not in session or session.get('role') == 2:
#         return redirect(url_for('login'))

#     # Get and clear any flashed messages
#     flashed_messages = get_flashed_messages()
#     msg = request.args.get('msg')
#     msg_type = request.args.get('msg_type', 'info')  # Default to 'info' if not specified
    
#     # Process flashed messages (only if no message from URL)
#     if not msg and flashed_messages:
#         # Use the first flashed message if exists
#         msg = flashed_messages[0][1]
#         msg_type = flashed_messages[0][0] if len(flashed_messages[0]) > 1 else 'info'

#     user_id = session['user_id']
#     conn = get_db_connection()
    
#     if request.method == 'POST':
#         action = request.form.get('action')
#         now = get_ist_now()  # Use IST time
        
#         latitude = request.form.get('latitude')
#         longitude = request.form.get('longitude')
#         location_name = request.form.get('location_name')

#         check_in_latitude = float(latitude) if latitude else None
#         check_in_longitude = float(longitude) if longitude else None

#         with conn.cursor() as cursor:
#             if action == 'checkin':
#                 cursor.execute("SELECT id FROM t_attendance_hr WHERE user_id=%s AND DATE(checkin_time) = %s", 
#                              (user_id, get_ist_date()))
                
#                 if cursor.fetchone():
#                     msg = "You have already checked in today."
#                     msg_type = 'warning'
#                 else:
#                     cursor.execute(
#                         "INSERT INTO t_attendance_hr (user_id, checkin_time, check_in_latitude, check_in_longitude, check_in_location_name) VALUES (%s, %s, %s, %s, %s)",
#                         (user_id, now, check_in_latitude, check_in_longitude, location_name)
#                     )
#                     msg = f"Checked in successfully at {get_ist_time_for_display()}."
#                     msg_type = 'success'

#             elif action == 'checkout':
#                 cursor.execute(
#                     "SELECT id, checkin_time FROM t_attendance_hr WHERE user_id=%s AND DATE(checkin_time) = %s AND checkout_time IS NULL",
#                     (user_id, get_ist_date())
#                 )
                
#                 attendance = cursor.fetchone()
#                 if attendance:
#                     check_out_latitude = float(latitude) if latitude else None
#                     check_out_longitude = float(longitude) if longitude else None

#                     cursor.execute(
#                         "UPDATE t_attendance_hr SET checkout_time=%s, work_duration=TIMEDIFF(%s, checkin_time), check_out_longitude=%s, check_out_latitude=%s, check_out_location_name=%s WHERE id=%s",
#                         (now, now, check_out_longitude, check_out_latitude, location_name, attendance['id'])
#                     )
#                     msg = f"Checked out successfully at {get_ist_time_for_display()}."
#                     msg_type = 'success'
#                 else:
#                     msg = "You must check in first or have already checked out."
#                     msg_type = 'warning'

#     # Get user details
#     with conn.cursor() as cursor:
#         cursor.execute("SELECT firstname, lastname FROM t_users_hr WHERE id = %s", (user_id,))
#         user = cursor.fetchone()

#     # Get attendance history
#     with conn.cursor() as cursor:
#         cursor.execute("""
#         SELECT checkin_time, checkout_time, work_duration,
#                check_in_location_name, check_out_location_name, auto_checkout
#         FROM t_attendance_hr 
#         WHERE user_id = %s 
#         ORDER BY checkin_time DESC 
#         LIMIT 10
#         """, (user_id,))
#         history = cursor.fetchall()

#     conn.close()

#     return render_template(
#         'dashboard_user.html',
#         firstname=user['firstname'] if user else '',
#         lastname=user['lastname'] if user else '',
#         history=history,
#         message=msg,
#         message_type=msg_type,
#         current_year=get_ist_date().year
#     )


# @app.route('/user_dashboard', methods=['GET', 'POST'])
# def user_dashboard():
#     # Authentication check
#     if 'user_id' not in session or session.get('role') == 2:
#         flash('Please login to access this page', 'error')
#         return redirect(url_for('login'))

#     # Initialize variables
#     user_id = session['user_id']
#     msg = None
#     msg_type = 'info'
#     user = None
#     history = []

#     # Process flashed messages
#     flashed_messages = get_flashed_messages(with_categories=True)
#     if flashed_messages:
#         # Use the most recent flashed message
#         msg_type, msg = flashed_messages[-1]

#     # Check for URL parameters (overrides flashed messages)
#     url_msg = request.args.get('msg')
#     if url_msg:
#         msg = url_msg
#         msg_type = request.args.get('msg_type', 'info')

#     # Database operations
#     conn = get_db_connection()
#     try:
#         # Handle POST requests (check-in/check-out)
#         if request.method == 'POST':
#             action = request.form.get('action')
#             now = get_ist_now()
            
#             # Get location data
#             latitude = request.form.get('latitude')
#             longitude = request.form.get('longitude')
#             location_name = request.form.get('location_name', '').strip()

#             with conn.cursor() as cursor:
#                 if action == 'checkin':
#                     # Check if already checked in today
#                     cursor.execute(
#                         "SELECT id FROM t_attendance_hr WHERE user_id=%s AND DATE(checkin_time) = %s", 
#                         (user_id, get_ist_date())
#                     )
                    
#                     if cursor.fetchone():
#                         msg = "You have already checked in today."
#                         msg_type = 'warning'
#                     else:
#                         # Record check-in
#                         cursor.execute(
#                             """INSERT INTO t_attendance_hr 
#                             (user_id, checkin_time, check_in_latitude, check_in_longitude, check_in_location_name) 
#                             VALUES (%s, %s, %s, %s, %s)""",
#                             (user_id, now, 
#                              float(latitude) if latitude else None,
#                              float(longitude) if longitude else None,
#                              location_name)
#                         )
#                         msg = f"Checked in successfully at {get_ist_time_for_display()}."
#                         msg_type = 'success'

#                 elif action == 'checkout':
#                     # Find today's check-in record
#                     cursor.execute(
#                         """SELECT id, checkin_time FROM t_attendance_hr 
#                         WHERE user_id=%s AND DATE(checkin_time) = %s AND checkout_time IS NULL""",
#                         (user_id, get_ist_date())
#                     )
                    
#                     attendance = cursor.fetchone()
#                     if attendance:
#                         # Record check-out
#                         cursor.execute(
#                             """UPDATE t_attendance_hr 
#                             SET checkout_time=%s, 
#                                 work_duration=TIMEDIFF(%s, checkin_time),
#                                 check_out_longitude=%s,
#                                 check_out_latitude=%s,
#                                 check_out_location_name=%s 
#                             WHERE id=%s""",
#                             (now, now,
#                              float(longitude) if longitude else None,
#                              float(latitude) if latitude else None,
#                              location_name,
#                              attendance['id'])
#                         )
#                         msg = f"Checked out successfully at {get_ist_time_for_display()}."
#                         msg_type = 'success'
#                     else:
#                         msg = "You must check in first or have already checked out."
#                         msg_type = 'warning'

#                 conn.commit()

#         # Get user details
#         with conn.cursor() as cursor:
#             cursor.execute(
#                 "SELECT firstname, lastname FROM t_users_hr WHERE id = %s", 
#                 (user_id,)
#             )
#             user = cursor.fetchone()

#         # Get attendance history
#         with conn.cursor() as cursor:
#             cursor.execute("""
#                 SELECT 
#                     checkin_time, 
#                     checkout_time, 
#                     work_duration,
#                     check_in_location_name, 
#                     check_out_location_name, 
#                     auto_checkout
#                 FROM t_attendance_hr 
#                 WHERE user_id = %s 
#                 ORDER BY checkin_time DESC 
#                 LIMIT 10
#                 """, (user_id,))
#             history = cursor.fetchall()

#     except Exception as e:
#         app.logger.error(f"Database error in user_dashboard: {str(e)}")
#         if not msg:  # Only override if no existing message
#             msg = "An error occurred while processing your request."
#             msg_type = 'error'
#     finally:
#         conn.close()

#     return render_template(
#         'dashboard_user.html',
#         firstname=user['firstname'] if user else '',
#         lastname=user['lastname'] if user else '',
#         history=history,
#         message=msg,
#         message_type=msg_type,
#         current_time=get_ist_now(),
#         current_year=get_ist_date().year
#     )

@app.route('/user_dashboard', methods=['GET', 'POST'])
def user_dashboard():
    # Authentication check
    if 'user_id' not in session or session.get('role') == 2:
        flash('Please login to access this page', 'error')
        return redirect(url_for('login'))

    # Initialize variables
    user_id = session['user_id']
    msg = None
    msg_type = 'info'
    user = None
    history = []

    # Process flashed messages - ENHANCED FOR LEAVE NOTIFICATIONS
    flashed_messages = get_flashed_messages(with_categories=True)
    if flashed_messages:
        # Use the most recent flashed message
        msg_type, msg = flashed_messages[-1]

    # Check for URL parameters (overrides flashed messages)
    url_msg = request.args.get('msg')
    if url_msg:
        msg = url_msg
        msg_type = request.args.get('msg_type', 'info')

    # Database operations
    conn = get_db_connection()
    try:
        # Handle POST requests (check-in/check-out)
        if request.method == 'POST':
            action = request.form.get('action')
            now = get_ist_now()
            
            # Get location data
            latitude = request.form.get('latitude')
            longitude = request.form.get('longitude')
            location_name = request.form.get('location_name', '').strip()

            with conn.cursor() as cursor:
                if action == 'checkin':
                    # Check if already checked in today
                    cursor.execute(
                        "SELECT id FROM t_attendance_hr WHERE user_id=%s AND DATE(checkin_time) = %s", 
                        (user_id, get_ist_date())
                    )
                    
                    if cursor.fetchone():
                        msg = "You have already checked in today."
                        msg_type = 'warning'
                    else:
                        # Record check-in
                        cursor.execute(
                            """INSERT INTO t_attendance_hr 
                            (user_id, checkin_time, check_in_latitude, check_in_longitude, check_in_location_name) 
                            VALUES (%s, %s, %s, %s, %s)""",
                            (user_id, now, 
                             float(latitude) if latitude else None,
                             float(longitude) if longitude else None,
                             location_name)
                        )
                        msg = f"Checked in successfully at {get_ist_time_for_display()}."
                        msg_type = 'success'

                elif action == 'checkout':
                    # Find today's check-in record
                    cursor.execute(
                        """SELECT id, checkin_time FROM t_attendance_hr 
                        WHERE user_id=%s AND DATE(checkin_time) = %s AND checkout_time IS NULL""",
                        (user_id, get_ist_date())
                    )
                    
                    attendance = cursor.fetchone()
                    if attendance:
                        # Record check-out
                        cursor.execute(
                            """UPDATE t_attendance_hr 
                            SET checkout_time=%s, 
                                work_duration=TIMEDIFF(%s, checkin_time),
                                check_out_longitude=%s,
                                check_out_latitude=%s,
                                check_out_location_name=%s 
                            WHERE id=%s""",
                            (now, now,
                             float(longitude) if longitude else None,
                             float(latitude) if latitude else None,
                             location_name,
                             attendance['id'])
                        )
                        msg = f"Checked out successfully at {get_ist_time_for_display()}."
                        msg_type = 'success'
                    else:
                        msg = "You must check in first or have already checked out."
                        msg_type = 'warning'

                conn.commit()

        # Get user details
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT firstname, lastname FROM t_users_hr WHERE id = %s", 
                (user_id,)
            )
            user = cursor.fetchone()

        # Get attendance history
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    checkin_time, 
                    checkout_time, 
                    work_duration,
                    check_in_location_name, 
                    check_out_location_name, 
                    auto_checkout
                FROM t_attendance_hr 
                WHERE user_id = %s 
                ORDER BY checkin_time DESC 
                LIMIT 10
                """, (user_id,))
            history = cursor.fetchall()

    except Exception as e:
        app.logger.error(f"Database error in user_dashboard: {str(e)}")
        if not msg:  # Only override if no existing message
            msg = "An error occurred while processing your request."
            msg_type = 'error'
    finally:
        conn.close()

    # ✅ UPDATED RETURN STATEMENT WITH CORRECT PARAMETER NAMES
    return render_template(
        'dashboard_user.html',
        firstname=user['firstname'] if user else '',
        lastname=user['lastname'] if user else '',
        history=history,
        msg=msg,                    # Changed from 'message' to 'msg'
        msg_type=msg_type,          # Changed from 'message_type' to 'msg_type'
        current_time=get_ist_now(),
        current_year=get_ist_date().year
    )
# Upload configuration
UPLOAD_FOLDER = 'static/uploads/profile_images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB max file size

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/user_profile', methods=['GET', 'POST'])
def user_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    conn = get_db_connection()
    
    if request.method == 'POST':
        # Handle image upload
        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file and file.filename != '' and allowed_file(file.filename):
                # Create upload directory if it doesn't exist
                os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                
                # Generate unique filename
                import uuid
                file_extension = file.filename.rsplit('.', 1)[1].lower()
                filename = f"profile_{user_id}_{uuid.uuid4().hex[:8]}.{file_extension}"
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                
                try:
                    # Save file
                    file.save(file_path)
                    
                    # Update database
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "UPDATE t_users_hr SET user_profile_image = %s WHERE id = %s",
                            (filename, user_id)
                        )
                    
                    flash('Profile image updated successfully!', 'success')
                except Exception as e:
                    flash(f'Error uploading image: {str(e)}', 'error')
            else:
                flash('Please select a valid image file (PNG, JPG, JPEG, GIF)', 'error')
    
    # Fetch user data
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
            SELECT firstname, lastname, phone, location, department,
                   designation, joining_date, gender, email, user_profile_image
            FROM t_users_hr
            WHERE id = %s
            LIMIT 1
            """, (user_id,))
            user = cursor.fetchone()
            
            if not user:
                return "User not found", 404
    finally:
        conn.close()
    
    return render_template('user_profile.html', user=user)

@app.route('/create_admin')
def create_admin():
    conn = get_db_connection()
    admin_email = 'admin@demo.com'
    admin_password = 'admin123'
    
    try:
        with conn.cursor() as cursor:
            # Check if admin already exists
            cursor.execute("SELECT id FROM t_users_hr WHERE email=%s", (admin_email,))
            if cursor.fetchone():
                return "Admin user already exists."
            
            # Hash the admin password
            hashed_password = hash_password(admin_password)
            
            cursor.execute(
                "INSERT INTO t_users_hr (firstname, lastname, is_active, email, password, role) VALUES (%s, %s, 1, %s, %s, 2)",
                ('Admin', 'User', admin_email, hashed_password)
            )
            
            return "Admin user created successfully. Email: admin@demo.com, Password: admin123"
    except Exception as e:
        return f"Error creating admin: {e}"
    finally:
        conn.close()

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    """Allow users to change their password"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    error = None
    success = None
    
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        if new_password != confirm_password:
            error = "New passwords do not match."
        elif len(new_password) < 6:
            error = "Password must be at least 6 characters long."
        else:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                # Verify current password
                cursor.execute("SELECT password FROM t_users_hr WHERE id=%s", (session['user_id'],))
                user = cursor.fetchone()
                
                if user and verify_password(current_password, user['password']):
                    # Update password
                    new_hashed_password = hash_password(new_password)
                    cursor.execute(
                        "UPDATE t_users_hr SET password=%s WHERE id=%s",
                        (new_hashed_password, session['user_id'])
                    )
                    success = "Password changed successfully!"
                else:
                    error = "Current password is incorrect."
            conn.close()
    
    return render_template('change_password.html', error=error, success=success)

@app.route('/monthly_report')
def monthly_report():
    if session.get('role') != 2:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    # Get month and year from query parameters
    selected_month = request.args.get('month', date.today().strftime('%Y-%m'))
    export_format = request.args.get('export', '')
    
    try:
        year, month = map(int, selected_month.split('-'))
        report_date = date(year, month, 1)
    except ValueError:
        report_date = date.today().replace(day=1)
        selected_month = report_date.strftime('%Y-%m')
    
    # Calculate date range for the month
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    
    with conn.cursor() as cursor:
        # Get all users and their attendance for the month
        cursor.execute("""
        SELECT 
            u.id,
            u.firstname,
            u.lastname,
            COUNT(DISTINCT DATE(a.checkin_time)) as days_present,
            COUNT(DISTINCT CASE WHEN a.checkout_time IS NOT NULL THEN DATE(a.checkin_time) END) as days_completed,
            SUM(TIME_TO_SEC(a.work_duration))/3600 as total_hours,
            AVG(TIME_TO_SEC(a.work_duration))/3600 as avg_hours_per_day,
            MIN(a.checkin_time) as first_checkin,
            MAX(a.checkout_time) as last_checkout,
            COUNT(DISTINCT CASE WHEN a.checkin_time IS NOT NULL AND a.checkout_time IS NULL THEN DATE(a.checkin_time) END) as incomplete_days,
            COUNT(DISTINCT CASE WHEN a.auto_checkout = 1 THEN DATE(a.checkin_time) END) as auto_checkout_days
        FROM t_users_hr u
        LEFT JOIN t_attendance_hr a ON u.id = a.user_id 
            AND DATE(a.checkin_time) >= %s
            AND DATE(a.checkin_time) < %s
        WHERE u.role = 1 AND u.is_active = 1
        GROUP BY u.id, u.firstname, u.lastname
        ORDER BY u.firstname, u.lastname
        """, (report_date, next_month))
        
        monthly_data = cursor.fetchall()
        
        # Calculate working days in the month (excluding weekends)
        cal = calendar.monthcalendar(year, month)
        working_days = sum(1 for week in cal for day in week[0:6] if day != 0)  # Mon-Fri only
        
        # Get total employee count
        cursor.execute("SELECT COUNT(*) as total_employees FROM t_users_hr WHERE role = 1 AND is_active = 1")
        total_employees = cursor.fetchone()['total_employees']
    
    conn.close()
    
    # Calculate summary statistics in Python
    active_employees = len([record for record in monthly_data if record.get('days_present', 0) > 0])
    total_hours_worked = sum(record.get('total_hours', 0) or 0 for record in monthly_data)
    
    summary_stats = {
        'active_employees': active_employees,
        'total_hours_worked': round(total_hours_worked, 1),
        'average_attendance': round(sum(record.get('days_present', 0) or 0 for record in monthly_data) / len(monthly_data) if monthly_data else 0, 1),
        'average_hours_per_employee': round(total_hours_worked / active_employees if active_employees > 0 else 0, 1)
    }
    
    # If export is requested, generate CSV or PDF
    if export_format == 'csv':
        return generate_csv_report(monthly_data, selected_month, working_days, total_employees)
    elif export_format == 'pdf':
        return generate_pdf_report(monthly_data, selected_month, working_days, total_employees)
    
    return render_template(
        'monthly_report.html',
        monthly_data=monthly_data,
        selected_month=selected_month,
        report_date=report_date,
        working_days=working_days,
        total_employees=total_employees,
        current_date=date.today(),
        summary_stats=summary_stats
    )

def generate_csv_report(monthly_data, selected_month, working_days, total_employees):
    """Generate CSV export of monthly report with auto-checkout indicators"""
    import calendar
    from datetime import datetime
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Parse selected_month to get year and month
    year, month = map(int, selected_month.split('-'))
    
    # Calculate total days in month and week offs (Sundays)
    total_days_in_month = calendar.monthrange(year, month)[1]
    
    # Count Sundays (week offs) in the month
    week_offs = 0
    for day in range(1, total_days_in_month + 1):
        date_obj = datetime(year, month, day)
        if date_obj.weekday() == 6:  # Sunday = 6 in Python (Monday = 0)
            week_offs += 1
    
    # Write header
    writer.writerow([f'Medscred HRMS - Monthly Attendance Report - {selected_month}'])
    writer.writerow([f'Total Working Days: {working_days}', f'Total Employees: {total_employees}', f'Week Offs (Sundays): {week_offs}'])
    writer.writerow([])  # Empty row
    
    # Write updated column headers - ADDED Auto-Checkout Days column
    writer.writerow([
        'Employee Name', 'Total Working Days', 'Week Offs', 'Days Present', 'Days Completed', 'Total Hours', 'Incomplete Days', 'Auto-Checkout Days'
    ])
    
    # Write data
    for record in monthly_data:
        auto_checkout_days = record.get('auto_checkout_days', 0)
        
        # Create employee name with indicator if they had auto-checkouts
        employee_name = f"{record['firstname']} {record['lastname']}"
        if auto_checkout_days > 0:
            employee_name += f" *{auto_checkout_days} auto*"  # Add asterisk indicator
        
        writer.writerow([
            employee_name,
            working_days,  # Total working days (same for all employees)
            week_offs,     # Week offs (same for all employees)
            record['days_present'] or 0,
            record['days_completed'] or 0,
            f"{record['total_hours']:.2f}" if record['total_hours'] else "0.00",
            record['incomplete_days'] or 0,
            auto_checkout_days  # NEW: Auto-checkout days count
        ])
    
    # Add legend at the bottom
    writer.writerow([])  # Empty row
        
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename=monthly_report_{selected_month}.csv"
    response.headers["Content-type"] = "text/csv"
    
    return response

def generate_pdf_report(monthly_data, selected_month, working_days, total_employees):
    """Generate PDF export of monthly report"""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        
        # Create styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1565c0'),
            alignment=1,  # Center alignment
            spaceAfter=20
        )
        
        # Content list
        content = []
        
        # Title
        title = Paragraph(f"Medscred HRMS - Monthly Attendance Report {selected_month}", title_style)
        content.append(title)
        content.append(Spacer(1, 20))
        
        # Summary info
        summary_data = [
            ['Total Working Days:', str(working_days)],
            ['Total Employees:', str(total_employees)],
            ['Report Generated:', date.today().strftime('%Y-%m-%d')]
        ]
        
        summary_table = Table(summary_data, colWidths=[2.5*inch, 1.5*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fbff')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e3f2fd'))
        ]))
        content.append(summary_table)
        content.append(Spacer(1, 30))
        
        # Data table
        if monthly_data:
            table_data = [['Employee Name', 'Days Present', 'Total Hours', 'Avg Hours/Day', 'Attendance %']]
            
            for record in monthly_data:
                attendance_pct = (record['days_present'] / working_days * 100) if working_days > 0 else 0
                table_data.append([
                    f"{record['firstname']} {record['lastname']}",
                    f"{record['days_present'] or 0} / {working_days}",
                    f"{record['total_hours']:.1f}h" if record['total_hours'] else "0.0h",
                    f"{record['avg_hours_per_day']:.1f}h" if record['avg_hours_per_day'] else "0.0h",
                    f"{attendance_pct:.1f}%"
                ])
            
            data_table = Table(table_data, colWidths=[2*inch, 1*inch, 1*inch, 1*inch, 1*inch])
            data_table.setStyle(TableStyle([
                # Header style
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2196f3')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                # Data style
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            content.append(data_table)
        else:
            no_data = Paragraph("No attendance data found for the selected month.", styles['Normal'])
            content.append(no_data)
        
        # Build PDF
        doc.build(content)
        buffer.seek(0)
        
        response = make_response(buffer.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename=monthly_report_{selected_month}.pdf"
        response.headers["Content-Type"] = "application/pdf"
        
        return response
        
    except ImportError:
        # If reportlab is not installed, return an error message
        from flask import jsonify
        return jsonify({
            'error': 'PDF generation requires reportlab library. Install it with: pip install reportlab'
        }), 500

@app.route('/attendance_analytics')
def attendance_analytics():
    """Advanced analytics dashboard"""
    if session.get('role') != 2:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    with conn.cursor() as cursor:
        # Late arrivals (after 9:30 AM)
        cursor.execute("""
        SELECT u.firstname, u.lastname, a.checkin_time, DATE(a.checkin_time) as date
        FROM t_attendance_hr a
        JOIN t_users_hr u ON a.user_id = u.id
        WHERE TIME(a.checkin_time) > '10:00:00'
        AND DATE(a.checkin_time) >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        AND u.role = 1
        ORDER BY a.checkin_time DESC
        LIMIT 50
        """)
        late_arrivals = cursor.fetchall()
        
        # Early departures (before 5:30 PM)
        cursor.execute("""
        SELECT u.firstname, u.lastname, a.checkout_time, DATE(a.checkout_time) as date
        FROM t_attendance_hr a
        JOIN t_users_hr u ON a.user_id = u.id
        WHERE TIME(a.checkout_time) < '07:00:00'
        AND a.checkout_time IS NOT NULL
        AND DATE(a.checkout_time) >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        AND u.role = 1
        ORDER BY a.checkout_time DESC
        LIMIT 50
        """)
        early_departures = cursor.fetchall()
        
        # Top performers (most hours worked)
        cursor.execute("""
        SELECT 
            u.firstname, u.lastname,
            SUM(TIME_TO_SEC(a.work_duration))/3600 as total_hours,
            COUNT(DISTINCT DATE(a.checkin_time)) as days_present
        FROM t_attendance_hr a
        JOIN t_users_hr u ON a.user_id = u.id
        WHERE DATE(a.checkin_time) >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        AND a.work_duration IS NOT NULL
        AND u.role = 1
        GROUP BY u.id, u.firstname, u.lastname
        HAVING total_hours > 0
        ORDER BY total_hours DESC
        LIMIT 10
        """)
        top_performers = cursor.fetchall()
    
    conn.close()
    
    return render_template(
        'attendance_analytics.html',
        late_arrivals=late_arrivals,
        early_departures=early_departures,
        top_performers=top_performers)


# @app.route('/apply_leave', methods=['GET', 'POST'])
# def apply_leave():
#     # Check if user is logged in
#     if 'user_id' not in session:
#         flash('Please login to access this page', 'error')
#         return redirect(url_for('login'))

#     if request.method == 'POST':
#         try:
#             # Get form data
#             user_id = session['user_id']
#             leave_type = request.form.get('leave_type')
#             start_date = request.form.get('start_date')
#             end_date = request.form.get('end_date')
#             reason = request.form.get('reason', '').strip()
#             half_day = 'half_day' in request.form
#             half_day_period = request.form.get('half_day_period') if half_day else None
#             emergency_contact = request.form.get('emergency_contact', '').strip()

#             # Validate required fields
#             if not all([leave_type, start_date, end_date, reason]):
#                 flash('All required fields must be filled', 'error')
#                 return render_template('apply_leave.html',
#                                     leave_type=leave_type,
#                                     start_date=start_date,
#                                     end_date=end_date,
#                                     reason=reason,
#                                     half_day=half_day,
#                                     half_day_period=half_day_period,
#                                     emergency_contact=emergency_contact)

#             # Date validation
#             try:
#                 start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
#                 end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
#                 today = get_ist_date()
#             except ValueError:
#                 flash('Invalid date format. Please use YYYY-MM-DD format', 'error')
#                 return render_template('apply_leave.html',
#                                     leave_type=leave_type,
#                                     start_date=start_date,
#                                     end_date=end_date,
#                                     reason=reason,
#                                     half_day=half_day,
#                                     half_day_period=half_day_period,
#                                     emergency_contact=emergency_contact)

#             # Business logic validation
#             if start_dt > end_dt:
#                 flash('End date cannot be before start date', 'error')
#                 return render_template('apply_leave.html',
#                                     leave_type=leave_type,
#                                     start_date=start_date,
#                                     end_date=end_date,
#                                     reason=reason,
#                                     half_day=half_day,
#                                     half_day_period=half_day_period,
#                                     emergency_contact=emergency_contact)

#             if start_dt < today:
#                 flash('Start date cannot be in the past', 'error')
#                 return render_template('apply_leave.html',
#                                     leave_type=leave_type,
#                                     start_date=start_date,
#                                     end_date=end_date,
#                                     reason=reason,
#                                     half_day=half_day,
#                                     half_day_period=half_day_period,
#                                     emergency_contact=emergency_contact)

#             # Calculate total days
#             total_days = 0.5 if half_day else (end_dt - start_dt).days + 1

#             # Database operations
#             conn = get_db_connection()
#             try:
#                 with conn.cursor() as cursor:
#                     # Check for overlapping leaves
#                     cursor.execute("""
#                         SELECT id FROM t_users_leave 
#                         WHERE user_id = %s 
#                         AND status IN ('pending', 'approved')
#                         AND (
#                             (start_date <= %s AND end_date >= %s) OR
#                             (start_date <= %s AND end_date >= %s) OR
#                             (start_date >= %s AND end_date <= %s)
#                         )
#                     """, (user_id, start_date, start_date, end_date, end_date, start_date, end_date))
                    
#                     if cursor.fetchone():
#                         flash('You already have a leave application for these dates', 'error')
#                         return render_template('apply_leave.html',
#                                             leave_type=leave_type,
#                                             start_date=start_date,
#                                             end_date=end_date,
#                                             reason=reason,
#                                             half_day=half_day,
#                                             half_day_period=half_day_period,
#                                             emergency_contact=emergency_contact)

#                     # Insert new leave application
#                     cursor.execute("""
#                         INSERT INTO t_users_leave 
#                         (user_id, leave_type, start_date, end_date, total_days, reason, 
#                          applied_date, half_day, half_day_period, emergency_contact)
#                         VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
#                     """, (user_id, leave_type, start_date, end_date, total_days, reason,
#                           get_ist_now(), half_day, half_day_period, emergency_contact))
                    
#                     conn.commit()

#                     # Successful submission - clear any existing messages
#                     get_flashed_messages()

#                     # Flash success message and redirect
#                     flash('Your leave application has been submitted successfully!', 'success')
#                     return redirect(url_for('user_dashboard'))

#             except Exception as e:
#                 conn.rollback()
#                 app.logger.error(f"Error submitting leave: {str(e)}")
#                 flash('An error occurred while submitting your leave application. Please try again.', 'error')
#                 return render_template('apply_leave.html',
#                                     leave_type=leave_type,
#                                     start_date=start_date,
#                                     end_date=end_date,
#                                     reason=reason,
#                                     half_day=half_day,
#                                     half_day_period=half_day_period,
#                                     emergency_contact=emergency_contact)
#             finally:
#                 conn.close()

#         except Exception as e:
#             app.logger.error(f"Unexpected error in apply_leave: {str(e)}")
#             flash('An unexpected error occurred. Please try again.', 'error')
#             return redirect(url_for('apply_leave'))

#     # GET request - clear any existing messages and show form
#     get_flashed_messages()
#     return render_template('apply_leave.html')

@app.route('/apply_leave', methods=['GET', 'POST'])
def apply_leave():
    # Check if user is logged in
    if 'user_id' not in session:
        flash('Please login to access this page', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            # Get form data
            user_id = session['user_id']
            leave_type = request.form.get('leave_type')
            start_date = request.form.get('start_date')
            end_date = request.form.get('end_date')
            reason = request.form.get('reason', '').strip()
            half_day = 'half_day' in request.form
            half_day_period = request.form.get('half_day_period') if half_day else None
            emergency_contact = request.form.get('emergency_contact', '').strip()

            # Validate required fields
            if not all([leave_type, start_date, end_date, reason]):
                flash('All required fields must be filled', 'error')
                return render_template('apply_leave.html',
                                    leave_type=leave_type,
                                    start_date=start_date,
                                    end_date=end_date,
                                    reason=reason,
                                    half_day=half_day,
                                    half_day_period=half_day_period,
                                    emergency_contact=emergency_contact)

            # Date validation
            try:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
                today = get_ist_date()
            except ValueError:
                flash('Invalid date format. Please use YYYY-MM-DD format', 'error')
                return render_template('apply_leave.html',
                                    leave_type=leave_type,
                                    start_date=start_date,
                                    end_date=end_date,
                                    reason=reason,
                                    half_day=half_day,
                                    half_day_period=half_day_period,
                                    emergency_contact=emergency_contact)

            # Business logic validation
            if start_dt > end_dt:
                flash('End date cannot be before start date', 'error')
                return render_template('apply_leave.html',
                                    leave_type=leave_type,
                                    start_date=start_date,
                                    end_date=end_date,
                                    reason=reason,
                                    half_day=half_day,
                                    half_day_period=half_day_period,
                                    emergency_contact=emergency_contact)

            if start_dt < today:
                flash('Start date cannot be in the past', 'error')
                return render_template('apply_leave.html',
                                    leave_type=leave_type,
                                    start_date=start_date,
                                    end_date=end_date,
                                    reason=reason,
                                    half_day=half_day,
                                    half_day_period=half_day_period,
                                    emergency_contact=emergency_contact)

            # Calculate total days
            total_days = 0.5 if half_day else (end_dt - start_dt).days + 1

            # Database operations
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    # Check for overlapping leaves
                    cursor.execute("""
                        SELECT id FROM t_users_leave 
                        WHERE user_id = %s 
                        AND status IN ('pending', 'approved')
                        AND (
                            (start_date <= %s AND end_date >= %s) OR
                            (start_date <= %s AND end_date >= %s) OR
                            (start_date >= %s AND end_date <= %s)
                        )
                    """, (user_id, start_date, start_date, end_date, end_date, start_date, end_date))
                    
                    if cursor.fetchone():
                        flash('You already have a leave application for these dates', 'error')
                        return render_template('apply_leave.html',
                                            leave_type=leave_type,
                                            start_date=start_date,
                                            end_date=end_date,
                                            reason=reason,
                                            half_day=half_day,
                                            half_day_period=half_day_period,
                                            emergency_contact=emergency_contact)

                    # Insert new leave application
                    cursor.execute("""
                        INSERT INTO t_users_leave 
                        (user_id, leave_type, start_date, end_date, total_days, reason, 
                         applied_date, half_day, half_day_period, emergency_contact)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (user_id, leave_type, start_date, end_date, total_days, reason,
                          get_ist_now(), half_day, half_day_period, emergency_contact))
                    
                    conn.commit()

                    # ✅ ENHANCED SUCCESS MESSAGE WITH DETAILED INFORMATION
                    if half_day:
                        duration_text = f"half-day ({half_day_period})"
                        date_text = start_date
                    elif start_date == end_date:
                        duration_text = "1 day"
                        date_text = start_date
                    else:
                        duration_text = f"{int(total_days)} days"
                        date_text = f"{start_date} to {end_date}"
                    
                    success_message = f'Leave application submitted successfully! Your {leave_type} request for {duration_text} ({date_text}) is now under review.'
                    flash(success_message, 'success')
                    
                    return redirect(url_for('user_dashboard'))

            except Exception as e:
                conn.rollback()
                app.logger.error(f"Error submitting leave: {str(e)}")
                flash('An error occurred while submitting your leave application. Please try again.', 'error')
                return render_template('apply_leave.html',
                                    leave_type=leave_type,
                                    start_date=start_date,
                                    end_date=end_date,
                                    reason=reason,
                                    half_day=half_day,
                                    half_day_period=half_day_period,
                                    emergency_contact=emergency_contact)
            finally:
                conn.close()

        except Exception as e:
            app.logger.error(f"Unexpected error in apply_leave: {str(e)}")
            flash('An unexpected error occurred. Please try again.', 'error')
            return redirect(url_for('apply_leave'))

    # GET request - clear any existing messages and show form
    get_flashed_messages()
    return render_template('apply_leave.html')

@app.route('/my_leaves')
def my_leaves():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT l.*, u.firstname, u.lastname 
                FROM t_users_leave l
                LEFT JOIN t_users_hr u ON l.approved_by = u.id
                WHERE l.user_id = %s
                ORDER BY l.applied_date DESC
            """, (session['user_id'],))
            leaves = cursor.fetchall()
            
        return render_template('my_leaves.html', leaves=leaves)
    except Exception as e:
        print(f"Error fetching leaves: {e}")
        return render_template('my_leaves.html', leaves=[], error=str(e))
    finally:
        conn.close()


@app.route('/admin_leaves')
def admin_leaves():
    if 'user_id' not in session or session.get('role') != 2:
        return redirect(url_for('login'))
    
    status_filter = request.args.get('status', 'all')
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if status_filter == 'all':
                cursor.execute("""
                    SELECT l.*, u.firstname, u.lastname, u.email, u.designation,
                           a.firstname as approved_by_fname, a.lastname as approved_by_lname
                    FROM t_users_leave l
                    JOIN t_users_hr u ON l.user_id = u.id
                    LEFT JOIN t_users_hr a ON l.approved_by = a.id
                    ORDER BY l.applied_date DESC
                """)
            else:
                cursor.execute("""
                    SELECT l.*, u.firstname, u.lastname, u.email, u.designation,
                           a.firstname as approved_by_fname, a.lastname as approved_by_lname
                    FROM t_users_leave l
                    JOIN t_users_hr u ON l.user_id = u.id
                    LEFT JOIN t_users_hr a ON l.approved_by = a.id
                    WHERE l.status = %s
                    ORDER BY l.applied_date DESC
                """, (status_filter,))
            
            leaves = cursor.fetchall()
            
        return render_template('admin_leaves.html', leaves=leaves, status_filter=status_filter)
    except Exception as e:
        print(f"Error fetching admin leaves: {e}")
        return render_template('admin_leaves.html', leaves=[], error=str(e))
    finally:
        conn.close()

@app.route('/approve_leave/<int:leave_id>', methods=['POST'])
def approve_leave(leave_id):
    print(f"Approve/Reject route called for leave_id: {leave_id}")  # Debug line
    
    if 'user_id' not in session:
        print("No user_id in session")  # Debug line
        return redirect(url_for('login'))
    
    # Check if user is admin - adjust this based on your role system
    user_role = session.get('role')
    print(f"User role: {user_role}")  # Debug line
    
    # Change this condition based on how you store admin role
    if user_role != 2 and user_role != 'admin':  # Adjust this based on your system
        print("User is not admin")  # Debug line
        return redirect(url_for('login'))
    
    action = request.form.get('action')
    admin_comments = request.form.get('admin_comments', '').strip()
    
    print(f"Action: {action}, Comments: {admin_comments}")  # Debug line
    
    if action not in ['approve', 'reject']:
        return redirect(url_for('admin_leaves', error="Invalid action"))
    
    new_status = 'approved' if action == 'approve' else 'rejected'
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE t_users_leave 
                SET status = %s, approved_by = %s, approved_date = %s, admin_comments = %s
                WHERE id = %s
            """, (new_status, session['user_id'], get_ist_now(), admin_comments, leave_id))
            
            conn.commit()  # Make sure to commit the transaction
            
        success_msg = f"Leave application {action}d successfully!"
        return redirect(url_for('admin_leaves', msg=success_msg))
        
    except Exception as e:
        print(f"Database error: {e}")  # Debug line
        return redirect(url_for('admin_leaves', error=f"Error {action}ing leave: {str(e)}"))
    finally:
        conn.close()


@app.route('/leave_details/<int:leave_id>')
def leave_details(leave_id):
    if 'user_id' not in session or session.get('role') != 2:
        return redirect(url_for('login'))

    user_role = session.get('role')
    if user_role != 2 and user_role != 'admin':  # Adjust this condition
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT l.*, u.firstname, u.lastname, u.email, u.designation, u.phone,
                       a.firstname as approved_by_fname, a.lastname as approved_by_lname
                FROM t_users_leave l
                JOIN t_users_hr u ON l.user_id = u.id
                LEFT JOIN t_users_hr a ON l.approved_by = a.id
                WHERE l.id = %s
            """, (leave_id,))
            
            leave = cursor.fetchone()
            
        if not leave:
            return redirect(url_for('admin_leaves', error="Leave application not found"))
            
        return render_template('leave_details.html', leave=leave)
    except Exception as e:
        return redirect(url_for('admin_leaves', error=f"Error fetching leave details: {str(e)}"))
    finally:
        conn.close()


@app.route('/employee_profile/<int:user_id>')
def employee_profile(user_id):
    """Individual employee attendance profile"""
    if session.get('role') != 2:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    with conn.cursor() as cursor:
        # Get employee details
        cursor.execute("""
        SELECT u.*, r.role_name
        FROM t_users_hr u
        LEFT JOIN roles_hr r ON u.role = r.role
        WHERE u.id = %s
        """, (user_id,))
        employee = cursor.fetchone()
        
        if not employee:
            return redirect(url_for('user_list'))
        
        # Get recent attendance (last 30 days)
        cursor.execute("""
        SELECT 
            DATE(checkin_time) as date,
            checkin_time,
            checkout_time,
            work_duration,
            latitude,
            longitude,
            location_name
        FROM t_attendance_hr
        WHERE user_id = %s
        AND DATE(checkin_time) >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        ORDER BY checkin_time DESC
        """, (user_id,))
        recent_attendance = cursor.fetchall()
        
        # Calculate statistics
        cursor.execute("""
        SELECT 
            COUNT(DISTINCT DATE(checkin_time)) as total_days,
            AVG(TIME_TO_SEC(work_duration))/3600 as avg_hours,
            SUM(TIME_TO_SEC(work_duration))/3600 as total_hours,
            COUNT(CASE WHEN TIME(checkin_time) > '09:30:00' THEN 1 END) as late_count
        FROM t_attendance_hr
        WHERE user_id = %s
        AND DATE(checkin_time) >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        AND work_duration IS NOT NULL
        """, (user_id,))
        stats = cursor.fetchone()
    
    conn.close()
    
    return render_template(
        'employee_profile.html',
        employee=employee,
        recent_attendance=recent_attendance,
        stats=stats
    )

@app.route('/favicon.ico')
def favicon():
    from flask import send_from_directory
    return send_from_directory(os.path.join(app.root_path, 'static'),
                             'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/test_db')
def test_db():
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 as test")
            result = cursor.fetchone()
        conn.close()
        return f"✅ Database connection successful! Result: {result}"
    except Exception as e:
        return f"❌ Database connection FAILED: {e}"

@app.route('/test_health')
def test_health():
    return "✅ App is running fine!", 200

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('errors/500.html'), 500

# Context processor to make current year available in all templates
@app.context_processor
def inject_current_year():
    return {'current_year': date.today().year}




if __name__ == '__main__':
    try:
        conn = get_db_connection()
        print("✅ Connected to the MySQL database.")
        print(f"📊 Database: {app.config['MYSQL_DB_NAME']}")
        print(f"🖥️ Host: {app.config['MYSQL_HOST_NAME']}")
        conn.close()
    except Exception as e:
        print("❌ Database connection error:", e)
    
    # Get port from environment or use default
    # port = int(os.environ.get('PORT', 5000))
    # host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    
    print(f"🚀 Starting Flask app on {host}:{port}")
    print(f"🔧 Debug mode: {app.config['DEBUG']}")
    print(f"🌍 Environment: {os.environ.get('APP_ENV', 'development')}")
    
    # Start scheduler only once and before app.run()
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        scheduler.start()
        print("📅 Scheduler started - Auto-checkout will run at 23:59:59 daily")
    
    app.run(debug=app.config['DEBUG'], port=port, host=host)


