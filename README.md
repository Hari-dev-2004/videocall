# VideoCall Platform

A real-time video chat application built with Flask and WebRTC.

## Features

- Create and join video chat rooms
- Real-time video and audio communication
- WebRTC for peer-to-peer connections
- Secure, low-latency connections
- Room participant tracking

## Local Development

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run the application:
   ```
   python app.py
   ```
4. Open http://127.0.0.1:8000 in your browser

## Deployment to Render

1. Create a new Web Service on Render
2. Connect your GitHub repository
3. Use the following settings:
   - **Environment**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn --worker-class eventlet -w 1 app:app`
4. Add the following environment variables:
   - `PORT`: 8000
   - `FLASK_DEBUG`: False
   - `SECRET_KEY`: [your-secret-key]

## Environment Variables

- `SECRET_KEY`: Secret key for Flask sessions
- `DATABASE_URL`: Database URL (defaults to local SQLite)
- `FLASK_DEBUG`: Set to "True" for debug mode
- `PORT`: Port to run the application (defaults to 8000)

## Database Schema

The application uses SQLite with the following tables:
- `users`: Stores user information
- `rooms`: Stores room information
- `room_participants`: Tracks participants joining and leaving rooms 