import os
import csv
import re
import json
import subprocess
import tempfile
from io import StringIO, BytesIO
from flask import Flask, render_template, request, jsonify, send_file
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)

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

def get_live_chat_messages(url):
    """Fetch live chat messages from a YouTube video using yt-dlp"""
    try:
        print(f"Attempting to download chat from: {url}")

        # Create a temporary directory for the chat file
        with tempfile.TemporaryDirectory() as temp_dir:
            output_template = os.path.join(temp_dir, 'chat')

            # Use yt-dlp to download live chat
            cmd = [
                'yt-dlp',
                '--write-subs',
                '--sub-lang', 'live_chat',
                '--skip-download',
                '--output', output_template,
                url
            ]

            print(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if result.returncode != 0:
                print(f"yt-dlp error: {result.stderr}")
                return {
                    'error': f'Failed to download chat. Please ensure the video has chat replay enabled. Error: {result.stderr[:200]}'
                }

            # Find the generated chat file
            chat_file = None
            for file in os.listdir(temp_dir):
                if 'live_chat' in file and file.endswith('.json'):
                    chat_file = os.path.join(temp_dir, file)
                    break

            if not chat_file or not os.path.exists(chat_file):
                return {
                    'error': 'No chat replay found. This video may not have chat replay enabled.'
                }

            # Parse the chat file (JSON Lines format - one JSON object per line)
            all_actions = []
            with open(chat_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        # Each line contains actions array
                        if 'replayChatItemAction' in data:
                            all_actions.append(data)
                    except json.JSONDecodeError as e:
                        print(f"Skipping invalid JSON line: {e}")
                        continue

            # Get video info from yt-dlp
            info_cmd = ['yt-dlp', '--dump-json', '--skip-download', url]
            info_result = subprocess.run(info_cmd, capture_output=True, text=True, timeout=30)

            video_title = 'Unknown'
            channel_name = 'Unknown'

            if info_result.returncode == 0:
                try:
                    video_info_data = json.loads(info_result.stdout)
                    video_title = video_info_data.get('title', 'Unknown')
                    channel_name = video_info_data.get('uploader', 'Unknown')
                except:
                    pass

            # Process messages
            messages = []

            for action in all_actions:
                # Handle replayChatItemAction
                if 'replayChatItemAction' not in action:
                    continue

                item_actions = action['replayChatItemAction'].get('actions', [])
                if not item_actions:
                    continue

                for item_action in item_actions:
                    # Get the actual chat item
                    if 'addChatItemAction' not in item_action:
                        continue

                    item = item_action['addChatItemAction'].get('item', {})

                    # Extract message data from different renderer types
                    renderer = item.get('liveChatTextMessageRenderer') or \
                              item.get('liveChatPaidMessageRenderer') or \
                              item.get('liveChatMembershipItemRenderer')

                    if not renderer:
                        continue

                    # Get timestamp
                    timestamp_usec = int(renderer.get('timestampUsec', 0))

                    # Get author info
                    author_name = renderer.get('authorName', {}).get('simpleText', 'Unknown')
                    author_channel_id = renderer.get('authorExternalChannelId', '')

                    # Get message text
                    message_text = ''
                    if 'message' in renderer:
                        message_runs = renderer['message'].get('runs', [])
                        message_text = ''.join([run.get('text', '') for run in message_runs])

                    # Get badges
                    badges = renderer.get('authorBadges', [])
                    is_verified = any('verifiedBadge' in badge.get('liveChatAuthorBadgeRenderer', {}).get('icon', {}).get('iconType', '')
                                     for badge in badges)
                    is_moderator = any('moderator' in badge.get('liveChatAuthorBadgeRenderer', {}).get('icon', {}).get('iconType', '').lower()
                                      for badge in badges)
                    is_owner = any('owner' in badge.get('liveChatAuthorBadgeRenderer', {}).get('icon', {}).get('iconType', '').lower()
                                  for badge in badges)
                    is_member = any('member' in badge.get('liveChatAuthorBadgeRenderer', {}).get('icon', {}).get('iconType', '').lower()
                                   for badge in badges)

                    message_data = {
                        'timestamp': timestamp_usec,
                        'author': author_name,
                        'message': message_text,
                        'author_channel_id': author_channel_id,
                        'is_verified': is_verified,
                        'is_chat_owner': is_owner,
                        'is_chat_sponsor': is_member,
                        'is_chat_moderator': is_moderator
                    }

                    messages.append(message_data)

            if len(messages) == 0:
                return {
                    'error': 'No chat messages found in the downloaded data. The chat may be empty or disabled.'
                }

            print(f"Successfully extracted {len(messages)} messages")

            return {
                'messages': messages,
                'count': len(messages),
                'video_info': {
                    'title': video_title,
                    'channel': channel_name,
                    'description': '',
                    'published_at': ''
                }
            }

    except subprocess.TimeoutExpired:
        return {'error': 'Download timed out. The video may be too long or the connection is slow.'}
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        import traceback
        traceback.print_exc()
        return {'error': f'Failed to fetch chat: {str(e)}'}

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

    # Get chat messages
    chat_result = get_live_chat_messages(url)

    if 'error' in chat_result:
        return jsonify(chat_result), 400

    return jsonify({
        'video_id': video_id,
        'video_info': chat_result['video_info'],
        'chat_data': {
            'messages': chat_result['messages'],
            'count': chat_result['count']
        }
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
        # Format timestamp
        timestamp = msg.get('timestamp', 0)
        if isinstance(timestamp, (int, float)):
            timestamp = datetime.fromtimestamp(timestamp / 1000000).isoformat()

        writer.writerow([
            timestamp,
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
        </div>

        <div class="chat-container">
"""

    for msg in messages:
        # Format timestamp
        timestamp = msg.get('timestamp', 0)
        try:
            if isinstance(timestamp, (int, float)):
                # Convert microseconds to datetime
                dt = datetime.fromtimestamp(timestamp / 1000000)
                time_str = dt.strftime('%H:%M:%S')
            else:
                time_str = str(timestamp)
        except:
            time_str = str(timestamp)

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
