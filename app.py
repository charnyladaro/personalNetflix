from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, abort, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
import ipaddress
from datetime import datetime
from functools import wraps
from PIL import Image, ImageDraw, ImageFont
import re

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'

# Configuration
UPLOAD_FOLDER = 'uploads/videos'
THUMBNAIL_FOLDER = 'uploads/thumbnails'
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mkv', 'mov', 'wmv'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['THUMBNAIL_FOLDER'] = THUMBNAIL_FOLDER

# Create directories if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(THUMBNAIL_FOLDER, exist_ok=True)

def sanitize_folder_name(name):
    """Sanitize series name for use as folder name"""
    # Remove or replace invalid characters for folder names
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Remove multiple spaces and replace with single underscore
    sanitized = re.sub(r'\s+', '_', sanitized)
    # Remove leading/trailing dots and spaces
    sanitized = sanitized.strip('. ')
    # Ensure it's not empty
    if not sanitized:
        sanitized = "Unknown_Series"
    return sanitized

def create_series_folder(series_name):
    """Create a folder for the series if it doesn't exist"""
    if not series_name:
        return None
    
    folder_name = sanitize_folder_name(series_name)
    series_folder_path = os.path.join(app.config['UPLOAD_FOLDER'], folder_name)
    
    # Create the series folder if it doesn't exist
    os.makedirs(series_folder_path, exist_ok=True)
    
    return folder_name

def get_video_file_path(video_filename, series_name=None):
    """Get the full path for video file, considering series folder"""
    if series_name:
        folder_name = sanitize_folder_name(series_name)
        return os.path.join(folder_name, video_filename)
    return video_filename

def get_full_video_path(relative_path):
    """Get the absolute path for video file"""
    return os.path.join(app.config['UPLOAD_FOLDER'], relative_path)

# Initialize database on app startup
def ensure_db_initialized():
    """Ensure database is initialized when app starts"""
    try:
        init_db()
        print("Database initialized successfully")
    except Exception as e:
        print(f"Warning: Could not initialize database on startup: {e}")

# Call this function when the app starts
ensure_db_initialized()

def get_featured_movie():
    """Get a featured movie - automatically selects the most recent upload"""
    try:
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Check if table exists first
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='movies'")
        if not c.fetchone():
            conn.close()
            return None
        
        # Get the most recently uploaded standalone movie with a thumbnail
        c.execute("""
            SELECT * FROM movies 
            WHERE (is_series = 0 OR is_series IS NULL) 
            AND thumbnail_file IS NOT NULL
            ORDER BY uploaded_at DESC 
            LIMIT 1
        """)
        
        featured_movie = c.fetchone()
        conn.close()
        return featured_movie
    except Exception as e:
        print(f"Error getting featured movie: {e}")
        return None

def check_opencv_available():
    """Check if OpenCV is available"""
    try:
        import cv2
        return True
    except ImportError:
        return False

def check_moviepy_available():
    """Check if moviepy is available"""
    try:
        from moviepy.editor import VideoFileClip
        return True
    except ImportError:
        return False

def generate_thumbnail_opencv(video_path, thumbnail_path, timestamp=10):
    """Generate thumbnail using OpenCV"""
    try:
        import cv2
        
        cap = cv2.VideoCapture(video_path)
        
        # Get video properties
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        duration = total_frames / fps if fps > 0 else 0
        
        # Choose timestamp (10 seconds or 10% of video duration)
        target_time = min(timestamp, duration * 0.1) if duration > 0 else timestamp
        frame_number = int(fps * target_time) if fps > 0 else 0
        
        # Set frame position
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        
        # Read frame
        ret, frame = cap.read()
        if ret:
            # Resize frame to thumbnail size
            height, width = frame.shape[:2]
            new_width = 320
            new_height = int((new_width / width) * height)
            resized = cv2.resize(frame, (new_width, new_height))
            
            # Save thumbnail
            success = cv2.imwrite(thumbnail_path, resized)
            cap.release()
            return success
        
        cap.release()
        return False
    except Exception as e:
        print(f"OpenCV thumbnail generation error: {e}")
        return False

def generate_thumbnail_moviepy(video_path, thumbnail_path, timestamp=10):
    """Generate thumbnail using moviepy"""
    try:
        from moviepy.editor import VideoFileClip
        
        clip = VideoFileClip(video_path)
        duration = clip.duration
        
        # Choose timestamp (10 seconds or 10% of video duration)
        target_time = min(timestamp, duration * 0.1) if duration > 0 else timestamp
        
        # Get frame at specified time
        frame = clip.get_frame(target_time)
        
        # Convert to PIL Image and save
        img = Image.fromarray(frame.astype('uint8'))
        img.thumbnail((320, 240), Image.Resampling.LANCZOS)
        img.save(thumbnail_path, 'JPEG', quality=85)
        
        clip.close()
        return True
    except Exception as e:
        print(f"MoviePy thumbnail generation error: {e}")
        return False

def generate_thumbnail_pillow_only(video_path, thumbnail_path):
    """Generate a simple placeholder thumbnail using PIL"""
    try:
        # Create a placeholder image
        img = Image.new('RGB', (320, 240), color='#333333')
        draw = ImageDraw.Draw(img)
        
        # Try to load a font, fallback to default
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except:
            font = ImageFont.load_default()
        
        # Get video filename
        video_name = os.path.basename(video_path)
        name_without_ext = os.path.splitext(video_name)[0]
        
        # Draw text
        text = f"🎬\n{name_without_ext[:20]}"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        x = (320 - text_width) // 2
        y = (240 - text_height) // 2
        
        draw.text((x, y), text, fill='#FFFFFF', font=font, align='center')
        
        # Save thumbnail
        img.save(thumbnail_path, 'JPEG', quality=85)
        return True
    except Exception as e:
        print(f"PIL thumbnail generation error: {e}")
        return False

def auto_generate_thumbnail(video_path, thumbnail_filename):
    """Try multiple methods to generate thumbnail"""
    thumbnail_path = os.path.join(app.config['THUMBNAIL_FOLDER'], thumbnail_filename)
    
    # Method 1: Try OpenCV
    if check_opencv_available():
        print("Trying OpenCV for thumbnail generation...")
        if generate_thumbnail_opencv(video_path, thumbnail_path):
            print("✓ OpenCV thumbnail generated successfully")
            return thumbnail_filename, True
    
    # Method 2: Try MoviePy
    if check_moviepy_available():
        print("Trying MoviePy for thumbnail generation...")
        if generate_thumbnail_moviepy(video_path, thumbnail_path):
            print("✓ MoviePy thumbnail generated successfully")
            return thumbnail_filename, True
    
    # Method 3: PIL placeholder
    print("Generating placeholder thumbnail with PIL...")
    if generate_thumbnail_pillow_only(video_path, thumbnail_path):
        print("✓ Placeholder thumbnail generated")
        return thumbnail_filename, False  # False indicates it's not a real video frame
    
    print("✗ All thumbnail generation methods failed")
    return None, False

def get_client_ip():
    """Get client IP address from various sources with Docker support"""
    try:
        # Check for forwarded IP first (most common in Docker setups)
        if request.headers.get('X-Forwarded-For'):
            # Get the first IP in the list (original client)
            forwarded_ips = request.headers.get('X-Forwarded-For').split(',')
            client_ip = forwarded_ips[0].strip()
            print(f"Got IP from X-Forwarded-For: {client_ip}")
            return client_ip
        
        # Check for real IP
        if request.headers.get('X-Real-IP'):
            client_ip = request.headers.get('X-Real-IP')
            print(f"Got IP from X-Real-IP: {client_ip}")
            return client_ip
        
        # Fallback to remote address
        client_ip = request.remote_addr
        print(f"Got IP from remote_addr: {client_ip}")
        
        # Docker bridge network fix - if we get Docker internal IP, assume localhost
        if client_ip and (client_ip.startswith('172.') or client_ip.startswith('192.168.') or client_ip == '::1'):
            print(f"Docker internal IP detected ({client_ip}), treating as localhost")
            return "127.0.0.1"
            
        return client_ip
    except Exception as e:
        print(f"Error in get_client_ip: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        # Fallback to localhost
        return "127.0.0.1"

def get_whitelisted_ips():
    """Get all whitelisted IPs from database"""
    try:
        print("Getting whitelisted IPs...")
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Check if table exists first
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ip_whitelist'")
        if not c.fetchone():
            print("IP whitelist table not found")
            conn.close()
            return set()
            
        c.execute("SELECT ip_address FROM ip_whitelist WHERE is_active = 1")
        ips = {row[0] for row in c.fetchall()}
        conn.close()
        print(f"Found whitelisted IPs: {ips}")
        return ips
    except Exception as e:
        print(f"Error getting whitelisted IPs: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        return set()

def validate_ip_address(ip):
    """Validate if the provided string is a valid IP address"""
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False

def ip_whitelist_required(f):
    """Decorator to check if IP is whitelisted - applies to ALL routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            print(f"IP whitelist check for function: {f.__name__}")
            # Get client IP
            client_ip = get_client_ip()
            whitelisted_ips = get_whitelisted_ips()
            
            print(f"Access attempt from IP: {client_ip}")
            print(f"Whitelisted IPs: {whitelisted_ips}")
            
            # Check IP whitelist BEFORE any other checks
            if client_ip not in whitelisted_ips:
                print(f"IP {client_ip} not in whitelist, blocking access")
                # Log the blocked attempt
                log_access_attempt(f"BLOCKED access from {client_ip}", False)
                return render_template('ip_blocked.html', current_ip=client_ip)
            
            print(f"IP {client_ip} is whitelisted, allowing access")
            return f(*args, **kwargs)
        except Exception as e:
            print(f"Error in ip_whitelist_required decorator: {e}")
            print(f"Error type: {type(e)}")
            import traceback
            traceback.print_exc()
            # If there's an error, allow access to prevent complete blocking
            return f(*args, **kwargs)
    
    return decorated_function

def admin_required(f):
    """Decorator to check if user is admin (IP already checked by ip_whitelist_required)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Only guard the privilege check; let downstream errors propagate
        try:
            print(f"Admin required check - user_id: {session.get('user_id')}, is_admin: {session.get('is_admin')}")
            if 'user_id' not in session or not session.get('is_admin'):
                print("Admin check failed - not logged in or not admin")
                flash('Access denied. Admin privileges required.')
                return redirect(url_for('login'))
            print("Admin check passed")
        except Exception as e:
            print(f"Error in admin_required decorator: {e}")
            print(f"Error type: {type(e)}")
            import traceback
            traceback.print_exc()
            flash('Error checking admin privileges. Please try again.')
            return redirect(url_for('login'))
        # Call the wrapped view outside of the try so genuine errors surface
        return f(*args, **kwargs)
    
    return decorated_function

def login_required(f):
    """Decorator to check if user is logged in (IP already checked by ip_whitelist_required)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            print(f"Login required check for function: {f.__name__}")
            print(f"Session user_id: {session.get('user_id')}")
            if 'user_id' not in session:
                print("Login check failed - not logged in")
                return redirect(url_for('login'))
            
            print("Login check passed")
            return f(*args, **kwargs)
        except Exception as e:
            print(f"Error in login_required decorator: {e}")
            print(f"Error type: {type(e)}")
            import traceback
            traceback.print_exc()
            flash('Error checking login status. Please try again.')
            return redirect(url_for('login'))
    
    return decorated_function

def allowed_file(filename, allowed_extensions):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def get_grouped_content():
    """Get movies and series grouped appropriately"""
    try:
        print("Getting grouped content...")
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Check if table exists first
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='movies'")
        if not c.fetchone():
            print("Movies table not found")
            conn.close()
            return [], []
        
        # Get standalone movies
        c.execute("""
            SELECT * FROM movies 
            WHERE is_series = 0 OR is_series IS NULL
            ORDER BY uploaded_at DESC
        """)
        movies = c.fetchall()
        print(f"Found {len(movies)} standalone movies")
        
        # Get series grouped by series name
        c.execute("""
            SELECT series_name, COUNT(*) as episode_count,
                   MIN(uploaded_at) as first_uploaded,
                   GROUP_CONCAT(id) as episode_ids,
                   (SELECT thumbnail_file FROM movies m2 
                    WHERE m2.series_name = m1.series_name 
                    AND m2.season_number = 1 AND m2.episode_number = 1 
                    LIMIT 1) as series_thumbnail
            FROM movies m1
            WHERE is_series = 1
            GROUP BY series_name
            ORDER BY first_uploaded DESC
        """)
        series = c.fetchall()
        print(f"Found {len(series)} series")
        
        conn.close()
        return movies, series
    except Exception as e:
        print(f"Error getting grouped content: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        return [], []

def get_pending_movie_requests_count():
    """Get count of pending movie requests"""
    try:
        print("Getting pending movie requests count...")
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Check if table exists first
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='movie_requests'")
        if not c.fetchone():
            print("Movie requests table not found")
            conn.close()
            return 0
            
        c.execute("SELECT COUNT(*) FROM movie_requests WHERE status = 'pending'")
        count = c.fetchone()[0]
        conn.close()
        print(f"Found {count} pending movie requests")
        return count
    except Exception as e:
        print(f"Error getting pending movie requests count: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        return 0

def get_user_movie_requests(user_id, limit=20):
    """Get movie requests for a specific user"""
    try:
        print(f"Getting movie requests for user {user_id}...")
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Check if table exists first
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='movie_requests'")
        if not c.fetchone():
            print("Movie requests table not found")
            conn.close()
            return []
            
        c.execute("""
            SELECT mr.*, u.username as processed_by_username
            FROM movie_requests mr
            LEFT JOIN users u ON mr.processed_by = u.id
            WHERE mr.user_id = ?
            ORDER BY mr.requested_at DESC
            LIMIT ?
        """, (user_id, limit))
        requests = c.fetchall()
        conn.close()
        print(f"Found {len(requests)} movie requests for user {user_id}")
        return requests
    except Exception as e:
        print(f"Error getting user movie requests: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        return []

def get_pending_requests_count():
    """Get count of pending IP access requests"""
    try:
        print("Getting pending requests count...")
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Check if table exists first
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ip_access_requests'")
        if not c.fetchone():
            print("IP access requests table not found")
            conn.close()
            return 0
            
        c.execute("SELECT COUNT(*) FROM ip_access_requests WHERE status = 'pending'")
        count = c.fetchone()[0]
        conn.close()
        print(f"Found {count} pending IP access requests")
        return count
    except Exception as e:
        print(f"Error getting pending requests count: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        return 0

def get_series_episodes(series_name):
    """Get all episodes for a specific series"""
    try:
        print(f"Getting series episodes for: {series_name}")
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Check if table exists first
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='movies'")
        if not c.fetchone():
            print("Movies table not found")
            conn.close()
            return []
            
        c.execute("""
            SELECT * FROM movies 
            WHERE series_name = ? AND is_series = 1
            ORDER BY season_number ASC, episode_number ASC
        """, (series_name,))
        episodes = c.fetchall()
        conn.close()
        print(f"Found {len(episodes)} episodes for series {series_name}")
        return episodes
    except Exception as e:
        print(f"Error getting series episodes: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        return []

def init_db():
    conn = sqlite3.connect('netflix.db')
    c = conn.cursor()
    
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Movies table (updated with series support)
    c.execute('''
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            genre TEXT,
            duration INTEGER,
            release_year INTEGER,
            video_file TEXT NOT NULL,
            thumbnail_file TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            auto_generated_thumb INTEGER DEFAULT 0,
            is_series INTEGER DEFAULT 0,
            series_name TEXT,
            season_number INTEGER,
            episode_number INTEGER,
            episode_title TEXT
        )
    ''')
    
    # Add series columns if they don't exist (for existing databases)
    try:
        c.execute('ALTER TABLE movies ADD COLUMN is_series INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    try:
        c.execute('ALTER TABLE movies ADD COLUMN series_name TEXT')
    except sqlite3.OperationalError:
        pass
    
    try:
        c.execute('ALTER TABLE movies ADD COLUMN season_number INTEGER')
    except sqlite3.OperationalError:
        pass
    
    try:
        c.execute('ALTER TABLE movies ADD COLUMN episode_number INTEGER')
    except sqlite3.OperationalError:
        pass
    
    try:
        c.execute('ALTER TABLE movies ADD COLUMN episode_title TEXT')
    except sqlite3.OperationalError:
        pass
    
    # Add Movie Requests table
    c.execute('''
        CREATE TABLE IF NOT EXISTS movie_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            request_type TEXT DEFAULT 'movie',
            genre TEXT,
            release_year INTEGER,
            series_name TEXT,
            season_number INTEGER,
            episode_number INTEGER,
            imdb_link TEXT,
            additional_info TEXT,
            status TEXT DEFAULT 'pending',
            admin_notes TEXT,
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP,
            processed_by INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (processed_by) REFERENCES users (id)
        )
    ''')
    
    # IP Whitelist table
    c.execute('''
        CREATE TABLE IF NOT EXISTS ip_whitelist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT UNIQUE NOT NULL,
            description TEXT,
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (added_by) REFERENCES users (id)
        )
    ''')
    
    # IP Access Requests table
    c.execute('''
        CREATE TABLE IF NOT EXISTS ip_access_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT NOT NULL,
            name TEXT,
            reason TEXT,
            request_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending',
            processed_time TIMESTAMP,
            processed_by INTEGER,
            FOREIGN KEY (processed_by) REFERENCES users (id)
        )
    ''')
    
    # Admin access log table
    c.execute('''
        CREATE TABLE IF NOT EXISTS admin_access_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            ip_address TEXT,
            access_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            action TEXT,
            success INTEGER DEFAULT 1
        )
    ''')
    
    # General access log table for non-admin users
    c.execute('''
        CREATE TABLE IF NOT EXISTS access_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            ip_address TEXT,
            access_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            action TEXT,
            success INTEGER DEFAULT 1
        )
    ''')
    
    # Create admin user if it doesn't exist
    c.execute("SELECT * FROM users WHERE username = 'admin'")
    if not c.fetchone():
        admin_password = generate_password_hash('admin123')  # Change this password!
        c.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, 1)", 
                 ('admin', admin_password))
    
    # Add default localhost IPs to whitelist if table is empty
    c.execute("SELECT COUNT(*) FROM ip_whitelist")
    if c.fetchone()[0] == 0:
        default_ips = [
            ('127.0.0.1', 'Localhost IPv4'),
            ('::1', 'Localhost IPv6'),
            ('192.168.1.102', 'My Local Network IP')
        ]
        for ip, desc in default_ips:
            c.execute("INSERT OR IGNORE INTO ip_whitelist (ip_address, description) VALUES (?, ?)", (ip, desc))
    
    conn.commit()
    conn.close()

def log_admin_access(action, success=True):
    """Log admin access attempts"""
    try:
        print(f"Attempting to log admin access: {action}, success: {success}")
        print(f"Session user_id: {session.get('user_id')}")
        print(f"Client IP: {get_client_ip()}")
        
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Check if table exists first
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='admin_access_log'")
        if not c.fetchone():
            print("Admin access log table not found")
            conn.close()
            return
            
        c.execute("""
            INSERT INTO admin_access_log (user_id, ip_address, action, success)
            VALUES (?, ?, ?, ?)
        """, (session.get('user_id'), get_client_ip(), action, 1 if success else 0))
        conn.commit()
        conn.close()
        print("Admin access logged successfully")
    except Exception as e:
        print(f"Error logging admin access: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()

def log_access_attempt(action, success=True):
    """Log general access attempts"""
    try:
        print(f"Attempting to log access attempt: {action}, success: {success}")
        print(f"Session user_id: {session.get('user_id')}")
        print(f"Client IP: {get_client_ip()}")
        
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Check if table exists first
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='access_log'")
        if not c.fetchone():
            print("Access log table not found")
            conn.close()
            return
            
        c.execute("""
            INSERT INTO access_log (user_id, ip_address, action, success)
            VALUES (?, ?, ?, ?)
        """, (session.get('user_id'), get_client_ip(), action, 1 if success else 0))
        conn.commit()
        conn.close()
        print("Access attempt logged successfully")
    except Exception as e:
        print(f"Error logging access attempt: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()

# Apply IP whitelist check to ALL routes
@app.before_request
def check_ip_whitelist():
    """Check IP whitelist before every request"""
    # Skip IP check for static files only
    if request.endpoint and request.endpoint.startswith('static'):
        return
    
    try:
        print(f"IP whitelist check for endpoint: {request.endpoint}")
        client_ip = get_client_ip()
        whitelisted_ips = get_whitelisted_ips()
        
        print(f"Before request - IP: {client_ip}, Whitelisted: {whitelisted_ips}")
        
        # If IP is whitelisted, allow access to all routes
        if client_ip in whitelisted_ips:
            print(f"IP {client_ip} is whitelisted, allowing access")
            return
        
        # If IP is not whitelisted, only allow access to request_ip_access and serve_thumbnail
        if request.endpoint not in ['request_ip_access', 'serve_thumbnail']:
            print(f"IP {client_ip} not whitelisted, blocking access to {request.endpoint}")
            log_access_attempt(f"BLOCKED access to {request.endpoint} from {client_ip}", False)
            
            # Check if there's already a pending request for this IP
            try:
                conn = sqlite3.connect('netflix.db')
                c = conn.cursor()
                
                # Check if table exists first
                c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ip_access_requests'")
                if c.fetchone():
                    c.execute("SELECT id FROM ip_access_requests WHERE ip_address = ? AND status = 'pending'", (client_ip,))
                    existing_request = c.fetchone()
                else:
                    existing_request = None
                conn.close()
                
                print(f"Existing request for IP {client_ip}: {existing_request}")
                return render_template('ip_blocked.html', 
                                     current_ip=client_ip, 
                                     has_pending_request=existing_request is not None)
            except Exception as e:
                print(f"Error checking IP access requests: {e}")
                return render_template('ip_blocked.html', 
                                     current_ip=client_ip, 
                                     has_pending_request=False)
    except Exception as e:
        print(f"Error in IP whitelist check: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        # If there's an error, allow access to prevent complete blocking
        return

@app.context_processor
def inject_pending_counts():
    """Inject pending counts into all templates"""
    try:
        print("Context processor: inject_pending_counts called")
        if 'user_id' in session and session.get('is_admin'):
            print(f"Context processor: user_id: {session.get('user_id')}, is_admin: {session.get('is_admin')}")
            try:
                # Ensure database is initialized
                conn = sqlite3.connect('netflix.db')
                c = conn.cursor()
                
                # Check if required tables exist
                c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('movie_requests', 'ip_access_requests')")
                existing_tables = [row[0] for row in c.fetchall()]
                print(f"Context processor: existing tables: {existing_tables}")
                conn.close()
                
                pending_requests = 0
                pending_movie_requests = 0
                
                if 'ip_access_requests' in existing_tables:
                    print("Context processor: getting pending IP requests count")
                    pending_requests = get_pending_requests_count()
                if 'movie_requests' in existing_tables:
                    print("Context processor: getting pending movie requests count")
                    pending_movie_requests = get_pending_movie_requests_count()
                
                print(f"Context processor: pending_requests: {pending_requests}, pending_movie_requests: {pending_movie_requests}")
                return {
                    'pending_requests': pending_requests,
                    'pending_movie_requests': pending_movie_requests
                }
            except Exception as e:
                print(f"Context processor: error in database operations: {e}")
                print(f"Error type: {type(e)}")
                import traceback
                traceback.print_exc()
                return {
                    'pending_requests': 0,
                    'pending_movie_requests': 0
                }
        else:
            print("Context processor: user not logged in or not admin")
    except Exception as e:
        print(f"Context processor: error in inject_pending_counts: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
    
    return {}

@app.route('/request-ip-access', methods=['GET', 'POST'])
def request_ip_access():
    """Handle IP access requests from blocked users"""
    try:
        client_ip = get_client_ip()
        whitelisted_ips = get_whitelisted_ips()
        
        # If IP is now whitelisted, redirect to login
        if client_ip in whitelisted_ips:
            return redirect(url_for('login'))
        
        if request.method == 'POST':
            ip_address = request.form.get('ip_address')
            name = request.form.get('name', '').strip()
            reason = request.form.get('reason', '').strip()
            
            if not ip_address or not validate_ip_address(ip_address):
                return render_template('ip_blocked.html', 
                                     current_ip=client_ip, 
                                     error="Invalid IP address")
            
            # Check if IP is already whitelisted
            if ip_address in whitelisted_ips:
                return render_template('ip_blocked.html', 
                                     current_ip=ip_address, 
                                     error="IP address is already whitelisted")
            
            try:
                conn = sqlite3.connect('netflix.db')
                c = conn.cursor()
                
                # Check if table exists first
                c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ip_access_requests'")
                if not c.fetchone():
                    conn.close()
                    return render_template('ip_blocked.html', 
                                         current_ip=client_ip, 
                                         error="Database not properly initialized. Please contact administrator.")
                
                # Check if there's already a pending request for this IP
                c.execute("SELECT id FROM ip_access_requests WHERE ip_address = ? AND status = 'pending'", (ip_address,))
                existing_request = c.fetchone()
                
                if existing_request:
                    conn.close()
                    return render_template('ip_blocked.html', 
                                         current_ip=ip_address, 
                                         error="Access request already pending for this IP address")
                
                # Create new access request
                c.execute("""
                    INSERT INTO ip_access_requests (ip_address, name, reason)
                    VALUES (?, ?, ?)
                """, (ip_address, name, reason))
                conn.commit()
                
                log_access_attempt(f"IP access request submitted from {ip_address} by {name or 'Anonymous'}")
                
                return render_template('ip_blocked.html', 
                                     current_ip=ip_address, 
                                     request_sent=True)
            except Exception as e:
                print(f"Error creating IP access request: {e}")
                return render_template('ip_blocked.html', 
                                     current_ip=ip_address, 
                                     error="Failed to submit access request")
            finally:
                if 'conn' in locals():
                    conn.close()
        
        # GET request - check if there's already a pending request for this IP
        try:
            conn = sqlite3.connect('netflix.db')
            c = conn.cursor()
            
            # Check if table exists first
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ip_access_requests'")
            if c.fetchone():
                c.execute("SELECT id FROM ip_access_requests WHERE ip_address = ? AND status = 'pending'", (client_ip,))
                existing_request = c.fetchone()
            else:
                existing_request = None
            conn.close()
            
            return render_template('ip_blocked.html', 
                                 current_ip=client_ip, 
                                 has_pending_request=existing_request is not None)
        except Exception as e:
            print(f"Error checking existing IP access request: {e}")
            return render_template('ip_blocked.html', 
                                 current_ip=client_ip, 
                                 has_pending_request=False)
    except Exception as e:
        print(f"Error in request_ip_access: {e}")
        return render_template('ip_blocked.html', 
                             current_ip=get_client_ip(), 
                             error="An error occurred. Please try again.")

@app.route('/')
def index():
    """Main route - redirect to login if not authenticated, otherwise show movies and series"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        movies, series = get_grouped_content()
        featured_movie = get_featured_movie()
        
        return render_template('index.html', 
                             movies=movies, 
                             series=series, 
                             featured_movie=featured_movie)
    except Exception as e:
        print(f"Error in index route: {e}")
        flash('Error loading content. Please try again.')
        return render_template('index.html', 
                             movies=[], 
                             series=[], 
                             featured_movie=None)


@app.route('/series/<series_name>')
@login_required
def view_series(series_name):
    """View all episodes in a series"""
    try:
        episodes = get_series_episodes(series_name)
        if not episodes:
            flash('Series not found')
            return redirect(url_for('index'))
        return render_template('series.html', series_name=series_name, episodes=episodes)
    except Exception as e:
        print(f"Error in view_series route: {e}")
        flash('Error loading series. Please try again.')
        return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login route - accessible to whitelisted IPs"""
    # If user is already logged in, redirect to home
    if 'user_id' in session:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        try:
            conn = sqlite3.connect('netflix.db')
            c = conn.cursor()
            
            # Check if table exists first
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if not c.fetchone():
                conn.close()
                flash('Database not properly initialized. Please contact administrator.')
                return render_template('login.html')
            
            c.execute("SELECT * FROM users WHERE username = ?", (username,))
            user = c.fetchone()
            conn.close()
            
            if user and check_password_hash(user[2], password):
                session['user_id'] = user[0]
                session['username'] = user[1]
                session['is_admin'] = user[3]
                
                log_access_attempt(f"Successful login for {username}")
                return redirect(url_for('index'))
            else:
                flash('Invalid username or password')
        except Exception as e:
            print(f"Error in login route: {e}")
            flash('Error during login. Please try again.')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Register route - accessible to whitelisted IPs"""
    # If user is already logged in, redirect to home
    if 'user_id' in session:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if len(username) < 3 or len(password) < 6:
            flash('Username must be at least 3 characters and password at least 6 characters')
            return render_template('register.html')
        
        try:
            conn = sqlite3.connect('netflix.db')
            c = conn.cursor()
            
            # Check if table exists first
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if not c.fetchone():
                conn.close()
                flash('Database not properly initialized. Please contact administrator.')
                return render_template('register.html')
            
            hashed_password = generate_password_hash(password)
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", 
                     (username, hashed_password))
            conn.commit()
            conn.close()
            flash('Registration successful! Please login.')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists')
        except Exception as e:
            print(f"Error in register route: {e}")
            flash('Error during registration. Please try again.')
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/watch/<int:movie_id>')
@login_required
def watch_movie(movie_id):
    """Watch a specific movie or episode"""
    try:
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Check if table exists first
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='movies'")
        if not c.fetchone():
            conn.close()
            flash('Movies table not found. Please ensure the database is properly initialized.')
            return redirect(url_for('index'))
        
        c.execute("SELECT * FROM movies WHERE id = ?", (movie_id,))
        movie = c.fetchone()
        conn.close()
        
        if not movie:
            flash('Movie not found')
            return redirect(url_for('index'))
        
        return render_template('watch.html', movie=movie)
    except Exception as e:
        print(f"Error in watch_movie route: {e}")
        flash('Error loading movie. Please try again.')
        return redirect(url_for('index'))

@app.route('/video/<path:filename>')
@login_required
def serve_video(filename):
    """Serve video files with support for series folders"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/thumbnail/<filename>')
def serve_thumbnail(filename):
    return send_from_directory(app.config['THUMBNAIL_FOLDER'], filename)

@app.route('/admin')
@admin_required
def admin():
    log_admin_access("Admin page access")
    
    try:
        # Ensure database is initialized
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Check if required tables exist
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('movies', 'users')")
        existing_tables = [row[0] for row in c.fetchall()]
        
        if 'movies' not in existing_tables or 'users' not in existing_tables:
            conn.close()
            flash('Database not properly initialized. Please visit /init-db to set up the database.')
            return render_template('admin.html', 
                                 movies=[],
                                 series_summary=[],
                                 opencv_available=False,
                                 moviepy_available=False,
                                 thumbnail_methods_available=False)
        
        # Get all content for admin management
        c.execute("SELECT * FROM movies ORDER BY uploaded_at DESC")
        all_content = c.fetchall()
        
        # Get series summary
        c.execute("""
            SELECT series_name, COUNT(*) as episode_count, 
                   MIN(season_number) as min_season, MAX(season_number) as max_season,
                   MIN(uploaded_at) as first_uploaded
            FROM movies 
            WHERE is_series = 1
            GROUP BY series_name
            ORDER BY first_uploaded DESC
        """)
        series_summary = c.fetchall()
        
        conn.close()
        
        # Check available methods
        opencv_available = check_opencv_available()
        moviepy_available = check_moviepy_available()
        thumbnail_methods_available = opencv_available or moviepy_available
        
        return render_template('admin.html', 
                             movies=all_content,
                             series_summary=series_summary,
                             opencv_available=opencv_available,
                             moviepy_available=moviepy_available,
                             thumbnail_methods_available=thumbnail_methods_available)
    except Exception as e:
        print(f"Error in admin route: {e}")
        flash(f'Error loading admin dashboard: {str(e)}')
        return render_template('admin.html', 
                             movies=[],
                             series_summary=[],
                             opencv_available=False,
                             moviepy_available=False,
                             thumbnail_methods_available=False)

@app.route('/admin/upload', methods=['GET', 'POST'])
@admin_required
def upload_movie():
    if request.method == 'POST':
        log_admin_access("Movie/Series upload attempt")
        
        title = request.form['title']
        description = request.form['description']
        genre = request.form['genre']
        duration = request.form['duration']
        release_year = request.form['release_year']
        
        # Series-specific fields
        is_series = 1 if request.form.get('is_series') == 'on' else 0
        series_name = request.form.get('series_name', '').strip()
        season_number = request.form.get('season_number')
        episode_number = request.form.get('episode_number')
        episode_title = request.form.get('episode_title', '').strip()
        
        # Validation for series
        if is_series:
            if not series_name:
                flash('Series name is required for series episodes')
                return render_template('upload.html')
            if not season_number or not episode_number:
                flash('Season and episode numbers are required for series')
                return render_template('upload.html')
            
            # Convert to integers and validate
            try:
                season_number = int(season_number)
                episode_number = int(episode_number)
                if season_number < 1 or episode_number < 1:
                    flash('Season and episode numbers must be positive integers')
                    return render_template('upload.html')
            except (ValueError, TypeError):
                flash('Season and episode numbers must be valid integers')
                return render_template('upload.html')
        
        # Handle video file
        video_file = request.files['video_file']
        thumbnail_file = request.files.get('thumbnail_file')
        
        if video_file and allowed_file(video_file.filename, ALLOWED_VIDEO_EXTENSIONS):
            # Create series folder if this is a series episode
            series_folder = None
            if is_series and series_name:
                series_folder = create_series_folder(series_name)
                print(f"Created/using series folder: {series_folder}")
            
            # Generate unique filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            original_filename = secure_filename(video_file.filename)
            
            if is_series:
                # For series, include series info in filename
                safe_series_name = sanitize_folder_name(series_name)
                video_filename = f"{safe_series_name}_S{season_number:02d}E{episode_number:02d}_{timestamp}_{original_filename}"
            else:
                video_filename = f"{timestamp}_{original_filename}"
            
            # Determine the final video file path
            if series_folder:
                # Save in series folder
                video_file_path = get_video_file_path(video_filename, series_name)
                full_video_path = get_full_video_path(video_file_path)
                
                # Ensure the series directory exists
                os.makedirs(os.path.dirname(full_video_path), exist_ok=True)
            else:
                # Save in root upload folder
                video_file_path = video_filename
                full_video_path = os.path.join(app.config['UPLOAD_FOLDER'], video_filename)
            
            # Save the video file
            video_file.save(full_video_path)
            print(f"Video saved to: {full_video_path}")
            
            thumbnail_filename = None
            is_auto_generated = False
            
            # Handle thumbnail
            if thumbnail_file and allowed_file(thumbnail_file.filename, ALLOWED_IMAGE_EXTENSIONS):
                # Custom thumbnail uploaded
                if is_series:
                    safe_series_name = sanitize_folder_name(series_name)
                    thumbnail_filename = secure_filename(f"thumb_{safe_series_name}_S{season_number:02d}E{episode_number:02d}_{timestamp}_{thumbnail_file.filename}")
                else:
                    thumbnail_filename = secure_filename(f"thumb_{timestamp}_{thumbnail_file.filename}")
                
                thumbnail_path = os.path.join(app.config['THUMBNAIL_FOLDER'], thumbnail_filename)
                thumbnail_file.save(thumbnail_path)
                print("✓ Custom thumbnail uploaded")
            else:
                # Auto-generate thumbnail
                if is_series:
                    safe_series_name = sanitize_folder_name(series_name)
                    auto_thumb_filename = f"auto_thumb_{safe_series_name}_S{season_number:02d}E{episode_number:02d}_{timestamp}.jpg"
                else:
                    auto_thumb_filename = f"auto_thumb_{timestamp}.jpg"
                
                thumbnail_filename, is_auto_generated = auto_generate_thumbnail(full_video_path, auto_thumb_filename)
            
            # Save to database
            try:
                conn = sqlite3.connect('netflix.db')
                c = conn.cursor()
                
                # Check if table exists first
                c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='movies'")
                if not c.fetchone():
                    conn.close()
                    flash('Movies table not found. Please ensure the database is properly initialized.')
                    return render_template('upload.html')
                
                # Store the relative path in database (includes series folder if applicable)
                c.execute("""
                    INSERT INTO movies (title, description, genre, duration, release_year, video_file, 
                                      thumbnail_file, auto_generated_thumb, is_series, series_name, 
                                      season_number, episode_number, episode_title)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (title, description, genre, 
                      int(duration) if duration else None, 
                      int(release_year) if release_year else None, 
                      video_file_path,  # This now includes series folder path if applicable
                      thumbnail_filename, 1 if is_auto_generated else 0,
                      is_series, series_name if is_series else None,
                      season_number if is_series else None,  # Now guaranteed to be int or None
                      episode_number if is_series else None,  # Now guaranteed to be int or None
                      episode_title if episode_title else None))
                conn.commit()
                conn.close()
                
                content_type = "Series episode" if is_series else "Movie"
                if is_series:
                    log_admin_access(f"{content_type} uploaded: {series_name} - S{season_number}E{episode_number}: {title}")
                    flash(f'{content_type} uploaded successfully! Series: {series_name} - Season {season_number}, Episode {episode_number}')
                else:
                    log_admin_access(f"{content_type} uploaded: {title}")
                    flash(f'{content_type} uploaded successfully!')
                
                return redirect(url_for('admin'))
            except Exception as e:
                print(f"Error saving movie to database: {e}")
                # Clean up uploaded files if database save fails
                try:
                    if os.path.exists(full_video_path):
                        os.remove(full_video_path)
                    if thumbnail_filename:
                        thumb_path = os.path.join(app.config['THUMBNAIL_FOLDER'], thumbnail_filename)
                        if os.path.exists(thumb_path):
                            os.remove(thumb_path)
                except:
                    pass
                flash('Error saving to database. Files have been cleaned up. Please try again.')
                return render_template('upload.html')
        else:
            flash('Invalid video file format')
    
    return render_template('upload.html')

@app.route('/admin/delete/<int:movie_id>')
@admin_required
def delete_movie(movie_id):
    try:
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Check if table exists first
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='movies'")
        if not c.fetchone():
            conn.close()
            flash('Movies table not found. Please ensure the database is properly initialized.')
            return redirect(url_for('admin'))
        
        c.execute("SELECT video_file, thumbnail_file, title, is_series, series_name FROM movies WHERE id = ?", (movie_id,))
        movie = c.fetchone()
        
        if movie:
            video_file, thumbnail_file, title, is_series, series_name = movie
            
            # Delete files
            try:
                if video_file:  # video file (may include series folder path)
                    full_video_path = get_full_video_path(video_file)
                    if os.path.exists(full_video_path):
                        os.remove(full_video_path)
                        print(f"Deleted video file: {full_video_path}")
                    
                    # Check if series folder is empty and delete if so
                    if is_series and series_name:
                        series_folder_path = os.path.join(app.config['UPLOAD_FOLDER'], sanitize_folder_name(series_name))
                        if os.path.exists(series_folder_path) and not os.listdir(series_folder_path):
                            os.rmdir(series_folder_path)
                            print(f"Deleted empty series folder: {series_folder_path}")
                
                if thumbnail_file:  # thumbnail file
                    thumb_path = os.path.join(app.config['THUMBNAIL_FOLDER'], thumbnail_file)
                    if os.path.exists(thumb_path):
                        os.remove(thumb_path)
                        print(f"Deleted thumbnail file: {thumb_path}")
            except OSError as e:
                print(f"Error deleting files: {e}")
                pass  # File might not exist
            
            # Delete from database
            c.execute("DELETE FROM movies WHERE id = ?", (movie_id,))
            conn.commit()
            conn.close()
            
            content_type = "Episode" if is_series else "Movie"
            log_admin_access(f"{content_type} deleted: {title}")
            flash(f'{content_type} "{title}" deleted successfully!')
        else:
            conn.close()
            flash('Movie not found')
        
        return redirect(url_for('admin'))
    except Exception as e:
        print(f"Error in delete_movie route: {e}")
        flash(f'Error deleting movie: {str(e)}')
        return redirect(url_for('admin'))

@app.route('/admin/regenerate-thumbnail/<int:movie_id>')
@admin_required
def regenerate_thumbnail(movie_id):
    """Regenerate thumbnail for a movie"""
    try:
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Check if table exists first
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='movies'")
        if not c.fetchone():
            conn.close()
            flash('Movies table not found. Please ensure the database is properly initialized.')
            return redirect(url_for('admin'))
        
        c.execute("SELECT video_file, thumbnail_file, title, is_series, series_name, season_number, episode_number FROM movies WHERE id = ?", (movie_id,))
        movie = c.fetchone()
        
        if not movie:
            conn.close()
            flash('Movie not found')
            return redirect(url_for('admin'))
        
        video_file, old_thumbnail, title, is_series, series_name, season_number, episode_number = movie
        
        # Get full video path
        full_video_path = get_full_video_path(video_file)
        
        if not os.path.exists(full_video_path):
            flash('Video file not found')
            return redirect(url_for('admin'))
        
        # Generate new thumbnail
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if is_series and series_name:
            safe_series_name = sanitize_folder_name(series_name)
            new_thumb_filename = f"regen_thumb_{safe_series_name}_S{season_number:02d}E{episode_number:02d}_{timestamp}.jpg"
        else:
            new_thumb_filename = f"regen_thumb_{timestamp}.jpg"
        
        thumbnail_filename, is_auto_generated = auto_generate_thumbnail(full_video_path, new_thumb_filename)
        
        if thumbnail_filename:
            # Delete old thumbnail if it was auto-generated
            if old_thumbnail and old_thumbnail.startswith(('auto_thumb_', 'regen_thumb_')):
                try:
                    old_thumb_path = os.path.join(app.config['THUMBNAIL_FOLDER'], old_thumbnail)
                    if os.path.exists(old_thumb_path):
                        os.remove(old_thumb_path)
                        print(f"Deleted old thumbnail: {old_thumb_path}")
                except OSError:
                    pass
            
            # Update database
            c.execute("""
                UPDATE movies 
                SET thumbnail_file = ?, auto_generated_thumb = ?
                WHERE id = ?
            """, (thumbnail_filename, 1 if is_auto_generated else 0, movie_id))
            conn.commit()
            
            content_type = "episode" if is_series else "movie"
            log_admin_access(f"Thumbnail regenerated for {content_type}: {title}")
            flash(f'Thumbnail regenerated for {content_type} "{title}"')
        else:
            flash('Failed to regenerate thumbnail')
        
        conn.close()
        return redirect(url_for('admin'))
    except Exception as e:
        print(f"Error in regenerate_thumbnail route: {e}")
        flash(f'Error regenerating thumbnail: {str(e)}')
        return redirect(url_for('admin'))

# Add these new routes after your existing routes

@app.route('/request-movie', methods=['GET', 'POST'])
@login_required
def request_movie():
    """Allow users to request movies or series"""
    if request.method == 'POST':
        title = request.form['title'].strip()
        description = request.form.get('description', '').strip()
        request_type = request.form.get('request_type', 'movie')
        genre = request.form.get('genre', '').strip()
        release_year = request.form.get('release_year')
        series_name = request.form.get('series_name', '').strip()
        season_number = request.form.get('season_number')
        episode_number = request.form.get('episode_number')
        imdb_link = request.form.get('imdb_link', '').strip()
        additional_info = request.form.get('additional_info', '').strip()
        
        if not title:
            flash('Title is required')
            return render_template('request_movie.html')
        
        # Validation for series requests
        if request_type == 'series' and not series_name:
            flash('Series name is required for series requests')
            return render_template('request_movie.html')
        
        try:
            conn = sqlite3.connect('netflix.db')
            c = conn.cursor()
            
            # Check if table exists first
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='movie_requests'")
            if not c.fetchone():
                conn.close()
                flash('Movie requests system not available. Please contact administrator.')
                return render_template('request_movie.html')
            
            c.execute("""
                INSERT INTO movie_requests (
                    user_id, title, description, request_type, genre, 
                    release_year, series_name, season_number, episode_number,
                    imdb_link, additional_info
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session['user_id'], title, description, request_type, genre,
                int(release_year) if release_year else None,
                series_name if series_name else None,
                int(season_number) if season_number else None,
                int(episode_number) if episode_number else None,
                imdb_link, additional_info
            ))
            
            conn.commit()
            conn.close()
            
            log_access_attempt(f"Movie request submitted: {title}")
            flash(f'Your {request_type} request for "{title}" has been submitted successfully!')
            return redirect(url_for('my_requests'))
            
        except Exception as e:
            flash('Error submitting request. Please try again.')
            print(f"Error submitting movie request: {e}")
    
    return render_template('request_movie.html')

@app.route('/my-requests')
@login_required
def my_requests():
    """View user's own movie requests"""
    try:
        requests = get_user_movie_requests(session['user_id'])
        return render_template('my_requests.html', requests=requests)
    except Exception as e:
        print(f"Error in my_requests route: {e}")
        flash('Error loading your requests. Please try again.')
        return render_template('my_requests.html', requests=[])

@app.route('/admin/movie-requests')
@admin_required
def admin_movie_requests():
    """Admin page to view and manage movie requests"""
    log_admin_access("Movie requests page access")
    
    try:
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Check if required tables exist first
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('movie_requests', 'users')")
        existing_tables = [row[0] for row in c.fetchall()]
        
        if 'movie_requests' not in existing_tables:
            conn.close()
            flash('Movie requests table not found. Please ensure the database is properly initialized.')
            return render_template('admin_movie_requests.html', 
                                 pending_movie_requests_list=[],
                                 all_movie_requests=[])
        
        if 'users' not in existing_tables:
            conn.close()
            flash('Users table not found. Please ensure the database is properly initialized.')
            return render_template('admin_movie_requests.html', 
                                 pending_movie_requests_list=[],
                                 all_movie_requests=[])
        
        # Check table structure to ensure columns exist
        try:
            c.execute("PRAGMA table_info(movie_requests)")
            movie_requests_columns = [row[1] for row in c.fetchall()]
            print(f"Movie requests table columns: {movie_requests_columns}")
            
            c.execute("PRAGMA table_info(users)")
            users_columns = [row[1] for row in c.fetchall()]
            print(f"Users table columns: {users_columns}")
            
            # Check if required columns exist
            required_mr_columns = ['id', 'user_id', 'title', 'status', 'requested_at', 'processed_by']
            required_users_columns = ['id', 'username']
            
            missing_mr_columns = [col for col in required_mr_columns if col not in movie_requests_columns]
            missing_users_columns = [col for col in required_users_columns if col not in users_columns]
            
            if missing_mr_columns:
                print(f"Missing columns in movie_requests: {missing_mr_columns}")
                flash(f'Movie requests table is missing required columns: {", ".join(missing_mr_columns)}')
                return render_template('admin_movie_requests.html', 
                                     pending_movie_requests_list=[],
                                     all_movie_requests=[])
            
            if missing_users_columns:
                print(f"Missing columns in users: {missing_users_columns}")
                flash(f'Users table is missing required columns: {", ".join(missing_users_columns)}')
                return render_template('admin_movie_requests.html', 
                                     pending_movie_requests_list=[],
                                     all_movie_requests=[])
            
        except Exception as table_info_error:
            print(f"Error checking table structure: {table_info_error}")
            flash('Error checking database table structure.')
            return render_template('admin_movie_requests.html', 
                                 pending_movie_requests_list=[],
                                 all_movie_requests=[])
        
        # Get pending requests with simpler query first
        try:
            c.execute("""
                SELECT mr.id, mr.title, mr.description, mr.status, mr.requested_at, u.username
                FROM movie_requests mr
                JOIN users u ON mr.user_id = u.id
                WHERE mr.status = 'pending'
                ORDER BY mr.requested_at ASC
            """)
            pending_movie_requests_list = c.fetchall()
            print(f"Pending requests query successful, found {len(pending_movie_requests_list)} requests")
        except Exception as pending_error:
            print(f"Error in pending requests query: {pending_error}")
            pending_movie_requests_list = []
        
        # Get all requests with admin info
        try:
            c.execute("""
                SELECT mr.id, mr.title, mr.description, mr.status, mr.requested_at, 
                       u.username, admin.username as processed_by_username
                FROM movie_requests mr
                JOIN users u ON mr.user_id = u.id
                LEFT JOIN users admin ON mr.processed_by = admin.id
                ORDER BY mr.requested_at DESC
                LIMIT 100
            """)
            all_movie_requests = c.fetchall()
            print(f"All requests query successful, found {len(all_movie_requests)} requests")
        except Exception as all_requests_error:
            print(f"Error in all requests query: {all_requests_error}")
            all_movie_requests = []
        
        conn.close()
        
        return render_template('admin_movie_requests.html', 
                             pending_movie_requests_list=pending_movie_requests_list,
                             all_movie_requests=all_movie_requests)
    except Exception as e:
        print(f"Error in admin_movie_requests: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        flash(f'Error loading movie requests: {str(e)}')
        return render_template('admin_movie_requests.html', 
                             pending_movie_requests_list=[],
                             all_movie_requests=[])

@app.route('/admin/movie-requests/approve/<int:request_id>')
@admin_required
def approve_movie_request(request_id):
    """Mark movie request as approved"""
    admin_notes = request.args.get('notes', '').strip()
    
    try:
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Check if table exists first
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='movie_requests'")
        if not c.fetchone():
            conn.close()
            flash('Movie requests table not found. Please ensure the database is properly initialized.')
            return redirect(url_for('admin_movie_requests'))
        
        # Get request details
        c.execute("SELECT title, user_id FROM movie_requests WHERE id = ? AND status = 'pending'", (request_id,))
        request_data = c.fetchone()
        
        if not request_data:
            flash('Request not found or already processed')
            conn.close()
            return redirect(url_for('admin_movie_requests'))
        
        title, user_id = request_data
        
        # Update request status
        c.execute("""
            UPDATE movie_requests 
            SET status = 'approved', processed_at = CURRENT_TIMESTAMP, 
                processed_by = ?, admin_notes = ?
            WHERE id = ?
        """, (session['user_id'], admin_notes, request_id))
        
        conn.commit()
        conn.close()
        
        log_admin_access(f"Approved movie request: {title}")
        flash(f'Movie request "{title}" approved successfully!')
        
        return redirect(url_for('admin_movie_requests'))
    except Exception as e:
        print(f"Error in approve_movie_request route: {e}")
        flash(f'Error approving request: {str(e)}')
        return redirect(url_for('admin_movie_requests'))

@app.route('/admin/movie-requests/reject/<int:request_id>')
@admin_required
def reject_movie_request(request_id):
    """Mark movie request as rejected"""
    admin_notes = request.args.get('notes', '').strip()
    
    try:
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Check if table exists first
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='movie_requests'")
        if not c.fetchone():
            conn.close()
            flash('Movie requests table not found. Please ensure the database is properly initialized.')
            return redirect(url_for('admin_movie_requests'))
        
        # Get request details
        c.execute("SELECT title FROM movie_requests WHERE id = ? AND status = 'pending'", (request_id,))
        request_data = c.fetchone()
        
        if not request_data:
            flash('Request not found or already processed')
            conn.close()
            return redirect(url_for('admin_movie_requests'))
        
        title = request_data[0]
        
        # Update request status
        c.execute("""
            UPDATE movie_requests 
            SET status = 'rejected', processed_at = CURRENT_TIMESTAMP, 
                processed_by = ?, admin_notes = ?
            WHERE id = ?
        """, (session['user_id'], admin_notes, request_id))
        
        conn.commit()
        conn.close()
        
        log_admin_access(f"Rejected movie request: {title}")
        flash(f'Movie request "{title}" rejected!')
        
        return redirect(url_for('admin_movie_requests'))
    except Exception as e:
        print(f"Error in reject_movie_request route: {e}")
        flash(f'Error rejecting request: {str(e)}')
        return redirect(url_for('admin_movie_requests'))

@app.route('/admin/movie-requests/mark-uploaded/<int:request_id>')
@admin_required
def mark_request_uploaded(request_id):
    """Mark movie request as uploaded"""
    admin_notes = request.args.get('notes', '').strip()
    
    try:
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Check if table exists first
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='movie_requests'")
        if not c.fetchone():
            conn.close()
            flash('Movie requests table not found. Please ensure the database is properly initialized.')
            return redirect(url_for('admin_movie_requests'))
        
        # Get request details
        c.execute("SELECT title FROM movie_requests WHERE id = ?", (request_id,))
        request_data = c.fetchone()
        
        if not request_data:
            flash('Request not found')
            conn.close()
            return redirect(url_for('admin_movie_requests'))
        
        title = request_data[0]
        
        # Update request status
        c.execute("""
            UPDATE movie_requests 
            SET status = 'uploaded', processed_at = CURRENT_TIMESTAMP, 
                processed_by = ?, admin_notes = ?
            WHERE id = ?
        """, (session['user_id'], admin_notes, request_id))
        
        conn.commit()
        conn.close()
        
        log_admin_access(f"Marked movie request as uploaded: {title}")
        flash(f'Movie request "{title}" marked as uploaded!')
        
        return redirect(url_for('admin_movie_requests'))
    except Exception as e:
        print(f"Error in mark_request_uploaded route: {e}")
        flash(f'Error marking request as uploaded: {str(e)}')
        return redirect(url_for('admin_movie_requests'))

@app.route('/admin/ip-whitelist')
@admin_required
def ip_whitelist():
    """Admin page to manage IP whitelist"""
    log_admin_access("IP whitelist page access")
    
    try:
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Check if table exists first
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ip_whitelist'")
        if not c.fetchone():
            conn.close()
            flash('IP whitelist table not found. Please ensure the database is properly initialized.')
            return render_template('ip_whitelist.html', 
                                 whitelist=[],
                                 current_ip=get_client_ip())
        
        c.execute("""
            SELECT w.id, w.ip_address, w.description, w.added_by, w.added_at, 
                   w.is_active, u.username as added_by_username
            FROM ip_whitelist w
            LEFT JOIN users u ON w.added_by = u.id
            ORDER BY w.added_at DESC
        """)
        whitelist_raw = c.fetchall()
        whitelist = [list(row) for row in whitelist_raw]
        conn.close()
        
        return render_template('ip_whitelist.html', 
                             whitelist=whitelist,
                             current_ip=get_client_ip())
    except Exception as e:
        print(f"Error in ip_whitelist route: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        flash(f'Error loading IP whitelist: {str(e)}')
        return render_template('ip_whitelist.html', 
                             whitelist=[],
                             current_ip=get_client_ip())

@app.route('/admin/ip-requests')
@admin_required
def ip_requests():
    """Admin page to view and manage IP access requests"""
    log_admin_access("IP requests page access")
    
    try:
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Check if table exists first
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ip_access_requests'")
        if not c.fetchone():
            conn.close()
            flash('IP access requests table not found. Please ensure the database is properly initialized.')
            return render_template('ip_requests.html', 
                                 pending_ip_requests_list=[],
                                 all_ip_requests=[])
        
        # Get pending requests
        c.execute("""
            SELECT ir.id, ir.ip_address, ir.name, ir.reason, ir.request_time,
                   ir.status, ir.processed_time, u.username as processed_by_username
            FROM ip_access_requests ir
            LEFT JOIN users u ON ir.processed_by = u.id
            WHERE ir.status = 'pending'
            ORDER BY ir.request_time ASC
        """)
        pending_requests_raw = c.fetchall()
        pending_ip_requests_list = [list(row) for row in pending_requests_raw]
        
        # Get all requests with admin info
        c.execute("""
            SELECT ir.id, ir.ip_address, ir.name, ir.reason, ir.request_time,
                   ir.status, ir.processed_time, u.username as processed_by_username
            FROM ip_access_requests ir
            LEFT JOIN users u ON ir.processed_by = u.id
            ORDER BY ir.request_time DESC
            LIMIT 100
        """)
        all_requests_raw = c.fetchall()
        all_ip_requests = [list(row) for row in all_requests_raw]
        
        conn.close()
        
        return render_template('ip_requests.html', 
                             pending_ip_requests_list=pending_ip_requests_list,
                             all_ip_requests=all_ip_requests)
    except Exception as e:
        print(f"Error in ip_requests route: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        flash(f'Error loading IP requests: {str(e)}')
        return render_template('ip_requests.html', 
                             pending_ip_requests_list=[],
                             all_ip_requests=[])

@app.route('/admin/ip-requests/approve/<int:request_id>')
@admin_required
def approve_ip_request(request_id):
    """Approve an IP access request"""
    conn = sqlite3.connect('netflix.db')
    c = conn.cursor()
    
    # Get request details
    c.execute("SELECT ip_address, name FROM ip_access_requests WHERE id = ? AND status = 'pending'", (request_id,))
    request_data = c.fetchone()
    
    if not request_data:
        flash('Request not found or already processed')
        conn.close()
        return redirect(url_for('ip_requests'))
    
    ip_address, name = request_data
    
    try:
        # Add IP to whitelist
        description = f"Approved request from {name or 'Anonymous'}"
        c.execute("""
            INSERT OR IGNORE INTO ip_whitelist (ip_address, description, added_by)
            VALUES (?, ?, ?)
        """, (ip_address, description, session['user_id']))
        
        # Update request status
        c.execute("""
            UPDATE ip_access_requests 
            SET status = 'approved', processed_time = CURRENT_TIMESTAMP, processed_by = ?
            WHERE id = ?
        """, (session['user_id'], request_id))
        
        conn.commit()
        
        log_admin_access(f"Approved IP access request for {ip_address}")
        flash(f'IP access request approved for {ip_address}')
        
    except sqlite3.IntegrityError:
        # IP already exists in whitelist
        c.execute("""
            UPDATE ip_access_requests 
            SET status = 'approved', processed_time = CURRENT_TIMESTAMP, processed_by = ?
            WHERE id = ?
        """, (session['user_id'], request_id))
        conn.commit()
        flash(f'IP {ip_address} was already in whitelist. Request marked as approved.')
    
    conn.close()
    return redirect(url_for('ip_requests'))

@app.route('/admin/ip-requests/reject/<int:request_id>')
@admin_required
def reject_ip_request(request_id):
    """Reject an IP access request"""
    conn = sqlite3.connect('netflix.db')
    c = conn.cursor()
    
    # Get request details
    c.execute("SELECT ip_address FROM ip_access_requests WHERE id = ? AND status = 'pending'", (request_id,))
    request_data = c.fetchone()
    
    if not request_data:
        flash('Request not found or already processed')
        conn.close()
        return redirect(url_for('ip_requests'))
    
    ip_address = request_data[0]
    
    # Update request status
    c.execute("""
        UPDATE ip_access_requests 
        SET status = 'rejected', processed_time = CURRENT_TIMESTAMP, processed_by = ?
        WHERE id = ?
    """, (session['user_id'], request_id))
    
    conn.commit()
    conn.close()
    
    log_admin_access(f"Rejected IP access request for {ip_address}")
    flash(f'IP access request rejected for {ip_address}')
    
    return redirect(url_for('ip_requests'))

@app.route('/admin/ip-whitelist/add', methods=['POST'])
@admin_required
def add_ip_whitelist():
    """Add IP to whitelist"""
    ip_address = request.form['ip_address'].strip()
    description = request.form['description'].strip()
    
    if not validate_ip_address(ip_address):
        flash('Invalid IP address format')
        return redirect(url_for('ip_whitelist'))
    
    conn = sqlite3.connect('netflix.db')
    c = conn.cursor()
    
    try:
        c.execute("""
            INSERT INTO ip_whitelist (ip_address, description, added_by)
            VALUES (?, ?, ?)
        """, (ip_address, description, session['user_id']))
        conn.commit()
        log_admin_access(f"Added IP to whitelist: {ip_address}")
        flash(f'IP address {ip_address} added to whitelist successfully!')
    except sqlite3.IntegrityError:
        flash('IP address already exists in whitelist')
    finally:
        conn.close()
    
    return redirect(url_for('ip_whitelist'))

@app.route('/admin/ip-whitelist/edit/<int:ip_id>', methods=['POST'])
@admin_required
def edit_ip_whitelist(ip_id):
    """Edit IP whitelist entry"""
    ip_address = request.form['ip_address'].strip()
    description = request.form['description'].strip()
    is_active = 1 if 'is_active' in request.form else 0
    
    if not validate_ip_address(ip_address):
        flash('Invalid IP address format')
        return redirect(url_for('ip_whitelist'))
    
    # Check if this is the current user's IP and they're trying to deactivate it
    current_ip = get_client_ip()
    if ip_address == current_ip and not is_active:
        flash('Cannot deactivate your current IP address - you would lose access!')
        return redirect(url_for('ip_whitelist'))
    
    conn = sqlite3.connect('netflix.db')
    c = conn.cursor()
    
    try:
        c.execute("""
            UPDATE ip_whitelist 
            SET ip_address = ?, description = ?, is_active = ?
            WHERE id = ?
        """, (ip_address, description, is_active, ip_id))
        conn.commit()
        log_admin_access(f"Updated IP whitelist entry: {ip_address}")
        flash(f'IP address {ip_address} updated successfully!')
    except sqlite3.IntegrityError:
        flash('IP address already exists in whitelist')
    finally:
        conn.close()
    
    return redirect(url_for('ip_whitelist'))

@app.route('/admin/ip-whitelist/delete/<int:ip_id>')
@admin_required
def delete_ip_whitelist(ip_id):
    """Delete IP from whitelist"""
    conn = sqlite3.connect('netflix.db')
    c = conn.cursor()
    
    # Get IP details first
    c.execute("SELECT ip_address FROM ip_whitelist WHERE id = ?", (ip_id,))
    ip_data = c.fetchone()
    
    if not ip_data:
        flash('IP address not found')
        conn.close()
        return redirect(url_for('ip_whitelist'))
    
    ip_address = ip_data[0]
    current_ip = get_client_ip()
    
    # Prevent deletion of current IP
    if ip_address == current_ip:
        flash('Cannot delete your current IP address - you would lose access!')
        conn.close()
        return redirect(url_for('ip_whitelist'))
    
    # Delete the IP
    c.execute("DELETE FROM ip_whitelist WHERE id = ?", (ip_id,))
    conn.commit()
    conn.close()
    
    log_admin_access(f"Deleted IP from whitelist: {ip_address}")
    flash(f'IP address {ip_address} removed from whitelist successfully!')
    
    return redirect(url_for('ip_whitelist'))

@app.route('/admin/ip-whitelist/toggle/<int:ip_id>')
@admin_required
def toggle_ip_whitelist(ip_id):
    """Toggle IP active status"""
    conn = sqlite3.connect('netflix.db')
    c = conn.cursor()
    
    # Get current status and IP
    c.execute("SELECT ip_address, is_active FROM ip_whitelist WHERE id = ?", (ip_id,))
    ip_data = c.fetchone()
    
    if not ip_data:
        flash('IP address not found')
        conn.close()
        return redirect(url_for('ip_whitelist'))
    
    ip_address, current_status = ip_data
    new_status = 0 if current_status else 1
    current_ip = get_client_ip()
    
    # Prevent deactivation of current IP
    if ip_address == current_ip and new_status == 0:
        flash('Cannot deactivate your current IP address - you would lose access!')
        conn.close()
        return redirect(url_for('ip_whitelist'))
    
    # Update status
    c.execute("UPDATE ip_whitelist SET is_active = ? WHERE id = ?", (new_status, ip_id))
    conn.commit()
    conn.close()
    
    status_text = "activated" if new_status else "deactivated"
    log_admin_access(f"IP {status_text}: {ip_address}")
    flash(f'IP address {ip_address} {status_text} successfully!')
    
    return redirect(url_for('ip_whitelist'))

@app.route('/admin/logs')
@admin_required
def admin_logs():
    """View admin access logs"""
    log_admin_access("Access logs viewed")
    
    try:
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Check if table exists first
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='admin_access_log'")
        if not c.fetchone():
            conn.close()
            flash('Admin logs table not found. Please ensure the database is properly initialized.')
            return render_template('admin_logs.html', logs=[], current_ip=get_client_ip())
        
        c.execute("""
            SELECT al.id, al.user_id, al.ip_address, al.access_time, 
                   al.action, al.success, u.username 
            FROM admin_access_log al
            LEFT JOIN users u ON al.user_id = u.id
            ORDER BY al.access_time DESC
            LIMIT 100
        """)
        logs_raw = c.fetchall()
        logs = [list(row) for row in logs_raw]
        conn.close()
        
        return render_template('admin_logs.html', logs=logs, current_ip=get_client_ip())
    except Exception as e:
        print(f"Error in admin_logs route: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        flash(f'Error loading admin logs: {str(e)}')
        return render_template('admin_logs.html', logs=[], current_ip=get_client_ip())

@app.route('/admin/users')
@admin_required
def admin_users():
    """Admin page to view and manage users"""
    log_admin_access("User management page access")
    
    try:
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Check if table exists first
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not c.fetchone():
            conn.close()
            flash('Users table not found. Please ensure the database is properly initialized.')
            return render_template('admin_users.html', users=[])
        
        # Get all users with their statistics
        c.execute("""
            SELECT u.id, u.username, u.is_admin, u.created_at,
                   COUNT(DISTINCT mr.id) as movie_requests,
                   COUNT(DISTINCT al.id) as admin_actions
            FROM users u
            LEFT JOIN movie_requests mr ON u.id = mr.user_id
            LEFT JOIN admin_access_log al ON u.id = al.user_id
            GROUP BY u.id, u.username, u.is_admin, u.created_at
            ORDER BY u.created_at DESC
        """)
        users = c.fetchall()
        conn.close()
        
        return render_template('admin_users.html', users=users, current_user_id=session.get('user_id'))
    except Exception as e:
        print(f"Error in admin_users route: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        flash(f'Error loading users: {str(e)}')
        return render_template('admin_users.html', users=[], current_user_id=session.get('user_id'))

@app.route('/admin/users/add', methods=['GET', 'POST'])
@admin_required
def add_user():
    """Add a new user"""
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        is_admin = 1 if 'is_admin' in request.form else 0
        
        if len(username) < 3 or len(password) < 6:
            flash('Username must be at least 3 characters and password at least 6 characters')
            return render_template('add_user.html')
        
        try:
            conn = sqlite3.connect('netflix.db')
            c = conn.cursor()
            
            hashed_password = generate_password_hash(password)
            c.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)", 
                     (username, hashed_password, is_admin))
            conn.commit()
            conn.close()
            
            log_admin_access(f"Created new user: {username}")
            flash(f'User "{username}" created successfully!')
            return redirect(url_for('admin_users'))
        except sqlite3.IntegrityError:
            flash('Username already exists')
        except Exception as e:
            print(f"Error creating user: {e}")
            flash('Error creating user. Please try again.')
    
    return render_template('add_user.html')

@app.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    """Edit an existing user"""
    # Prevent editing of current admin user's admin status
    current_user_id = session.get('user_id')
    
    try:
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        if request.method == 'POST':
            username = request.form['username'].strip()
            new_password = request.form.get('password', '').strip()
            is_admin = 1 if 'is_admin' in request.form else 0
            
            # Security check: prevent removing admin status from current user
            if user_id == current_user_id and not is_admin:
                flash('Cannot remove admin privileges from your own account!')
                c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
                user = c.fetchone()
                conn.close()
                return render_template('edit_user.html', user=user, current_user_id=current_user_id)
            
            if len(username) < 3:
                flash('Username must be at least 3 characters')
                c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
                user = c.fetchone()
                conn.close()
                return render_template('edit_user.html', user=user, current_user_id=current_user_id)
            
            try:
                if new_password:
                    if len(new_password) < 6:
                        flash('Password must be at least 6 characters')
                        c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
                        user = c.fetchone()
                        conn.close()
                        return render_template('edit_user.html', user=user, current_user_id=current_user_id)
                    
                    hashed_password = generate_password_hash(new_password)
                    c.execute("UPDATE users SET username = ?, password = ?, is_admin = ? WHERE id = ?", 
                             (username, hashed_password, is_admin, user_id))
                else:
                    c.execute("UPDATE users SET username = ?, is_admin = ? WHERE id = ?", 
                             (username, is_admin, user_id))
                
                conn.commit()
                log_admin_access(f"Updated user: {username}")
                flash(f'User "{username}" updated successfully!')
                conn.close()
                return redirect(url_for('admin_users'))
            except sqlite3.IntegrityError:
                flash('Username already exists')
        
        # GET request - show edit form
        c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = c.fetchone()
        conn.close()
        
        if not user:
            flash('User not found')
            return redirect(url_for('admin_users'))
        
        return render_template('edit_user.html', user=user, current_user_id=current_user_id)
    except Exception as e:
        print(f"Error in edit_user route: {e}")
        flash(f'Error editing user: {str(e)}')
        return redirect(url_for('admin_users'))

@app.route('/admin/users/delete/<int:user_id>')
@admin_required
def delete_user(user_id):
    """Delete a user"""
    current_user_id = session.get('user_id')
    
    # Prevent deletion of current user
    if user_id == current_user_id:
        flash('Cannot delete your own account!')
        return redirect(url_for('admin_users'))
    
    try:
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Get user details before deletion
        c.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        user = c.fetchone()
        
        if not user:
            flash('User not found')
            conn.close()
            return redirect(url_for('admin_users'))
        
        username = user[0]
        
        # Delete user and related data
        c.execute("DELETE FROM movie_requests WHERE user_id = ?", (user_id,))
        c.execute("DELETE FROM admin_access_log WHERE user_id = ?", (user_id,))
        c.execute("DELETE FROM access_log WHERE user_id = ?", (user_id,))
        c.execute("DELETE FROM users WHERE id = ?", (user_id,))
        
        conn.commit()
        conn.close()
        
        log_admin_access(f"Deleted user: {username}")
        flash(f'User "{username}" deleted successfully!')
        
        return redirect(url_for('admin_users'))
    except Exception as e:
        print(f"Error in delete_user route: {e}")
        flash(f'Error deleting user: {str(e)}')
        return redirect(url_for('admin_users'))

@app.route('/admin/users/toggle-admin/<int:user_id>')
@admin_required
def toggle_user_admin(user_id):
    """Toggle user admin status"""
    current_user_id = session.get('user_id')
    
    # Prevent changing own admin status
    if user_id == current_user_id:
        flash('Cannot change your own admin privileges!')
        return redirect(url_for('admin_users'))
    
    try:
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Get current status
        c.execute("SELECT username, is_admin FROM users WHERE id = ?", (user_id,))
        user = c.fetchone()
        
        if not user:
            flash('User not found')
            conn.close()
            return redirect(url_for('admin_users'))
        
        username, current_status = user
        new_status = 0 if current_status else 1
        
        # Update status
        c.execute("UPDATE users SET is_admin = ? WHERE id = ?", (new_status, user_id))
        conn.commit()
        conn.close()
        
        status_text = "granted" if new_status else "revoked"
        log_admin_access(f"Admin privileges {status_text} for user: {username}")
        flash(f'Admin privileges {status_text} for user "{username}"!')
        
        return redirect(url_for('admin_users'))
    except Exception as e:
        print(f"Error in toggle_user_admin route: {e}")
        flash(f'Error updating user privileges: {str(e)}')
        return redirect(url_for('admin_users'))

# Debug route to help with IP issues
@app.route('/debug-ip')
def debug_ip():
    """Debug route to see what IP Flask detects"""
    client_ip = get_client_ip()
    whitelisted_ips = get_whitelisted_ips()
    
    debug_info = {
        "detected_ip": client_ip,
        "request.remote_addr": request.remote_addr,
        "X-Forwarded-For": request.headers.get('X-Forwarded-For'),
        "X-Real-IP": request.headers.get('X-Real-IP'),
        "whitelisted_ips": list(whitelisted_ips),
        "is_whitelisted": client_ip in whitelisted_ips
    }
    
    return f"<pre style='color: white; background: #222; padding: 20px;'>{str(debug_info)}</pre>"

@app.route('/init-db')
def init_database():
    """Manually initialize the database"""
    try:
        init_db()
        return "Database initialized successfully!"
    except Exception as e:
        return f"Error initializing database: {str(e)}"

# Add API endpoint for user count
@app.route('/api/user-count')
@admin_required
def api_user_count():
    """API endpoint to get user count statistics"""
    try:
        conn = sqlite3.connect('netflix.db')
        c = conn.cursor()
        
        # Check if table exists first
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not c.fetchone():
            conn.close()
            return jsonify({'error': 'Users table not found'}), 500
        
        # Get user counts
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
        admin_users = c.fetchone()[0]
        
        regular_users = total_users - admin_users
        
        conn.close()
        
        return jsonify({
            'total': total_users,
            'admins': admin_users,
            'regular': regular_users
        })
    except Exception as e:
        print(f"Error in api_user_count: {e}")
        return jsonify({'error': 'Failed to get user count'}), 500

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)