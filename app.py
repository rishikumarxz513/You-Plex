from flask import Flask, after_this_request, render_template, request, send_file, jsonify
from flask_socketio import SocketIO
from pytubefix import YouTube, Playlist, Search
import os
import threading

app = Flask(__name__)
app.config['SECRET_KEY'] = 'streamline_key_99'
socketio = SocketIO(app)

# --- Progress Callback ---
def progress_check(stream, chunk, bytes_remaining):
    total_size = stream.filesize
    bytes_downloaded = total_size - bytes_remaining
    percentage = (bytes_downloaded / total_size) * 100
    socketio.emit('progress', {'percentage': round(percentage, 1)})

# --- Page Routes ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/video')
def video_page():
    url = request.args.get('url', '')
    return render_template('video.html', url=url)

@app.route('/audio')
def audio_page():
    url = request.args.get('url', '')
    return render_template('audio.html', url=url)

@app.route('/playlist')
def playlist_page():
    url = request.args.get('url', '')
    return render_template('playlist.html', url=url)

@app.route('/captions')
def captions_page():
    url = request.args.get('url', '')
    return render_template('captions.html', url=url)

# --- Functional API Routes ---
@app.route('/search', methods=['POST'])
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

@app.route('/get_file/<filename>')
def get_file(filename):
    path = os.path.join("downloads", filename)
    @after_this_request
    def cleanup(response):
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            print(f"Cleanup error: {e}")
        return response
    return send_file(path, as_attachment=True)

# --- WebSocket Events (Progress Bar Enabled) ---
@socketio.on('start_video_download')
def handle_video(data):
    try:
        yt = YouTube(data['url'], on_progress_callback=progress_check)
        stream = yt.streams.get_highest_resolution()
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
        
        # Generate SRT content: caption.generate_srt_captions()
        srt_content = caption.generate_srt_captions()
        
        # Prepare the file name and path
        safe_title = "".join([c for c in yt.title if c.isalnum() or c in (' ', '_')]).rstrip()
        filename = f"{safe_title}_{data['code']}.srt".replace(" ", "_")
        path = os.path.join("downloads", filename)

        # Save Subtitles to a Text/SRT File: caption.save_captions(filename)
        # Using the built-in save_captions method from pytubefix
        caption.save_captions(path)
        
        # Inform the frontend that the file is ready for the user to download
        socketio.emit('caption_ready', {'file_url': f'/get_file/{filename}'})
    except Exception as e:
        socketio.emit('error', {'message': str(e)})

@app.route('/get_file/<filename>')
def deliver_and_cleanup(filename):
    """Sends the file to the user and deletes it from the server immediately after."""
    # Construct the path to the downloads folder
    path = os.path.join("downloads", filename)
    
    # This part handles the automatic deletion after the user receives the file
    @after_this_request
    def remove_file(response):
        try:
            if os.path.exists(path):
                os.remove(path)
                print(f"Successfully cleaned up: {filename}")
        except Exception as e:
            app.logger.error(f"Error during server cleanup: {e}")
        return response

    # Check if the file actually exists before sending
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    else:
        return "File not found or already deleted.", 404

if __name__ == '__main__':
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)