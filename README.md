# YouTube Live Chat Downloader

A web application that allows you to download chat replays from YouTube Live streams. Export chat messages as CSV or as a beautiful YouTube-style HTML file.

## Features

- Clean, modern web interface
- Fetch chat messages from past YouTube Live streams
- Export chat as CSV (with timestamps, authors, and message content)
- Export chat as YouTube-style HTML (preserves chat formatting and badges)
- Docker support for easy deployment on Unraid or any Docker host
- Uses official YouTube Data API v3

## Prerequisites

- Python 3.11+ (for local development)
- Docker and Docker Compose (for containerized deployment)
- YouTube Data API v3 Key

## Getting a YouTube API Key

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Enable the YouTube Data API v3:
   - Go to "APIs & Services" > "Library"
   - Search for "YouTube Data API v3"
   - Click "Enable"
4. Create credentials:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "API Key"
   - Copy your API key
5. (Optional) Restrict your API key:
   - Click on your API key to edit it
   - Under "API restrictions", select "Restrict key"
   - Choose "YouTube Data API v3"
   - Save

## Setup

### Option 1: Docker Compose (Recommended for Unraid)

1. Clone or download this repository

2. Create a `.env` file in the project directory:
   ```bash
   cp .env.example .env
   ```

3. Edit the `.env` file and add your YouTube API key:
   ```
   YOUTUBE_API_KEY=your_actual_api_key_here
   ```

4. Build and run the container:
   ```bash
   docker-compose up -d
   ```

5. Access the application at `http://localhost:5000`

### Option 2: Docker Run

```bash
docker build -t youtube-live-downloader .

docker run -d \
  --name youtube-live-downloader \
  -p 5000:5000 \
  -e YOUTUBE_API_KEY=your_api_key_here \
  --restart unless-stopped \
  youtube-live-downloader
```

### Option 3: Local Development

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create a `.env` file:
   ```bash
   cp .env.example .env
   ```

3. Add your YouTube API key to the `.env` file

4. Run the application:
   ```bash
   python app.py
   ```

5. Access the application at `http://localhost:5000`

## Unraid Deployment

### Using Docker Compose (Community Applications)

1. Install the "Compose Manager" plugin from Community Applications (if not already installed)

2. Create a new compose stack:
   - Navigate to Docker > Compose
   - Click "Add New Stack"
   - Name it "youtube-live-downloader"
   - Paste the contents of `docker-compose.yml`

3. Set up environment variables:
   - Add `YOUTUBE_API_KEY` in the environment variables section
   - Or create a `.env` file in your appdata folder

4. Set the port mapping (default is 5000)

5. Click "Compose Up" to start the container

### Using Unraid Docker Template

1. Navigate to Docker > Add Container

2. Configure the container:
   - **Name:** youtube-live-downloader
   - **Repository:** (build the image first or use a registry)
   - **Network Type:** Bridge
   - **Port:** 5000 (container) -> 5000 (host)
   - **Environment Variable:**
     - Key: `YOUTUBE_API_KEY`
     - Value: your_api_key_here

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

## API Limitations

The YouTube Data API v3 has quota limits:
- Default quota: 10,000 units per day
- Each API call consumes units (liveChatMessages.list costs ~5 units per request)
- A typical stream with 1000+ messages may require multiple API calls

If you hit quota limits, you'll need to wait until the next day or request a quota increase from Google.

## Troubleshooting

### "Live chat is not available for this video"
- The video must be a completed live stream with chat replay enabled
- The video owner may have disabled chat replay
- Very old streams may not have archived chat data

### "YouTube API error"
- Check that your API key is valid and properly set in the `.env` file
- Ensure the YouTube Data API v3 is enabled in your Google Cloud project
- Check if you've exceeded your daily quota

### Container won't start
- Verify the `.env` file exists and contains a valid API key
- Check Docker logs: `docker logs youtube-live-downloader`
- Ensure port 5000 is not already in use

## Project Structure

```
youtube-live-downloader/
├── app.py                 # Flask application
├── requirements.txt       # Python dependencies
├── Dockerfile            # Docker configuration
├── docker-compose.yml    # Docker Compose configuration
├── .env.example          # Environment variables template
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

- This tool only works with archived/completed live streams, not currently active streams
- Chat messages are fetched from YouTube's official API
- Export files are generated on-demand and not stored on the server
- All processing happens on your server, keeping your data private
