from flask import Flask, request, jsonify, send_from_directory
from flask import render_template
import sqlite3
import os
import cv2
import logging
from flask_cors import CORS
from ultralytics import YOLO
from PIL import Image
import io
from werkzeug.utils import secure_filename

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# Load YOLOv8 model
model = YOLO('Football-players.pt')

# Ensure output directory exists
os.makedirs('static/runs', exist_ok=True)

@app.route('/upload_image', methods=['POST'])
def upload_image():
    if 'image' not in request.files:
        logger.error("No image uploaded in request")
        return jsonify({'error': 'No image uploaded'}), 400

    image = request.files['image']
    filename = secure_filename(image.filename)
    img_path = os.path.join('static', filename)

    try:
        # Save the uploaded image
        image.save(img_path)
        logger.info(f"Image saved to {img_path}")

        # Run YOLO inference
        results = model(img_path)
        logger.info("YOLO inference completed")

        # Plot annotated image
        annotated_frame = results[0].plot()

        # Save the annotated image
        output_path = os.path.join('static', 'runs', filename)
        cv2.imwrite(output_path, annotated_frame)
        logger.info(f"Annotated image saved to {output_path}")

        return jsonify({'filename': f'static/runs/{filename}'}), 200

    except Exception as e:
        logger.error(f"Error processing image {filename}: {str(e)}")
        return jsonify({'error': f'Failed to process image: {str(e)}'}), 500

    finally:
        # Clean up temporary image file
        if os.path.exists(img_path):
            try:
                os.remove(img_path)
                logger.info(f"Temporary image {img_path} deleted")
            except Exception as e:
                logger.error(f"Failed to delete temporary image {img_path}: {str(e)}")

# Route to serve annotated images explicitly
@app.route('/static/runs/<path:filename>')
def serve_annotated_image(filename):
    try:
        return send_from_directory('static/runs', filename)
    except Exception as e:
        logger.error(f"Error serving annotated image {filename}: {str(e)}")
        return jsonify({'error': 'File not found'}), 404

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database initialization
def init_db():
    db_path = 'users.db'
    try:
        if not os.path.exists(db_path):
            logger.info(f"Creating new database file: {db_path}")
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute('''CREATE TABLE users 
                         (email TEXT PRIMARY KEY, password TEXT, status TEXT)''')
            c.execute("INSERT INTO users (email, password, status) VALUES (?, ?, ?)",
                      ('admin@example.com', 'admin123', 'approved'))
            conn.commit()
            logger.info("Database initialized successfully with users table and default admin.")
        else:
            logger.info(f"Database file {db_path} already exists. Skipping initialization.")
    except sqlite3.Error as e:
        logger.error(f"Database initialization failed: {e}")
        raise
    finally:
        if 'conn' in locals():
            conn.close()

# Initialize database on startup
init_db()

# Serve HTML files
@app.route('/')
def serve_index():
    return render_template('index.html')

@app.route('/auth.html')
def serve_auth():
    return render_template('auth.html')

@app.route('/admin.html')
def serve_admin():
    return render_template('admin.html')

@app.route('/user.html')
def serve_user():
    return render_template('user.html')

# Register a new user (pending approval)
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    email = data['email']
    password = data['password']
    
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        
        c.execute("SELECT * FROM users WHERE email = ?", (email,))
        if c.fetchone():
            conn.close()
            return jsonify({'message': 'User already exists'}), 400
        
        c.execute("INSERT INTO users (email, password, status) VALUES (?, ?, ?)",
                  (email, password, 'pending'))
        conn.commit()
        logger.info(f"User {email} registered successfully with pending status.")
        return jsonify({'message': 'Registration successful, awaiting admin approval'}), 200
    except sqlite3.Error as e:
        logger.error(f"Error during registration: {e}")
        return jsonify({'message': 'Registration failed due to a server error'}), 500
    finally:
        conn.close()

# Login endpoint
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data['email']
    password = data['password']
    
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email = ? AND password = ? AND status = 'approved'",
                  (email, password))
        user = c.fetchone()
        
        if user:
            logger.info(f"User {email} logged in successfully.")
            return jsonify({'message': 'Login successful', 'isAdmin': email == 'admin@example.com'}), 200
        return jsonify({'message': 'Invalid credentials or not approved'}), 401
    except sqlite3.Error as e:
        logger.error(f"Error during login: {e}")
        return jsonify({'message': 'Login failed due to a server error'}), 500
    finally:
        conn.close()

# Get pending users (for admin)
@app.route('/pending_users', methods=['GET'])
def get_pending_users():
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT email FROM users WHERE status = 'pending'")
        users = [{'email': row[0]} for row in c.fetchall()]
        logger.info(f"Fetched {len(users)} pending users.")
        return jsonify(users), 200
    except sqlite3.Error as e:
        logger.error(f"Error fetching pending users: {e}")
        return jsonify({'message': 'Failed to fetch pending users'}), 500
    finally:
        conn.close()

# Approve or reject a user (for admin)
@app.route('/manage_user', methods=['POST'])
def manage_user():
    data = request.get_json()
    email = data['email']
    action = data['action']
    
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        
        if action == 'approve':
            c.execute("UPDATE users SET status = 'approved' WHERE email = ?", (email,))
            logger.info(f"User {email} approved.")
        elif action == 'reject':
            c.execute("DELETE FROM users WHERE email = ?", (email,))
            logger.info(f"User {email} rejected and deleted.")
        
        conn.commit()
        return jsonify({'message': f'User {action}d successfully'}), 200
    except sqlite3.Error as e:
        logger.error(f"Error managing user {email}: {e}")
        return jsonify({'message': 'Failed to manage user'}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=False, host='0.0.0.0', port=port)
