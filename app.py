from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_socketio import SocketIO, emit, join_room, leave_room
import sqlite3
import uuid
import os
from datetime import datetime
import secrets

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(16))
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Database setup
DATABASE = os.environ.get('DATABASE_URL', 'videocall.db')

def init_db():
    """Initialize the database with required tables"""
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Rooms table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rooms (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (created_by) REFERENCES users (id)
            )
        ''')
        
        # Room participants table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS room_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id TEXT,
                user_id INTEGER,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                left_at TIMESTAMP,
                FOREIGN KEY (room_id) REFERENCES rooms (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        conn.commit()

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def get_or_create_user(username):
    """Get existing user or create new one"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Try to get existing user
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        
        if user:
            return user['id']
        else:
            # Create new user
            cursor.execute('INSERT INTO users (username) VALUES (?)', (username,))
            return cursor.lastrowid

@app.route('/')
def index():
    """Home page"""
    return render_template('index.html')

@app.route('/create', methods=['POST'])
def create_room():
    """Create a new room"""
    username = request.form.get('username', '').strip()
    room_name = request.form.get('room_name', '').strip()
    
    if not username or not room_name:
        return redirect(url_for('index'))
    
    # Get or create user
    user_id = get_or_create_user(username)
    
    # Generate room ID
    room_id = str(uuid.uuid4())[:8]
    
    # Create room
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO rooms (id, name, created_by) VALUES (?, ?, ?)
        ''', (room_id, room_name, user_id))
    
    # Store in session
    session['username'] = username
    session['user_id'] = user_id
    session['room_id'] = room_id
    session['room_name'] = room_name
    
    return redirect(url_for('room', room_id=room_id))

@app.route('/join', methods=['POST'])
def join_room_route():
    """Join an existing room"""
    username = request.form.get('username', '').strip()
    room_id = request.form.get('room_id', '').strip()
    
    if not username or not room_id:
        return redirect(url_for('index'))
    
    # Get or create user
    user_id = get_or_create_user(username)
    
    # Check if room exists
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM rooms WHERE id = ? AND is_active = 1', (room_id,))
        room_data = cursor.fetchone()
        
        if not room_data:
            # Room doesn't exist or is inactive
            return render_template('index.html', error=f"Room {room_id} doesn't exist or has ended")
    
    # Store in session
    session['username'] = username
    session['user_id'] = user_id
    session['room_id'] = room_id
    session['room_name'] = room_data['name']
    
    return redirect(url_for('room', room_id=room_id))

@app.route('/room/<room_id>')
def room(room_id):
    """Video call room"""
    if 'username' not in session:
        return redirect(url_for('index'))
    
    # Verify room exists
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM rooms WHERE id = ? AND is_active = 1', (room_id,))
        room_data = cursor.fetchone()
        
        if not room_data:
            return redirect(url_for('index'))
    
    return render_template('room.html', 
                         room_id=room_id, 
                         username=session['username'],
                         room_name=room_data['name'])

@app.route('/api/rooms/<room_id>/participants')
def get_participants(room_id):
    """Get current participants in a room"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.username, rp.joined_at
            FROM room_participants rp
            JOIN users u ON rp.user_id = u.id
            WHERE rp.room_id = ? AND rp.left_at IS NULL
            ORDER BY rp.joined_at
        ''', (room_id,))
        
        participants = [dict(row) for row in cursor.fetchall()]
        return jsonify(participants)

@app.route('/api/rooms')
def get_active_rooms():
    """Get list of active rooms (for testing/debugging)"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT r.id, r.name, u.username as creator, r.created_at,
            (SELECT COUNT(*) FROM room_participants 
             WHERE room_id = r.id AND left_at IS NULL) as participant_count
            FROM rooms r
            JOIN users u ON r.created_by = u.id
            WHERE r.is_active = 1
            ORDER BY r.created_at DESC
            LIMIT 10
        ''')
        
        rooms = [dict(row) for row in cursor.fetchall()]
        return jsonify(rooms)

# WebRTC Signaling through Socket.IO
@socketio.on('join_room')
def on_join_room(data):
    """Handle user joining a room"""
    room_id = data['room_id']
    username = session.get('username')
    user_id = session.get('user_id')
    
    if not username or not user_id:
        return
    
    join_room(room_id)
    
    # Record participant joining
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO room_participants (room_id, user_id) VALUES (?, ?)
        ''', (room_id, user_id))
    
    # Notify others
    emit('user_joined', {
        'username': username,
        'user_id': user_id
    }, room=room_id, include_self=False)
    
    # Send current participants to the new user
    emit('room_users', get_room_participants(room_id))

@socketio.on('leave_room')
def on_leave_room(data):
    """Handle user leaving a room"""
    room_id = data['room_id']
    username = session.get('username')
    user_id = session.get('user_id')
    
    if not username or not user_id:
        return
    
    leave_room(room_id)
    
    # Update participant record
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE room_participants 
            SET left_at = CURRENT_TIMESTAMP 
            WHERE room_id = ? AND user_id = ? AND left_at IS NULL
        ''', (room_id, user_id))
    
    # Notify others
    emit('user_left', {
        'username': username,
        'user_id': user_id
    }, room=room_id, include_self=False)

@socketio.on('webrtc_offer')
def handle_offer(data):
    """Handle WebRTC offer"""
    target_user = data.get('target_user')
    if target_user:
        # Send to specific user
        room_id = data['room_id']
        from_user = data.get('from_user')
        emit('webrtc_offer', {
            'offer': data['offer'],
            'from_user': from_user,
            'target_user': target_user
        }, room=room_id, include_self=False)

@socketio.on('webrtc_answer')
def handle_answer(data):
    """Handle WebRTC answer"""
    target_user = data.get('target_user')
    if target_user:
        # Send to specific user
        room_id = data['room_id']
        from_user = data.get('from_user')
        emit('webrtc_answer', {
            'answer': data['answer'],
            'from_user': from_user,
            'target_user': target_user
        }, room=room_id, include_self=False)

@socketio.on('webrtc_ice_candidate')
def handle_ice_candidate(data):
    """Handle ICE candidate"""
    target_user = data.get('target_user')
    if target_user:
        # Send to specific user
        room_id = data['room_id']
        from_user = data.get('from_user')
        emit('webrtc_ice_candidate', {
            'candidate': data['candidate'],
            'from_user': from_user,
            'target_user': target_user
        }, room=room_id, include_self=False)

def get_room_participants(room_id):
    """Get list of current room participants"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.id, u.username
            FROM room_participants rp
            JOIN users u ON rp.user_id = u.id
            WHERE rp.room_id = ? AND rp.left_at IS NULL
        ''', (room_id,))
        
        return [{'user_id': row['id'], 'username': row['username']} 
                for row in cursor.fetchall()]

# Production WSGI server setup
if __name__ == '__main__':
    # Initialize database
    init_db()
    
    # Get port from environment variable for Render deployment
    port = int(os.environ.get('PORT', 8000))
    
    # Run the application
    socketio.run(app, host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', 'False') == 'True')