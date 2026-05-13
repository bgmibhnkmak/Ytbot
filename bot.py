#!/usr/bin/env python3
"""
Advanced YouTube Downloader Telegram Bot
Features: Audio/Video, Format Selection, Playlist, Quality Choice
Deploy: Railway + Render + VPS
"""

import os
import re
import asyncio
import logging
from typing import Dict, List
import yt_dlp
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from telebot.handlers import StateFilter, ContentTypeFilter
from telebot.storage import StateMemoryStorage
from urllib.parse import urlparse

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot Token (Railway Environment Variable)
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = TeleBot(BOT_TOKEN, state_storage=StateMemoryStorage())

# Download limits
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_DURATION = 3600  # 1 hour

class YouTubeDownloader:
    def __init__(self):
        self.download_path = "downloads/"
        os.makedirs(self.download_path, exist_ok=True)
    
    async def get_formats(self, url: str) -> Dict:
        """Get available formats for video"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                formats = []
                # Video formats
                for f in info.get('formats', []):
                    if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                        height = f.get('height', 0)
                        fps = f.get('fps', 0)
                        ext = f.get('ext', 'mp4')
                        formats.append({
                            'format_id': f['format_id'],
                            'height': height,
                            'fps': fps,
                            'ext': ext,
                            'filesize': f.get('filesize', 0),
                            'type': 'video'
                        })
                
                # Audio only
                audio_formats = []
                for f in info.get('formats', []):
                    if f.get('vcodec') == 'none' and f.get('acodec') != 'none':
                        audio_formats.append({
                            'format_id': f['format_id'],
                            'ext': f.get('ext', 'mp3'),
                            'type': 'audio'
                        })
                
                return {
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail'),
                    'formats': formats[:10],  # Top 10 video formats
                    'audio_formats': audio_formats[:5]
                }
        except Exception as e:
            logger.error(f"Error getting formats: {e}")
            return None
    
    async def download_video(self, url: str, format_id: str, audio_only: bool = False) -> str:
        """Download video/audio"""
        filename = f"{self.download_path}{int(time.time())}.%(ext)s"
        
        ydl_opts = {
            'format': format_id if not audio_only else 'bestaudio/best',
            'outtmpl': filename,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }] if audio_only else [],
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                
                if audio_only:
                    filename = filename.rsplit('.', 1)[0] + '.mp3'
                
                # Check file size
                if os.path.getsize(filename) > MAX_FILE_SIZE:
                    os.remove(filename)
                    return None
                
                return filename
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None

downloader = YouTubeDownloader()

# ==================== HANDLERS ====================

@bot.message_handler(commands=['start'])
def start_command(message):
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        InlineKeyboardButton("🎵 Audio", callback_data="type_audio"),
        InlineKeyboardButton("🎥 Video", callback_data="type_video")
    )
    markup.add(InlineKeyboardButton("ℹ️ How to use", callback_data="help"))
    
    bot.send_message(
        message.chat.id,
        "🎵 *YouTube Downloader Bot*\n\n"
        "Send me YouTube/Instagram/TikTok link!\n"
        "Choose Audio or Video format.",
        reply_markup=markup,
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call: CallbackQuery):
    if call.data == "help":
        help_text = """
*How to use:*

1️⃣ Send YouTube/Instagram/TikTok link
2️⃣ Choose Audio or Video  
3️⃣ Select quality/format
4️⃣ Download!

*Supported:*
✅ YouTube, YouTube Shorts
✅ Instagram Reels
✅ TikTok
✅ Facebook
✅ Twitter/X
        """
        bot.edit_message_text(help_text, call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    
    elif call.data.startswith("type_"):
        media_type = "Audio" if call.data == "type_audio" else "Video"
        bot.edit_message_text(
            f"🎵 *{media_type} Mode*\n\n"
            f"Send me the link to download!",
            call.message.chat.id,
            call.message.message_id,
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(call.message, process_url)
    
    elif call.data.startswith("format_"):
        # Extract format details from callback data
        parts = call.data.split("_")
        format_id = "_".join(parts[1:])
        url = call.message.text.split("URL: ")[1].split("\n")[0] if "URL: " in call.message.text else ""
        
        if not url:
            bot.answer_callback_query(call.id, "Error: URL not found!")
            return
        
        bot.answer_callback_query(call.id, "⏳ Downloading...")
        bot.edit_message_text("⏳ Downloading... Please wait!", call.message.chat.id, call.message.message_id)
        
        # Download async
        asyncio.create_task(download_and_send(call.message.chat.id, call.message.message_id, url, format_id))

async def download_and_send(chat_id: int, msg_id: int, url: str, format_id: str):
    """Download and send file"""
    filename = await downloader.download_video(url, format_id)
    
    if filename and os.path.exists(filename):
        try:
            with open(filename, 'rb') as video_file:
                bot.send_video(chat_id, video_file, caption=f"✅ Downloaded!\n{url}")
            os.remove(filename)  # Cleanup
        except Exception as e:
            bot.send_message(chat_id, f"❌ File too large or error: {e}")
            if os.path.exists(filename):
                os.remove(filename)
    else:
        bot.edit_message_text("❌ Download failed!", chat_id, msg_id)

def process_url(message):
    """Process YouTube URL"""
    url = message.text.strip()
    
    if not is_valid_url(url):
        bot.reply_to(message, "❌ Invalid URL!\nSend YouTube/Instagram/TikTok link.")
        return
    
    # Show formats
    asyncio.create_task(show_formats(message.chat.id, message.message_id, url))

async def show_formats(chat_id: int, msg_id: int, url: str):
    """Show available formats"""
    formats_info = await downloader.get_formats(url)
    
    if not formats_info:
        bot.send_message(chat_id, "❌ Cannot fetch video info!")
        return
    
    if formats_info['duration'] > MAX_DURATION:
        bot.send_message(chat_id, "❌ Video too long! Max 1 hour.")
        return
    
    markup = InlineKeyboardMarkup(row_width=1)
    
    # Add video formats
    for fmt in formats_info['formats']:
        label = f"{fmt['height']}p {fmt['fps']}fps ({fmt['ext']})"
        markup.add(InlineKeyboardButton(label, callback_data=f"format_{fmt['format_id']}"))
    
    # Audio option
    markup.add(InlineKeyboardButton("🎵 MP3 Audio (192kbps)", callback_data="format_bestaudio"))
    
    text = f"""🎥 *{formats_info['title'][:100]}...*

📺 *Duration:* {formats_info['duration']//60}:{formats_info['duration']%60:02d}
🔗 *URL:* {url}

Choose format:"""

    try:
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup, parse_mode='Markdown')
    except:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode='Markdown')

def is_valid_url(url: str) -> bool:
    """Validate URL"""
    patterns = [
        r'youtube\.com/watch\?v=',
        r'youtu\.be/',
        r'instagram\.com',
        r'tiktok\.com',
        r'facebook\.com',
        r'twitter\.com',
        r'x\.com'
    ]
    return any(re.search(pattern, url, re.IGNORECASE) for pattern in patterns)

# Error handler
@bot.message_handler(content_types=['photo', 'sticker', 'voice'])
def handle_unsupported(message):
    bot.reply_to(message, "❌ Send only YouTube/Instagram/TikTok links!")

if __name__ == "__main__":
    logger.info("🚀 Bot started!")
    bot.infinity_polling()