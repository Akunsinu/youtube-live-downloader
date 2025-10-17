import os
import csv
import re
import json
import subprocess
import tempfile
import html as html_module
from io import StringIO, BytesIO
from collections import Counter
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

                    # Get author avatar (use highest quality available)
                    author_photo = renderer.get('authorPhoto', {}).get('thumbnails', [])
                    avatar_url = ''
                    if author_photo:
                        # Get the last thumbnail (usually highest quality)
                        avatar_url = author_photo[-1].get('url', '')

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
                        'avatar_url': avatar_url,
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
    html_content = generate_youtube_style_html_with_analytics(messages, video_info)

    video_title = video_info.get('title', 'chat').replace(' ', '_')
    filename = f"{video_title}_chat.html"

    return send_file(
        BytesIO(html_content.encode('utf-8')),
        mimetype='text/html',
        as_attachment=True,
        download_name=filename
    )

def generate_youtube_style_html_with_analytics(messages, video_info):
    """Generate YouTube-style HTML for chat messages with search and analytics"""

    # Calculate analytics
    total_messages = len(messages)
    unique_chatters = len(set(msg['author'] for msg in messages))

    # Count messages per author
    author_counts = Counter(msg['author'] for msg in messages)
    top_chatters = author_counts.most_common(10)

    # Count badges
    owner_count = sum(1 for msg in messages if msg.get('is_chat_owner', False))
    mod_count = sum(1 for msg in messages if msg.get('is_chat_moderator', False))
    member_count = sum(1 for msg in messages if msg.get('is_chat_sponsor', False))
    verified_count = sum(1 for msg in messages if msg.get('is_verified', False))

    # Convert messages to JSON for JavaScript
    messages_json = json.dumps(messages)

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
            max-width: 1400px;
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

        .controls {{
            background-color: #212121;
            padding: 15px 20px;
            border-radius: 12px;
            margin-bottom: 20px;
        }}

        .search-box {{
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
        }}

        .search-box input {{
            flex: 1;
            padding: 10px 15px;
            background-color: #2a2a2a;
            border: 1px solid #3a3a3a;
            border-radius: 8px;
            color: #fff;
            font-size: 14px;
        }}

        .search-box input:focus {{
            outline: none;
            border-color: #667eea;
        }}

        .search-box button {{
            padding: 10px 20px;
            background-color: #667eea;
            border: none;
            border-radius: 8px;
            color: #fff;
            cursor: pointer;
            font-size: 14px;
        }}

        .search-box button:hover {{
            background-color: #5568d3;
        }}

        .search-stats {{
            color: #aaa;
            font-size: 13px;
        }}

        .main-content {{
            display: grid;
            grid-template-columns: 300px 1fr;
            gap: 20px;
        }}

        .analytics-panel {{
            background-color: #212121;
            border-radius: 12px;
            padding: 20px;
            height: fit-content;
            position: sticky;
            top: 20px;
        }}

        .analytics-section {{
            margin-bottom: 25px;
        }}

        .analytics-section:last-child {{
            margin-bottom: 0;
        }}

        .analytics-section h3 {{
            font-size: 16px;
            margin-bottom: 12px;
            color: #667eea;
        }}

        .stat-item {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #2a2a2a;
        }}

        .stat-item:last-child {{
            border-bottom: none;
        }}

        .stat-label {{
            color: #aaa;
            font-size: 13px;
        }}

        .stat-value {{
            color: #fff;
            font-weight: 500;
            font-size: 13px;
        }}

        .top-chatter {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 6px 0;
            font-size: 12px;
        }}

        .top-chatter-name {{
            color: #fff;
            flex: 1;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}

        .top-chatter-count {{
            color: #667eea;
            font-weight: 500;
            margin-left: 10px;
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
            gap: 12px;
        }}

        .chat-message:hover {{
            background-color: #2a2a2a;
        }}

        .chat-message.hidden {{
            display: none;
        }}

        .chat-message.highlight {{
            background-color: #3a3a00;
        }}

        .avatar {{
            width: 24px;
            height: 24px;
            border-radius: 50%;
            object-fit: cover;
            flex-shrink: 0;
        }}

        .timestamp {{
            color: #717171;
            font-size: 12px;
            min-width: 80px;
            margin-right: 15px;
            flex-shrink: 0;
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

        .highlight-text {{
            background-color: #ffd600;
            color: #000;
            padding: 2px 4px;
            border-radius: 2px;
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

        @media (max-width: 1024px) {{
            .main-content {{
                grid-template-columns: 1fr;
            }}

            .analytics-panel {{
                position: static;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{video_info.get('title', 'YouTube Live Chat')}</h1>
            <div class="channel">{video_info.get('channel', 'Unknown Channel')}</div>
        </div>

        <div class="controls">
            <div class="search-box">
                <input type="text" id="searchInput" placeholder="Search messages, usernames...">
                <button onclick="searchMessages()">Search</button>
                <button onclick="clearSearch()" style="background-color: #3a3a3a;">Clear</button>
            </div>
            <div class="search-stats" id="searchStats">Showing all {total_messages} messages</div>
        </div>

        <div class="main-content">
            <div class="analytics-panel">
                <div class="analytics-section">
                    <h3>📊 Overview</h3>
                    <div class="stat-item">
                        <span class="stat-label">Total Messages</span>
                        <span class="stat-value">{total_messages:,}</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Unique Chatters</span>
                        <span class="stat-value">{unique_chatters:,}</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Avg. msgs/user</span>
                        <span class="stat-value">{total_messages / max(unique_chatters, 1):.1f}</span>
                    </div>
                </div>

                <div class="analytics-section">
                    <h3>🏅 Badges</h3>
                    <div class="stat-item">
                        <span class="stat-label">👑 Owners</span>
                        <span class="stat-value">{owner_count}</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">🛡️ Moderators</span>
                        <span class="stat-value">{mod_count}</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">💎 Members</span>
                        <span class="stat-value">{member_count}</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">✓ Verified</span>
                        <span class="stat-value">{verified_count}</span>
                    </div>
                </div>

                <div class="analytics-section">
                    <h3>🔥 Top Chatters</h3>
"""

    for i, (author, count) in enumerate(top_chatters, 1):
        html += f"""                    <div class="top-chatter">
                        <span class="top-chatter-name">{i}. {author}</span>
                        <span class="top-chatter-count">{count}</span>
                    </div>
"""

    html += """                </div>
            </div>

            <div class="chat-container" id="chatContainer">
"""

    # Generate chat messages
    for msg in messages:
        # Format timestamp
        from datetime import datetime as dt
        timestamp = msg.get('timestamp', 0)
        try:
            if isinstance(timestamp, (int, float)):
                dt_obj = dt.fromtimestamp(timestamp / 1000000)
                time_str = dt_obj.strftime('%H:%M:%S')
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
        avatar_url = msg.get('avatar_url', '')

        # Escape HTML in message and author
        import html as html_module
        author_escaped = html_module.escape(msg['author'])
        message_escaped = html_module.escape(msg['message'])

        html += f"""                <div class="chat-message" data-author="{author_escaped.lower()}" data-message="{message_escaped.lower()}">
                    <div class="timestamp">{time_str}</div>
                    <img src="{avatar_url}" alt="{author_escaped}" class="avatar" loading="lazy">
                    <div class="message-content">
                        <div class="author-line">
                            {badges_html}
                            <span class="{author_class}">{author_escaped}</span>
                        </div>
                        <div class="message">{message_escaped}</div>
                    </div>
                </div>
"""

    html += f"""            </div>
        </div>
    </div>

    <script>
        const allMessages = {messages_json};
        let currentFilter = '';

        function searchMessages() {{
            const searchTerm = document.getElementById('searchInput').value.toLowerCase().trim();
            currentFilter = searchTerm;

            if (!searchTerm) {{
                clearSearch();
                return;
            }}

            const messages = document.querySelectorAll('.chat-message');
            let visibleCount = 0;

            messages.forEach(msg => {{
                const author = msg.dataset.author || '';
                const message = msg.dataset.message || '';

                if (author.includes(searchTerm) || message.includes(searchTerm)) {{
                    msg.classList.remove('hidden');
                    msg.classList.add('highlight');
                    visibleCount++;
                }} else {{
                    msg.classList.add('hidden');
                    msg.classList.remove('highlight');
                }}
            }});

            document.getElementById('searchStats').textContent =
                `Showing ${{visibleCount}} of {total_messages} messages matching "${{searchTerm}}"`;
        }}

        function clearSearch() {{
            currentFilter = '';
            document.getElementById('searchInput').value = '';

            const messages = document.querySelectorAll('.chat-message');
            messages.forEach(msg => {{
                msg.classList.remove('hidden');
                msg.classList.remove('highlight');
            }});

            document.getElementById('searchStats').textContent =
                'Showing all {total_messages} messages';
        }}

        // Allow Enter key to search
        document.getElementById('searchInput').addEventListener('keypress', function(e) {{
            if (e.key === 'Enter') {{
                searchMessages();
            }}
        }});

        // Real-time search (optional)
        document.getElementById('searchInput').addEventListener('input', function() {{
            if (this.value.trim() === '') {{
                clearSearch();
            }}
        }});
    </script>
</body>
</html>"""

    return html
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
