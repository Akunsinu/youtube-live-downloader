import os
import csv
import re
from io import StringIO, BytesIO
from flask import Flask, render_template, request, jsonify, send_file
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)

# YouTube API setup
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')

def extract_video_id(url):
    """Extract video ID from various YouTube URL formats"""
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)',
        r'youtube\.com\/live\/([^&\n?#]+)'
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_video_info(video_id):
    """Get video metadata"""
    try:
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

        request = youtube.videos().list(
            part='snippet,liveStreamingDetails',
            id=video_id
        )
        response = request.execute()

        if not response['items']:
            return None

        video = response['items'][0]
        return {
            'title': video['snippet']['title'],
            'channel': video['snippet']['channelTitle'],
            'description': video['snippet']['description'],
            'published_at': video['snippet']['publishedAt']
        }
    except HttpError as e:
        print(f"An HTTP error occurred: {e}")
        return None

def get_live_chat_messages(video_id):
    """Fetch live chat messages from a YouTube video"""
    try:
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

        # Get the live chat ID
        video_response = youtube.videos().list(
            part='liveStreamingDetails',
            id=video_id
        ).execute()

        if not video_response['items']:
            return {'error': 'Video not found'}

        video = video_response['items'][0]

        # Check if video has live chat
        if 'liveStreamingDetails' not in video:
            return {'error': 'This video does not have live chat data'}

        if 'activeLiveChatId' not in video['liveStreamingDetails']:
            return {'error': 'Live chat is not available for this video'}

        live_chat_id = video['liveStreamingDetails']['activeLiveChatId']

        messages = []
        next_page_token = None

        # Fetch all chat messages
        while True:
            chat_response = youtube.liveChatMessages().list(
                liveChatId=live_chat_id,
                part='snippet,authorDetails',
                maxResults=2000,
                pageToken=next_page_token
            ).execute()

            for item in chat_response['items']:
                message_data = {
                    'timestamp': item['snippet']['publishedAt'],
                    'author': item['authorDetails']['displayName'],
                    'message': item['snippet']['displayMessage'],
                    'author_channel_id': item['authorDetails']['channelId'],
                    'is_verified': item['authorDetails'].get('isVerified', False),
                    'is_chat_owner': item['authorDetails'].get('isChatOwner', False),
                    'is_chat_sponsor': item['authorDetails'].get('isChatSponsor', False),
                    'is_chat_moderator': item['authorDetails'].get('isChatModerator', False)
                }
                messages.append(message_data)

            next_page_token = chat_response.get('nextPageToken')
            if not next_page_token:
                break

        return {'messages': messages, 'count': len(messages)}

    except HttpError as e:
        error_content = e.content.decode('utf-8')
        print(f"An HTTP error occurred: {error_content}")
        return {'error': f'YouTube API error: {error_content}'}
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return {'error': str(e)}

@app.route('/')
def index():
    """Render the landing page"""
    return render_template('index.html')

@app.route('/api/fetch-chat', methods=['POST'])
def fetch_chat():
    """API endpoint to fetch chat messages"""
    data = request.json
    url = data.get('url')

    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({'error': 'Invalid YouTube URL'}), 400

    # Get video info
    video_info = get_video_info(video_id)
    if not video_info:
        return jsonify({'error': 'Could not fetch video information'}), 400

    # Get chat messages
    chat_data = get_live_chat_messages(video_id)

    if 'error' in chat_data:
        return jsonify(chat_data), 400

    return jsonify({
        'video_id': video_id,
        'video_info': video_info,
        'chat_data': chat_data
    })

@app.route('/api/export-csv', methods=['POST'])
def export_csv():
    """Export chat messages as CSV"""
    data = request.json
    messages = data.get('messages', [])
    video_info = data.get('video_info', {})

    if not messages:
        return jsonify({'error': 'No messages to export'}), 400

    # Create CSV in memory
    output = StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow(['Timestamp', 'Author', 'Message', 'Is Verified', 'Is Owner', 'Is Sponsor', 'Is Moderator'])

    # Write data
    for msg in messages:
        writer.writerow([
            msg['timestamp'],
            msg['author'],
            msg['message'],
            msg.get('is_verified', False),
            msg.get('is_chat_owner', False),
            msg.get('is_chat_sponsor', False),
            msg.get('is_chat_moderator', False)
        ])

    # Prepare file for download
    output.seek(0)
    video_title = video_info.get('title', 'chat').replace(' ', '_')
    filename = f"{video_title}_chat.csv"

    return send_file(
        BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )

@app.route('/api/export-html', methods=['POST'])
def export_html():
    """Export chat messages as YouTube-style HTML"""
    data = request.json
    messages = data.get('messages', [])
    video_info = data.get('video_info', {})

    if not messages:
        return jsonify({'error': 'No messages to export'}), 400

    # Generate HTML
    html_content = generate_youtube_style_html(messages, video_info)

    video_title = video_info.get('title', 'chat').replace(' ', '_')
    filename = f"{video_title}_chat.html"

    return send_file(
        BytesIO(html_content.encode('utf-8')),
        mimetype='text/html',
        as_attachment=True,
        download_name=filename
    )

def generate_youtube_style_html(messages, video_info):
    """Generate YouTube-style HTML for chat messages"""
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{video_info.get('title', 'YouTube Live Chat')} - Chat Replay</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: "Roboto", "Arial", sans-serif;
            background-color: #0f0f0f;
            color: #fff;
            padding: 20px;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        .header {{
            background-color: #212121;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 20px;
        }}

        .header h1 {{
            font-size: 24px;
            margin-bottom: 10px;
        }}

        .header .channel {{
            color: #aaa;
            font-size: 14px;
        }}

        .stats {{
            background-color: #212121;
            padding: 15px 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            display: flex;
            gap: 30px;
        }}

        .stat {{
            color: #aaa;
            font-size: 14px;
        }}

        .stat strong {{
            color: #fff;
        }}

        .chat-container {{
            background-color: #212121;
            border-radius: 12px;
            padding: 20px;
            max-height: 80vh;
            overflow-y: auto;
        }}

        .chat-message {{
            display: flex;
            padding: 8px 0;
            align-items: flex-start;
        }}

        .chat-message:hover {{
            background-color: #2a2a2a;
        }}

        .timestamp {{
            color: #717171;
            font-size: 12px;
            min-width: 80px;
            margin-right: 15px;
        }}

        .author {{
            font-weight: 500;
            margin-right: 8px;
            color: #fff;
            font-size: 13px;
        }}

        .author.owner {{
            color: #ffd600;
        }}

        .author.moderator {{
            color: #5e84f1;
        }}

        .author.sponsor {{
            color: #0f9d58;
        }}

        .author.verified {{
            display: inline-flex;
            align-items: center;
        }}

        .author.verified::after {{
            content: "✓";
            display: inline-block;
            background-color: #606060;
            color: #fff;
            border-radius: 50%;
            width: 14px;
            height: 14px;
            font-size: 10px;
            text-align: center;
            line-height: 14px;
            margin-left: 4px;
        }}

        .badge {{
            display: inline-block;
            background-color: #cc0000;
            color: #fff;
            font-size: 10px;
            padding: 2px 6px;
            border-radius: 2px;
            margin-right: 6px;
            font-weight: 500;
        }}

        .badge.owner {{
            background-color: #ffd600;
            color: #0f0f0f;
        }}

        .badge.moderator {{
            background-color: #5e84f1;
        }}

        .badge.sponsor {{
            background-color: #0f9d58;
        }}

        .message {{
            color: #fff;
            font-size: 13px;
            line-height: 18px;
            word-wrap: break-word;
            flex: 1;
        }}

        .message-content {{
            display: flex;
            flex-direction: column;
            flex: 1;
        }}

        .author-line {{
            display: flex;
            align-items: center;
            margin-bottom: 4px;
        }}

        /* Scrollbar styling */
        .chat-container::-webkit-scrollbar {{
            width: 8px;
        }}

        .chat-container::-webkit-scrollbar-track {{
            background: #0f0f0f;
        }}

        .chat-container::-webkit-scrollbar-thumb {{
            background: #717171;
            border-radius: 4px;
        }}

        .chat-container::-webkit-scrollbar-thumb:hover {{
            background: #909090;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{video_info.get('title', 'YouTube Live Chat')}</h1>
            <div class="channel">{video_info.get('channel', 'Unknown Channel')}</div>
        </div>

        <div class="stats">
            <div class="stat"><strong>{len(messages)}</strong> messages</div>
            <div class="stat">Published: <strong>{video_info.get('published_at', 'Unknown')}</strong></div>
        </div>

        <div class="chat-container">
"""

    for msg in messages:
        # Format timestamp
        try:
            timestamp = datetime.fromisoformat(msg['timestamp'].replace('Z', '+00:00'))
            time_str = timestamp.strftime('%H:%M:%S')
        except:
            time_str = msg['timestamp']

        # Determine author class and badges
        author_class = "author"
        badges = []

        if msg.get('is_chat_owner'):
            author_class += " owner"
            badges.append('<span class="badge owner">OWNER</span>')
        elif msg.get('is_chat_moderator'):
            author_class += " moderator"
            badges.append('<span class="badge moderator">MOD</span>')

        if msg.get('is_chat_sponsor'):
            badges.append('<span class="badge sponsor">MEMBER</span>')

        if msg.get('is_verified'):
            author_class += " verified"

        badges_html = ''.join(badges)

        html += f"""            <div class="chat-message">
                <div class="timestamp">{time_str}</div>
                <div class="message-content">
                    <div class="author-line">
                        {badges_html}
                        <span class="{author_class}">{msg['author']}</span>
                    </div>
                    <div class="message">{msg['message']}</div>
                </div>
            </div>
"""

    html += """        </div>
    </div>
</body>
</html>"""

    return html

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
