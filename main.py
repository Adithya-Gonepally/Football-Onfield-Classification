from flask import Flask, request, jsonify, send_from_directory, render_template
import sqlite3
import os
import cv2
import logging
from flask_cors import CORS
from ultralytics import YOLO
from werkzeug.utils import secure_filename

# Setup
app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# Load model
# MODEL_PATH = os.getenv('MODEL_PATH', 'Football-players.pt')
model = YOLO('Football-players.pt')

# Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure output directory exists
os.makedirs('static/runs', exist_ok=True)

# Initialize DB
DB_PATH = os.getenv('DB_PATH', 'users.db')
def init_db():
    if not os.path.exists(DB_PATH):
        logger.info("Creating DB...")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''CREATE TABLE users (email TEXT PRIMARY KEY, password TEXT, status TEXT)''')
        c.execute("INSERT INTO users (email, password, status) VALUES (?, ?, ?)", ('admin@example.com', 'admin123', 'approved'))
        conn.commit()
        conn.close()

init_db()

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

@app.route('/upload_image', methods=['POST'])
def upload_image():
    if 'image' not in request.files:
        logger.error("No image in request.")
        return jsonify({'error': 'No image uploaded'}), 400

    image = request.files['image']
    filename = secure_filename(image.filename)
    img_path = os.path.join('static', filename)

    try:
        image.save(img_path)
        results = model(img_path)
        annotated_frame = results[0].plot()
        output_path = os.path.join('static', 'runs', filename)
        cv2.imwrite(output_path, annotated_frame)
        return jsonify({'filename': f'static/runs/{filename}'}), 200
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(img_path):
            try:
                os.remove(img_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp file: {e}")

@app.route('/static/runs/<path:filename>')
def serve_annotated_image(filename):
    try:
        return send_from_directory('static/runs', filename)
    except:
        return jsonify({'error': 'File not found'}), 404

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    email = data['email']
    password = data['password']

    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email = ?", (email,))
        if c.fetchone():
            return jsonify({'message': 'User already exists'}), 400
        c.execute("INSERT INTO users (email, password, status) VALUES (?, ?, ?)", (email, password, 'pending'))
        conn.commit()
        return jsonify({'message': 'Registration successful, awaiting approval'}), 200
    except sqlite3.Error as e:
        logger.error(e)
        return jsonify({'message': 'Server error'}), 500
    finally:
        conn.close()

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data['email']
    password = data['password']
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email = ? AND password = ? AND status = 'approved'", (email, password))
        user = c.fetchone()
        if user:
            return jsonify({'message': 'Login successful', 'isAdmin': email == 'admin@example.com'}), 200
        return jsonify({'message': 'Invalid credentials or not approved'}), 401
    except sqlite3.Error as e:
        logger.error(e)
        return jsonify({'message': 'Server error'}), 500
    finally:
        conn.close()

@app.route('/pending_users', methods=['GET'])
def get_pending_users():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT email FROM users WHERE status = 'pending'")
        users = [{'email': row[0]} for row in c.fetchall()]
        return jsonify(users), 200
    except sqlite3.Error as e:
        logger.error(e)
        return jsonify({'message': 'Server error'}), 500
    finally:
        conn.close()

@app.route('/manage_user', methods=['POST'])
def manage_user():
    data = request.get_json()
    email = data['email']
    action = data['action']
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        if action == 'approve':
            c.execute("UPDATE users SET status = 'approved' WHERE email = ?", (email,))
        elif action == 'reject':
            c.execute("DELETE FROM users WHERE email = ?", (email,))
        conn.commit()
        return jsonify({'message': f'User {action}d successfully'}), 200
    except sqlite3.Error as e:
        logger.error(e)
        return jsonify({'message': 'Server error'}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
