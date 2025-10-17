# YouTube Live Chat Downloader

A web application that allows you to download chat replays from YouTube Live streams. Export chat messages as CSV or as a beautiful YouTube-style HTML file.

## Features

- Clean, modern web interface
- Fetch chat messages from past YouTube Live streams
- Export chat as CSV (with timestamps, authors, and message content)
- Export chat as YouTube-style HTML (preserves chat formatting and badges)
- Docker support for easy deployment on Unraid or any Docker host
- No API key required - uses yt-dlp for reliable chat extraction

## Prerequisites

- Python 3.11+ (for local development)
- Docker and Docker Compose (for containerized deployment)

## Setup

### Option 1: Docker Compose (Recommended for Unraid)

1. Clone or download this repository

2. Build and run the container:
   ```bash
   docker-compose up -d
   ```

3. Access the application at `http://localhost:5000`

### Option 2: Docker Run

```bash
docker build -t youtube-live-downloader .

docker run -d \
  --name youtube-live-downloader \
  -p 5000:5000 \
  --restart unless-stopped \
  youtube-live-downloader
```

### Option 3: Local Development

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the application:
   ```bash
   python app.py
   ```

3. Access the application at `http://localhost:5000`

## Unraid Deployment

### Using Docker Compose (Community Applications)

1. Install the "Compose Manager" plugin from Community Applications (if not already installed)

2. Create a new compose stack:
   - Navigate to Docker > Compose
   - Click "Add New Stack"
   - Name it "youtube-live-downloader"
   - Paste the contents of `docker-compose.yml`

3. Set the port mapping (default is 5000)

4. Click "Compose Up" to start the container

### Using Unraid Docker Template

1. Navigate to Docker > Add Container

2. Configure the container:
   - **Name:** youtube-live-downloader
   - **Repository:** (build the image first or use a registry)
   - **Network Type:** Bridge
   - **Port:** 5000 (container) -> 5000 (host)

3. Click "Apply"

4. Access via `http://[UNRAID-IP]:5000`

## Usage

1. Open the web interface in your browser

2. Enter a YouTube Live stream URL (must be a completed/archived live stream)
   - Format: `https://www.youtube.com/watch?v=VIDEO_ID`
   - Or: `https://www.youtube.com/live/VIDEO_ID`

3. Click "Fetch Chat"

4. Once the chat is loaded, you'll see:
   - Video title and channel name
   - Number of messages found
   - Export buttons for CSV and HTML

5. Click either:
   - "Download CSV" for a spreadsheet-friendly format
   - "Download HTML" for a YouTube-style chat replay page

## Output Formats

### CSV Format
The CSV file includes the following columns:
- Timestamp (ISO 8601 format)
- Author (display name)
- Message (chat message content)
- Is Verified (boolean)
- Is Owner (boolean)
- Is Sponsor/Member (boolean)
- Is Moderator (boolean)

### HTML Format
The HTML export creates a fully styled, self-contained HTML file that mimics YouTube's chat interface:
- Dark theme matching YouTube
- Proper formatting for usernames, timestamps, and messages
- Visual badges for owners, moderators, and channel members
- Verified checkmarks
- Color-coded roles
- Scrollable chat replay

## Troubleshooting

### "Failed to fetch chat" error
- The video must be a completed live stream with chat replay enabled
- The video owner may have disabled chat replay
- Very old streams may not have archived chat data
- The URL must be valid and accessible

### Container won't start
- Check Docker logs: `docker logs youtube-live-downloader`
- Ensure port 5000 is not already in use
- Verify Docker has internet access to fetch chat data

### Chat download is slow
- Large streams with thousands of messages may take a few minutes to download
- The application fetches all messages before displaying results
- Be patient and wait for the fetch to complete

## Project Structure

```
youtube-live-downloader/
├── app.py                 # Flask application
├── requirements.txt       # Python dependencies
├── Dockerfile            # Docker configuration
├── docker-compose.yml    # Docker Compose configuration
├── .gitignore           # Git ignore rules
├── README.md            # This file
└── templates/
    └── index.html       # Web interface
```

## License

This project is provided as-is for personal use.

## Contributing

Feel free to open issues or submit pull requests for improvements.

## Notes

- This tool works with archived/completed live streams that have chat replay enabled
- Chat messages are fetched using yt-dlp, which is actively maintained and reliable
- Export files are generated on-demand and not stored on the server
- All processing happens on your server, keeping your data private
- No YouTube API key required
- Supports all standard chat message types including Super Chats and memberships
