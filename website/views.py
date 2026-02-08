from flask import Blueprint, render_template, request, send_file, jsonify, after_this_request, current_app
from flask_socketio import SocketIO
from pytubefix import YouTube, Playlist, Search
import os
from . import socketio

views = Blueprint('views', __name__)

# --- Progress Callback ---
def progress_check(stream, chunk, bytes_remaining):
    total_size = stream.filesize
    bytes_downloaded = total_size - bytes_remaining
    percentage = (bytes_downloaded / total_size) * 100
    socketio.emit('progress', {'percentage': round(percentage, 1)})

# --- Page Routes ---
@views.route('/')
def home():
    return render_template('index.html')

@views.route('/video')
def video_page():
    url = request.args.get('url', '')
    return render_template('video.html', url=url)

@views.route('/audio')
def audio_page():
    url = request.args.get('url', '')
    return render_template('audio.html', url=url)

@views.route('/playlist')
def playlist_page():
    url = request.args.get('url', '')
    return render_template('playlist.html', url=url)

@views.route('/captions')
def captions_page():
    url = request.args.get('url', '')
    return render_template('captions.html', url=url)

# --- Functional API Routes ---
@views.route('/search', methods=['POST'])
def handle_search():
    query = request.form.get('query')
    results = Search(query)
    video_list = []
    for video in results.videos[:6]:
        video_list.append({
            'title': video.title,
            'url': video.watch_url,
            'thumbnail': video.thumbnail_url,
            'duration': video.length
        })
    return jsonify(video_list)

@views.route('/get_file/<filename>')
def deliver_and_cleanup(filename):
    # Use absolute path to ensure correct file resolution
    file_path = os.path.join(os.getcwd(), "downloads", filename)

    # Check existence before attempting to send
    if not os.path.exists(file_path):
        return "File not found.", 404

    # Create the response object using send_file
    response = send_file(file_path, as_attachment=True)

    # Register a callback to run AFTER the response is sent and closed
    @response.call_on_close
    def cleanup():
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Successfully cleaned up: {filename}")
        except Exception as e:
            print(f"Error during server cleanup: {e}")

    return response

# --- WebSocket Events (Progress Bar Enabled) ---
@socketio.on('start_video_download')
def handle_video(data):
    try:
        yt = YouTube(data['url'], on_progress_callback=progress_check)
        stream = yt.streams.get_highest_resolution()
        # Output path is relative to CWD (root), which is correct
        file_path = stream.download(output_path="downloads/")
        socketio.emit('video_ready', {'file_url': f'/get_file/{os.path.basename(file_path)}'})
    except Exception as e:
        socketio.emit('error', {'message': str(e)})

@socketio.on('start_audio_download')
def handle_audio(data):
    try:
        yt = YouTube(data['url'], on_progress_callback=progress_check)
        stream = yt.streams.get_audio_only()
        file_path = stream.download(output_path="downloads/")
        socketio.emit('download_ready', {'file_url': f'/get_file/{os.path.basename(file_path)}'})
    except Exception as e:
        socketio.emit('error', {'message': str(e)})

@socketio.on('start_playlist_download')
def handle_playlist(data):
    try:
        pl = Playlist(data['url'])
        socketio.emit('playlist_info', {'title': pl.title, 'count': len(pl.videos)})
        for index, video in enumerate(pl.videos):
            socketio.emit('next_video', {'index': index, 'title': video.title})
            video.streams.get_highest_resolution().download(output_path=f"downloads/{pl.title}/")
            socketio.emit('video_done', {'index': index})
        socketio.emit('playlist_complete', {'folder': pl.title})
    except Exception as e:
        socketio.emit('error', {'message': str(e)})

@socketio.on('fetch_captions')
def handle_captions(data):
    """View Available Subtitles"""
    try:
        yt = YouTube(data['url'])
        # View Available Subtitles: yt.captions
        tracks = [{'code': code, 'name': cap.name} for code, cap in yt.captions.items()]
        
        # We emit the list of available tracks to the frontend
        socketio.emit('captions_list', {'title': yt.title, 'tracks': tracks})
    except Exception as e:
        socketio.emit('error', {'message': str(e)})

@socketio.on('download_caption')
def handle_cap_dl(data):
    """Print and Save Subtitle Tracks"""
    try:
        yt = YouTube(data['url'])
        # Access specific track: yt.captions['code']
        caption = yt.captions[data['code']]
        
        # Generate SRT content
        srt_content = caption.generate_srt_captions()
        
        # Prepare the file name and path
        safe_title = "".join([c for c in yt.title if c.isalnum() or c in (' ', '_')]).rstrip()
        filename = f"{safe_title}_{data['code']}.srt".replace(" ", "_")
        
        # FIX: Ensure we write to the same absolute path that get_file reads from
        path = os.path.join(os.getcwd(), "downloads", filename)

        # Save Subtitles to a Text/SRT File
        caption.save_captions(path)
        
        # Inform the frontend that the file is ready for the user to download
        socketio.emit('caption_ready', {'file_url': f'/get_file/{filename}'})
    except Exception as e:
        socketio.emit('error', {'message': str(e)})