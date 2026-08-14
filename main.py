import time
import random
import string
import re
import os
import json
import threading
import uuid
import http.server
import socketserver

import customtkinter as ctk

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException

# Try importing multimedia libraries
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    print("Warning: 'pygame' not found. Sound effects will be disabled. Run 'pip install pygame' to enable.")

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("Warning: 'pillow' not found. Custom visual themes will be disabled. Run 'pip install pillow' to enable.")


# ==========================================
# CUSTOMTKINTER THEME SETUP (Gemini Style)
# ==========================================
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

# Gemini Colors
BG_MAIN = "#131314"
BG_SIDEBAR = "#1e1f20"
BG_INPUT = "#1e1f20"
BG_USER_BUBBLE = "#282a2c"
TEXT_MAIN = "#e3e3e3"
HOVER_COLOR = "#333537"

# ==========================================
# CONFIG & HISTORY MANAGEMENT
# ==========================================
CONFIG_FILE = "config.json"
HISTORY_FILE = "chats.json"

def generate_api_key():
    return "sk-freeai-" + ''.join(random.choices(string.ascii_letters + string.digits, k=32))

def load_config():
    default_config = {
        "calibrated": False,
        "local_api_key": generate_api_key(),
        "api_port": 5000,
        "ai_personality": "",
        "about_user": "",
        "visual_theme": "Default",
        "sound_theme": "Default"
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                default_config.update(data)
                if "local_api_key" not in data:
                    default_config["local_api_key"] = generate_api_key()
        except Exception:
            pass
    return default_config

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_history(history):
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=4)


# ==========================================
# THEME & AUDIO MANAGEMENT
# ==========================================
def get_available_themes():
    themes = ["Default"]
    if os.path.exists("Themes"):
        for name in os.listdir("Themes"):
            if os.path.isdir(os.path.join("Themes", name)):
                themes.append(name)
    return themes

def get_available_sfx():
    sfx = ["Default"]
    if os.path.exists("Sfx"):
        for name in os.listdir("Sfx"):
            if os.path.isdir(os.path.join("Sfx", name)):
                sfx.append(name)
    return sfx

def get_theme_image_path(theme_name):
    if theme_name == "Default": 
        return None
    path = os.path.join("Themes", theme_name)
    if os.path.exists(path):
        for file in os.listdir(path):
            if file.lower().endswith((".png", ".jpg", ".jpeg")):
                return os.path.join(path, file)
    return None

class AudioManager:
    def __init__(self):
        self.enabled = PYGAME_AVAILABLE
        self.button_sound = None
        self.typing_sounds = []
        self.last_type_time = 0
        self.type_index = 0
        self.play_in_order = False
        
        if self.enabled:
            try:
                pygame.mixer.init()
            except Exception as e:
                print(f"Failed to initialize audio mixer: {e}")
                self.enabled = False

    def load_theme(self, theme_name):
        self.button_sound = None
        self.typing_sounds.clear()
        self.type_index = 0
        self.play_in_order = False
        
        if theme_name == "Default" or not self.enabled:
            return
            
        btn_path = os.path.join("Sfx", theme_name, "Button.mp3")
        if os.path.exists(btn_path):
            try:
                self.button_sound = pygame.mixer.Sound(btn_path)
            except Exception:
                pass
                
        type_dir = os.path.join("Sfx", theme_name, "Type")
        if os.path.exists(type_dir):
            files_in_dir = os.listdir(type_dir)
            
            # Check for the "inorder" flag file
            if any(f.lower() in ["inorder", "inorder.txt"] for f in files_in_dir):
                self.play_in_order = True

            # Get sound files and sort them naturally (so 10.mp3 comes after 9.mp3)
            sound_files = [f for f in files_in_dir if f.lower().endswith((".mp3", ".wav"))]
            
            def natural_sort_key(s):
                return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]
                
            sound_files.sort(key=natural_sort_key)

            for file in sound_files:
                try:
                    snd = pygame.mixer.Sound(os.path.join(type_dir, file))
                    self.typing_sounds.append(snd)
                except Exception:
                    pass

    def play_button(self):
        if self.enabled and self.button_sound:
            try:
                self.button_sound.play()
            except Exception:
                pass

    def play_type(self):
        if self.enabled and self.typing_sounds:
            now = time.time()
            # Throttle to prevent severe overlapping lag
            if now - self.last_type_time > 0.08:
                try:
                    if self.play_in_order:
                        self.typing_sounds[self.type_index].play()
                        self.type_index = (self.type_index + 1) % len(self.typing_sounds)
                    else:
                        random.choice(self.typing_sounds).play()
                    self.last_type_time = now
                except Exception:
                    pass

# ==========================================
# SELENIUM BROWSER AUTOMATION
# ==========================================
class ChatGPTBrowser:
    def __init__(self, update_status_callback):
        self.driver = None
        self.update_status = update_status_callback
        self.is_hidden = False

    def generate_verification_code(self):
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

    def start_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        
        local_driver_path = r".\chromedriver\win64\150.0.7871.124\chromedriver.exe"
        
        try:
            if os.path.exists(local_driver_path):
                service = Service(executable_path=local_driver_path)
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                self.driver = webdriver.Chrome(options=chrome_options)
            
            self.driver.get("https://chat.openai.com")
            self.is_hidden = False
            return True
        except Exception as e:
            print(f"Driver Error: {e}")
            return False

    def close_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass

    def minimize_to_background(self):
        if self.driver:
            try:
                self.driver.set_window_position(-32000, -32000)
                self.is_hidden = True
            except Exception:
                pass

    def toggle_window_visibility(self):
        if not self.driver:
            return False
        try:
            if self.is_hidden:
                self.driver.set_window_position(0, 0)
                self.driver.maximize_window()
                self.is_hidden = False
            else:
                self.driver.set_window_position(-32000, -32000)
                self.is_hidden = True
            return True
        except Exception:
            return False

    def scan_for_code(self, code):
        for i in range(10):
            try:
                textareas = self.driver.find_elements(By.CSS_SELECTOR, "textarea")
                for textarea in textareas:
                    if code in (textarea.get_attribute("value") or "") or code in (textarea.text or ""):
                        return True

                editables = self.driver.find_elements(By.CSS_SELECTOR, "[contenteditable='true'], #prompt-textarea")
                for editable in editables:
                    if code in editable.text:
                        return True
            except Exception:
                pass
            time.sleep(1)
        return False

    def find_chat_input(self):
        selectors = ["#prompt-textarea", "textarea", "[contenteditable='true']", "div[data-placeholder]"]
        for selector in selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for el in elements:
                    if el.is_displayed():
                        return el
            except:
                continue
        return None

    def get_assistant_message_count(self):
        try:
            return len(self.driver.find_elements(By.CSS_SELECTOR, "[data-message-author-role='assistant']"))
        except:
            return 0

    def get_latest_assistant_text(self):
        try:
            responses = self.driver.find_elements(By.CSS_SELECTOR, "[data-message-author-role='assistant']")
            if responses:
                latest = responses[-1]
                inner_text_elements = latest.find_elements(By.CSS_SELECTOR, ".markdown, .prose, div[class*='markdown']")
                if inner_text_elements:
                    return inner_text_elements[0].text
                
                raw_text = latest.text
                for ui_word in ["Bewerken\n", "Edit\n", "Copy\n", "Kopiëren\n"]:
                    if raw_text.startswith(ui_word):
                        raw_text = raw_text[len(ui_word):]
                return raw_text
        except StaleElementReferenceException:
            pass
        except Exception:
            pass
        return None

    def send_message_and_get_response(self, prompt_text, stream_callback=None):
        input_box = self.find_chat_input()
        if not input_box:
            return None

        initial_count = self.get_assistant_message_count()

        try:
            input_box.click()
            time.sleep(0.3)
            self.driver.execute_script("""
                arguments[0].focus();
                if (arguments[0].tagName.toLowerCase() === 'textarea') {
                    arguments[0].value = arguments[1];
                } else {
                    arguments[0].innerText = arguments[1];
                }
                arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
            """, input_box, prompt_text)
            time.sleep(0.5)
            input_box.send_keys(Keys.ENTER)
        except Exception:
            return None

        timeout = 45
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.get_assistant_message_count() > initial_count:
                break
            time.sleep(0.5)

        last_text = ""
        stable_ticks = 0

        while time.time() - start_time < timeout:
            current_text = self.get_latest_assistant_text() or ""
            
            if stream_callback and current_text != last_text:
                stream_callback(current_text)

            try:
                stop_buttons = self.driver.find_elements(By.CSS_SELECTOR, "button[aria-label='Stop streaming'], button[data-testid='stop-button']")
            except:
                stop_buttons = []
            
            if not stop_buttons and current_text and current_text == last_text:
                stable_ticks += 1
                if stable_ticks >= 2:
                    break
            else:
                stable_ticks = 0
                
            if current_text:
                last_text = current_text
                
            time.sleep(0.5)

        return last_text

    def run_calibration(self):
        calibration_prompt = "Calibration test: Please reply ONLY with a random 4-digit number (e.g. 8492) and nothing else."
        response = self.send_message_and_get_response(calibration_prompt)
        if not response:
            return False, None
            
        match = re.search(r'\b\d{4}\b', response)
        if match:
            return True, match.group(0)
        return False, response


# ==========================================
# LOCAL API SERVER HANDLER
# ==========================================
class ChatAPIHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_POST(self):
        if self.path == '/v1/chat/completions':
            app_instance = self.server.app_instance
            expected_key = app_instance.config_data.get('local_api_key')

            auth_header = self.headers.get('Authorization')
            if not auth_header or auth_header != f"Bearer {expected_key}":
                self.send_error(401, "Unauthorized: Invalid API Key")
                return

            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                req_json = json.loads(post_data)
                
                messages = req_json.get('messages', [])
                if not messages:
                    self.send_error(400, "Bad Request: No messages provided")
                    return
                
                prompt = ""
                for msg in messages:
                    prompt += f"[{msg['role'].upper()}]: {msg['content']}\n"
                prompt += "\n[ASSISTANT]:"

                if not app_instance.browser.driver:
                    self.send_error(503, "Service Unavailable: Browser not launched")
                    return

                app_instance.after(0, lambda: app_instance.update_status("API Request Processing..."))
                app_instance.after(0, app_instance.prepare_bot_bubble)

                def stream_update(text):
                    app_instance.after(0, lambda: app_instance.update_bot_bubble(text))

                with app_instance.browser_lock:
                    response_text = app_instance.browser.send_message_and_get_response(prompt, stream_callback=stream_update)

                if not response_text:
                    self.send_error(500, "Internal Server Error: ChatGPT failed to respond")
                    return

                res_json = {
                    "id": f"chatcmpl-{uuid.uuid4()}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": "freeai-browser-engine",
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": response_text
                        },
                        "finish_reason": "stop"
                    }]
                }

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(res_json).encode('utf-8'))
                
                app_instance.after(0, lambda: app_instance.update_status("API Request Completed"))

            except Exception as e:
                self.send_error(500, f"Server Error: {str(e)}")
        else:
            self.send_error(404, "Not Found")


# ==========================================
# GEMINI-STYLE GUI APPLICATION
# ==========================================
class ModernChatApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("FreeAI - Gemini Interface")
        self.geometry("1200x800")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.configure(fg_color=BG_MAIN)
        
        try:
            import ctypes
            myappid = u'freeai.chat.gemini.1.0' 
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            self.iconbitmap("icon.ico")
        except Exception:
            pass

        self.config_data = load_config()
        self.history = load_history()
        self.current_chat_id = None
        self.needs_context_injection = False

        self.browser = ChatGPTBrowser(self.update_status)
        self.audio = AudioManager()
        self.audio.load_theme(self.config_data.get("sound_theme", "Default"))
        
        self.verification_code = ""
        self.history_buttons_pool = []
        self.current_bot_label = None
        self.current_bg_image = None 
        
        self.browser_lock = threading.Lock()
        self.api_server = None
        self.api_thread = None

        self.setup_ui()
        self.update_history_sidebar()
        self.apply_visual_theme()

    def setup_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ====================
        # SIDEBAR FRAME (LEFT)
        # ====================
        self.sidebar_frame = ctk.CTkFrame(self, width=280, corner_radius=0, fg_color=BG_SIDEBAR)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(3, weight=1)

        self.brand_label = ctk.CTkLabel(self.sidebar_frame, text="✦ FreeAI", font=ctk.CTkFont(size=20, weight="bold"), text_color="#c4c7c5")
        self.brand_label.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        self.btn_new_chat = ctk.CTkButton(
            self.sidebar_frame, 
            text="✎ Nieuw gesprek", 
            anchor="w",
            fg_color="transparent", 
            hover_color=HOVER_COLOR, 
            text_color="#c4c7c5",
            font=ctk.CTkFont(size=14),
            command=self.start_new_chat
        )
        self.btn_new_chat.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        self.history_scroll = ctk.CTkScrollableFrame(self.sidebar_frame, fg_color="transparent", label_text="Recent", label_text_color="#a8abae", label_anchor="w", label_font=ctk.CTkFont(size=12, weight="bold"))
        self.history_scroll.grid(row=3, column=0, padx=5, pady=5, sticky="nsew")

        self.setup_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.setup_frame.grid(row=4, column=0, padx=10, pady=15, sticky="ew")
        
        self.btn_api_config = ctk.CTkButton(self.setup_frame, text="🌐 Local API Server", height=28, fg_color="#10a37f", hover_color="#1a7f64", font=ctk.CTkFont(size=12), command=self.open_api_config_modal)
        self.btn_api_config.pack(fill="x", pady=(0, 5))

        self.btn_settings = ctk.CTkButton(self.setup_frame, text="⚙️ Settings & Themes", height=28, fg_color="#333537", hover_color="#444", font=ctk.CTkFont(size=12), command=self.open_settings_modal)
        self.btn_settings.pack(fill="x", pady=(0, 15))

        self.lbl_status = ctk.CTkLabel(self.setup_frame, text="Status: Offline", text_color="#a8abae", font=ctk.CTkFont(size=11), anchor="w")
        self.lbl_status.pack(fill="x", pady=(0, 5))

        self.btn_launch = ctk.CTkButton(self.setup_frame, text="Launch Browser", height=28, font=ctk.CTkFont(size=12), command=self.launch_browser)
        self.btn_launch.pack(fill="x", pady=2)

        self.btn_verify = ctk.CTkButton(self.setup_frame, text="Verify Connection", height=28, font=ctk.CTkFont(size=12), state="disabled", command=self.verify_connection)
        self.btn_verify.pack(fill="x", pady=2)

        self.btn_toggle_win = ctk.CTkButton(self.setup_frame, text="🌐 Show/Hide Chrome", height=28, fg_color="#333537", hover_color="#444", font=ctk.CTkFont(size=12), command=self.toggle_browser_window)
        self.btn_toggle_win.pack(fill="x", pady=2)

        self.btn_recalibrate = ctk.CTkButton(self.setup_frame, text="Recalibrate", height=28, fg_color="transparent", border_width=1, border_color="#555", font=ctk.CTkFont(size=12), command=self.force_recalibrate)
        self.btn_recalibrate.pack(fill="x", pady=2)

        # ====================
        # MAIN CHAT FRAME (RIGHT)
        # ====================
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=BG_MAIN)
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        
        self.bg_image_label = ctk.CTkLabel(self.main_frame, text="")
        self.bg_image_label.place(relx=0.5, rely=0.5, anchor="center")
        self.bg_image_label.lower()

        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        self.chat_display = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent")
        self.chat_display.grid(row=0, column=0, sticky="nsew", padx=40, pady=(20, 0))

        self.input_container = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.input_container.grid(row=1, column=0, sticky="ew", padx=100, pady=(10, 30))
        self.input_container.grid_columnconfigure(0, weight=1)

        self.input_bg = ctk.CTkFrame(self.input_container, fg_color=BG_INPUT, corner_radius=25)
        self.input_bg.grid(row=0, column=0, sticky="ew", ipady=5)
        self.input_bg.grid_columnconfigure(0, weight=1)

        self.chat_input = ctk.CTkTextbox(self.input_bg, height=50, fg_color="transparent", border_width=0, text_color=TEXT_MAIN, font=ctk.CTkFont(size=15))
        self.chat_input.grid(row=0, column=0, sticky="ew", padx=(20, 10), pady=10)
        
        self.chat_input.bind("<Key>", self.on_key_press)
        self.chat_input.bind("<Return>", self.on_enter_pressed)

        self.btn_send = ctk.CTkButton(self.input_bg, text="➤", width=40, height=40, corner_radius=20, fg_color="transparent", hover_color=HOVER_COLOR, text_color=TEXT_MAIN, font=ctk.CTkFont(size=20), state="disabled", command=self.send_message)
        self.btn_send.grid(row=0, column=1, padx=(0, 15))


    # --- Theme Logic ---
    def apply_visual_theme(self):
        theme_name = self.config_data.get("visual_theme", "Default")
        img_path = get_theme_image_path(theme_name)
        
        if PIL_AVAILABLE and img_path and os.path.exists(img_path):
            try:
                img = Image.open(img_path)
                self.current_bg_image = ctk.CTkImage(light_image=img, dark_image=img, size=(1920, 1080))
                self.bg_image_label.configure(image=self.current_bg_image)
                self.main_frame.configure(fg_color="transparent")
            except Exception as e:
                print(f"Error loading background theme: {e}")
                self.bg_image_label.configure(image="")
                self.main_frame.configure(fg_color=BG_MAIN)
        else:
            self.bg_image_label.configure(image="")
            self.main_frame.configure(fg_color=BG_MAIN)


    # --- Settings Logic ---
    def open_settings_modal(self):
        self.audio.play_button()
        modal = ctk.CTkToplevel(self)
        modal.title("Settings, Themes & Profile")
        modal.geometry("550x650")
        modal.attributes("-topmost", True)
        modal.transient(self)
        modal.grab_set()

        scroll_frame = ctk.CTkScrollableFrame(modal, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(scroll_frame, text="Customization & Themes", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(10, 10))
        
        # Visual Themes
        av_themes = get_available_themes()
        ctk.CTkLabel(scroll_frame, text="Visual Theme (Background):", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=20)
        theme_menu = ctk.CTkOptionMenu(scroll_frame, values=av_themes)
        theme_menu.pack(padx=20, pady=(5, 15), fill="x")
        theme_menu.set(self.config_data.get("visual_theme", "Default"))

        # Sound Themes
        av_sfx = get_available_sfx()
        ctk.CTkLabel(scroll_frame, text="Sound Theme (SFX):", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=20)
        sfx_menu = ctk.CTkOptionMenu(scroll_frame, values=av_sfx)
        sfx_menu.pack(padx=20, pady=(5, 15), fill="x")
        sfx_menu.set(self.config_data.get("sound_theme", "Default"))

        ctk.CTkLabel(scroll_frame, text="AI Profile & Personality", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 10))
        
        ctk.CTkLabel(scroll_frame, text="AI Personality / Style:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=20)
        ai_personality_box = ctk.CTkTextbox(scroll_frame, height=80)
        ai_personality_box.pack(padx=20, pady=(5, 15), fill="x")
        ai_personality_box.insert("1.0", self.config_data.get("ai_personality", ""))

        ctk.CTkLabel(scroll_frame, text="What should the AI know about you?:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=20)
        about_user_box = ctk.CTkTextbox(scroll_frame, height=80)
        about_user_box.pack(padx=20, pady=(5, 15), fill="x")
        about_user_box.insert("1.0", self.config_data.get("about_user", ""))

        def save_settings():
            self.audio.play_button()
            self.config_data["visual_theme"] = theme_menu.get()
            self.config_data["sound_theme"] = sfx_menu.get()
            self.config_data["ai_personality"] = ai_personality_box.get("1.0", "end").strip()
            self.config_data["about_user"] = about_user_box.get("1.0", "end").strip()
            save_config(self.config_data)
            
            # Apply instantly
            self.apply_visual_theme()
            self.audio.load_theme(self.config_data["sound_theme"])
            
            modal.destroy()

        ctk.CTkButton(scroll_frame, text="Save Settings", command=save_settings, fg_color="#10a37f", hover_color="#1a7f64").pack(pady=20)

        # Credits
        credits_lbl = ctk.CTkLabel(scroll_frame, text="Created by matsdepe-rgb (GitHub)", text_color="gray", font=ctk.CTkFont(size=11, slant="italic"))
        credits_lbl.pack(side="bottom", pady=15)

    # --- API Server Logic ---
    def open_api_config_modal(self):
        self.audio.play_button()
        modal = ctk.CTkToplevel(self)
        modal.title("Local API Provider Settings")
        modal.geometry("500x350")
        modal.attributes("-topmost", True)
        modal.transient(self)
        modal.grab_set()

        ctk.CTkLabel(modal, text="Host your own Local API", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 5))
        ctk.CTkLabel(modal, text="Use these details in other apps to connect to this hidden browser.", text_color="gray").pack(pady=(0, 20))

        url_frame = ctk.CTkFrame(modal, fg_color="transparent")
        url_frame.pack(fill="x", padx=40, pady=5)
        ctk.CTkLabel(url_frame, text="Base URL:", width=80, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left")
        
        base_url = f"http://127.0.0.1:{self.config_data['api_port']}/v1"
        url_entry = ctk.CTkEntry(url_frame, width=280)
        url_entry.pack(side="left", padx=10)
        url_entry.insert(0, base_url)
        url_entry.configure(state="readonly")

        key_frame = ctk.CTkFrame(modal, fg_color="transparent")
        key_frame.pack(fill="x", padx=40, pady=5)
        ctk.CTkLabel(key_frame, text="API Key:", width=80, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left")
        
        key_entry = ctk.CTkEntry(key_frame, width=280)
        key_entry.pack(side="left", padx=10)
        key_entry.insert(0, self.config_data['local_api_key'])
        key_entry.configure(state="readonly")

        status_lbl = ctk.CTkLabel(modal, text=f"Server is currently {'RUNNING' if self.api_server else 'STOPPED'}", text_color="#10a37f" if self.api_server else "red")
        status_lbl.pack(pady=(20, 5))

        def toggle_server():
            self.audio.play_button()
            if self.api_server:
                self.stop_api_server()
                status_lbl.configure(text="Server is currently STOPPED", text_color="red")
                server_btn.configure(text="Start API Server")
            else:
                self.start_api_server()
                status_lbl.configure(text="Server is currently RUNNING", text_color="#10a37f")
                server_btn.configure(text="Stop API Server")

        server_btn = ctk.CTkButton(modal, text="Stop API Server" if self.api_server else "Start API Server", command=toggle_server)
        server_btn.pack(pady=10)

    def start_api_server(self):
        if self.api_server:
            return
        port = self.config_data['api_port']
        self.api_server = socketserver.ThreadingTCPServer(('127.0.0.1', port), ChatAPIHandler)
        self.api_server.app_instance = self
        
        self.api_thread = threading.Thread(target=self.api_server.serve_forever, daemon=True)
        self.api_thread.start()

    def stop_api_server(self):
        if self.api_server:
            self.api_server.shutdown()
            self.api_server.server_close()
            self.api_server = None

    # --- Real-time Streaming Helpers ---
    def prepare_bot_bubble(self):
        msg_container = ctk.CTkFrame(self.chat_display, fg_color="transparent")
        msg_container.pack(fill="x", pady=15)

        bubble = ctk.CTkFrame(msg_container, fg_color="transparent")
        bubble.pack(side="left", padx=10, fill="y")
        
        icon = ctk.CTkLabel(bubble, text="✦", font=ctk.CTkFont(size=18), text_color="#10a37f")
        icon.pack(side="left", anchor="n", padx=(0, 10), pady=5)
        
        lbl = ctk.CTkLabel(bubble, text="Thinking...", justify="left", wraplength=750, text_color=TEXT_MAIN, font=ctk.CTkFont(size=15))
        lbl.pack(side="left", padx=5, pady=5)
        
        self.current_bot_label = lbl
        self.chat_display._parent_canvas.yview_moveto(1.0)

    def update_bot_bubble(self, text):
        if self.current_bot_label:
            self.current_bot_label.configure(text=text)
            self.chat_display._parent_canvas.yview_moveto(1.0)

    def append_user_bubble(self, text):
        msg_container = ctk.CTkFrame(self.chat_display, fg_color="transparent")
        msg_container.pack(fill="x", pady=15)
        bubble = ctk.CTkFrame(msg_container, fg_color=BG_USER_BUBBLE, corner_radius=20)
        bubble.pack(side="right", padx=10, fill="y", ipadx=5)
        lbl = ctk.CTkLabel(bubble, text=text, justify="left", wraplength=600, text_color=TEXT_MAIN, font=ctk.CTkFont(size=15))
        lbl.pack(padx=15, pady=10)
        self.chat_display._parent_canvas.yview_moveto(1.0)

    def append_system_bubble(self, text):
        msg_container = ctk.CTkFrame(self.chat_display, fg_color="transparent")
        msg_container.pack(fill="x", pady=15)
        lbl = ctk.CTkLabel(msg_container, text=text, justify="center", text_color="#7a7a7a", font=ctk.CTkFont(size=12, slant="italic"))
        lbl.pack(pady=5)
        self.chat_display._parent_canvas.yview_moveto(1.0)

    def clear_chat_display(self):
        self.current_bot_label = None
        for widget in self.chat_display.winfo_children():
            widget.destroy()

    # --- Safe Widget Pool Logic for Sidebar ---
    def update_history_sidebar(self):
        history_items = list(reversed(list(self.history.items())))
        
        for i in range(len(history_items), len(self.history_buttons_pool)):
            self.history_buttons_pool[i].pack_forget()

        for i, (chat_id, chat_data) in enumerate(history_items):
            title = chat_data.get('title', 'Untitled Chat')
            if i < len(self.history_buttons_pool):
                btn = self.history_buttons_pool[i]
                btn.configure(text=title, command=lambda cid=chat_id: self.load_chat(cid))
                btn.pack(fill="x", pady=2)
            else:
                btn = ctk.CTkButton(
                    self.history_scroll, 
                    text=title, 
                    anchor="w", 
                    fg_color="transparent", 
                    text_color="#c4c7c5",
                    hover_color=HOVER_COLOR,
                    font=ctk.CTkFont(size=13),
                    command=lambda cid=chat_id: self.load_chat(cid)
                )
                btn.pack(fill="x", pady=2)
                self.history_buttons_pool.append(btn)

    def start_new_chat(self):
        self.audio.play_button()
        self.current_chat_id = str(uuid.uuid4())
        self.history[self.current_chat_id] = {"title": "Nieuw gesprek", "messages": []}
        save_history(self.history)
        self.update_history_sidebar()
        self.clear_chat_display()
        self.needs_context_injection = False

    def load_chat(self, chat_id):
        self.audio.play_button()
        self.current_chat_id = chat_id
        chat_data = self.history[chat_id]
        self.clear_chat_display()

        for msg in chat_data['messages']:
            if msg['role'] == 'user':
                self.append_user_bubble(msg['content'])
            else:
                self.prepare_bot_bubble()
                self.update_bot_bubble(msg['content'])

        self.append_system_bubble("Loaded chat history. Context will be attached to your next message.")
        self.needs_context_injection = True

    def build_compact_context(self):
        if not self.current_chat_id or not self.history[self.current_chat_id]['messages']:
            return ""
        context_str = "[SYSTEM LOG: Context Restoration]\n"
        
        personality = self.config_data.get("ai_personality", "")
        about_user = self.config_data.get("about_user", "")
        if personality or about_user:
            context_str += "--- PERSISTENT INSTRUCTIONS ---\n"
            if personality: context_str += f"AI Personality: {personality}\n"
            if about_user: context_str += f"About User: {about_user}\n"
            context_str += "-------------------------------\n"

        for msg in self.history[self.current_chat_id]['messages']:
            role = "User" if msg['role'] == 'user' else "Assistant"
            context_str += f"{role}: {msg['content']}\n"
        context_str += "\n[SYSTEM LOG: End of Context. Respond directly to user's next prompt:]\n\n"
        return context_str

    # --- UI Helpers & Popups ---
    def update_status(self, text):
        self.lbl_status.configure(text=text)

    def toggle_browser_window(self):
        self.audio.play_button()
        if not self.browser.driver:
            self.show_error("Error", "Launch and verify the browser first!")
            return
        self.browser.toggle_window_visibility()

    def show_error(self, title, message):
        err_win = ctk.CTkToplevel(self)
        err_win.title(title)
        err_win.geometry("400x200")
        err_win.attributes("-topmost", True)
        err_win.grab_set()

        lbl = ctk.CTkLabel(err_win, text=message, wraplength=350, font=ctk.CTkFont(size=14))
        lbl.pack(pady=30)
        btn = ctk.CTkButton(err_win, text="OK", command=err_win.destroy, width=100)
        btn.pack()

    # --- Automation Threads ---
    def launch_browser(self):
        self.audio.play_button()
        self.btn_launch.configure(state="disabled")
        self.update_status("Starting Chrome...")
        threading.Thread(target=self._launch_browser_thread, daemon=True).start()

    def _launch_browser_thread(self):
        if self.browser.start_driver():
            self.update_status("Browser opened. Please log in.")
            self.btn_verify.configure(state="normal")
        else:
            self.update_status("Failed to launch Chrome.")
            self.btn_launch.configure(state="normal")

    def verify_connection(self):
        self.audio.play_button()
        self.btn_verify.configure(state="disabled")
        self.verification_code = self.browser.generate_verification_code()
        
        ver_win = ctk.CTkToplevel(self)
        ver_win.title("Security Check")
        ver_win.geometry("400x260")
        ver_win.attributes("-topmost", True)
        ver_win.transient(self)
        ver_win.grab_set()

        ctk.CTkLabel(ver_win, text="Paste this code into ChatGPT in Chrome:", font=ctk.CTkFont(size=14)).pack(pady=(20, 10))
        
        code_lbl = ctk.CTkLabel(ver_win, text=self.verification_code, font=ctk.CTkFont(size=32, weight="bold"), text_color="#10a37f")
        code_lbl.pack(pady=10)

        def copy_to_clipboard():
            self.audio.play_button()
            self.clipboard_clear()
            self.clipboard_append(self.verification_code)
            ver_win.update()
            copy_btn.configure(text="Copied!")
            ver_win.after(2000, lambda: copy_btn.configure(text="Copy Code"))

        copy_btn = ctk.CTkButton(ver_win, text="Copy Code", command=copy_to_clipboard, width=120)
        copy_btn.pack(pady=5)

        def on_done():
            self.audio.play_button()
            ver_win.grab_release()
            ver_win.destroy()
            self.update_status("Scanning for code...")
            threading.Thread(target=self._verify_thread, daemon=True).start()

        done_btn = ctk.CTkButton(ver_win, text="Done / I pasted it", command=on_done, fg_color="#10a37f", hover_color="#1a7f64")
        done_btn.pack(pady=(15, 10))

    def _verify_thread(self):
        if self.browser.scan_for_code(self.verification_code):
            self.update_status("Verified!")
            if not self.config_data.get("calibrated", False):
                self.prompt_calibration()
            else:
                self.browser.minimize_to_background()
                self.enable_chat()
        else:
            self.update_status("Verification failed.")
            self.btn_verify.configure(state="normal")

    def prompt_calibration(self):
        self.update_status("Calibrating...")
        threading.Thread(target=self._calibration_thread, daemon=True).start()

    def _calibration_thread(self):
        success, code_or_msg = self.browser.run_calibration()
        if success:
            cal_win = ctk.CTkToplevel(self)
            cal_win.title("Calibration")
            cal_win.geometry("350x200")
            cal_win.attributes("-topmost", True)
            cal_win.transient(self)
            cal_win.grab_set()

            ctk.CTkLabel(cal_win, text=f"Detected Calibration Code:\n\n{code_or_msg}\n\nIs this correct?", font=ctk.CTkFont(size=14)).pack(pady=20)
            
            btn_frame = ctk.CTkFrame(cal_win, fg_color="transparent")
            btn_frame.pack(pady=10)

            def on_yes():
                self.audio.play_button()
                cal_win.destroy()
                self.config_data["calibrated"] = True
                save_config(self.config_data)
                self.update_status("Ready")
                self.browser.minimize_to_background()
                self.enable_chat()

            def on_no():
                self.audio.play_button()
                cal_win.destroy()
                self.update_status("Calibration rejected.")

            ctk.CTkButton(btn_frame, text="Yes", command=on_yes, width=100, fg_color="#10a37f", hover_color="#1a7f64").pack(side="left", padx=10)
            ctk.CTkButton(btn_frame, text="No", command=on_no, width=100, fg_color="gray", hover_color="#444").pack(side="left", padx=10)

        else:
            self.show_error("Calibration Failed", f"Could not parse code.\nResponse: {code_or_msg}")
            self.update_status("Calibration failed.")

    def force_recalibrate(self):
        self.audio.play_button()
        if not self.browser.driver:
            self.show_error("Error", "Launch and verify the browser first!")
            return
        self.config_data["calibrated"] = False
        save_config(self.config_data)
        self.prompt_calibration()

    def enable_chat(self):
        self.btn_send.configure(state="normal")
        if not self.current_chat_id:
            self.start_new_chat()

    # --- Messaging ---
    def on_key_press(self, event):
        if event.keysym != "Return" and event.char:
            self.audio.play_type()

    def on_enter_pressed(self, event):
        if event.state & 0x0001:  # Shift + Enter for multiline
            return None
        self.send_message()
        return "break"

    def send_message(self):
        self.audio.play_button()
        text = self.chat_input.get("1.0", "end").strip()
        if not text:
            return

        self.chat_input.delete("1.0", "end")
        self.btn_send.configure(state="disabled")
        
        self.append_user_bubble(text)

        if not self.current_chat_id:
            self.start_new_chat()

        if len(self.history[self.current_chat_id]['messages']) == 0:
            self.history[self.current_chat_id]['title'] = text[:20] + "..."
            self.update_history_sidebar()

        self.history[self.current_chat_id]['messages'].append({"role": "user", "content": text})
        save_history(self.history)

        self.update_status("Generating response...")
        threading.Thread(target=self._send_thread, args=(text,), daemon=True).start()

    def _send_thread(self, text):
        msg_to_send = text
        
        is_first_message = (len(self.history[self.current_chat_id]['messages']) == 1)
        
        if is_first_message:
            personality = self.config_data.get("ai_personality", "")
            about_user = self.config_data.get("about_user", "")
            
            if personality or about_user:
                sys_prompt = "[SYSTEM INSTRUCTIONS]\n"
                if personality:
                    sys_prompt += f"AI Personality/Style: {personality}\n"
                if about_user:
                    sys_prompt += f"About the User: {about_user}\n"
                sys_prompt += "[END SYSTEM INSTRUCTIONS. Acknowledge silently and apply to the following message:]\n\n"
                msg_to_send = sys_prompt + text
                
        elif self.needs_context_injection:
            msg_to_send = self.build_compact_context() + text
            self.needs_context_injection = False

        self.after(0, self.prepare_bot_bubble)

        def stream_update(current_text):
            self.audio.play_type()
            self.after(0, lambda: self.update_bot_bubble(current_text))

        with self.browser_lock:
            response = self.browser.send_message_and_get_response(msg_to_send, stream_callback=stream_update)

        if response:
            self.history[self.current_chat_id]['messages'].append({"role": "assistant", "content": response})
            save_history(self.history)
            self.after(0, lambda: self.update_bot_bubble(response))
            self.after(0, lambda: self.update_status("Ready"))
        else:
            self.after(0, lambda: self.update_bot_bubble("System Error: Failed to receive response or timeout."))
            self.after(0, lambda: self.update_status("Response timeout."))

        self.after(0, lambda: self.btn_send.configure(state="normal"))

    def on_closing(self):
        self.stop_api_server()
        self.browser.close_driver()
        self.destroy()

if __name__ == "__main__":
    app = ModernChatApp()
    app.mainloop()
