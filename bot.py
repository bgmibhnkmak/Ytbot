#!/usr/bin/env python3
"""
🚀 YouTube Downloader Bot - Railway Fixed Version
No StateFilter, Simplified & Stable
"""

import os
import re
import time
import logging
import asyncio
from typing import Dict, List, Optional
import yt_dlp
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from urllib.parse import urlparse, parse_qs

# Fix logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(level)s - %(message)s')
logger = logging.getLogger(__name__)

# Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable required!")

bot = TeleBot(BOT_TOKEN)

# Config
DOWNLOAD_PATH = "downloads/"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_DURATION = 1800  # 30 minutes

os.makedirs(DOWNLOAD_PATH, exist_ok=True)

class YouTubeDownloader:
    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Check if URL is supported"""
        patterns = [
            r'(youtube\.com|youtu\.be|youtube-nocookie\.com)',
            r'instagram\.com/(p|reel|tv)/',
            r'tiktok\.com/@[\w.]+/video/',
            r'facebook\.com.*video',
            r'(twitter\.com|x\.com)/[\w]+/status/'
        ]
        return bool(re.search('|'.join(patterns), url, re.IGNORECASE))
    
    @staticmethod
    async def get_info(url: str) -> Optional[Dict]:
        """Get video info & formats"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        
        try:
            loop = asyncio.get_event_loop()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await loop.run_in_executor(None, ydl.extract_info, url, False)
                
                video_formats = []
                audio_formats = []
                
                for f in info.get('formats', []):
                    if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                        height = f.get('height', 360)
                        if height <= 1080:  # Only reasonable qualities
                            video_formats.append({
                                'id': f['format_id'],
                                'quality': f"{height}p",
                                'ext': f.get('ext', 'mp4'),
                                'size': f.get('filesize_approx', 0)
                            })
                    
                    elif f.get('vcodec') == 'none' and f.get('acodec') != 'none':
                        audio_formats.append({'id': f['format_id'], 'quality': 'Audio'})
                
                return {
                    'title': info.get('title', 'Unknown')[:100],
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                    'formats': video_formats[:8],
                    'audio': audio_formats[0]['id'] if audio_formats else None
                }
        except Exception as e:
            logger.error(f"Info error: {e}")
            return None
    
    @staticmethod
    def download_file(url: str, format_id: str, is_audio: bool = False) -> Optional[str]:
        """Download file synchronously"""
        filename = f"{DOWNLOAD_PATH}{int(time.time())}.%(ext)s"
        
        ydl_opts = {
            'format': format_id,
            'outtmpl': filename,
        }
        
        if is_audio:
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                
                if is_audio:
                    filename = filename.rsplit('.', 1)[0] + '.mp3'
                
                # Size check
                if os.path.exists(filename) and os.path.getsize(filename) > MAX_FILE_SIZE:
                    os.remove(filename)
                    return None
                
                return filename
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None

downloader = YouTubeDownloader()

# ==================== COMMANDS ====================

@bot.message_handler(commands=['start', 'help'])
def start(message):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎵 Audio Only", callback_data="mode_audio"),
        InlineKeyboardButton("🎥 Video", callback_data="mode_video")
    )
    markup.add(InlineKeyboardButton("📋 Supported Sites", callback_data="sites"))
    
    text = """
🎥 *YouTube Downloader Bot*

*Send any YouTube/Instagram/TikTok link!*

✅ YouTube, Shorts, Playlist
✅ Instagram Reels  
✅ TikTok Videos
✅ Facebook Videos
✅ Twitter Videos

*Choose mode below:*
    """
    
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(func=lambda m: True)
def handle_url(message):
    """Handle URL messages"""
    url = message.text.strip()
    
    if not downloader.is_valid_url(url):
        bot.reply_to(message, "❌ *Unsupported URL!*\n\nSend YouTube/Instagram/TikTok link.", parse_mode='Markdown')
        return
    
    if len(url) > 1000:
        bot.reply_to(message, "❌ URL too long!")
        return
    
    bot.reply_to(message, "⏳ *Fetching formats...*", parse_mode='Markdown')
    
    # Process URL async
    asyncio.create_task(process_single_url(message.chat.id, message.message_id, url))

async def process_single_url(chat_id: int, msg_id: int, url: str):
    """Process single URL"""
    info = await downloader.get_info(url)
    
    if not info:
        bot.send_message(chat_id, "❌ Cannot fetch video info!")
        return
    
    if info['duration'] > MAX_DURATION:
        bot.send_message(chat_id, f"❌ Video too long! Max {MAX_DURATION//60} minutes.")
        return
    
    markup = InlineKeyboardMarkup(row_width=1)
    
    # Video formats
    for fmt in info['formats']:
        markup.add(InlineKeyboardButton(
            f"🎥 {fmt['quality']} ({fmt['ext']})",
            callback_data=f"dl_v_{fmt['id']}_{url[:50]}"
        ))
    
    # Audio
    if info['audio']:
        markup.add(InlineKeyboardButton("🎵 MP3 Audio (192kbps)", 
                                       callback_data=f"dl_a_{info['audio']}_{url[:50]}"))
    
    markup.add(InlineKeyboardButton("🔄 Refresh", callback_data="refresh"))
    
    text = f"""🎬 *{info['title']}*

👤 {info['uploader']}
⏱️ {info['duration']//60}:{info['duration']%60:02d}
🔗 `{url}`

*Choose quality:*
    """
    
    try:
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup, parse_mode='Markdown')
    except:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode='Markdown', disable_web_page_preview=True)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call: CallbackQuery):
    data = call.data
    
    if data in ["mode_audio", "mode_video", "sites"]:
        start(call.message)
        bot.answer_callback_query(call.id)
        return
    
    elif data == "refresh":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        return
    
    # Download callbacks
    try:
        parts = data.split("_", 2)
        dl_type = parts[1]  # v or a
        format_id = parts[2].split("_", 1)[0]
        url = "_".join(parts[2].split("_")[1:])  # Reconstruct URL
        
        bot.answer_callback_query(call.id, "⏳ Downloading...")
        bot.edit_message_text("🔄 *Downloading... Please wait (1-5 min)*", 
                            call.message.chat.id, call.message.message_id, parse_mode='Markdown')
        
        # Download & send
        asyncio.create_task(download_and_send(call.message.chat.id, call.message.message_id, url, format_id, dl_type == "a"))
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Error: {str(e)[:50]}")
        logger.error(f"Callback error: {e}")

async def download_and_send(chat_id: int, msg_id: int, url: str, format_id: str, is_audio: bool):
    """Download and send file"""
    try:
        filename = downloader.download_file(url, format_id, is_audio)
        
        if not filename or not os.path.exists(filename):
            bot.edit_message_text("❌ *Download failed!* Try different quality.", chat_id, msg_id, parse_mode='Markdown')
            return
        
        filesize = os.path.getsize(filename)
        logger.info(f"Sending {filename} ({filesize/1024/1024:.1f}MB)")
        
        if is_audio:
            with open(filename, 'rb') as f:
                bot.send_audio(chat_id, f, title="Audio", caption=f"✅ *Downloaded!*\n{filesize/1024/1024:.1f}MB")
        else:
            with open(filename, 'rb') as f:
                bot.send_video(chat_id, f, caption=f"✅ *Downloaded!*\n{filesize/1024/1024:.1f}MB")
        
        # Cleanup
        os.remove(filename)
        bot.delete_message(chat_id, msg_id)
        
    except Exception as e:
        logger.error(f"Send error: {e}")
        bot.edit_message_text(f"❌ *Send failed:* {str(e)[:100]}", chat_id, msg_id, parse_mode='Markdown')

# Run bot
if __name__ == "__main__":
    logger.info("🚀 YouTube Downloader Bot Started!")
    logger.info(f"Download path: {DOWNLOAD_PATH}")
    bot.infinity_polling(none_stop=True)